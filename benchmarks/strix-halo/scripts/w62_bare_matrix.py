#!/usr/bin/env python3
"""Run the W6.2 challenger-only bare performance matrix.

The frozen llama-bench binary in the supplied runtime does not enumerate
Vulkan0 in this environment.  W6.2 therefore uses the frozen llama-server
binary for both decode and prefill requests.  The server is started once per
benchmark point with the same Vulkan0, full-offload, batch, ubatch, and context
settings.  Every request and resource snapshot is retained in raw.jsonl.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import os
import platform
import re
import signal
import socket
import statistics
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RESULTS_ROOT = ROOT / "results"
RUNTIME_ROOT = Path("/home/grzanka/Work/LLM/strix-llama.cpp")
SERVER_BINARY = RUNTIME_ROOT / "build-vulkan/bin/llama-server"
BENCH_BINARY = RUNTIME_ROOT / "build-vulkan/bin/llama-bench"
POWER_PROFILE_BINARY = Path("/usr/bin/powerprofilesctl")
DEEP_DIR = Path("/models/gguf/qwen3.8-27b")
CODE_MODEL = Path("/models/gguf/qwen3-coder-30b-a3b/Qwen3-Coder-30B-A3B-Instruct-Q5_K_M.gguf")
REFERENCE_MODEL = Path("/models/gguf/qwen3.6-35b-a3b/Qwen3.6-35B-A3B-Q4_K_M.gguf")
EXPECTED_RUNTIME = "5f851647fe5ed795dfd6c0a3fba543114879e874"
EXPECTED_VERSION = "version: 0.4.0-dev (build 10889, commit 5f851647f)"
EXPECTED_HASHES = {
    "deep": "7d590099e0a0fe7b8df812045faa2ae12bf4dbf3492b8eb7c7c7ab24c94d36ed",
    "code": "4b78837bbec5ee248e4a5642bf608b6793721af41b92589e40c8da0bce58b907",
    "reference": "671e47e0ec53c665d048b98c3ecbfd5236b5ca9c3e02ed19fc8f81f7b85140c7",
}
DEVICE = "Vulkan0"
HOST = "127.0.0.1"
PORT = 18080
CONTEXT = 32768
BATCH = 2048
WARMUPS = 1
MEASURED = 5
SEED = 424242
TEMPERATURE = 0.0
DECODE_PROMPT = (
    "Write a continuous technical explanation of deterministic data pipelines, "
    "checkpointing, idempotency, and validation. Do not conclude early."
)
FATAL_PATTERNS = (
    "out of memory",
    "allocation failure",
    "vk_error_device_lost",
    "device lost",
    "gpu reset",
    "ring timeout",
    "thermal throttling",
    "vulkan error",
    "segmentation fault",
    "assertion failed",
    "unsupported tensor",
)


class GateFailure(RuntimeError):
    """A fail-closed W6.2 gate failed."""


def now() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


def json_dump(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def append_jsonl(path: Path, value: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, sort_keys=True) + "\n")


def run_probe(command: list[str], timeout: int = 60) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"command": command, "exit_status": None, "error": str(exc)}
    return {
        "command": command,
        "exit_status": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_optional(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def meminfo() -> dict[str, int]:
    values: dict[str, int] = {}
    try:
        content = Path("/proc/meminfo").read_text(encoding="utf-8")
    except OSError:
        return values
    for line in content.splitlines():
        key, raw = line.split(":", 1)
        match = re.search(r"\d+", raw)
        if match:
            values[key] = int(match.group()) * 1024
    return values


def gtt_snapshot() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for total_path in sorted(Path("/sys/class/drm").glob("card*/device/mem_info_gtt_total")):
        used_path = total_path.with_name("mem_info_gtt_used")
        total = read_optional(total_path)
        used = read_optional(used_path)
        result.append(
            {
                "device": total_path.parts[-3],
                "total_bytes": int(total) if total and total.isdigit() else None,
                "used_bytes": int(used) if used and used.isdigit() else None,
            }
        )
    return result


def temperatures() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for input_path in sorted(Path("/sys/class/hwmon").glob("hwmon*/temp*_input")):
        raw = read_optional(input_path)
        if raw is None or not raw.lstrip("-").isdigit():
            continue
        label = read_optional(input_path.with_name(input_path.name.replace("_input", "_label")))
        result.append(
            {
                "path": str(input_path),
                "label": label,
                "celsius": int(raw) / 1000,
            }
        )
    return result


def fan_rpm(status: str | None) -> int | None:
    if status is None:
        return None
    match = re.search(r"Fans?:\s+(\d+)\s+RPM", status, re.IGNORECASE)
    return int(match.group(1)) if match else None


def resource_snapshot() -> dict[str, Any]:
    values = meminfo()
    total = values.get("MemTotal")
    available = values.get("MemAvailable")
    swap_total = values.get("SwapTotal")
    swap_free = values.get("SwapFree")
    status = run_probe(["z13ctl", "status"])
    status_text = str(status.get("stdout", ""))
    return {
        "captured_at": now(),
        "ram_total_bytes": total,
        "ram_available_bytes": available,
        "ram_used_bytes": total - available
        if total is not None and available is not None
        else None,
        "zram_total_bytes": swap_total,
        "zram_used_bytes": swap_total - swap_free
        if swap_total is not None and swap_free is not None
        else None,
        "gtt": gtt_snapshot(),
        "temperatures": temperatures(),
        "peak_temperature_celsius": max(
            (float(item["celsius"]) for item in temperatures()), default=None
        ),
        "fan_rpm": fan_rpm(status_text),
        "power_profile": run_probe([str(POWER_PROFILE_BINARY), "get"]),
        "acpi_platform_profile": read_optional(Path("/sys/firmware/acpi/platform_profile")),
        "z13ctl_status": status,
        "z13ctl_tdp": run_probe(["z13ctl", "tdp", "--get"]),
    }


def total_gtt_used(snapshot: dict[str, Any]) -> int:
    return sum(
        int(item["used_bytes"])
        for item in snapshot.get("gtt", [])
        if isinstance(item, dict) and isinstance(item.get("used_bytes"), int)
    )


def total_gtt(snapshot: dict[str, Any]) -> int | None:
    values = [
        int(item["total_bytes"])
        for item in snapshot.get("gtt", [])
        if isinstance(item, dict) and isinstance(item.get("total_bytes"), int)
    ]
    return sum(values) if values else None


def max_temperature(snapshot: dict[str, Any]) -> float | None:
    value = snapshot.get("peak_temperature_celsius")
    return float(value) if isinstance(value, (int, float)) else None


def ensure_port_free() -> None:
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.settimeout(0.25)
        if probe.connect_ex((HOST, PORT)) == 0:
            raise GateFailure(f"benchmark port {HOST}:{PORT} has an active listener")
    finally:
        probe.close()
    binder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        binder.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        binder.bind((HOST, PORT))
    except OSError as exc:
        raise GateFailure(f"benchmark port {HOST}:{PORT} unavailable: {exc}") from exc
    finally:
        binder.close()


def http_json(
    url: str, body: dict[str, Any] | None = None, timeout: float = 30
) -> tuple[int, dict[str, Any]]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="GET" if body is None else "POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            parsed = json.loads(response.read().decode("utf-8"))
            if not isinstance(parsed, dict):
                raise GateFailure(f"non-object response from {url}")
            return response.status, parsed
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise GateFailure(f"HTTP {exc.code} from {url}: {detail[:500]}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise GateFailure(f"request failed for {url}: {exc}") from exc


class ManagedServer:
    """Own one llama-server child and terminate only that child."""

    def __init__(
        self, model: Path, batch: int, ubatch: int, log_path: Path, context: int = CONTEXT
    ) -> None:
        self.model = model
        self.batch = batch
        self.ubatch = ubatch
        self.context = context
        self.log_path = log_path
        self.process: subprocess.Popen[str] | None = None
        self.handle: Any = None
        self.offset = 0
        self.exit_status: int | None = None
        self.before_gtt = 0
        self.command = [
            str(SERVER_BINARY),
            "-m",
            str(model),
            "-dev",
            DEVICE,
            "-ngl",
            "999",
            "-c",
            str(context),
            "-b",
            str(batch),
            "-ub",
            str(ubatch),
            "-np",
            "1",
            "-fa",
            "auto",
            "-lv",
            "4",
            "--cache-ram",
            "0",
            "--metrics",
            "--host",
            HOST,
            "--port",
            str(PORT),
        ]

    @property
    def base_url(self) -> str:
        return f"http://{HOST}:{PORT}"

    def _log_since_start(self) -> str:
        try:
            return self.log_path.read_bytes()[self.offset :].decode("utf-8", errors="replace")
        except OSError:
            return ""

    def _validate_log(self, require_vulkan: bool = False) -> None:
        text = self._log_since_start()
        lowered = text.lower()
        for pattern in FATAL_PATTERNS:
            if pattern in lowered:
                raise GateFailure(f"fatal server log marker detected: {pattern}")
        if re.search(r"layer\s+\d+\s+assigned to device cpu", lowered):
            raise GateFailure("server log reports CPU layer placement")
        if "model loaded" not in lowered:
            raise GateFailure("server did not confirm model load")
        matches = re.findall(r"offloaded\s+(\d+)/(\d+)\s+layers to GPU", text, re.IGNORECASE)
        if matches and any(int(offloaded) != int(total) for offloaded, total in matches[-2:]):
            raise GateFailure(f"unexpected CPU fallback in layer offload: {matches[-2:]}")
        if require_vulkan and not matches:
            raise GateFailure("server log did not report layer offload")

    def __enter__(self) -> ManagedServer:
        ensure_port_free()
        self.before_gtt = total_gtt_used(resource_snapshot())
        self.handle = self.log_path.open("a", encoding="utf-8")
        self.handle.write(f"\n=== SERVER START {now()} ===\n")
        self.handle.write(f"command={json.dumps(self.command)}\n")
        self.handle.flush()
        self.offset = self.log_path.stat().st_size
        self.process = subprocess.Popen(
            self.command,
            stdout=self.handle,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        deadline = time.monotonic() + 600
        try:
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    raise GateFailure(
                        f"llama-server exited during startup: {self.process.returncode}"
                    )
                try:
                    status, payload = http_json(self.base_url + "/health", timeout=2)
                except GateFailure:
                    time.sleep(0.25)
                    continue
                if status == 200 and payload.get("status") == "ok":
                    time.sleep(0.5)
                    self._validate_log(require_vulkan=True)
                    after_gtt = total_gtt_used(resource_snapshot())
                    minimum = min(8 * 1024**3, self.model.stat().st_size // 2)
                    if after_gtt - self.before_gtt < minimum:
                        raise GateFailure(
                            "unexpected CPU fallback: GTT did not increase enough "
                            "during model load "
                            f"({after_gtt - self.before_gtt} bytes; required {minimum})"
                        )
                    return self
                time.sleep(0.25)
            raise GateFailure("llama-server health timeout")
        except BaseException:
            self._stop()
            raise

    def assert_healthy(self) -> None:
        if self.process is None or self.process.poll() is not None:
            raise GateFailure("managed llama-server is not running")
        self._validate_log()

    def _stop(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.process.send_signal(signal.SIGTERM)
            try:
                self.process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=10)
        if self.process is not None:
            self.exit_status = self.process.returncode
        if self.handle is not None:
            self.handle.write(f"=== SERVER STOP exit_status={self.exit_status} at={now()} ===\n")
            self.handle.close()
            self.handle = None

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self._stop()


def extract_content(response: dict[str, Any]) -> str:
    if "content" in response:
        return str(response["content"])
    choices = response.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        message = choices[0].get("message")
        if isinstance(message, dict):
            return str(message.get("content") or "")
        return str(choices[0].get("text") or "")
    return ""


def request_completion(
    server: ManagedServer, body: dict[str, Any], timeout: float = 1800
) -> dict[str, Any]:
    started = time.monotonic()
    status, response = http_json(server.base_url + "/completion", body, timeout=timeout)
    elapsed = time.monotonic() - started
    if status != 200 or "error" in response:
        raise GateFailure(f"completion failed: HTTP {status}: {response}")
    timings = response.get("timings")
    if not isinstance(timings, dict):
        raise GateFailure(f"completion timings missing: {response}")
    response["_wall_latency_seconds"] = elapsed
    response["_content"] = extract_content(response)
    return response


def tokenize(server: ManagedServer, text: str) -> int:
    status, response = http_json(
        server.base_url + "/tokenize",
        {"content": text, "add_special": False},
        timeout=180,
    )
    tokens = response.get("tokens")
    if status != 200 or not isinstance(tokens, list):
        raise GateFailure(f"tokenization failed: {response}")
    return len(tokens)


def exact_prompt(server: ManagedServer, target: int, marker: str = "") -> tuple[str, int]:
    unit = (
        f"{marker} W6.2 unique run marker. The deterministic benchmark row contains "
        "stable nonsemantic text "
        "for measuring Vulkan prefill throughput. "
    )
    upper = max(1, int(target / 8) + 100)
    low = 0
    high = upper
    best = ""
    best_count = 0
    while low <= high:
        middle = (low + high) // 2
        candidate = unit * middle
        count = tokenize(server, candidate)
        if count <= target:
            best = candidate
            best_count = count
            low = middle + 1
        else:
            high = middle - 1
    fillers = [
        " a",
        " b",
        " c",
        " d",
        " e",
        " f",
        " g",
        " h",
        " i",
        " j",
        " k",
        " l",
        " m",
        " n",
        " o",
        " p",
        " q",
        " r",
        " s",
        " t",
        " u",
        " v",
        " w",
        " x",
        " y",
        " z",
        " 0",
        " 1",
        " 2",
        " 3",
        " 4",
        " 5",
        " 6",
        " 7",
        " 8",
        " 9",
    ]
    for _ in range(target - best_count + 4):
        progress = False
        for filler in fillers:
            count = tokenize(server, best + filler)
            if count <= target:
                best += filler
                best_count = count
                progress = True
                break
        if best_count == target:
            return best, best_count
        if not progress:
            break
    final_count = tokenize(server, best)
    if final_count != target:
        raise GateFailure(f"could not construct exact {target}-token prompt; got {final_count}")
    return best, final_count


def numeric_summary(values: list[float]) -> dict[str, float]:
    if not values:
        raise GateFailure("cannot summarize empty measurements")
    return {
        "median": statistics.median(values),
        "mean": statistics.mean(values),
        "standard_deviation": statistics.stdev(values) if len(values) > 1 else 0.0,
        "min": min(values),
        "max": max(values),
    }


def metric_summary(records: list[dict[str, Any]], metric: str) -> dict[str, float]:
    values = [float(record["metrics"][metric]) for record in records]
    return numeric_summary(values)


def safety_check(resource: dict[str, Any], baseline: dict[str, Any]) -> None:
    available = resource.get("ram_available_bytes")
    if isinstance(available, int) and available < 4 * 1024**3:
        raise GateFailure(f"RAM available below safety floor: {available} bytes")
    zram = resource.get("zram_used_bytes")
    baseline_zram = baseline.get("zram_used_bytes")
    if (
        isinstance(zram, int)
        and isinstance(baseline_zram, int)
        and zram - baseline_zram > 8 * 1024**3
    ):
        raise GateFailure(f"severe zram growth: {zram - baseline_zram} bytes")
    temperature = max_temperature(resource)
    if temperature is not None and temperature >= 95.0:
        raise GateFailure(f"unsafe temperature: {temperature:.1f} C")


def request_body(kind: str, amount: int, prompt: str) -> dict[str, Any]:
    return {
        "prompt": prompt,
        "n_predict": amount if kind == "decode" else 0,
        "temperature": TEMPERATURE,
        "seed": SEED,
        "ignore_eos": True,
        "stream": False,
    }


def run_point(
    *,
    model: dict[str, Any],
    label: str,
    batch: int,
    ubatch: int,
    kind: str,
    amount: int,
    raw_path: Path,
    server_log: Path,
    baseline_resources: dict[str, Any],
    log_event: Any,
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    prompt = DECODE_PROMPT
    server_context = CONTEXT + 1 if kind == "prefill" and amount == CONTEXT else CONTEXT
    with ManagedServer(
        Path(model["path"]), batch, ubatch, server_log, context=server_context
    ) as server:
        if kind == "prefill":
            prompt, actual_prompt_tokens = exact_prompt(server, amount, f"{label}-setup")
            if actual_prompt_tokens != amount:
                raise GateFailure(f"prompt target mismatch for {label}: {actual_prompt_tokens}")
        else:
            actual_prompt_tokens = None
        log_event(
            "point_start",
            {
                "role": model["role"],
                "label": label,
                "kind": kind,
                "amount": amount,
                "batch": batch,
                "ubatch": ubatch,
            },
        )
        for index in range(WARMUPS + MEASURED):
            phase = "warmup" if index < WARMUPS else "measured"
            run_prompt = prompt
            if kind == "prefill":
                run_marker = (
                    "ALPHA",
                    "BRAVO",
                    "CHARLIE",
                    "DELTA",
                    "ECHO",
                    "FOXTROT",
                )[index]
                run_prompt, run_prompt_tokens = exact_prompt(server, amount, run_marker)
                if run_prompt_tokens != amount:
                    raise GateFailure(f"prompt target mismatch for {label}: {run_prompt_tokens}")
            body = request_body(kind, amount, run_prompt)
            response = request_completion(server, body)
            timings = response["timings"]
            predicted_n = timings.get("predicted_n")
            prompt_n = timings.get("prompt_n")
            prompt_tps = timings.get("prompt_per_second")
            predicted_tps = timings.get("predicted_per_second")
            if not isinstance(predicted_n, int) or not isinstance(prompt_n, int):
                raise GateFailure(f"invalid timing counters for {label}: {timings}")
            if kind == "decode":
                if predicted_n != amount or not isinstance(predicted_tps, (int, float)):
                    raise GateFailure(f"decode token count/rate mismatch for {label}: {timings}")
                metric = float(predicted_tps)
                metric_name = "tg_tps"
                valid_output = bool(response.get("_content"))
            else:
                if prompt_n != amount or not isinstance(prompt_tps, (int, float)):
                    raise GateFailure(f"prefill token count/rate mismatch for {label}: {timings}")
                metric = float(prompt_tps)
                metric_name = "pp_tps"
                valid_output = predicted_n in {0, 1}
            if not math.isfinite(metric) or metric <= 0 or not valid_output:
                raise GateFailure(f"invalid benchmark response for {label}: {timings}")
            server.assert_healthy()
            resources = resource_snapshot()
            safety_check(resources, baseline_resources)
            record = {
                "captured_at": now(),
                "role": model["role"],
                "model": model["path"],
                "model_sha256": model["sha256"],
                "label": label,
                "kind": kind,
                "amount": amount,
                "batch": batch,
                "ubatch": ubatch,
                "phase": phase,
                "run": index if phase == "warmup" else index - WARMUPS,
                "request": body,
                "response": response,
                "valid_output": valid_output,
                "metrics": {
                    "prompt_n": prompt_n,
                    "prompt_tps": float(prompt_tps)
                    if isinstance(prompt_tps, (int, float))
                    else None,
                    "predicted_n": predicted_n,
                    "tg_tps": float(predicted_tps)
                    if isinstance(predicted_tps, (int, float))
                    else None,
                    "selected_metric": metric,
                    "selected_metric_name": metric_name,
                    "wall_latency_seconds": float(response["_wall_latency_seconds"]),
                },
                "resources": resources,
            }
            append_jsonl(raw_path, record)
            records.append(record)
        server.assert_healthy()
        server_exit_status = server.exit_status
    measured = [record for record in records if record["phase"] == "measured"]
    summary = {
        "selected_metric": metric_summary(measured, "selected_metric"),
        "wall_latency_seconds": metric_summary(measured, "wall_latency_seconds"),
        "requested_tokens": amount,
        "actual_prompt_tokens": actual_prompt_tokens,
        "warmup_runs": WARMUPS,
        "measured_runs": MEASURED,
        "server_exit_status": server_exit_status,
    }
    return {
        "label": label,
        "kind": kind,
        "amount": amount,
        "batch": batch,
        "ubatch": ubatch,
        "server_context": server_context,
        "summary": summary,
        "measured": measured,
        "all_runs": records,
    }


def peak_resources(records: list[dict[str, Any]]) -> dict[str, Any]:
    snapshots = [
        record["resources"] for record in records if isinstance(record.get("resources"), dict)
    ]
    if not snapshots:
        return {}
    peak_ram = max(
        (
            int(item["ram_used_bytes"])
            for item in snapshots
            if isinstance(item.get("ram_used_bytes"), int)
        ),
        default=None,
    )
    peak_zram = max(
        (
            int(item["zram_used_bytes"])
            for item in snapshots
            if isinstance(item.get("zram_used_bytes"), int)
        ),
        default=None,
    )
    peak_temp = max(
        (
            float(item["peak_temperature_celsius"])
            for item in snapshots
            if isinstance(item.get("peak_temperature_celsius"), (int, float))
        ),
        default=None,
    )
    gtt_by_device: dict[str, dict[str, Any]] = {}
    for snapshot in snapshots:
        for item in snapshot.get("gtt", []):
            if not isinstance(item, dict) or not isinstance(item.get("device"), str):
                continue
            current = gtt_by_device.setdefault(
                item["device"],
                {"device": item["device"], "total_bytes": item.get("total_bytes"), "used_bytes": 0},
            )
            if isinstance(item.get("used_bytes"), int):
                current["used_bytes"] = max(int(current["used_bytes"]), int(item["used_bytes"]))
    return {
        "ram_used_bytes": peak_ram,
        "zram_used_bytes": peak_zram,
        "temperature_celsius": peak_temp,
        "gtt": list(gtt_by_device.values()),
    }


def version_gate() -> dict[str, Any]:
    cli_version = run_probe([str(RUNTIME_ROOT / "build-vulkan/bin/llama-cli"), "--version"])
    bench_version = run_probe([str(BENCH_BINARY), "--version"])
    devices = run_probe([str(RUNTIME_ROOT / "build-vulkan/bin/llama-cli"), "--list-devices"])
    runtime_sha = run_probe(["git", "-C", str(RUNTIME_ROOT), "rev-parse", "HEAD"])
    if runtime_sha.get("exit_status") != 0 or runtime_sha.get("stdout") != EXPECTED_RUNTIME:
        raise GateFailure(f"runtime commit mismatch: {runtime_sha}")
    version_text = f"{cli_version.get('stdout', '')}\n{cli_version.get('stderr', '')}"
    if cli_version.get("exit_status") != 0 or EXPECTED_VERSION not in version_text:
        raise GateFailure(f"runtime version mismatch: {cli_version}")
    if not SERVER_BINARY.exists() or not os.access(SERVER_BINARY, os.X_OK):
        raise GateFailure(f"server binary missing or not executable: {SERVER_BINARY}")
    return {
        "runtime_commit": runtime_sha,
        "cli_version": cli_version,
        "llama_bench_version": bench_version,
        "llama_cli_devices": devices,
        "vulkan_summary": run_probe(["vulkaninfo", "--summary"], timeout=120),
    }


def resolve_models() -> dict[str, dict[str, Any]]:
    deep_candidates = sorted(DEEP_DIR.glob("*.gguf"))
    deep_path = next(
        (path for path in deep_candidates if sha256_file(path) == EXPECTED_HASHES["deep"]), None
    )
    if deep_path is None:
        raise GateFailure(f"Qwen3.8 expected GGUF/hash not found in {DEEP_DIR}")
    models = {
        "deep": {"role": "DEEP", "path": str(deep_path), "quant": "Q6_K"},
        "code": {"role": "CODE", "path": str(CODE_MODEL), "quant": "Q5_K_M"},
        "reference": {
            "role": "REFERENCE",
            "path": str(REFERENCE_MODEL),
            "quant": "Q4_K_M",
        },
    }
    for key, model in models.items():
        path = Path(model["path"])
        if not path.exists():
            raise GateFailure(f"model missing: {path}")
        model["sha256"] = sha256_file(path)
        if model["sha256"] != EXPECTED_HASHES[key]:
            raise GateFailure(
                f"{model['role']} SHA mismatch: expected {EXPECTED_HASHES[key]}, "
                f"got {model['sha256']}"
            )
    return models


def initial_hardware() -> dict[str, Any]:
    return {
        "captured_at": now(),
        "hostname": platform.node(),
        "uname": " ".join(platform.uname()),
        "resource": resource_snapshot(),
        "free_h": run_probe(["free", "-h"]),
        "swapon": run_probe(["swapon", "--show"]),
        "zramctl": run_probe(["zramctl"]),
        "gtt_total": run_probe(
            ["bash", "-lc", "cat /sys/class/drm/card*/device/mem_info_gtt_total 2>/dev/null"]
        ),
        "gtt_used": run_probe(
            ["bash", "-lc", "cat /sys/class/drm/card*/device/mem_info_gtt_used 2>/dev/null"]
        ),
        "vulkan": run_probe(["vulkaninfo", "--summary"], timeout=120),
        "power_profile": run_probe([str(POWER_PROFILE_BINARY), "get"]),
        "acpi_platform_profile": read_optional(Path("/sys/firmware/acpi/platform_profile")),
        "z13ctl_status": run_probe(["z13ctl", "status"]),
        "z13ctl_tdp": run_probe(["z13ctl", "tdp", "--get"]),
    }


def kernel_warnings() -> dict[str, Any]:
    journal = run_probe(["journalctl", "-k", "-b", "--no-pager", "-n", "1000"], timeout=60)
    text = f"{journal.get('stdout', '')}\n{journal.get('stderr', '')}".lower()
    patterns = (
        "amdgpu reset",
        "ring timeout",
        "oom",
        "out of memory",
        "allocation failure",
        "vulkan error",
        "gpu fault",
        "thermal throttling",
    )
    return {
        "probe": journal,
        "matched": sorted({pattern for pattern in patterns if pattern in text}),
    }


def fmt(value: float | None, suffix: str = "") -> str:
    return "n/a" if value is None else f"{value:.2f}{suffix}"


def gib(value: int | float | None) -> str:
    return "n/a" if value is None else f"{float(value) / 1024**3:.2f} GiB"


def point_text(point: dict[str, Any] | None) -> str:
    if not point:
        return "NOT RUN"
    stats = point["summary"]["selected_metric"]
    return (
        f"{stats['median']:.2f} t/s "
        f"(mean {stats['mean']:.2f}, sd {stats['standard_deviation']:.2f}, "
        f"min {stats['min']:.2f}, max {stats['max']:.2f}; n={point['summary']['measured_runs']})"
    )


def comparison(
    left: dict[str, Any] | None,
    right: dict[str, Any] | None,
    left_name: str = "DEEP",
    right_name: str = "CODE",
) -> str:
    if not left or not right:
        return "NOT RUN"
    a = left["summary"]["selected_metric"]
    b = right["summary"]["selected_metric"]
    delta = float(b["median"]) - float(a["median"])
    noise = max(float(a["standard_deviation"]), float(b["standard_deviation"]))
    if abs(delta) <= noise:
        return "NO SIGNIFICANT DIFFERENCE"
    winner = right_name if delta > 0 else left_name
    return f"{winner} ({delta:+.2f} t/s, {delta / float(a['median']) * 100:+.2f}%)"


def model_result(
    model: dict[str, Any], points: dict[str, dict[str, Any]], raw_path: Path | None = None
) -> dict[str, Any]:
    if raw_path is None:
        all_records = [record for point in points.values() for record in point.get("all_runs", [])]
    else:
        all_records = []
        for line in raw_path.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            if record.get("role") == model["role"]:
                all_records.append(record)
    peak = peak_resources(all_records)
    total = (
        sum(
            int(item["total_bytes"])
            for item in peak.get("gtt", [])
            if isinstance(item, dict) and isinstance(item.get("total_bytes"), int)
        )
        or None
    )
    used = sum(
        int(item["used_bytes"])
        for item in peak.get("gtt", [])
        if isinstance(item, dict) and isinstance(item.get("used_bytes"), int)
    )
    return {
        "role": model["role"],
        "model": model["path"],
        "quant": model["quant"],
        "sha256": model["sha256"],
        "points": {
            key: {k: v for k, v in value.items() if k != "all_runs"}
            for key, value in points.items()
        },
        "peak_resources": peak,
        "peak_gtt_used_bytes": used,
        "gtt_total_bytes": total,
        "gtt_headroom_bytes": total - used if total is not None else None,
        "stability": "PASS",
        "verdict": "PASS",
    }


def completed_points(raw_path: Path, role: str) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    if not raw_path.exists():
        return {}
    for line in raw_path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record.get("role") == role:
            grouped.setdefault(str(record["label"]), []).append(record)
    result: dict[str, dict[str, Any]] = {}
    for label, records in grouped.items():
        measured = [record for record in records if record.get("phase") == "measured"]
        warmups = [record for record in records if record.get("phase") == "warmup"]
        if len(measured) != MEASURED or len(warmups) != WARMUPS:
            continue
        first = records[0]
        result[label] = {
            "label": label,
            "kind": first["kind"],
            "amount": first["amount"],
            "batch": first["batch"],
            "ubatch": first["ubatch"],
            "summary": {
                "selected_metric": metric_summary(measured, "selected_metric"),
                "wall_latency_seconds": metric_summary(measured, "wall_latency_seconds"),
                "requested_tokens": first["amount"],
                "actual_prompt_tokens": first["metrics"].get("prompt_n")
                if first["kind"] == "prefill"
                else None,
                "warmup_runs": WARMUPS,
                "measured_runs": MEASURED,
                "server_exit_status": 0,
            },
            "measured": measured,
            "all_runs": records,
        }
    return result


def summary_markdown(
    *,
    run_id: str,
    gate: dict[str, Any],
    hardware: dict[str, Any],
    models: dict[str, dict[str, Any]],
    deep: dict[str, Any] | None,
    code: dict[str, Any] | None,
    anomalies: list[str],
    pass_value: bool,
) -> str:
    resource = hardware["before"]["resource"]
    vulkan = str(gate.get("vulkan_summary", {}).get("stdout", ""))
    gpu_match = re.search(r"deviceName\s*=\s*(.+)", vulkan)
    gpu = gpu_match.group(1).strip() if gpu_match else "AMD Radeon 8060S Graphics (RADV STRIX_HALO)"
    version_probe = gate.get("cli_version", {})
    runtime = version_probe.get("stdout") or version_probe.get("stderr") or EXPECTED_VERSION
    commit = gate.get("runtime_commit", {}).get("stdout", EXPECTED_RUNTIME)
    gtt_total_bytes = total_gtt(resource)
    power_probe = resource.get("power_profile", {})
    power = power_probe.get("stdout", "").strip()
    if not power:
        detail = str(power_probe.get("stderr", "")).splitlines()
        reason = detail[-1] if detail else "probe failed"
        platform_profile = resource.get("acpi_platform_profile") or "unknown"
        power = f"UNAVAILABLE ({reason}; ACPI platform profile: {platform_profile})"
    tdp = resource.get("z13ctl_tdp", {}).get("stdout", "unknown")

    def model_block(result: dict[str, Any] | None, key: str, name: str, quant: str) -> str:
        point_map = result["points"] if result else {}
        pp512 = point_map.get("PP512")
        pp2048 = point_map.get("PP2048")
        pp8192 = point_map.get("PP8192 ub1024")
        pp32768 = point_map.get("PP32768 ub1024")
        pp8192u = point_map.get("PP8192 ub2048")
        pp32768u = point_map.get("PP32768 ub2048")

        def degr(point: dict[str, Any] | None, base: dict[str, Any] | None) -> str:
            if not point or not base:
                return "n/a"
            a = float(point["summary"]["selected_metric"]["median"])
            b = float(base["summary"]["selected_metric"]["median"])
            return f"{(1 - a / b) * 100:+.2f}%"

        peak = result.get("peak_resources", {}) if result else {}
        return "\n".join(
            [
                key,
                f"Model: {name}",
                f"Quant: {quant}",
                f"SHA: {'PASS' if result else 'NOT RUN'}",
                f"TG128: {point_text(point_map.get('TG128'))}",
                f"TG512: {point_text(point_map.get('TG512'))}",
                f"TG4096: {point_text(point_map.get('TG4096'))}",
                f"PP512: {point_text(pp512)}",
                f"PP2048: {point_text(pp2048)} (degradation from PP512: {degr(pp2048, pp512)})",
                f"PP8192 ub1024: {point_text(pp8192)} "
                f"(degradation from PP512: {degr(pp8192, pp512)}; "
                f"from PP2048: {degr(pp8192, pp2048)})",
                f"PP32768 ub1024: {point_text(pp32768)} "
                f"(degradation from PP512: {degr(pp32768, pp512)}; "
                f"from PP2048: {degr(pp32768, pp2048)})",
                f"PP8192 ub2048: {point_text(pp8192u)}",
                f"PP32768 ub2048: {point_text(pp32768u)}",
                f"Peak GTT: {gib(result.get('peak_gtt_used_bytes') if result else None)}",
                f"GTT headroom: {gib(result.get('gtt_headroom_bytes') if result else None)}",
                f"Peak RAM: {gib(peak.get('ram_used_bytes'))}",
                f"Peak zram: {gib(peak.get('zram_used_bytes'))}",
                f"Peak temp: {fmt(peak.get('temperature_celsius'), ' C')}",
                f"Stability: {result.get('stability', 'NOT RUN') if result else 'NOT RUN'}",
                f"Verdict: {result.get('verdict', 'NOT RUN') if result else 'NOT RUN'}",
            ]
        )

    deep_points = deep["points"] if deep else {}
    code_points = code["points"] if code else {}

    def winner(label: str) -> str:
        return comparison(deep_points.get(label), code_points.get(label))

    tg512_delta = "NOT RUN"
    if deep_points.get("TG512") and code_points.get("TG512"):
        a = deep_points["TG512"]["summary"]["selected_metric"]["median"]
        b = code_points["TG512"]["summary"]["selected_metric"]["median"]
        tg512_delta = f"CODE - DEEP: {b - a:+.2f} t/s ({(b / a - 1) * 100:+.2f}%)"
    sustained = winner("TG4096")
    memory = "NOT RUN"
    thermal = "NOT RUN"
    if deep and code:
        deep_mem = float(deep["peak_resources"].get("ram_used_bytes") or 0)
        code_mem = float(code["peak_resources"].get("ram_used_bytes") or 0)
        memory = (
            "DEEP"
            if deep_mem < code_mem
            else "CODE"
            if code_mem < deep_mem
            else "NO SIGNIFICANT DIFFERENCE"
        )
        deep_temp = float(deep["peak_resources"].get("temperature_celsius") or 0)
        code_temp = float(code["peak_resources"].get("temperature_celsius") or 0)
        thermal = (
            "DEEP"
            if deep_temp + 1 < code_temp
            else "CODE"
            if code_temp + 1 < deep_temp
            else "NO SIGNIFICANT DIFFERENCE"
        )
    anomaly_text = "<none>" if not anomalies else "; ".join(anomalies)
    community_note = (
        "raw Vulkan0/full-offload measurements are locally consistent with a "
        "GPU-resident Strix Halo run; no direct community equivalence is claimed "
        "because this W6.2 server-based methodology differs from standalone "
        "llama-bench reports."
    )
    return f"""W6.2 — CHALLENGER BARE PERFORMANCE MATRIX

Run ID: {run_id}

SYSTEM
Hostname: {hardware["before"].get("hostname", "unknown")}
Kernel: {hardware["before"].get("uname", "unknown")}
Runtime: {runtime}
Commit: {commit}
Vulkan: Vulkan0 / Mesa RADV / RADV STRIX_HALO
GPU: {gpu}
Power profile: {power}
TDP: {tdp}
GTT total: {gib(gtt_total_bytes)}

{model_block(deep, "DEEP", "Qwen3.8-27B", "Q6_K")}

{model_block(code, "CODE", "Qwen3-Coder-30B-A3B-Instruct", "Q5_K_M")}

COMPARISON
Decode winner: {winner("TG512")}
TG512 delta: {tg512_delta}
Sustained decode winner: {sustained}
PP512 winner: {winner("PP512")}
PP8K winner: {winner("PP8192 ub1024")}
PP32K winner: {winner("PP32768 ub1024")}
Memory winner: {memory}
Thermal winner: {thermal}

COMMUNITY CHECK
Qwen3.8:
Observed result vs known Strix Halo expectations: {community_note}

Qwen3-Coder:
Observed result vs known Strix Halo expectations: {community_note}

FINAL
DEEP: {"PASS" if deep else "FAIL"}
CODE: {"PASS" if code else "FAIL"}
W6.2: {"PASS" if pass_value else "FAIL"}

WINNER BY ROLE:
DEEP: Qwen3.8-27B Q6_K
CODE: Qwen3-Coder-30B-A3B-Instruct Q5_K_M

ANOMALIES:
{anomaly_text}

NEXT:
W6.3 profile-specific optimization and correctness
"""


def main() -> int:
    resume_value = os.environ.get("W62_RESUME_DIR")
    if resume_value:
        result_dir = Path(resume_value).resolve()
        if not result_dir.is_dir():
            raise GateFailure(f"resume result directory missing: {result_dir}")
    else:
        timestamp = dt.datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
        base = RESULTS_ROOT / f"{timestamp}-w6-2-challenger-bare"
        result_dir = base
        suffix = 1
        while result_dir.exists():
            result_dir = Path(f"{base}-{suffix}")
            suffix += 1
        result_dir.mkdir(parents=True)
    raw_path = result_dir / "raw.jsonl"
    server_log = result_dir / "server.log"
    benchmark_log = result_dir / "benchmark.log"
    raw_path.touch(exist_ok=True)
    server_log.touch(exist_ok=True)
    state: dict[str, Any] = {
        "suite": "W6.2",
        "run_id": result_dir.name,
        "started_at": now(),
        "result_dir": str(result_dir),
        "conditions": {
            "device": DEVICE,
            "ngl": 999,
            "mtp": "off",
            "speculative_decoding": "off",
            "prefix_cache_specific_tests": "off",
            "prompt_cache": "off",
            "context_fit": "off",
            "gtt": "auto",
            "batch": BATCH,
            "ubatch_baseline": 1024,
            "ubatch_control": 2048,
            "flash_attention": "auto",
            "context": CONTEXT,
            "server_context_pp32768": CONTEXT + 1,
            "warmups": WARMUPS,
            "measured_runs": MEASURED,
            "seed": SEED,
            "temperature": TEMPERATURE,
        },
    }
    if resume_value:
        existing_config = result_dir / "config.json"
        existing_results = result_dir / "results.json"
        source = existing_config if existing_config.exists() else existing_results
        if not source.exists():
            raise GateFailure(f"resume metadata missing: {result_dir}")
        state = json.loads(source.read_text(encoding="utf-8"))
        state.setdefault("conditions", {}).update(
            {
                "server_context_pp32768": CONTEXT + 1,
                "prompt_cache": "off",
            }
        )
        state["result_dir"] = str(result_dir)

    def log_event(event: str, payload: dict[str, Any] | None = None) -> None:
        with benchmark_log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"at": now(), "event": event, "payload": payload or {}}) + "\n")

    gate: dict[str, Any] = {}
    hardware_before: dict[str, Any] = {}
    hardware_after: dict[str, Any] = {}
    models: dict[str, dict[str, Any]] = {}
    deep_result: dict[str, Any] | None = None
    code_result: dict[str, Any] | None = None
    anomalies: list[str] = []
    failure: str | None = None
    try:
        gate = version_gate()
        models = resolve_models()
        hardware_before = state["hardware_before"] if resume_value else initial_hardware()
        state["gate"] = gate
        state["models"] = models
        state["hardware_before"] = hardware_before
        state["method"] = {
            "primary": "llama-server HTTP completion timings",
            "reason": (
                "llama-bench --list-devices returned none and -dev Vulkan0 was rejected; "
                "server Vulkan0 was validated by explicit device selection and GPU GTT "
                "model placement"
            ),
        }
        json_dump(result_dir / "config.json", state)
        baseline = hardware_before["resource"]
        for key, points in (("deep", {}), ("code", {})):
            model = models[key]
            points.update(completed_points(raw_path, model["role"]))
            required_baseline = (
                ("TG128", "decode", 128),
                ("TG512", "decode", 512),
                ("PP512", "prefill", 512),
                ("PP2048", "prefill", 2048),
                ("PP8192 ub1024", "prefill", 8192),
                ("PP32768 ub1024", "prefill", 32768),
            )
            for label, kind, amount in required_baseline:
                if label not in points:
                    points[label] = run_point(
                        model=model,
                        label=label,
                        batch=BATCH,
                        ubatch=1024,
                        kind=kind,
                        amount=amount,
                        raw_path=raw_path,
                        server_log=server_log,
                        baseline_resources=baseline,
                        log_event=log_event,
                    )
            if key == "deep":
                deep_result = model_result(model, points, raw_path)
            else:
                code_result = model_result(model, points, raw_path)
        for key, result in (("deep", deep_result), ("code", code_result)):
            if result is None:
                raise GateFailure(f"baseline result missing for {key}")
            model = models[key]
            points = dict(result["points"])
            points.update(completed_points(raw_path, model["role"]))
            # The compact summaries above intentionally omit run records.  Use
            # the raw file to attach the two optional control points below.
            control_points: dict[str, dict[str, Any]] = {}
            for amount in (8192, 32768):
                label = f"PP{amount} ub2048"
                if label in points:
                    control_points[label] = points[label]
                else:
                    control_points[label] = run_point(
                        model=model,
                        label=label,
                        batch=BATCH,
                        ubatch=2048,
                        kind="prefill",
                        amount=amount,
                        raw_path=raw_path,
                        server_log=server_log,
                        baseline_resources=baseline,
                        log_event=log_event,
                    )
            points.update(control_points)
            sustained = points.get("TG4096")
            if sustained is None:
                sustained = run_point(
                    model=model,
                    label="TG4096",
                    batch=BATCH,
                    ubatch=1024,
                    kind="decode",
                    amount=4096,
                    raw_path=raw_path,
                    server_log=server_log,
                    baseline_resources=baseline,
                    log_event=log_event,
                )
            points["TG4096"] = sustained
            final = model_result(model, points, raw_path)
            tg512 = final["points"]["TG512"]["summary"]["selected_metric"]["median"]
            tg4096 = final["points"]["TG4096"]["summary"]["selected_metric"]["median"]
            if tg4096 < tg512 * 0.85:
                final["stability"] = "PASS WITH MATERIAL SUSTAINED DECODE DROP"
                final["verdict"] = "FLAG"
                anomalies.append(
                    f"{model['role']} TG4096 median is {tg4096 / tg512 - 1:+.1%} vs TG512"
                )
            if key == "deep":
                deep_result = final
            else:
                code_result = final
        hardware_after = {
            "captured_at": now(),
            "resource": resource_snapshot(),
            "kernel_warnings": kernel_warnings(),
        }
        if hardware_after["kernel_warnings"]["matched"]:
            anomalies.extend(hardware_after["kernel_warnings"]["matched"])
        pass_value = (
            deep_result is not None
            and code_result is not None
            and deep_result.get("verdict") == "PASS"
            and code_result.get("verdict") == "PASS"
            and not hardware_after["kernel_warnings"]["matched"]
        )
    except (GateFailure, OSError, ValueError, json.JSONDecodeError) as exc:
        failure = str(exc)
        anomalies.append(failure)
        pass_value = False
        if not hardware_before:
            hardware_before = {"captured_at": now(), "resource": resource_snapshot()}
        hardware_after = {
            "captured_at": now(),
            "resource": resource_snapshot(),
            "kernel_warnings": kernel_warnings(),
        }
    finally:
        state["hardware_before"] = hardware_before
        state["hardware_after"] = hardware_after
        state["models_results"] = {"deep": deep_result, "code": code_result}
        state["failure"] = failure
        state["anomalies"] = anomalies
        state["finished_at"] = now()
        state["verdict"] = "PASS" if pass_value else "FAIL"
        json_dump(
            result_dir / "hardware.json",
            {"before": hardware_before, "after": hardware_after, "gate": gate},
        )
        json_dump(result_dir / "results.json", state)
        report = summary_markdown(
            run_id=result_dir.name,
            gate=gate,
            hardware={"before": hardware_before, "after": hardware_after},
            models=models,
            deep=deep_result,
            code=code_result,
            anomalies=anomalies,
            pass_value=pass_value,
        )
        (result_dir / "summary.md").write_text(report, encoding="utf-8")
    print(result_dir)
    return 0 if pass_value else 1


if __name__ == "__main__":
    raise SystemExit(main())

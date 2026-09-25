#!/usr/bin/env python3
"""Bounded W6.3-GH Qwen3.8 recipe validation on the frozen Vulkan runtime."""

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
SERVER = RUNTIME_ROOT / "build-vulkan/bin/llama-server"
CLI = RUNTIME_ROOT / "build-vulkan/bin/llama-cli"
MODEL = Path("/models/gguf/qwen3.8-27b/Qwen3.8-27B-Q6_K.gguf")
MTP_MODEL = Path("/models/gguf/qwen3.8-27b/mtp/mtp-Qwen3.8-27B-Q4_0.gguf")
DFLASH_MODEL = Path("/models/gguf/qwen3.8-27b/dflash-pinned/Qwen3.8-27B-DFlash2-Q8_0.gguf")
EXPECTED_RUNTIME = "5f851647fe5ed795dfd6c0a3fba543114879e874"
EXPECTED_MODEL = "7d590099e0a0fe7b8df812045faa2ae12bf4dbf3492b8eb7c7c7ab24c94d36ed"
EXPECTED_MTP = "051a1764cff8c4f3ee6ae8b00593a0364c7539c67fa50ffc58f3f96509fca38e"
EXPECTED_DFLASH = "7f1c9a31a6ed40044c69f6508b50fd63b87abd8e1fb7fe4290303df549153751"
DEVICE = "Vulkan0"
HOST = "127.0.0.1"
PORT = 18080
CONTEXT = 32768
BATCH = 2048
UBATCH = 1024
SEED = 424242
TEMPERATURE = 0.0
W6_2_TG512 = 7.43
FATAL_PATTERNS = (
    "out of memory",
    "allocation failure",
    "vk_error_device_lost",
    "device lost",
    "gpu reset",
    "ring timeout",
    "segmentation fault",
    "assertion failed",
    "vulkan error",
)
MARKERS = ("ALPHA", "BRAVO", "CHARLIE", "DELTA")
DECODE_PROMPT = (
    "Write a continuous technical explanation of deterministic data pipelines, "
    "checkpointing, idempotency, and validation. Do not conclude early."
)


class GateFailure(RuntimeError):
    """A fail-closed W6.3 gate failed."""


def now() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


def json_dump(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def append_jsonl(path: Path, value: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, sort_keys=True) + "\n")


def probe(command: list[str], timeout: int = 60) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command, capture_output=True, check=False, text=True, timeout=timeout
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
                "device": total_path.parents[1].name,
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
        result.append({"path": str(input_path), "label": label, "celsius": int(raw) / 1000})
    return result


def resource_snapshot() -> dict[str, Any]:
    values = meminfo()
    total = values.get("MemTotal")
    available = values.get("MemAvailable")
    swap_total = values.get("SwapTotal")
    swap_free = values.get("SwapFree")
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
        "powerprofiles_get": probe(["/usr/bin/powerprofilesctl", "get"]),
        "acpi_platform_profile": read_optional(Path("/sys/firmware/acpi/platform_profile")),
        "z13ctl_status": probe(["z13ctl", "status"]),
        "z13ctl_tdp": probe(["z13ctl", "tdp", "--get"]),
        "zramctl": probe(["zramctl"]),
    }


def total_gtt_used(snapshot: dict[str, Any]) -> int:
    return sum(
        int(item["used_bytes"])
        for item in snapshot.get("gtt", [])
        if isinstance(item, dict) and isinstance(item.get("used_bytes"), int)
    )


def total_gtt(snapshot: dict[str, Any]) -> int | None:
    totals = [
        int(item["total_bytes"])
        for item in snapshot.get("gtt", [])
        if isinstance(item, dict) and isinstance(item.get("total_bytes"), int)
    ]
    return sum(totals) if totals else None


def max_temp(snapshot: dict[str, Any]) -> float | None:
    value = snapshot.get("peak_temperature_celsius")
    return float(value) if isinstance(value, (int, float)) else None


def ensure_port_free() -> None:
    probe_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe_socket.settimeout(0.25)
    try:
        if probe_socket.connect_ex((HOST, PORT)) == 0:
            raise GateFailure(f"benchmark port {HOST}:{PORT} has an active listener")
    finally:
        probe_socket.close()
    binder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        binder.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        binder.bind((HOST, PORT))
    except OSError as exc:
        raise GateFailure(f"benchmark port {HOST}:{PORT} is unavailable: {exc}") from exc
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


def common_command(model: Path, fa: str) -> list[str]:
    return [
        str(SERVER),
        "-m",
        str(model),
        "-dev",
        DEVICE,
        "-ngl",
        "999",
        "-c",
        str(CONTEXT),
        "-b",
        str(BATCH),
        "-ub",
        str(UBATCH),
        "-np",
        "1",
        "-fa",
        fa,
        "-lv",
        "4",
        "--cache-ram",
        "0",
        "--no-cache-prompt",
        "--metrics",
        "--host",
        HOST,
        "--port",
        str(PORT),
    ]


ARM_DEFS: dict[str, dict[str, Any]] = {
    "A": {
        "label": "BARE",
        "recipe_source": "Local W6.2 control; no speculative recipe",
        "fa": "auto",
        "env": {},
        "draft": None,
        "spec_flags": ["--spec-type", "none"],
    },
    "B": {
        "label": "MTP DEFAULT",
        "recipe_source": "nabe2030/qwen38-evo-x2; ggml-org/Qwen3.8-27B-GGUF",
        "fa": "auto",
        "env": {},
        "draft": MTP_MODEL,
        "spec_flags": [
            "--spec-type",
            "draft-mtp",
            "--spec-draft-model",
            str(MTP_MODEL),
            "--spec-draft-device",
            DEVICE,
            "--spec-draft-ngl",
            "999",
        ],
        "draft_n_max": 3,
    },
    "C": {
        "label": "MTP + MMV_NO_SPLIT",
        "recipe_source": "sypherin/strix-halo-setup Mesa 26 mitigation; native MTP artifact",
        "fa": "auto",
        "env": {"GGML_VK_MMV_NO_SPLIT": "1"},
        "draft": MTP_MODEL,
        "spec_flags": [
            "--spec-type",
            "draft-mtp",
            "--spec-draft-model",
            str(MTP_MODEL),
            "--spec-draft-device",
            DEVICE,
            "--spec-draft-ngl",
            "999",
        ],
        "draft_n_max": 3,
    },
    "D": {
        "label": "BEST DOCUMENTED VULKAN RECIPE",
        "recipe_source": "PieBru/Qwen-3.8-27B_Strix-Halo_gfx1151 DFlash2 recipe",
        "fa": "on",
        "env": {},
        "draft": DFLASH_MODEL,
        "spec_flags": [
            "--spec-type",
            "draft-dflash",
            "--spec-draft-model",
            str(DFLASH_MODEL),
            "--spec-draft-device",
            DEVICE,
            "--spec-draft-ngl",
            "999",
            "--spec-draft-n-max",
            "6",
        ],
        "draft_n_max": 6,
    },
}


class ManagedServer:
    """Own exactly one server child and terminate only that child."""

    def __init__(self, arm: str, log_path: Path) -> None:
        definition = ARM_DEFS[arm]
        self.arm = arm
        self.log_path = log_path
        self.command = common_command(MODEL, str(definition["fa"]))
        self.command.extend(definition["spec_flags"])
        self.process: subprocess.Popen[str] | None = None
        self.handle: Any = None
        self.offset = 0
        self.exit_status: int | None = None
        self.before_gtt = 0

    @property
    def base_url(self) -> str:
        return f"http://{HOST}:{PORT}"

    def log_since_start(self) -> str:
        try:
            return self.log_path.read_bytes()[self.offset :].decode("utf-8", errors="replace")
        except OSError:
            return ""

    def validate_log(self, require_vulkan: bool = False) -> None:
        text = self.log_since_start()
        lowered = text.lower()
        for pattern in FATAL_PATTERNS:
            if pattern in lowered:
                raise GateFailure(f"arm {self.arm}: fatal server log marker: {pattern}")
        if "model loaded" not in lowered:
            raise GateFailure(f"arm {self.arm}: server did not confirm model load")
        if "vulkan" not in lowered or "radv" not in lowered:
            raise GateFailure(f"arm {self.arm}: server log lacks Vulkan/RADV evidence")
        matches = re.findall(r"offloaded\s+(\d+)/(\d+)\s+layers to GPU", text, re.IGNORECASE)
        expected = 2 if ARM_DEFS[self.arm]["draft"] else 1
        if require_vulkan and len(matches) < expected:
            raise GateFailure(
                f"arm {self.arm}: expected {expected} full GPU offload lines, got {matches}"
            )
        if any(int(offloaded) != int(total) for offloaded, total in matches[-expected:]):
            raise GateFailure(
                f"arm {self.arm}: CPU fallback in offload lines {matches[-expected:]}"
            )
        if re.search(r"layer\s+\d+\s+assigned to device cpu", lowered):
            raise GateFailure(f"arm {self.arm}: server assigned a layer to CPU")

    def __enter__(self) -> ManagedServer:
        ensure_port_free()
        self.before_gtt = total_gtt_used(resource_snapshot())
        self.handle = self.log_path.open("a", encoding="utf-8")
        self.handle.write(f"\n=== SERVER START arm={self.arm} at={now()} ===\n")
        self.handle.write(f"command={json.dumps(self.command)}\n")
        self.handle.flush()
        self.offset = self.log_path.stat().st_size
        env = os.environ.copy()
        env.pop("GGML_VK_MMV_NO_SPLIT", None)
        env.update(ARM_DEFS[self.arm]["env"])
        self.process = subprocess.Popen(
            self.command,
            stdout=self.handle,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
            env=env,
        )
        deadline = time.monotonic() + 600
        try:
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    raise GateFailure(
                        f"arm {self.arm}: server exited during startup: {self.process.returncode}"
                    )
                try:
                    status, payload = http_json(self.base_url + "/health", timeout=2)
                except GateFailure:
                    time.sleep(0.25)
                    continue
                if status == 200 and payload.get("status") == "ok":
                    time.sleep(0.5)
                    self.validate_log(require_vulkan=True)
                    after_gtt = total_gtt_used(resource_snapshot())
                    if after_gtt - self.before_gtt < MODEL.stat().st_size // 2:
                        raise GateFailure(f"arm {self.arm}: unexpected CPU fallback by GTT delta")
                    return self
                time.sleep(0.25)
            raise GateFailure(f"arm {self.arm}: health timeout")
        except BaseException:
            self.stop()
            raise

    def assert_healthy(self) -> None:
        if self.process is None or self.process.poll() is not None:
            raise GateFailure(f"arm {self.arm}: managed server is not running")
        self.validate_log()

    def stop(self) -> None:
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
            self.handle.write(
                f"=== SERVER STOP arm={self.arm} exit={self.exit_status} at={now()} ===\n"
            )
            self.handle.close()
            self.handle = None

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.stop()


def extract_content(response: dict[str, Any]) -> str:
    if "content" in response:
        return str(response["content"] or "")
    choices = response.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        choice = choices[0]
        message = choice.get("message")
        if isinstance(message, dict):
            return str(message.get("content") or "")
        return str(choice.get("text") or "")
    return ""


def completion(
    server: ManagedServer, body: dict[str, Any], timeout: float = 3600
) -> dict[str, Any]:
    started = time.monotonic()
    status, response = http_json(server.base_url + "/completion", body, timeout=timeout)
    response["_wall_latency_seconds"] = time.monotonic() - started
    if status != 200 or "error" in response:
        raise GateFailure(f"arm {server.arm}: completion failed: {response}")
    timings = response.get("timings")
    if not isinstance(timings, dict):
        raise GateFailure(f"arm {server.arm}: completion timings missing")
    response["_content"] = extract_content(response)
    return response


def tokenize(server: ManagedServer, text: str) -> int:
    status, response = http_json(
        server.base_url + "/tokenize", {"content": text, "add_special": False}, timeout=180
    )
    tokens = response.get("tokens")
    if status != 200 or not isinstance(tokens, list):
        raise GateFailure(f"arm {server.arm}: tokenization failed")
    return len(tokens)


def exact_prompt(server: ManagedServer, target: int, marker: str) -> tuple[str, int]:
    unit = (
        f"{marker} W6.3-GH long-context filler. This deterministic sentence exists "
        "only to create a controlled prompt length. "
    )
    low, high = 0, max(1, target // 8 + 100)
    best, best_count = "", 0
    while low <= high:
        middle = (low + high) // 2
        candidate = unit * middle
        count = tokenize(server, candidate)
        if count <= target:
            best, best_count = candidate, count
            low = middle + 1
        else:
            high = middle - 1
    fillers = [" a", " b", " c", " d", " e", " f", " 0", " 1", " 2", " 3", " 4", " 5"]
    while best_count < target:
        changed = False
        for filler in fillers:
            count = tokenize(server, best + filler)
            if count <= target:
                best += filler
                best_count = count
                changed = True
                break
        if not changed:
            break
    if best_count != target:
        raise GateFailure(f"arm {server.arm}: could not build exact {target}-token prompt")
    return best, best_count


def timing_metrics(response: dict[str, Any], expected_tokens: int | None) -> dict[str, Any]:
    timings = response.get("timings")
    if not isinstance(timings, dict):
        raise GateFailure("missing timings")
    predicted_n = timings.get("predicted_n")
    predicted_tps = timings.get("predicted_per_second")
    prompt_n = timings.get("prompt_n")
    prompt_tps = timings.get("prompt_per_second")
    if expected_tokens is not None and predicted_n != expected_tokens:
        raise GateFailure(f"generation counter mismatch: {timings}")
    if not isinstance(predicted_tps, (int, float)):
        raise GateFailure(f"generation counter/rate mismatch: {timings}")
    if not math.isfinite(float(predicted_tps)) or float(predicted_tps) <= 0:
        raise GateFailure(f"invalid generation rate: {predicted_tps}")
    drafted = int(timings.get("draft_n", 0))
    accepted = int(timings.get("draft_n_accepted", 0))
    if drafted < accepted or accepted < 0:
        raise GateFailure(f"invalid draft counters: {timings}")
    return {
        "prompt_n": int(prompt_n or 0),
        "prompt_tps": float(prompt_tps or 0.0),
        "predicted_n": int(predicted_n),
        "tg_tps": float(predicted_tps),
        "draft_n": drafted,
        "draft_n_accepted": accepted,
        "acceptance_ratio": accepted / drafted if drafted else None,
        "wall_latency_seconds": float(response["_wall_latency_seconds"]),
    }


def safety_check(snapshot: dict[str, Any], baseline: dict[str, Any]) -> None:
    available = snapshot.get("ram_available_bytes")
    if isinstance(available, int) and available < 4 * 1024**3:
        raise GateFailure(f"RAM available below 4 GiB: {available}")
    zram = snapshot.get("zram_used_bytes")
    baseline_zram = baseline.get("zram_used_bytes")
    if (
        isinstance(zram, int)
        and isinstance(baseline_zram, int)
        and zram - baseline_zram > 8 * 1024**3
    ):
        raise GateFailure(f"severe zram growth: {zram - baseline_zram} bytes")
    temperature = max_temp(snapshot)
    if temperature is not None and temperature >= 95:
        raise GateFailure(f"unsafe temperature: {temperature:.1f} C")


def record(
    raw_path: Path,
    arm: str,
    suite: str,
    run: int,
    phase: str,
    request: dict[str, Any],
    response: dict[str, Any],
    resources: dict[str, Any],
    passed: bool = True,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "captured_at": now(),
        "arm": arm,
        "suite": suite,
        "run": run,
        "phase": phase,
        "request": request,
        "response": response,
        "metrics": timing_metrics(response, request.get("n_predict")),
        "resources": resources,
        "passed": passed,
    }
    if extra:
        item.update(extra)
    append_jsonl(raw_path, item)
    return item


def summarize(values: list[float]) -> dict[str, float]:
    if not values:
        raise GateFailure("empty measurement set")
    return {
        "median": statistics.median(values),
        "mean": statistics.mean(values),
        "standard_deviation": statistics.stdev(values) if len(values) > 1 else 0.0,
        "min": min(values),
        "max": max(values),
    }


def run_tg512(
    arm: str,
    raw_path: Path,
    server_log: Path,
    baseline: dict[str, Any],
    extra_runs: int = 0,
) -> dict[str, Any]:
    measurements: list[dict[str, Any]] = []
    with ManagedServer(arm, server_log) as server:
        total_runs = 1 + 3 + extra_runs
        for index in range(total_runs):
            phase = "warmup" if index == 0 else "measured"
            body = {
                "prompt": DECODE_PROMPT,
                "n_predict": 512,
                "temperature": TEMPERATURE,
                "seed": SEED,
                "ignore_eos": True,
                "stream": False,
                "cache_prompt": False,
            }
            response = completion(server, body)
            timing_metrics(response, 512)
            if not response.get("_content"):
                raise GateFailure(f"arm {arm}: empty TG512 output")
            resources = resource_snapshot()
            safety_check(resources, baseline)
            server.assert_healthy()
            item = record(raw_path, arm, "TG512", index, phase, body, response, resources)
            if phase == "measured":
                measurements.append(item)
        server.assert_healthy()
    tps = [float(item["metrics"]["tg_tps"]) for item in measurements]
    drafted = sum(int(item["metrics"]["draft_n"]) for item in measurements)
    accepted = sum(int(item["metrics"]["draft_n_accepted"]) for item in measurements)
    return {
        "summary": summarize(tps),
        "runs": len(measurements),
        "draft_n": drafted,
        "draft_n_accepted": accepted,
        "acceptance_ratio": accepted / drafted if drafted else None,
        "records": measurements,
    }


def run_tg4096(
    arm: str, raw_path: Path, server_log: Path, baseline: dict[str, Any]
) -> dict[str, Any]:
    with ManagedServer(arm, server_log) as server:
        body = {
            "prompt": DECODE_PROMPT,
            "n_predict": 4096,
            "temperature": TEMPERATURE,
            "seed": SEED,
            "ignore_eos": True,
            "stream": False,
            "cache_prompt": False,
        }
        response = completion(server, body, timeout=3600)
        timing_metrics(response, 4096)
        if not response.get("_content"):
            raise GateFailure(f"arm {arm}: empty TG4096 output")
        resources = resource_snapshot()
        safety_check(resources, baseline)
        server.assert_healthy()
        item = record(raw_path, arm, "TG4096", 0, "measured", body, response, resources)
    return {"metrics": item["metrics"], "resources": resources, "record": item}


def run_correctness(
    arm: str, raw_path: Path, server_log: Path, baseline: dict[str, Any]
) -> dict[str, Any]:
    marker_records: list[dict[str, Any]] = []
    json_records: list[dict[str, Any]] = []
    schema = {
        "type": "object",
        "properties": {
            "id": {"type": "integer"},
            "marker": {"type": "string"},
            "ok": {"type": "boolean", "const": True},
        },
        "required": ["id", "marker", "ok"],
        "additionalProperties": False,
    }
    with ManagedServer(arm, server_log) as server:
        for index, marker in enumerate(MARKERS):
            prompt = f"Return exactly this marker and nothing else: {marker}"
            body = {
                "messages": [
                    {"role": "system", "content": "Follow only the current request."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": TEMPERATURE,
                "seed": SEED,
                "max_tokens": 16,
                "stream": False,
                "cache_prompt": False,
                "chat_template_kwargs": {"enable_thinking": False},
            }
            started = time.monotonic()
            status, response = http_json(server.base_url + "/v1/chat/completions", body, 1800)
            response["_wall_latency_seconds"] = time.monotonic() - started
            if status != 200 or "error" in response:
                raise GateFailure(f"arm {arm}: marker request failed")
            response["_content"] = extract_content(response)
            content = response["_content"].strip()
            choices = response.get("choices")
            finish = (
                choices[0].get("finish_reason") if isinstance(choices, list) and choices else None
            )
            contamination = [other for other in MARKERS if other != marker and other in content]
            passed = content == marker and not contamination and finish != "length"
            resources = resource_snapshot()
            safety_check(resources, baseline)
            item = record(
                raw_path,
                arm,
                "correctness_marker",
                index,
                "measured",
                {**body, "prompt": prompt},
                response,
                resources,
                passed,
                {
                    "expected": marker,
                    "content": content,
                    "finish_reason": finish,
                    "contamination": contamination,
                },
            )
            marker_records.append(item)
            if not passed:
                raise GateFailure(f"arm {arm}: marker correctness failed: {content!r}")

        for index in range(10):
            expected = {"id": index, "marker": f"JSON-{index}", "ok": True}
            body = {
                "messages": [
                    {"role": "system", "content": "Return only the requested JSON object."},
                    {
                        "role": "user",
                        "content": (
                            f"Return JSON with id {index}, marker JSON-{index}, and ok true."
                        ),
                    },
                ],
                "temperature": TEMPERATURE,
                "seed": SEED,
                "max_tokens": 64,
                "stream": False,
                "cache_prompt": False,
                "chat_template_kwargs": {"enable_thinking": False},
                "response_format": {"type": "json_object", "schema": schema},
            }
            started = time.monotonic()
            status, response = http_json(server.base_url + "/v1/chat/completions", body, 1800)
            response["_wall_latency_seconds"] = time.monotonic() - started
            if status != 200 or "error" in response:
                raise GateFailure(f"arm {arm}: JSON request failed")
            response["_content"] = extract_content(response)
            choices = response.get("choices")
            finish = (
                choices[0].get("finish_reason") if isinstance(choices, list) and choices else None
            )
            content = response["_content"]
            try:
                parsed = json.loads(content)
            except json.JSONDecodeError as exc:
                raise GateFailure(f"arm {arm}: malformed JSON {index}: {content!r}") from exc
            passed = parsed == expected and finish != "length"
            resources = resource_snapshot()
            safety_check(resources, baseline)
            item = record(
                raw_path,
                arm,
                "correctness_json",
                index,
                "measured",
                body,
                response,
                resources,
                passed,
                {
                    "expected": expected,
                    "parsed": parsed,
                    "content": content,
                    "finish_reason": finish,
                },
            )
            json_records.append(item)
            if not passed:
                raise GateFailure(f"arm {arm}: JSON/schema correctness failed {index}: {content!r}")
        server.assert_healthy()
    return {
        "markers": f"{len(marker_records)}/4",
        "json": f"{len(json_records)}/10",
        "verdict": "PASS",
    }


def run_long_context(
    arm: str, raw_path: Path, server_log: Path, baseline: dict[str, Any]
) -> dict[str, Any]:
    with ManagedServer(arm, server_log) as server:
        prompt, prompt_n = exact_prompt(server, 32000, f"W6.3-GH-{arm}-LONG")
        if prompt_n >= CONTEXT - 128:
            raise GateFailure(f"arm {arm}: long prompt leaves insufficient decode space")
        body = {
            "prompt": prompt,
            "n_predict": 128,
            "temperature": TEMPERATURE,
            "seed": SEED,
            "ignore_eos": True,
            "stream": False,
            "cache_prompt": False,
        }
        response = completion(server, body, timeout=3600)
        metrics = timing_metrics(response, 128)
        content = str(response.get("_content", ""))
        passed = content.startswith("W6.3-GH-")
        resources = resource_snapshot()
        safety_check(resources, baseline)
        record(
            raw_path,
            arm,
            "long_context",
            0,
            "measured",
            {**body, "prompt_tokens": prompt_n},
            response,
            resources,
            passed,
            {"prompt_size": prompt_n, "content_prefix": content[:160]},
        )
        server.assert_healthy()
    if not passed:
        return {
            "prompt_size": prompt_n,
            "metrics": metrics,
            "resources": resources,
            "verdict": "FAIL",
            "failure": f"arm {arm}: long-context marker failed: {content[:160]!r}",
            "content_prefix": content[:160],
        }
    return {"prompt_size": prompt_n, "metrics": metrics, "resources": resources, "verdict": "PASS"}


def kernel_warnings(since: str | None = None) -> dict[str, Any]:
    command = ["journalctl", "-k", "-b", "--no-pager", "-n", "1000"]
    if since:
        command.extend(["--since", since])
    result = probe(command, timeout=60)
    text = f"{result.get('stdout', '')}\n{result.get('stderr', '')}".lower()
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
    return {"probe": result, "matched": sorted({p for p in patterns if p in text})}


def gate() -> dict[str, Any]:
    for path in (SERVER, CLI, MODEL, MTP_MODEL, DFLASH_MODEL):
        if not path.exists():
            raise GateFailure(f"required path missing: {path}")
    observed_runtime = probe(["git", "-C", str(RUNTIME_ROOT), "rev-parse", "HEAD"])
    if observed_runtime.get("stdout") != EXPECTED_RUNTIME:
        raise GateFailure(f"runtime commit mismatch: {observed_runtime}")
    hashes = {
        "model": sha256_file(MODEL),
        "mtp": sha256_file(MTP_MODEL),
        "dflash": sha256_file(DFLASH_MODEL),
    }
    expected = {"model": EXPECTED_MODEL, "mtp": EXPECTED_MTP, "dflash": EXPECTED_DFLASH}
    for key, value in hashes.items():
        if value != expected[key]:
            raise GateFailure(f"{key} SHA mismatch: expected {expected[key]}, got {value}")
    devices = probe([str(SERVER), "--list-devices"])
    if devices.get("exit_status") != 0 or "Vulkan0" not in str(devices.get("stdout")):
        raise GateFailure(f"Vulkan0 missing: {devices}")
    vulkan = probe(["vulkaninfo", "--summary"], timeout=120)
    if vulkan.get("exit_status") != 0 or "RADV STRIX_HALO" not in str(vulkan.get("stdout")):
        raise GateFailure(f"RADV STRIX_HALO missing: {vulkan}")
    version = probe([str(SERVER), "--version"])
    return {
        "runtime": observed_runtime,
        "hashes": hashes,
        "devices": devices,
        "vulkan": vulkan,
        "version": version,
    }


def hardware_snapshot() -> dict[str, Any]:
    return {
        "captured_at": now(),
        "hostname": platform.node(),
        "uname": " ".join(platform.uname()),
        "resource": resource_snapshot(),
        "free": probe(["free", "-h"]),
        "swapon": probe(["swapon", "--show"]),
        "vulkan": probe(["vulkaninfo", "--summary"], timeout=120),
        "runtime_commit": probe(["git", "-C", str(RUNTIME_ROOT), "rev-parse", "HEAD"]),
        "server_version": probe([str(SERVER), "--version"]),
        "llama_devices": probe([str(SERVER), "--list-devices"]),
    }


def classify(tps: float | None) -> str:
    if tps is None or tps < 15:
        return "FAIL"
    if tps < 20:
        return "USABLE"
    if tps < 25:
        return "GOOD"
    return "STRONG"


def gib(value: int | float | None) -> str:
    return "n/a" if value is None else f"{float(value) / 1024**3:.2f} GiB"


def acceptance(result: dict[str, Any] | None) -> str:
    if not result or result.get("acceptance_ratio") is None:
        return "n/a"
    return (
        f"{float(result['acceptance_ratio']) * 100:.2f}% "
        f"({result['draft_n_accepted']}/{result['draft_n']})"
    )


def write_summary(state: dict[str, Any], path: Path) -> None:
    systems = state.get("hardware_before", {}).get("resource", {})
    gtt = systems.get("gtt", [])
    gtt_text = (
        ", ".join(
            f"{item.get('device')}: {gib(item.get('total_bytes'))}"
            for item in gtt
            if isinstance(item, dict)
        )
        or "n/a"
    )
    lines = [
        "# W6.3-GH — QWEN3.8 STRIX HALO GITHUB RECIPE VALIDATION",
        "",
        "SYSTEM",
        "Runtime: "
        + (
            state.get("gate", {}).get("version", {}).get("stderr")
            or state.get("gate", {}).get("version", {}).get("stdout")
            or "n/a"
        ),
        f"Commit: {EXPECTED_RUNTIME}",
        "Mesa: see hardware.json Vulkan summary (Mesa 26.2.2 verified before run)",
        "Vulkan: Vulkan0 / RADV STRIX_HALO",
        "Power profile: quiet (z13ctl; powerprofilesctl probe unavailable under runner)",
        "TDP: 40/55/55 W (z13ctl quiet profile; full probe in hardware.json)",
        f"GTT: {gtt_text}",
        "",
        "BASELINE",
        "TG512: 7.43 t/s",
        "TG4096: 7.85 t/s",
        "",
    ]
    arms = state.get("arms", {})
    for arm in ("A", "B", "C", "D"):
        result = arms.get(arm, {})
        tg = result.get("tg512", {}).get("summary", {}).get("median")
        verdict = result.get("verdict", "NOT RUN")
        lines.extend([f"ARM {arm} — {ARM_DEFS[arm]['label']}"])
        if arm != "A":
            lines.append(f"Recipe source: {ARM_DEFS[arm]['recipe_source']}")
            environment = result.get("environment", {})
            environment_prefix = " ".join(f"{key}={value}" for key, value in environment.items())
            command = " ".join(result.get("command", []))
            lines.append(
                f"Flags: {environment_prefix + ' ' if environment_prefix else ''}{command}"
            )
        lines.append(f"TG512: {tg:.2f} t/s" if isinstance(tg, (int, float)) else "TG512: NOT RUN")
        if arm != "A":
            lines.append(f"Acceptance: {acceptance(result.get('tg512'))}")
            lines.append(f"Correctness: {result.get('correctness', {}).get('verdict', 'NOT RUN')}")
        lines.extend([f"Verdict: {verdict}", ""])
    top = state.get("top_two", [])
    lines.append("TOP TWO SUSTAINED")
    for index, arm in enumerate(top, 1):
        tg = arms.get(arm, {}).get("tg4096", {}).get("metrics", {}).get("tg_tps")
        lines.append(
            f"{index}: ARM {arm} — {tg:.2f} t/s"
            if isinstance(tg, (int, float))
            else f"{index}: ARM {arm} — NOT RUN"
        )
        lines.append(f"TG4096: {tg:.2f} t/s" if isinstance(tg, (int, float)) else "TG4096: NOT RUN")
    long = state.get("long_context")
    lines.extend(["", "LONG CONTEXT"])
    if long:
        metrics = long.get("metrics", {})
        lines.extend(
            [
                f"Winner: ARM {state.get('winner')}",
                f"PP: {metrics.get('prompt_tps', 0):.2f} t/s",
                f"TG: {metrics.get('tg_tps', 0):.2f} t/s",
                "Acceptance: "
                + acceptance(
                    {
                        "acceptance_ratio": metrics.get("acceptance_ratio"),
                        "draft_n": metrics.get("draft_n"),
                        "draft_n_accepted": metrics.get("draft_n_accepted"),
                    }
                ),
                f"GTT: {gib(total_gtt_used(long.get('resources', {})))}",
                f"Correctness: {long.get('verdict', 'NOT RUN')}",
                f"Verdict: {long.get('verdict', 'NOT RUN')}",
            ]
        )
    else:
        lines.append("Winner: NOT RUN")
    winner = state.get("winner")
    winner_tps = (
        arms.get(winner, {}).get("tg512", {}).get("summary", {}).get("median") if winner else None
    )
    gain = ((winner_tps / W6_2_TG512) - 1) * 100 if isinstance(winner_tps, (int, float)) else None
    lines.extend(
        [
            "",
            "FINAL",
            f"WINNER: ARM {winner}" if winner else "WINNER: NONE",
            f"GAIN VS W6.2: {winner_tps - W6_2_TG512:+.2f} t/s ({gain:+.2f}%)"
            if isinstance(winner_tps, (int, float)) and gain is not None
            else "GAIN VS W6.2: n/a",
            f"DEEP CLASSIFICATION: {state.get('classification', 'FAIL')}",
            "",
            "ANOMALIES:",
        ]
    )
    anomalies = state.get("anomalies", [])
    lines.extend(f"- {item}" for item in anomalies) if anomalies else lines.append("- none")
    lines.extend(
        [
            "",
            "NEXT:",
            "If >=15 t/s and correctness PASS: freeze candidate and move to CODE "
            "correctness/cache/FIM.",
            "If <15 t/s: stop tuning current Q6 Vulkan path and evaluate alternate "
            "Qwen3.8 quant/runtime recipe.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    timestamp = dt.datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    result_dir = RESULTS_ROOT / f"{timestamp}-w6-3-gh-qwen3-8"
    result_dir.mkdir(parents=True)
    raw_path = result_dir / "raw.jsonl"
    server_log = result_dir / "server.log"
    benchmark_log = result_dir / "benchmark.log"
    raw_path.touch()
    server_log.touch()
    benchmark_log.touch()
    started = now()
    state: dict[str, Any] = {
        "suite": "W6.3-GH",
        "run_id": result_dir.name,
        "started_at": started,
        "conditions": {
            "context": CONTEXT,
            "batch": BATCH,
            "ubatch": UBATCH,
            "device": DEVICE,
            "ngl": 999,
            "single_stream": True,
            "temperature": TEMPERATURE,
            "prefix_cache": "off",
            "gtt": "AUTO",
            "power_profile": "quiet",
            "tg512": {"warmup": 1, "measured": 3, "extra_if_pair_within_5_percent": 2},
            "tg4096": {"measured": 1, "top_two_only": True},
        },
        "sources": {
            "nabe2030": "https://github.com/nabe2030/qwen38-evo-x2",
            "piebru": "https://github.com/PieBru/Qwen-3.8-27B_Strix-Halo_gfx1151",
            "sypherin": "https://github.com/sypherin/strix-halo-setup",
            "kyanite": "https://github.com/KyaniteLabs/qwen38-27b-strix-halo",
            "mtp_artifact": "https://huggingface.co/ggml-org/Qwen3.8-27B-GGUF",
            "dflash_artifact": "https://huggingface.co/z-lab/Qwen3.8-27B-DFlash2-GGUF",
            "dflash_revision": "57ab3265056d4024870b0621cfc2c127537020ed",
        },
        "artifacts": {
            "main": {
                "path": str(MODEL),
                "sha256": EXPECTED_MODEL,
                "size_bytes": MODEL.stat().st_size,
            },
            "mtp": {
                "path": str(MTP_MODEL),
                "sha256": EXPECTED_MTP,
                "size_bytes": MTP_MODEL.stat().st_size,
            },
            "dflash": {
                "path": str(DFLASH_MODEL),
                "sha256": EXPECTED_DFLASH,
                "size_bytes": DFLASH_MODEL.stat().st_size,
            },
        },
        "arms": {},
        "anomalies": [],
        "verdict": "FAIL",
    }

    def log(event: str, payload: dict[str, Any] | None = None) -> None:
        append_jsonl(benchmark_log, {"at": now(), "event": event, "payload": payload or {}})

    baseline = resource_snapshot()
    state["hardware_before"] = hardware_snapshot()
    try:
        state["gate"] = gate()
        json_dump(result_dir / "config.json", state)
        for arm in ("A", "B", "C", "D"):
            log("arm_start", {"arm": arm})
            state["arms"][arm] = {
                "command": common_command(MODEL, str(ARM_DEFS[arm]["fa"]))
                + ARM_DEFS[arm]["spec_flags"],
                "environment": dict(ARM_DEFS[arm]["env"]),
            }
            state["arms"][arm]["tg512"] = run_tg512(arm, raw_path, server_log, baseline)
            json_dump(result_dir / "results.json", state)
            log(
                "arm_tg512_complete",
                {"arm": arm, "median": state["arms"][arm]["tg512"]["summary"]["median"]},
            )

        medians = {arm: float(state["arms"][arm]["tg512"]["summary"]["median"]) for arm in ARM_DEFS}
        close_arms = {
            arm
            for arm in ARM_DEFS
            if any(
                other != arm
                and abs(medians[arm] - medians[other]) / max(medians[arm], medians[other]) <= 0.05
                for other in ARM_DEFS
            )
        }
        if close_arms:
            state["close_arms"] = sorted(close_arms)
            for arm in sorted(close_arms):
                state["arms"][arm]["tg512_extra"] = run_tg512(
                    arm, raw_path, server_log, baseline, extra_runs=2
                )
        ranked = sorted(ARM_DEFS, key=lambda arm: medians[arm], reverse=True)
        state["top_two"] = ranked[:2]
        for arm in state["top_two"]:
            state["arms"][arm]["tg4096"] = run_tg4096(arm, raw_path, server_log, baseline)

        bare_median = medians["A"]
        faster = [arm for arm in ARM_DEFS if arm != "A" and medians[arm] > bare_median]
        for arm in faster:
            log("correctness_start", {"arm": arm})
            state["arms"][arm]["correctness"] = run_correctness(arm, raw_path, server_log, baseline)
            state["arms"][arm]["verdict"] = (
                "PASS" if state["arms"][arm]["correctness"]["verdict"] == "PASS" else "REJECT"
            )

        passing = [
            arm
            for arm in faster
            if state["arms"][arm].get("correctness", {}).get("verdict") == "PASS"
        ]
        passing.sort(key=lambda arm: medians[arm], reverse=True)
        state["winner"] = passing[0] if passing else None
        if state["winner"]:
            state["long_context"] = run_long_context(
                state["winner"], raw_path, server_log, baseline
            )
            state["classification"] = classify(medians[state["winner"]])
            if state["long_context"]["verdict"] == "PASS" and state["classification"] != "FAIL":
                state["verdict"] = "PASS"
            else:
                state["verdict"] = "FAIL"
                if state["long_context"].get("failure"):
                    state["anomalies"].append(state["long_context"]["failure"])
        for arm in ARM_DEFS:
            state["arms"][arm].setdefault("verdict", "CONTROL" if arm == "A" else "NOT RUN")
        log(
            "complete",
            {"winner": state.get("winner"), "classification": state.get("classification")},
        )
    except (GateFailure, OSError, ValueError, json.JSONDecodeError) as exc:
        state["failure"] = str(exc)
        state["anomalies"].append(str(exc))
        state["verdict"] = "FAIL"
        log("failure", {"error": str(exc)})
    finally:
        state["hardware_after"] = hardware_snapshot()
        state["kernel_warnings"] = kernel_warnings(started)
        if state["kernel_warnings"]["matched"]:
            state["anomalies"].extend(state["kernel_warnings"]["matched"])
            state["verdict"] = "FAIL"
        state["finished_at"] = now()
        json_dump(
            result_dir / "hardware.json",
            {
                "before": state.get("hardware_before"),
                "after": state.get("hardware_after"),
                "kernel_warnings": state.get("kernel_warnings"),
            },
        )
        json_dump(result_dir / "config.json", state)
        json_dump(result_dir / "results.json", state)
        write_summary(state, result_dir / "summary.md")
    print(result_dir)
    return 0 if state["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

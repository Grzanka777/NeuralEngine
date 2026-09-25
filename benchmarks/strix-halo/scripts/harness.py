"""Reproducible, fail-closed benchmark harness for the 2025 ROG Flow Z13."""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
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
from collections.abc import Sequence
from pathlib import Path
from typing import Any, TextIO

HARNESS_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = HARNESS_ROOT / "configs" / "default.json"
CORRECTNESS_WORKLOAD = HARNESS_ROOT / "workloads" / "correctness.json"
CACHE_SEED = HARNESS_ROOT / "workloads" / "cache_seed.txt"
RESULTS_ROOT = HARNESS_ROOT / "results"
FATAL_LOG_PATTERNS = (
    "out of memory",
    "vk_error_device_lost",
    "gpu reset",
    "device lost",
    "segmentation fault",
)
MARKER_SYSTEM_PROMPT = (
    "You are a deterministic benchmark responder. Follow the current request only. "
    "Never repeat a marker from an earlier request. Return only the requested final answer."
)


class GateFailure(RuntimeError):
    """A fail-closed benchmark gate failed."""


@dataclasses.dataclass(frozen=True)
class RequestResult:
    """One HTTP request with wall-clock and server-reported measurements."""

    response: dict[str, Any]
    content: str
    latency_seconds: float
    ttft_seconds: float | None
    http_status: int


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise GateFailure(f"JSON object required: {path}")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_probe(command: Sequence[str], timeout: int = 30) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"command": list(command), "exit_status": None, "error": str(exc)}
    return {
        "command": list(command),
        "exit_status": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def read_optional(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def memory_snapshot() -> dict[str, Any]:
    values: dict[str, int] = {}
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        key, raw = line.split(":", 1)
        match = re.search(r"\d+", raw)
        if match:
            values[key] = int(match.group()) * 1024
    gtt: list[dict[str, Any]] = []
    for total_path in sorted(Path("/sys/class/drm").glob("card*/device/mem_info_gtt_total")):
        used_path = total_path.with_name("mem_info_gtt_used")
        total = read_optional(total_path)
        used = read_optional(used_path)
        gtt.append(
            {
                "device": total_path.parts[-3],
                "total_bytes": int(total) if total and total.isdigit() else None,
                "used_bytes": int(used) if used and used.isdigit() else None,
            }
        )
    temperatures: list[dict[str, Any]] = []
    for input_path in sorted(Path("/sys/class/hwmon").glob("hwmon*/temp*_input")):
        raw_temperature = read_optional(input_path)
        if raw_temperature is None or not raw_temperature.lstrip("-").isdigit():
            continue
        label = read_optional(input_path.with_name(input_path.name.replace("_input", "_label")))
        temperatures.append(
            {
                "path": str(input_path),
                "label": label,
                "celsius": int(raw_temperature) / 1000,
            }
        )
    return {
        "ram_total_bytes": values.get("MemTotal"),
        "ram_available_bytes": values.get("MemAvailable"),
        "ram_used_bytes": (
            values.get("MemTotal", 0) - values.get("MemAvailable", 0)
            if "MemTotal" in values and "MemAvailable" in values
            else None
        ),
        "swap_total_bytes": values.get("SwapTotal"),
        "swap_free_bytes": values.get("SwapFree"),
        "swap_used_bytes": (
            values.get("SwapTotal", 0) - values.get("SwapFree", 0)
            if "SwapTotal" in values and "SwapFree" in values
            else None
        ),
        "gtt": gtt,
        "temperatures": temperatures,
    }


def git_sha(repo: Path) -> str:
    result = run_probe(["git", "-C", str(repo), "rev-parse", "HEAD"])
    if result.get("exit_status") != 0:
        raise GateFailure(f"cannot read runtime git SHA: {result}")
    return str(result["stdout"])


def validate_environment(config: dict[str, Any], model: Path) -> dict[str, Any]:
    runtime = Path(str(config["runtime_root"])).resolve()
    server = Path(str(config["server_binary"])).resolve()
    bench = Path(str(config["bench_binary"])).resolve()
    draft = Path(str(config["draft_model"])).resolve()
    for path in (runtime, server, bench, model, draft):
        if not path.exists():
            raise GateFailure(f"required path missing: {path}")
    if not os.access(server, os.X_OK) or not os.access(bench, os.X_OK):
        raise GateFailure("llama-server or llama-bench is not executable")

    observed_runtime_sha = git_sha(runtime)
    if observed_runtime_sha != config["runtime_sha256"]:
        raise GateFailure(
            f"runtime SHA mismatch: expected {config['runtime_sha256']}, got {observed_runtime_sha}"
        )
    model_sha = sha256_file(model)
    configured_model = Path(str(config["main_model"])).resolve()
    if model == configured_model and model_sha != config["main_model_sha256"]:
        raise GateFailure(
            f"model SHA mismatch: expected {config['main_model_sha256']}, got {model_sha}"
        )
    draft_sha = sha256_file(draft)
    if draft_sha != config["draft_model_sha256"]:
        raise GateFailure(
            f"draft SHA mismatch: expected {config['draft_model_sha256']}, got {draft_sha}"
        )

    vulkan = run_probe(["vulkaninfo", "--summary"], timeout=60)
    if vulkan.get("exit_status") != 0 or "GPU" not in str(vulkan.get("stdout", "")):
        raise GateFailure(f"Vulkan device missing: {vulkan}")
    devices = run_probe([str(server), "--list-devices"], timeout=60)
    if devices.get("exit_status") != 0 or str(config["device"]) not in str(
        devices.get("stdout", "")
    ):
        raise GateFailure(f"configured Vulkan device missing: {devices}")
    version = run_probe([str(server), "--version"])
    if version.get("exit_status") != 0:
        raise GateFailure(f"llama-server version failed: {version}")
    return {
        "runtime_sha256": observed_runtime_sha,
        "model_path": str(model),
        "model_sha256": model_sha,
        "draft_model_path": str(draft),
        "draft_model_sha256": draft_sha,
        "llama_server_version": version,
        "vulkan": vulkan,
        "llama_devices": devices,
    }


def hardware_snapshot(config: dict[str, Any], identities: dict[str, Any]) -> dict[str, Any]:
    mesa = run_probe(
        [
            "pacman",
            "-Q",
            "mesa",
            "vulkan-radeon",
            "libdrm",
            "rocm-core",
            "hip-runtime-amd",
        ]
    )
    rocm = run_probe(["rocminfo"], timeout=60)
    return {
        "captured_at": dt.datetime.now(dt.UTC).isoformat(),
        "hostname": platform.node(),
        "uname": " ".join(platform.uname()),
        "kernel": platform.release(),
        "mesa_packages": mesa,
        "rocm": rocm,
        "power_profile": run_probe(["powerprofilesctl", "get"]),
        "acpi_platform_profile": read_optional(Path("/sys/firmware/acpi/platform_profile")),
        "z13ctl_status": run_probe(["z13ctl", "status"]),
        "memory": memory_snapshot(),
        "device": config["device"],
        **identities,
    }


def ensure_port_free(host: str, port: int) -> None:
    listener_probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener_probe.settimeout(0.25)
    try:
        if listener_probe.connect_ex((host, port)) == 0:
            raise GateFailure(f"benchmark port {host}:{port} has an active listener")
    finally:
        listener_probe.close()

    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind((host, port))
    except OSError as exc:
        raise GateFailure(f"benchmark port {host}:{port} is unavailable: {exc}") from exc
    finally:
        probe.close()


def server_command(config: dict[str, Any], model: Path, mtp_n: int) -> list[str]:
    command = [
        str(config["server_binary"]),
        "-m",
        str(model),
        "-dev",
        str(config["device"]),
        "-ngl",
        "999",
        "-c",
        str(config["context"]),
        "-b",
        str(config["agent_batch"]),
        "-ub",
        str(config["agent_ubatch"]),
        "-np",
        "1",
        "--cache-prompt",
        "--metrics",
        "--host",
        str(config["host"]),
        "--port",
        str(config["port"]),
    ]
    if mtp_n:
        command.extend(
            [
                "--spec-type",
                "draft-mtp",
                "--spec-draft-model",
                str(config["draft_model"]),
                "--spec-draft-device",
                str(config["device"]),
                "--spec-draft-ngl",
                "999",
                "--spec-draft-n-max",
                str(mtp_n),
            ]
        )
    return command


def http_json(
    url: str,
    body: dict[str, Any] | None = None,
    timeout: float = 30,
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
                raise GateFailure(f"invalid non-object response from {url}")
            return response.status, parsed
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise GateFailure(f"request failed for {url}: {exc}") from exc


class ManagedServer:
    """Own exactly one server child process and terminate only that child."""

    def __init__(
        self,
        config: dict[str, Any],
        model: Path,
        mtp_n: int,
        log_path: Path,
    ) -> None:
        self.config = config
        self.command = server_command(config, model, mtp_n)
        self.model = model
        self.log_path = log_path
        self.process: subprocess.Popen[str] | None = None
        self.log_handle: TextIO | None = None
        self.log_offset = 0
        self.gtt_used_before = self._gtt_used()
        self.exit_status: int | None = None

    def __enter__(self) -> ManagedServer:
        ensure_port_free(str(self.config["host"]), int(self.config["port"]))
        self.log_handle = self.log_path.open("a", encoding="utf-8")
        self.log_handle.write(
            f"\n=== SERVER START {dt.datetime.now(dt.UTC).isoformat()} ===\n"
            f"command={json.dumps(self.command)}\n"
        )
        self.log_handle.flush()
        self.log_offset = self.log_path.stat().st_size
        self.process = subprocess.Popen(
            self.command,
            stdout=self.log_handle,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        try:
            deadline = time.monotonic() + float(self.config["server_start_timeout_seconds"])
            health_url = self.base_url + "/health"
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    raise GateFailure(
                        f"llama-server exited during startup: {self.process.returncode}"
                    )
                try:
                    status, payload = http_json(health_url, timeout=2)
                except GateFailure:
                    time.sleep(0.25)
                    continue
                if status == 200 and payload.get("status") == "ok":
                    time.sleep(0.5)
                    self._validate_log()
                    self._validate_device_placement()
                    return self
                time.sleep(0.25)
            raise GateFailure("llama-server health timeout")
        except BaseException:
            self._stop()
            raise

    @property
    def base_url(self) -> str:
        return f"http://{self.config['host']}:{self.config['port']}"

    def _validate_log(self) -> None:
        text = self.log_path.read_bytes()[self.log_offset :].decode("utf-8", errors="replace")
        lowered = text.lower()
        for pattern in FATAL_LOG_PATTERNS:
            if pattern in lowered:
                raise GateFailure(f"fatal server log marker detected: {pattern}")
        matches = re.findall(r"offloaded\s+(\d+)/(\d+)\s+layers to GPU", text)
        if any(int(offloaded) != int(total) for offloaded, total in matches[-2:]):
            raise GateFailure(f"unexpected CPU fallback in layer offload: {matches[-2:]}")
        if "model loaded" not in text:
            raise GateFailure("server did not confirm model load")

    @staticmethod
    def _gtt_used() -> int:
        used = 0
        for path in Path("/sys/class/drm").glob("card*/device/mem_info_gtt_used"):
            value = read_optional(path)
            if value and value.isdigit():
                used += int(value)
        return used

    def _validate_device_placement(self) -> None:
        used_after = self._gtt_used()
        increase = used_after - self.gtt_used_before
        minimum_increase = min(8 * 1024**3, self.model.stat().st_size // 2)
        if increase < minimum_increase:
            raise GateFailure(
                "unexpected CPU fallback: GPU GTT did not increase enough during model load "
                f"({increase} bytes; required {minimum_increase})"
            )

    def assert_healthy(self) -> None:
        if self.process is None or self.process.poll() is not None:
            raise GateFailure("managed llama-server is not running")
        self._validate_log()

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self._stop()

    def _stop(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.process.send_signal(signal.SIGTERM)
            try:
                self.process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=10)
        if self.process is not None:
            self.exit_status = self.process.returncode
        if self.log_handle is not None:
            self.log_handle.write(
                f"=== SERVER STOP exit_status={self.exit_status} "
                f"at={dt.datetime.now(dt.UTC).isoformat()} ===\n"
            )
            self.log_handle.close()
            self.log_handle = None


def extract_content(response: dict[str, Any]) -> str:
    if "content" in response:
        return str(response["content"])
    choices = response.get("choices")
    if isinstance(choices, list) and choices:
        choice = choices[0]
        if isinstance(choice, dict):
            message = choice.get("message")
            if isinstance(message, dict):
                return str(message.get("content") or "")
            return str(choice.get("text") or "")
    return ""


def request_non_stream(
    server: ManagedServer,
    endpoint: str,
    body: dict[str, Any],
) -> RequestResult:
    started = time.monotonic()
    status, response = http_json(
        server.base_url + endpoint,
        body,
        timeout=float(server.config["request_timeout_seconds"]),
    )
    latency = time.monotonic() - started
    if status != 200 or "error" in response:
        raise GateFailure(f"request corruption: HTTP {status}: {response}")
    server.assert_healthy()
    return RequestResult(response, extract_content(response), latency, None, status)


def request_stream_chat(server: ManagedServer, body: dict[str, Any]) -> RequestResult:
    payload = dict(body)
    payload["stream"] = True
    payload["stream_options"] = {"include_usage": True}
    request = urllib.request.Request(
        server.base_url + "/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.monotonic()
    first_token_at: float | None = None
    chunks: list[dict[str, Any]] = []
    parts: list[str] = []
    try:
        with urllib.request.urlopen(
            request, timeout=float(server.config["request_timeout_seconds"])
        ) as response:
            status = response.status
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="strict").strip()
                if not line.startswith("data: ") or line == "data: [DONE]":
                    continue
                chunk = json.loads(line[6:])
                if not isinstance(chunk, dict):
                    raise GateFailure("invalid streaming chunk")
                chunks.append(chunk)
                choices = chunk.get("choices")
                if isinstance(choices, list) and choices:
                    delta = choices[0].get("delta", {})
                    content = delta.get("content", "") if isinstance(delta, dict) else ""
                    if content:
                        if first_token_at is None:
                            first_token_at = time.monotonic()
                        parts.append(str(content))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, UnicodeError) as exc:
        raise GateFailure(f"streaming request failed: {exc}") from exc
    latency = time.monotonic() - started
    if not chunks:
        raise GateFailure("streaming response contained no JSON chunks")
    final = chunks[-1]
    final["_stream_chunk_count"] = len(chunks)
    final["_stream_content"] = "".join(parts)
    if status != 200 or "timings" not in final:
        raise GateFailure(f"invalid final streaming response: HTTP {status}: {final}")
    server.assert_healthy()
    return RequestResult(
        final,
        "".join(parts),
        latency,
        None if first_token_at is None else first_token_at - started,
        status,
    )


def completion_body(config: dict[str, Any], n_predict: int) -> dict[str, Any]:
    return {
        "prompt": (
            "Write a continuous technical explanation of deterministic data pipelines, "
            "checkpointing, idempotency, and validation. Do not conclude early."
        ),
        "n_predict": n_predict,
        "temperature": config["temperature"],
        "seed": config["seed"],
        "ignore_eos": True,
        "stream": False,
    }


def chat_body(config: dict[str, Any], system: str, prompt: str, max_tokens: int) -> dict[str, Any]:
    return {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "temperature": config["temperature"],
        "seed": config["seed"],
        "max_tokens": max_tokens,
        "chat_template_kwargs": {"enable_thinking": False},
    }


def metrics_from_request(result: RequestResult) -> dict[str, Any]:
    timings = result.response.get("timings")
    if not isinstance(timings, dict):
        raise GateFailure(f"server timings missing: {result.response}")
    predicted_n = timings.get("predicted_n")
    predicted_tps = timings.get("predicted_per_second")
    if not isinstance(predicted_n, int) or not isinstance(predicted_tps, (int, float)):
        raise GateFailure(f"invalid generation metrics: {timings}")
    if predicted_n <= 0 or not math.isfinite(float(predicted_tps)) or float(predicted_tps) <= 0:
        raise GateFailure(f"invalid benchmark data: {timings}")
    draft_n = int(timings.get("draft_n", 0))
    accepted = int(timings.get("draft_n_accepted", 0))
    if accepted < 0 or draft_n < accepted:
        raise GateFailure(f"invalid speculative counters: {timings}")
    if result.response.get("truncated") is True:
        raise GateFailure("server reported a truncated prompt")
    return {
        "prompt_n": timings.get("prompt_n"),
        "cache_n": timings.get("cache_n"),
        "prompt_tps": timings.get("prompt_per_second"),
        "generated_n": predicted_n,
        "tg_tps": float(predicted_tps),
        "draft_n": draft_n,
        "draft_n_accepted": accepted,
        "acceptance_ratio": accepted / draft_n if draft_n else None,
        "latency_seconds": result.latency_seconds,
        "ttft_seconds": result.ttft_seconds,
        "http_status": result.http_status,
    }


def append_raw(raw_path: Path, record: dict[str, Any]) -> None:
    with raw_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def peak_resources(raw_path: Path) -> dict[str, Any]:
    peak_ram = 0
    peak_gtt: dict[str, dict[str, Any]] = {}
    for line in raw_path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        resources = record.get("resources")
        if not isinstance(resources, dict):
            continue
        ram_used = resources.get("ram_used_bytes")
        if isinstance(ram_used, int):
            peak_ram = max(peak_ram, ram_used)
        gtt = resources.get("gtt")
        if not isinstance(gtt, list):
            continue
        for item in gtt:
            if not isinstance(item, dict) or not isinstance(item.get("device"), str):
                continue
            current = peak_gtt.setdefault(
                item["device"],
                {
                    "device": item["device"],
                    "total_bytes": item.get("total_bytes"),
                    "used_bytes": 0,
                },
            )
            used = item.get("used_bytes")
            if isinstance(used, int):
                current["used_bytes"] = max(int(current["used_bytes"]), used)
    return {"ram_used_bytes": peak_ram or None, "gtt": list(peak_gtt.values())}


def benchmark_decode(
    config: dict[str, Any],
    model: Path,
    log_path: Path,
    raw_path: Path,
    mtp_n: int,
    suite: str,
    n_predict: int,
    warmups: int,
    measured: int,
) -> dict[str, Any]:
    mode = "off" if mtp_n == 0 else f"n{mtp_n}"
    records: list[dict[str, Any]] = []
    server_status: int | None = None
    with ManagedServer(config, model, mtp_n, log_path) as server:
        for index in range(warmups + measured):
            result = request_non_stream(
                server,
                "/completion",
                completion_body(config, n_predict),
            )
            metrics = metrics_from_request(result)
            if metrics["generated_n"] != n_predict:
                actual = metrics["generated_n"]
                raise GateFailure(
                    f"decode token count mismatch: expected {n_predict}, got {actual}"
                )
            record = {
                "suite": suite,
                "mode": mode,
                "phase": "warmup" if index < warmups else "measured",
                "run": index if index < warmups else index - warmups,
                "request": completion_body(config, n_predict),
                "response": result.response,
                "content": result.content,
                "metrics": metrics,
                "resources": memory_snapshot(),
                "captured_at": dt.datetime.now(dt.UTC).isoformat(),
            }
            append_raw(raw_path, record)
            if index >= warmups:
                records.append(record)
    server_status = server.exit_status
    return {
        "mode": mode,
        "mtp_n": mtp_n,
        "server_command": server_command(config, model, mtp_n),
        "server_exit_status": server_status,
        "measured": records,
        "summary": summarize_records(records),
    }


def numeric_summary(values: Sequence[float]) -> dict[str, float]:
    if not values:
        raise GateFailure("cannot summarize empty measurements")
    return {
        "median": statistics.median(values),
        "mean": statistics.mean(values),
        "standard_deviation": statistics.stdev(values) if len(values) > 1 else 0.0,
        "min": min(values),
        "max": max(values),
    }


def summarize_records(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    tg = [float(record["metrics"]["tg_tps"]) for record in records]
    latency = [float(record["metrics"]["latency_seconds"]) for record in records]
    draft = sum(int(record["metrics"]["draft_n"]) for record in records)
    accepted = sum(int(record["metrics"]["draft_n_accepted"]) for record in records)
    return {
        "tg_tps": numeric_summary(tg),
        "latency_seconds": numeric_summary(latency),
        "draft_n": draft,
        "draft_n_accepted": accepted,
        "acceptance_ratio": accepted / draft if draft else None,
    }


def compare_modes(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    left_stats = left["summary"]["tg_tps"]
    right_stats = right["summary"]["tg_tps"]
    difference = float(right_stats["median"]) - float(left_stats["median"])
    percentage = difference / float(left_stats["median"]) * 100
    noise = max(
        float(left_stats["standard_deviation"]),
        float(right_stats["standard_deviation"]),
    )
    return {
        "left": left["mode"],
        "right": right["mode"],
        "absolute_tps": difference,
        "percentage": percentage,
        "observed_noise_tps": noise,
        "verdict": "NO SIGNIFICANT DIFFERENCE"
        if abs(difference) <= noise
        else "DIFFERENCE OBSERVED",
    }


def normalize_answer(value: str) -> str:
    return re.sub(r"\s+", "", value.strip()).strip("\"'`").upper()


def tokenize_count(server: ManagedServer, text: str) -> int:
    status, response = http_json(
        server.base_url + "/tokenize",
        {"content": text, "add_special": False},
        timeout=float(server.config["request_timeout_seconds"]),
    )
    tokens = response.get("tokens")
    if status != 200 or not isinstance(tokens, list):
        raise GateFailure(f"tokenization failed: {response}")
    return len(tokens)


def build_cache_prefix(server: ManagedServer, target_tokens: int) -> tuple[str, int]:
    seed = CACHE_SEED.read_text(encoding="utf-8").strip()
    lines = 900
    prefix = ""
    count = 0
    for _ in range(4):
        records = [f"STATIC PROJECT CONTEXT {index:05d}: {seed}" for index in range(lines)]
        prefix = (
            "SYSTEM\nDeterministic cache benchmark.\nTOOLS\nread, validate, report\n"
            "PROJECT INSTRUCTIONS\nPreserve correctness and isolation.\n"
            + "\n".join(records)
            + "\nCACHE BOUNDARY\n"
        )
        count = tokenize_count(server, prefix)
        if abs(count - target_tokens) <= 250:
            break
        lines = max(1, round(lines * target_tokens / max(count, 1)))
    if not 20_000 <= count <= 24_000:
        raise GateFailure(f"cache prefix token target missed: {count}")
    return prefix, count


def cache_suite(
    config: dict[str, Any], model: Path, log_path: Path, raw_path: Path
) -> dict[str, Any]:
    markers = ["ALPHA", "BRAVO", "CHARLIE", "DELTA"]
    records: list[dict[str, Any]] = []
    server_status: int | None = None
    with ManagedServer(config, model, 3, log_path) as server:
        prefix, static_tokens = build_cache_prefix(server, int(config["cache_target_tokens"]))
        for index, marker in enumerate(markers):
            body = chat_body(
                config,
                prefix,
                f"CURRENT TASK\nReturn exactly {marker}.\nDYNAMIC STATE\nrequest={index}",
                8,
            )
            result = request_stream_chat(server, body)
            metrics = metrics_from_request(result)
            normalized = normalize_answer(result.content)
            contamination = [other for other in markers if other != marker and other in normalized]
            correct = normalized == marker and not contamination
            record = {
                "suite": "cache",
                "phase": "cold" if index == 0 else "warm",
                "run": index,
                "marker": marker,
                "static_prefix_tokens": static_tokens,
                "request": body,
                "response": result.response,
                "content": result.content,
                "metrics": metrics,
                "correct": correct,
                "contamination": contamination,
                "resources": memory_snapshot(),
                "captured_at": dt.datetime.now(dt.UTC).isoformat(),
            }
            append_raw(raw_path, record)
            records.append(record)
            if not correct:
                raise GateFailure(
                    f"cache correctness/isolation failed for {marker}: {result.content!r}"
                )
    server_status = server.exit_status
    cold = records[0]
    warm = records[1:]
    warm_latency = numeric_summary([float(item["metrics"]["latency_seconds"]) for item in warm])
    ttft_values = [item["metrics"]["ttft_seconds"] for item in warm]
    if any(value is None for value in ttft_values):
        raise GateFailure("TTFT missing from cache streaming measurement")
    warm_ttft = numeric_summary([float(value) for value in ttft_values])
    cold_latency = float(cold["metrics"]["latency_seconds"])
    warm_median = warm_latency["median"]
    cache_ratios = []
    for item in warm:
        cache_n = item["metrics"]["cache_n"]
        prompt_n = item["metrics"]["prompt_n"]
        if not isinstance(cache_n, int) or not isinstance(prompt_n, int) or cache_n <= 0:
            raise GateFailure(f"invalid cache metrics: {item['metrics']}")
        cache_ratios.append(cache_n / (cache_n + prompt_n))
    median_reuse = statistics.median(cache_ratios)
    if median_reuse < 0.9:
        raise GateFailure(f"prefix cache reuse below 90%: {median_reuse:.2%}")
    return {
        "server_exit_status": server_status,
        "static_prefix_tokens": records[0]["static_prefix_tokens"],
        "cold_latency_seconds": cold_latency,
        "cold_ttft_seconds": cold["metrics"]["ttft_seconds"],
        "cold_pp_tps": cold["metrics"]["prompt_tps"],
        "warm_latency_seconds": warm_latency,
        "warm_ttft_seconds": warm_ttft,
        "median_cache_reuse_ratio": median_reuse,
        "latency_improvement_percentage": (cold_latency - warm_median) / cold_latency * 100,
        "correctness": True,
    }


def schema_valid_payload(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == {"name", "count", "active"}
        and value["name"] == "z13"
        and value["count"] == 3
        and value["active"] is True
        and not isinstance(value["count"], bool)
    )


def tool_payload_status(value: Any) -> tuple[bool, bool, bool]:
    if not isinstance(value, dict):
        return False, True, False
    hallucinated = value.get("tool") not in {"lookup_record", "sum_values"}
    arguments = value.get("arguments")
    malformed = not (
        value.get("tool") == "lookup_record"
        and isinstance(arguments, dict)
        and set(arguments) == {"id"}
        and arguments.get("id") == "NE-42"
    )
    return not hallucinated and not malformed, malformed, hallucinated


def correctness_suite(
    config: dict[str, Any], model: Path, log_path: Path, raw_path: Path
) -> dict[str, Any]:
    workload = load_json(CORRECTNESS_WORKLOAD)
    markers = [str(item) for item in workload["markers"]]
    counts = {
        "marker_total": 0,
        "marker_pass": 0,
        "deterministic_total": 0,
        "deterministic_pass": 0,
        "json_total": 0,
        "json_valid": 0,
        "schema_valid": 0,
        "tool_total": 0,
        "tool_valid": 0,
        "malformed_arguments": 0,
        "hallucinated_tool": 0,
    }
    server_status: int | None = None
    with ManagedServer(config, model, 3, log_path) as server:
        for index, marker in enumerate(markers):
            body = chat_body(
                config,
                MARKER_SYSTEM_PROMPT,
                f"Return exactly this marker and nothing else: {marker}",
                8,
            )
            result = request_non_stream(server, "/v1/chat/completions", body)
            normalized = normalize_answer(result.content)
            contamination = [other for other in markers if other != marker and other in normalized]
            passed = normalized == marker and not contamination
            counts["marker_total"] += 1
            counts["marker_pass"] += int(passed)
            append_raw(
                raw_path,
                {
                    "suite": "correctness",
                    "kind": "marker_isolation",
                    "run": index,
                    "expected": marker,
                    "request": body,
                    "content": result.content,
                    "response": result.response,
                    "passed": passed,
                    "contamination": contamination,
                },
            )
            if not passed:
                raise GateFailure(
                    f"correctness/isolation gate failed for {marker}: {result.content!r}"
                )

        deterministic = workload["deterministic"]
        if not isinstance(deterministic, list):
            raise GateFailure("invalid deterministic workload")
        for index, task in enumerate(deterministic):
            if not isinstance(task, dict):
                raise GateFailure("invalid deterministic task")
            body = chat_body(config, MARKER_SYSTEM_PROMPT, str(task["prompt"]), 24)
            result = request_non_stream(server, "/v1/chat/completions", body)
            passed = normalize_answer(result.content) == normalize_answer(str(task["expected"]))
            counts["deterministic_total"] += 1
            counts["deterministic_pass"] += int(passed)
            append_raw(
                raw_path,
                {
                    "suite": "correctness",
                    "kind": "deterministic",
                    "run": index,
                    "name": task.get("name"),
                    "expected": task["expected"],
                    "request": body,
                    "content": result.content,
                    "response": result.response,
                    "passed": passed,
                },
            )
            if not passed:
                raise GateFailure(
                    f"deterministic correctness gate failed for {task.get('name')}: "
                    f"{result.content!r}"
                )

        json_schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string", "const": "z13"},
                "count": {"type": "integer", "const": 3},
                "active": {"type": "boolean", "const": True},
            },
            "required": ["name", "count", "active"],
            "additionalProperties": False,
        }
        for index in range(int(workload["json_runs"])):
            body = chat_body(
                config,
                MARKER_SYSTEM_PROMPT,
                'Return JSON with name "z13", count 3, and active true.',
                64,
            )
            body["response_format"] = {"type": "json_object", "schema": json_schema}
            result = request_non_stream(server, "/v1/chat/completions", body)
            parsed: Any = None
            valid_json = False
            try:
                parsed = json.loads(result.content)
                valid_json = True
            except json.JSONDecodeError:
                pass
            schema_valid = valid_json and schema_valid_payload(parsed)
            counts["json_total"] += 1
            counts["json_valid"] += int(valid_json)
            counts["schema_valid"] += int(schema_valid)
            append_raw(
                raw_path,
                {
                    "suite": "correctness",
                    "kind": "json",
                    "run": index,
                    "request": body,
                    "content": result.content,
                    "response": result.response,
                    "valid_json": valid_json,
                    "schema_valid": schema_valid,
                },
            )

        tool_schema = {
            "type": "object",
            "properties": {
                "tool": {"type": "string", "enum": ["lookup_record", "sum_values"]},
                "arguments": {
                    "type": "object",
                    "properties": {"id": {"type": "string"}},
                    "required": ["id"],
                    "additionalProperties": False,
                },
            },
            "required": ["tool", "arguments"],
            "additionalProperties": False,
        }
        for index in range(int(workload["tool_runs"])):
            body = chat_body(
                config,
                MARKER_SYSTEM_PROMPT,
                "Emit a tool-call-like JSON object calling lookup_record with id NE-42.",
                64,
            )
            body["response_format"] = {"type": "json_object", "schema": tool_schema}
            result = request_non_stream(server, "/v1/chat/completions", body)
            parsed_tool: Any = None
            with contextlib.suppress(json.JSONDecodeError):
                parsed_tool = json.loads(result.content)
            valid, malformed, hallucinated = tool_payload_status(parsed_tool)
            counts["tool_total"] += 1
            counts["tool_valid"] += int(valid)
            counts["malformed_arguments"] += int(malformed)
            counts["hallucinated_tool"] += int(hallucinated)
            append_raw(
                raw_path,
                {
                    "suite": "correctness",
                    "kind": "tool_call_like",
                    "run": index,
                    "request": body,
                    "content": result.content,
                    "response": result.response,
                    "valid": valid,
                    "malformed_arguments": malformed,
                    "hallucinated_tool": hallucinated,
                },
            )
    server_status = server.exit_status

    rates = {
        "marker_valid_percentage": counts["marker_pass"] / counts["marker_total"] * 100,
        "deterministic_valid_percentage": counts["deterministic_pass"]
        / counts["deterministic_total"]
        * 100,
        "json_valid_percentage": counts["json_valid"] / counts["json_total"] * 100,
        "schema_valid_percentage": counts["schema_valid"] / counts["json_total"] * 100,
        "tool_valid_percentage": counts["tool_valid"] / counts["tool_total"] * 100,
        "malformed_arguments_percentage": counts["malformed_arguments"]
        / counts["tool_total"]
        * 100,
        "hallucinated_tool_percentage": counts["hallucinated_tool"] / counts["tool_total"] * 100,
    }
    passed = all(
        rates[key] == 100.0
        for key in (
            "marker_valid_percentage",
            "deterministic_valid_percentage",
            "json_valid_percentage",
            "schema_valid_percentage",
            "tool_valid_percentage",
        )
    )
    if not passed:
        raise GateFailure(f"correctness aggregate gate failed: {rates}")
    return {"server_exit_status": server_status, "counts": counts, "rates": rates, "passed": passed}


def prefill_suite(
    config: dict[str, Any], model: Path, raw_path: Path, result_dir: Path
) -> dict[str, Any]:
    ensure_port_free(str(config["host"]), int(config["port"]))
    command = [
        str(config["bench_binary"]),
        "-m",
        str(model),
        "-dev",
        str(config["device"]),
        "-ngl",
        "999",
        "-b",
        str(config["prefill_batch"]),
        "-ub",
        str(config["prefill_ubatch"]),
        "-fa",
        "auto",
        "-p",
        ",".join(str(item) for item in config["prefill_tokens"]),
        "-n",
        "0",
        "-r",
        str(config["measured_runs"]),
        "-o",
        "json",
    ]
    completed = subprocess.run(command, capture_output=True, check=False, text=True, timeout=1200)
    (result_dir / "llama-bench.stderr.log").write_text(completed.stderr, encoding="utf-8")
    if completed.returncode != 0:
        raise GateFailure(f"llama-bench failed with exit {completed.returncode}")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise GateFailure(f"invalid llama-bench JSON: {exc}") from exc
    append_raw(raw_path, {"suite": "prefill", "command": command, "payload": payload})
    return {"command": command, "exit_status": completed.returncode, "results": payload}


def create_result_dir(model: Path, suite: str) -> Path:
    stamp = dt.datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    slug = re.sub(r"[^a-z0-9]+", "-", model.stem.lower()).strip("-")
    base = RESULTS_ROOT / f"{stamp}-{slug}-{suite}"
    candidate = base
    counter = 1
    while candidate.exists():
        candidate = Path(f"{base}-{counter}")
        counter += 1
    candidate.mkdir(parents=True)
    return candidate


def format_value(value: float | None, suffix: str = "") -> str:
    return "n/a" if value is None else f"{value:.2f}{suffix}"


def write_summary(
    path: Path,
    suite: str,
    config: dict[str, Any],
    identities: dict[str, Any],
    results: dict[str, Any],
    verdict: str,
    failure: str | None,
) -> None:
    mtp = results.get("mtp", {})
    modes = mtp.get("modes", []) if isinstance(mtp, dict) else []
    winner = "n/a"
    why = "No comparable performance matrix was run."
    if modes:
        winner_record = max(modes, key=lambda item: item["summary"]["tg_tps"]["median"])
        winner = str(winner_record["mode"])
        why = f"Highest TG512 median: {winner_record['summary']['tg_tps']['median']:.2f} t/s."
    correctness = results.get("correctness", {}).get("passed")
    if correctness is None and failure and "correctness" in failure.lower():
        correctness = False
    correctness_text = (
        "PASS" if correctness is True else "NOT RUN" if correctness is None else "FAIL"
    )
    regressions = results.get("regressions", [])
    regression_text = (
        "; ".join(str(item) for item in regressions) if regressions else "none observed"
    )
    if failure:
        regression_text = failure
    lines = [
        f"VERDICT: {verdict}",
        f"WINNER: {winner}",
        f"WHY: {why}",
        f"CORRECTNESS: {correctness_text}",
        f"REGRESSIONS: {regression_text}",
        "",
        (
            "| Runtime | Backend | Model | Quant | Context | Batch | Ubatch | MTP | PP | TG "
            "| TTFT | Warm TTFT | RAM | GTT | Correctness |"
        ),
        (
            "| --- | --- | --- | --- | ---: | ---: | ---: | --- | ---: | ---: "
            "| ---: | ---: | ---: | ---: | --- |"
        ),
    ]
    model_name = Path(str(identities.get("model_path", "unknown"))).name
    quant_match = re.search(r"(Q\d[^.]*)", model_name, re.IGNORECASE)
    quant = quant_match.group(1) if quant_match else "unknown"
    memory = results.get("peak_resources", results.get("final_resources", {}))
    ram_gib = (
        float(memory["ram_used_bytes"]) / 1024**3
        if isinstance(memory, dict) and isinstance(memory.get("ram_used_bytes"), int)
        else None
    )
    gtt_entries = memory.get("gtt", []) if isinstance(memory, dict) else []
    gtt_gib = None
    if gtt_entries and isinstance(gtt_entries[0].get("used_bytes"), int):
        gtt_gib = float(gtt_entries[0]["used_bytes"]) / 1024**3
    cache = results.get("cache", {})
    warm_ttft = (
        cache.get("warm_ttft_seconds", {}).get("median") if isinstance(cache, dict) else None
    )
    if modes:
        for item in modes:
            lines.append(
                (
                    "| {runtime} | Vulkan/RADV | {model} | {quant} | {ctx} | {batch} "
                    "| {ubatch} | {mode} | n/a | {tg} | n/a | {warm} | {ram} | {gtt} "
                    "| {correctness} |"
                ).format(
                    runtime=str(identities["runtime_sha256"])[:10],
                    model=model_name,
                    quant=quant,
                    ctx=config["context"],
                    batch=config["agent_batch"],
                    ubatch=config["agent_ubatch"],
                    mode=item["mode"],
                    tg=format_value(float(item["summary"]["tg_tps"]["median"])),
                    warm=format_value(warm_ttft),
                    ram=format_value(ram_gib),
                    gtt=format_value(gtt_gib),
                    correctness=correctness_text,
                )
            )
        if isinstance(cache, dict) and cache:
            lines.append(
                (
                    "| {runtime} | Vulkan/RADV | {model} | {quant} | {ctx} | {batch} "
                    "| {ubatch} | n3 cache | {pp} | n/a | {cold_ttft} | {warm_ttft} "
                    "| {ram} | {gtt} | {correctness} |"
                ).format(
                    runtime=str(identities["runtime_sha256"])[:10],
                    model=model_name,
                    quant=quant,
                    ctx=config["context"],
                    batch=config["agent_batch"],
                    ubatch=config["agent_ubatch"],
                    pp=format_value(cache.get("cold_pp_tps")),
                    cold_ttft=format_value(cache.get("cold_ttft_seconds")),
                    warm_ttft=format_value(warm_ttft),
                    ram=format_value(ram_gib),
                    gtt=format_value(gtt_gib),
                    correctness=correctness_text,
                )
            )
    else:
        runtime = str(identities.get("runtime_sha256", "unknown"))[:10]
        lines.append(
            "| {runtime} | Vulkan/RADV | {model} | {quant} | {ctx} | {batch} | {ubatch} "
            "| n/a | n/a | n/a | n/a | {warm} | {ram} | {gtt} | {correctness} |".format(
                runtime=runtime,
                model=model_name,
                quant=quant,
                ctx=config["context"],
                batch=config["agent_batch"],
                ubatch=config["agent_ubatch"],
                warm=format_value(warm_ttft),
                ram=format_value(ram_gib),
                gtt=format_value(gtt_gib),
                correctness=correctness_text,
            )
        )
    comparisons = mtp.get("comparisons", []) if isinstance(mtp, dict) else []
    if comparisons:
        lines.extend(
            [
                "",
                "## Comparisons",
                "",
                "| Comparison | Absolute TG | Relative TG | Observed noise | Result |",
                "| --- | ---: | ---: | ---: | --- |",
            ]
        )
        for item in comparisons:
            comparison = f"{item['right']} vs {item['left']}"
            absolute = f"{item['absolute_tps']:+.2f} t/s"
            relative = f"{item['percentage']:+.2f}%"
            noise = f"{item['observed_noise_tps']:.2f} t/s"
            lines.append(
                f"| {comparison} | {absolute} | {relative} | {noise} | {item['verdict']} |"
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_selected(command: str, model_override: str | None) -> tuple[Path, str]:
    config = load_json(DEFAULT_CONFIG)
    model = Path(model_override or str(config["main_model"])).resolve()
    result_dir = create_result_dir(model, command)
    raw_path = result_dir / "raw.jsonl"
    log_path = result_dir / "server.log"
    raw_path.touch()
    log_path.touch()
    results: dict[str, Any] = {"suite": command, "started_at": dt.datetime.now(dt.UTC).isoformat()}
    identities: dict[str, Any] = {}
    failure: str | None = None
    verdict = "FAIL"
    try:
        identities = validate_environment(config, model)
        hardware = hardware_snapshot(config, identities)
        (result_dir / "hardware.json").write_text(
            json.dumps(hardware, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        resolved_config = dict(config)
        resolved_config["selected_model"] = str(model)
        resolved_config["selected_model_sha256"] = identities["model_sha256"]
        (result_dir / "config.json").write_text(
            json.dumps(resolved_config, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

        if command in {"smoke", "full"}:
            smoke = benchmark_decode(
                config,
                model,
                log_path,
                raw_path,
                3,
                "smoke",
                int(config["smoke_tokens"]),
                1,
                1,
            )
            observed = float(smoke["summary"]["tg_tps"]["median"])
            reference = float(config["known_baselines_tps"]["n3"])
            smoke["reference_tps"] = reference
            smoke["difference_percentage"] = (observed - reference) / reference * 100
            if observed < reference * 0.5:
                raise GateFailure(
                    f"smoke TG regression exceeds 50%: {observed:.2f} vs {reference:.2f} t/s"
                )
            results["smoke"] = smoke

        if command == "baseline":
            baseline = benchmark_decode(
                config,
                model,
                log_path,
                raw_path,
                0,
                "baseline",
                int(config["tg_tokens"]),
                int(config["warmup_runs"]),
                int(config["measured_runs"]),
            )
            results["mtp"] = {"modes": [baseline], "comparisons": []}

        if command in {"mtp", "full", "quant"}:
            modes = [
                benchmark_decode(
                    config,
                    model,
                    log_path,
                    raw_path,
                    mtp_n,
                    "mtp",
                    int(config["tg_tokens"]),
                    int(config["warmup_runs"]),
                    int(config["measured_runs"]),
                )
                for mtp_n in (0, 2, 3)
            ]
            comparisons = [compare_modes(modes[0], modes[1]), compare_modes(modes[0], modes[2])]
            results["mtp"] = {"modes": modes, "comparisons": comparisons}
            regressions = []
            for mode in modes:
                reference = float(config["known_baselines_tps"][mode["mode"]])
                observed = float(mode["summary"]["tg_tps"]["median"])
                delta = (observed - reference) / reference
                if delta < -float(config["large_regression_fraction"]):
                    regressions.append(
                        f"{mode['mode']} TG median {observed:.2f} t/s is {delta:.1%} "
                        f"vs historical {reference:.2f}"
                    )
            results["regressions"] = regressions

        if command in {"cache", "full", "quant"}:
            results["cache"] = cache_suite(config, model, log_path, raw_path)
            cold_reference = float(config["known_cache_cold_seconds"])
            cold_observed = float(results["cache"]["cold_latency_seconds"])
            cold_delta = (cold_observed - cold_reference) / cold_reference
            if cold_delta > float(config["large_regression_fraction"]):
                results.setdefault("regressions", []).append(
                    f"cache cold latency {cold_observed:.2f}s is {cold_delta:+.1%} "
                    f"vs historical {cold_reference:.2f}s"
                )

        if command in {"correctness", "full", "quant"}:
            results["correctness"] = correctness_suite(config, model, log_path, raw_path)

        if command == "prefill":
            results["prefill"] = prefill_suite(config, model, raw_path, result_dir)

        results["final_resources"] = memory_snapshot()
        results["peak_resources"] = peak_resources(raw_path)
        results["performance_valid"] = (
            results.get("correctness", {}).get("passed") is True
            if command in {"full", "quant"}
            else None
        )
        verdict = "PASS"
    except GateFailure as exc:
        failure = str(exc)
        results["failure_gate"] = failure
        results["final_resources"] = memory_snapshot()
    finally:
        results["finished_at"] = dt.datetime.now(dt.UTC).isoformat()
        results["verdict"] = verdict
        results["gates"] = {
            "harness": "PASS" if identities else "FAIL",
            "smoke": "PASS" if "smoke" in results else "NOT RUN",
            "baseline": (
                "PASS"
                if isinstance(results.get("mtp"), dict)
                and len(results["mtp"].get("modes", [])) >= 1
                else "NOT RUN"
            ),
            "cache": "PASS" if results.get("cache", {}).get("correctness") is True else "NOT RUN",
            "correctness": (
                "PASS" if results.get("correctness", {}).get("passed") is True else "NOT RUN"
            ),
        }
        if failure and "correctness" in failure.lower():
            results["gates"]["correctness"] = "FAIL"
        if not (result_dir / "hardware.json").exists():
            (result_dir / "hardware.json").write_text(
                json.dumps(
                    {"captured_at": dt.datetime.now(dt.UTC).isoformat(), **identities}, indent=2
                )
                + "\n",
                encoding="utf-8",
            )
        if not (result_dir / "config.json").exists():
            (result_dir / "config.json").write_text(
                json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
        (result_dir / "results.json").write_text(
            json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        write_summary(
            result_dir / "summary.md",
            command,
            config,
            identities,
            results,
            verdict,
            failure,
        )
    return result_dir, verdict


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("smoke", "baseline", "mtp", "cache", "correctness", "prefill", "full"):
        subparsers.add_parser(name)
    quant = subparsers.add_parser("quant")
    quant.add_argument("model", help="existing GGUF path; the harness never downloads models")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    model = args.model if args.command == "quant" else None
    result_dir, verdict = run_selected(str(args.command), model)
    print(result_dir)
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

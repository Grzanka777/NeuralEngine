#!/usr/bin/env python3
"""Run the W6.3 Qwen3.8 MTP rescue benchmark on the frozen Vulkan runtime."""

from __future__ import annotations

import datetime as dt
import json
import math
import re
import time
from pathlib import Path
from typing import Any

from w62_bare_matrix import (
    BATCH,
    CONTEXT,
    DEVICE,
    EXPECTED_RUNTIME,
    EXPECTED_VERSION,
    RESULTS_ROOT,
    RUNTIME_ROOT,
    SEED,
    SERVER_BINARY,
    TEMPERATURE,
    GateFailure,
    ManagedServer,
    append_jsonl,
    exact_prompt,
    extract_content,
    http_json,
    initial_hardware,
    json_dump,
    kernel_warnings,
    max_temperature,
    now,
    numeric_summary,
    resource_snapshot,
    run_probe,
    safety_check,
    sha256_file,
    total_gtt,
    total_gtt_used,
)

MODEL = Path("/models/gguf/qwen3.8-27b/Qwen3.8-27B-Q6_K.gguf")
MTP_MODEL = Path("/models/gguf/qwen3.8-27b/mtp/mtp-Qwen3.8-27B-Q4_0.gguf")
EXPECTED_MODEL_SHA = "7d590099e0a0fe7b8df812045faa2ae12bf4dbf3492b8eb7c7c7ab24c94d36ed"
EXPECTED_MTP_SHA = "051a1764cff8c4f3ee6ae8b00593a0364c7539c67fa50ffc58f3f96509fca38e"
TG512_RUNS = 3
TG512_EXTRA_RUNS = 2
DECODE_PROMPT = (
    "Write a continuous technical explanation of deterministic data pipelines, "
    "checkpointing, idempotency, and validation. Do not conclude early."
)
MARKERS = ("ALPHA", "BRAVO", "CHARLIE", "DELTA")
SAFE_GTT_HEADROOM = 2 * 1024**3


class W63Server(ManagedServer):
    """W6.2 server wrapper extended with frozen-build MTP options."""

    def __init__(self, mode: str, log_path: Path) -> None:
        super().__init__(MODEL, BATCH, 1024, log_path, context=CONTEXT)
        self.mode = mode
        self.command.extend(["--no-cache-prompt", "--spec-type", "none"])
        if mode != "off":
            self.command[-1] = "draft-mtp"
            self.command.extend(
                [
                    "--spec-draft-model",
                    str(MTP_MODEL),
                    "--spec-draft-device",
                    DEVICE,
                    "--spec-draft-ngl",
                    "999",
                    "--spec-draft-n-max",
                    "3" if mode == "adaptive" else mode[1:],
                ]
            )
            if mode == "adaptive":
                self.command.append("--spec-draft-adaptive")

    def __enter__(self) -> W63Server:
        super().__enter__()
        text = self._log_since_start()
        matches = re.findall(r"offloaded\s+(\d+)/(\d+)\s+layers to GPU", text, re.I)
        required = 2 if self.mode != "off" else 1
        if len(matches) < required:
            self._stop()
            raise GateFailure(
                f"{self.mode}: expected {required} full GPU offload confirmations, got {matches}"
            )
        if any(int(a) != int(b) for a, b in matches[-required:]):
            self._stop()
            raise GateFailure(f"{self.mode}: CPU fallback in model offload: {matches[-required:]}")
        return self


def completion(server: W63Server, body: dict[str, Any], timeout: float = 1800) -> dict[str, Any]:
    started = time.monotonic()
    status, response = http_json(server.base_url + "/completion", body, timeout=timeout)
    wall = time.monotonic() - started
    if status != 200 or "error" in response:
        raise GateFailure(f"completion failed: HTTP {status}: {response}")
    timings = response.get("timings")
    if not isinstance(timings, dict):
        raise GateFailure(f"completion timings missing: {response}")
    response["_wall_latency_seconds"] = wall
    response["_content"] = extract_content(response)
    return response


def chat(server: W63Server, prompt: str, max_tokens: int = 16) -> tuple[dict[str, Any], str]:
    body = {
        "messages": [
            {
                "role": "system",
                "content": (
                    "Follow the current instruction exactly. Return only the requested final "
                    "answer. Never repeat content from an earlier request."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": TEMPERATURE,
        "seed": SEED,
        "max_tokens": max_tokens,
        "stream": False,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    started = time.monotonic()
    status, response = http_json(server.base_url + "/v1/chat/completions", body, timeout=1800)
    response["_wall_latency_seconds"] = time.monotonic() - started
    if status != 200 or "error" in response:
        raise GateFailure(f"chat completion failed: HTTP {status}: {response}")
    return response, extract_content(response)


def extract_metrics(response: dict[str, Any], expected: int | None = None) -> dict[str, Any]:
    timings = response.get("timings")
    if not isinstance(timings, dict):
        raise GateFailure(f"missing timings: {response}")
    predicted_n = timings.get("predicted_n")
    tps = timings.get("predicted_per_second")
    if not isinstance(predicted_n, int) or not isinstance(tps, (int, float)):
        raise GateFailure(f"invalid generation timing counters: {timings}")
    if expected is not None and predicted_n != expected:
        raise GateFailure(f"generation token mismatch: expected {expected}, got {predicted_n}")
    if not math.isfinite(float(tps)) or float(tps) <= 0:
        raise GateFailure(f"invalid generation rate: {tps}")
    drafted = int(timings.get("draft_n", 0))
    accepted = int(timings.get("draft_n_accepted", 0))
    if drafted < accepted or accepted < 0:
        raise GateFailure(f"invalid speculative counters: {timings}")
    return {
        "prompt_n": int(timings.get("prompt_n", 0)),
        "prompt_tps": float(timings.get("prompt_per_second", 0.0)),
        "predicted_n": predicted_n,
        "tg_tps": float(tps),
        "draft_n": drafted,
        "draft_n_accepted": accepted,
        "acceptance_ratio": accepted / drafted if drafted else None,
        "wall_latency_seconds": float(response["_wall_latency_seconds"]),
    }


def check_resources(snapshot: dict[str, Any], baseline: dict[str, Any]) -> None:
    safety_check(snapshot, baseline)
    gtt_total = total_gtt(snapshot)
    gtt_used = total_gtt_used(snapshot)
    if gtt_total is not None and gtt_total - gtt_used < SAFE_GTT_HEADROOM:
        raise GateFailure(
            f"unsafe GTT headroom: {gtt_total - gtt_used} bytes (minimum {SAFE_GTT_HEADROOM})"
        )


def raw_record(
    raw_path: Path,
    *,
    suite: str,
    mode: str,
    run: int,
    phase: str,
    request: dict[str, Any],
    response: dict[str, Any],
    resources: dict[str, Any],
    passed: bool = True,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metrics = extract_metrics(response)
    record = {
        "captured_at": now(),
        "suite": suite,
        "mode": mode,
        "run": run,
        "phase": phase,
        "model": str(MODEL),
        "model_sha256": EXPECTED_MODEL_SHA,
        "mtp_model": str(MTP_MODEL) if mode != "off" else None,
        "mtp_sha256": EXPECTED_MTP_SHA if mode != "off" else None,
        "request": request,
        "response": response,
        "metrics": metrics,
        "resources": resources,
        "passed": passed,
    }
    if extra:
        record.update(extra)
    append_jsonl(raw_path, record)
    return record


def stats(records: list[dict[str, Any]], field: str) -> dict[str, float]:
    return numeric_summary([float(record["metrics"][field]) for record in records])


def run_decode(
    server: W63Server,
    mode: str,
    tokens: int,
    raw_path: Path,
    baseline: dict[str, Any],
) -> dict[str, Any]:
    target_runs = TG512_RUNS if tokens == 512 else 1
    warmups = 1 if tokens == 512 else 0
    records: list[dict[str, Any]] = []
    for index in range(warmups + target_runs):
        phase = "warmup" if index < warmups else "measured"
        body = {
            "prompt": DECODE_PROMPT,
            "n_predict": tokens,
            "temperature": TEMPERATURE,
            "seed": SEED,
            "ignore_eos": True,
            "stream": False,
            "cache_prompt": False,
        }
        response = completion(server, body)
        extract_metrics(response, tokens)
        if not response.get("_content"):
            raise GateFailure(f"{mode} TG{tokens}: empty/corrupt output")
        resources = resource_snapshot()
        check_resources(resources, baseline)
        server.assert_healthy()
        record = raw_record(
            raw_path,
            suite=f"TG{tokens}",
            mode=mode,
            run=index if phase == "warmup" else index - warmups,
            phase=phase,
            request=body,
            response=response,
            resources=resources,
        )
        records.append(record)
    measured = [record for record in records if record["phase"] == "measured"]
    if tokens == 512:
        initial = stats(measured, "tg_tps")
        coefficient = initial["standard_deviation"] / initial["mean"]
        if coefficient > 0.10:
            for extra_index in range(TG512_EXTRA_RUNS):
                body = {
                    "prompt": DECODE_PROMPT,
                    "n_predict": tokens,
                    "temperature": TEMPERATURE,
                    "seed": SEED,
                    "ignore_eos": True,
                    "stream": False,
                    "cache_prompt": False,
                }
                response = completion(server, body)
                extract_metrics(response, tokens)
                resources = resource_snapshot()
                check_resources(resources, baseline)
                record = raw_record(
                    raw_path,
                    suite="TG512",
                    mode=mode,
                    run=TG512_RUNS + extra_index,
                    phase="measured",
                    request=body,
                    response=response,
                    resources=resources,
                )
                records.append(record)
                measured.append(record)
    drafted = sum(int(record["metrics"]["draft_n"]) for record in measured)
    accepted = sum(int(record["metrics"]["draft_n_accepted"]) for record in measured)
    return {
        "summary": stats(measured, "tg_tps"),
        "wall": stats(measured, "wall_latency_seconds"),
        "runs": len(measured),
        "warmups": warmups,
        "draft_n": drafted,
        "draft_n_accepted": accepted,
        "acceptance_ratio": accepted / drafted if drafted else None,
        "records": records,
    }


def correctness(
    server: W63Server, mode: str, raw_path: Path, baseline: dict[str, Any]
) -> dict[str, Any]:
    marker_pass = 0
    json_pass = 0
    records: list[dict[str, Any]] = []
    for index, marker in enumerate(MARKERS):
        prompt = f"Return exactly this marker and nothing else: {marker}"
        response, content = chat(server, prompt, 8)
        normalized = content.strip()
        contamination = [other for other in MARKERS if other != marker and other in normalized]
        passed = normalized == marker and not contamination
        resources = resource_snapshot()
        check_resources(resources, baseline)
        records.append(
            raw_record(
                raw_path,
                suite="correctness_marker",
                mode=mode,
                run=index,
                phase="measured",
                request={"prompt": prompt},
                response=response,
                resources=resources,
                passed=passed,
                extra={
                    "expected": marker,
                    "content": content,
                    "contamination": contamination,
                },
            )
        )
        if not passed:
            raise GateFailure(f"{mode}: correctness/isolation failed for {marker}: {content!r}")
        marker_pass += 1

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
    for index in range(10):
        expected = {"id": index, "marker": f"JSON-{index}", "ok": True}
        body = {
            "messages": [
                {"role": "system", "content": "Return only the requested JSON object."},
                {
                    "role": "user",
                    "content": (f"Return JSON with id {index}, marker JSON-{index}, and ok true."),
                },
            ],
            "temperature": TEMPERATURE,
            "seed": SEED,
            "max_tokens": 64,
            "stream": False,
            "chat_template_kwargs": {"enable_thinking": False},
            "response_format": {"type": "json_object", "schema": schema},
        }
        started = time.monotonic()
        status, response = http_json(server.base_url + "/v1/chat/completions", body, timeout=1800)
        response["_wall_latency_seconds"] = time.monotonic() - started
        if status != 200 or "error" in response:
            raise GateFailure(f"{mode}: JSON request failed: {response}")
        content = extract_content(response)
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise GateFailure(f"{mode}: malformed JSON response {index}: {content!r}") from exc
        passed = parsed == expected
        resources = resource_snapshot()
        check_resources(resources, baseline)
        records.append(
            raw_record(
                raw_path,
                suite="correctness_json",
                mode=mode,
                run=index,
                phase="measured",
                request=body,
                response=response,
                resources=resources,
                passed=passed,
                extra={"expected": expected, "parsed": parsed, "content": content},
            )
        )
        if not passed:
            raise GateFailure(f"{mode}: JSON schema/content failed {index}: {content!r}")
        json_pass += 1
    return {
        "markers": f"{marker_pass}/{len(MARKERS)}",
        "json": f"{json_pass}/10",
        "verdict": "PASS",
        "records": records,
    }


def peak(records: list[dict[str, Any]]) -> dict[str, Any]:
    snapshots = [record["resources"] for record in records]
    gtt_used = max((total_gtt_used(item) for item in snapshots), default=0)
    gtt_totals = [total_gtt(item) for item in snapshots]
    gtt_total_value = next((value for value in gtt_totals if value is not None), None)
    return {
        "gtt_used_bytes": gtt_used,
        "gtt_total_bytes": gtt_total_value,
        "gtt_headroom_bytes": (gtt_total_value - gtt_used if gtt_total_value is not None else None),
        "ram_used_bytes": max(
            (int(item.get("ram_used_bytes") or 0) for item in snapshots), default=0
        ),
        "zram_used_bytes": max(
            (int(item.get("zram_used_bytes") or 0) for item in snapshots), default=0
        ),
        "temperature_celsius": max(
            (max_temperature(item) or 0.0 for item in snapshots), default=0.0
        ),
        "fan_rpm": max((int(item.get("fan_rpm") or 0) for item in snapshots), default=0),
    }


def run_mode(
    mode: str, raw_path: Path, server_log: Path, baseline: dict[str, Any]
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    with W63Server(mode, server_log) as server:
        load = resource_snapshot()
        check_resources(load, baseline)
        load_record = {
            "captured_at": now(),
            "suite": "memory_load_gate",
            "mode": mode,
            "phase": "measured",
            "model": str(MODEL),
            "mtp_model": str(MTP_MODEL) if mode != "off" else None,
            "resources": load,
            "passed": True,
        }
        append_jsonl(raw_path, load_record)
        tg512 = run_decode(server, mode, 512, raw_path, baseline)
        tg4096 = run_decode(server, mode, 4096, raw_path, baseline)
        correct = correctness(server, mode, raw_path, baseline)
        records.extend(tg512.pop("records"))
        records.extend(tg4096.pop("records"))
        records.extend(correct.pop("records"))
        server.assert_healthy()
    records.append(load_record)
    return {
        "mode": mode,
        "draft_n_max": None if mode == "off" else (3 if mode == "adaptive" else int(mode[1:])),
        "adaptive": mode == "adaptive",
        "tg512": tg512,
        "tg4096": tg4096,
        "correctness": correct,
        "peak": peak(records),
        "verdict": "PASS",
    }


def long_context(
    mode: str, raw_path: Path, server_log: Path, baseline: dict[str, Any]
) -> dict[str, Any]:
    with W63Server(mode, server_log) as server:
        padding, padding_n = exact_prompt(server, 32000, f"W6.3-{mode}-LONG")
        instruction = (
            "\nCurrent instruction: begin with LONGCTX_OK, then provide a continuous "
            "technical explanation of checkpoint recovery. Do not conclude early."
        )
        prompt = padding + instruction
        prompt_n = len(
            http_json(
                server.base_url + "/tokenize",
                {"content": prompt, "add_special": False},
                timeout=180,
            )[1]["tokens"]
        )
        if prompt_n >= CONTEXT - 128:
            raise GateFailure(f"long-context prompt leaves insufficient decode space: {prompt_n}")
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
        metrics = extract_metrics(response, 128)
        content = str(response.get("_content", ""))
        passed = content.lstrip().startswith("LONGCTX_OK")
        resources = resource_snapshot()
        check_resources(resources, baseline)
        record = raw_record(
            raw_path,
            suite="long_context",
            mode=mode,
            run=0,
            phase="measured",
            request={**body, "prompt": f"<retained in raw; {prompt_n} tokens>"},
            response=response,
            resources=resources,
            passed=passed,
            extra={"prompt_size": prompt_n, "padding_tokens": padding_n},
        )
        if not passed:
            raise GateFailure(f"{mode}: long-context marker correctness failed: {content[:160]!r}")
    return {
        "mode": mode,
        "prompt_size": prompt_n,
        "pp_tps": metrics["prompt_tps"],
        "tg_tps": metrics["tg_tps"],
        "draft_n": metrics["draft_n"],
        "draft_n_accepted": metrics["draft_n_accepted"],
        "acceptance_ratio": metrics["acceptance_ratio"],
        "resources": resources,
        "correctness": "PASS",
        "verdict": "PASS",
        "record": record,
    }


def gate() -> dict[str, Any]:
    runtime = run_probe(["git", "-C", str(RUNTIME_ROOT), "rev-parse", "HEAD"])
    if runtime.get("exit_status") != 0 or runtime.get("stdout") != EXPECTED_RUNTIME:
        raise GateFailure(f"runtime commit mismatch: {runtime}")
    version = run_probe([str(SERVER_BINARY), "--version"])
    version_text = f"{version.get('stdout', '')}\n{version.get('stderr', '')}"
    if version.get("exit_status") != 0 or EXPECTED_VERSION not in version_text:
        raise GateFailure(f"runtime version mismatch: {version}")
    devices = run_probe([str(RUNTIME_ROOT / "build-vulkan/bin/llama-cli"), "--list-devices"])
    device_text = f"{devices.get('stdout', '')}\n{devices.get('stderr', '')}"
    if (
        devices.get("exit_status") != 0
        or DEVICE not in device_text
        or "RADV STRIX_HALO" not in device_text
    ):
        raise GateFailure(f"required Vulkan device missing: {devices}")
    if not MODEL.exists() or sha256_file(MODEL) != EXPECTED_MODEL_SHA:
        raise GateFailure("Qwen3.8 model SHA mismatch")
    if not MTP_MODEL.exists() or sha256_file(MTP_MODEL) != EXPECTED_MTP_SHA:
        raise GateFailure("Qwen3.8 MTP artifact missing or SHA mismatch")
    help_probe = run_probe([str(SERVER_BINARY), "--help"], timeout=120)
    help_text = f"{help_probe.get('stdout', '')}\n{help_probe.get('stderr', '')}"
    required_flags = (
        "draft-mtp",
        "--spec-draft-model",
        "--spec-draft-device",
        "--spec-draft-ngl",
        "--spec-draft-n-max",
        "--spec-draft-adaptive",
    )
    missing = [flag for flag in required_flags if flag not in help_text]
    if help_probe.get("exit_status") != 0 or missing:
        raise GateFailure(f"required local MTP support missing: {missing}")
    return {"runtime": runtime, "version": version, "devices": devices, "help": help_probe}


def read_raw(raw_path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in raw_path.read_text(encoding="utf-8").splitlines()]


def gib(value: int | float | None) -> str:
    return "n/a" if value is None else f"{float(value) / 1024**3:.2f} GiB"


def metric_text(point: dict[str, Any] | None) -> str:
    if not point:
        return "NOT RUN"
    value = point["summary"]
    return (
        f"{value['median']:.2f} t/s (mean {value['mean']:.2f}, "
        f"sd {value['standard_deviation']:.2f}, min {value['min']:.2f}, "
        f"max {value['max']:.2f}; n={point['runs']})"
    )


def acceptance_text(point: dict[str, Any] | None) -> str:
    if not point or point.get("acceptance_ratio") is None:
        return "n/a"
    return (
        f"{point['acceptance_ratio'] * 100:.2f}% ({point['draft_n_accepted']}/{point['draft_n']})"
    )


def summary_markdown(state: dict[str, Any]) -> str:
    modes = state.get("modes", {})
    hardware = state.get("hardware_before", {})
    resource = hardware.get("resource", {})
    gate_data = state.get("gate", {})
    version = (
        gate_data.get("version", {}).get("stdout")
        or gate_data.get("version", {}).get("stderr")
        or EXPECTED_VERSION
    )
    power = resource.get("power_profile", {}).get("stdout", "unknown")
    tdp = resource.get("z13ctl_tdp", {}).get("stdout", "unknown")

    def block(mode: str, label: str) -> str:
        result = modes.get(mode)
        peak_data = result.get("peak", {}) if result else {}
        correctness_value = (
            result.get("correctness", {}).get("verdict", "NOT RUN") if result else "NOT RUN"
        )
        return "\n".join(
            [
                label,
                f"TG512: {metric_text(result.get('tg512') if result else None)}",
                f"TG4096: {metric_text(result.get('tg4096') if result else None)}",
                *(
                    [f"Acceptance: {acceptance_text(result.get('tg512') if result else None)}"]
                    if mode != "off"
                    else []
                ),
                f"Peak GTT: {gib(peak_data.get('gtt_used_bytes'))}",
                f"Correctness: {correctness_value}",
                f"Verdict: {result.get('verdict', 'NOT RUN') if result else 'NOT RUN'}",
            ]
        )

    winner = state.get("winner")
    long_data = state.get("long_context")
    off = modes.get("off")
    selected = modes.get(winner) if winner else None
    gain512 = "n/a"
    gain4096 = "n/a"
    if off and selected:
        off512 = float(off["tg512"]["summary"]["median"])
        win512 = float(selected["tg512"]["summary"]["median"])
        off4096 = float(off["tg4096"]["summary"]["median"])
        win4096 = float(selected["tg4096"]["summary"]["median"])
        gain512 = f"{win512 - off512:+.2f} t/s ({win512 / off512 - 1:+.2%})"
        gain4096 = f"{win4096 - off4096:+.2f} t/s ({win4096 / off4096 - 1:+.2%})"
    anomaly_text = "<none>" if not state.get("anomalies") else "; ".join(state["anomalies"])
    long_mode = long_data.get("mode", "NOT RUN") if long_data else "NOT RUN"
    mtp_sha_status = "PASS" if state.get("mtp_sha256") == EXPECTED_MTP_SHA else "FAIL"
    mtp_sha = state.get("mtp_sha256", "unknown")
    next_step = (
        "freeze DEEP candidate and move to W6.4 CODE correctness/cache/FIM/tool-calling."
        if state.get("verdict") == "PASS"
        else "investigate alternate Qwen3.8 runtime/quant path before production."
    )
    return f"""W6.3 — QWEN3.8 DEEP PROFILE RESCUE

SYSTEM
Runtime: {version}
Commit: {gate_data.get("runtime", {}).get("stdout", EXPECTED_RUNTIME)}
Vulkan: Vulkan0 / Mesa RADV / RADV STRIX_HALO
Power profile: {power}
TDP: {tdp}
GTT total: {gib(total_gtt(resource))}

MODEL
Qwen3.8-27B
Quant: Q6_K
SHA: {"PASS" if state.get("model_sha256") == EXPECTED_MODEL_SHA else "FAIL"}
MTP artifact: {MTP_MODEL}
MTP SHA: {mtp_sha_status} ({mtp_sha})

{block("off", "OFF")}

{block("n2", "N2")}

{block("n3", "N3")}

ADAPTIVE
Tested: {"YES" if "adaptive" in modes else "NO"}
TG512: {metric_text(modes.get("adaptive", {}).get("tg512"))}
TG4096: {metric_text(modes.get("adaptive", {}).get("tg4096"))}
Acceptance: {acceptance_text(modes.get("adaptive", {}).get("tg512"))}
Peak GTT: {gib(modes.get("adaptive", {}).get("peak", {}).get("gtt_used_bytes"))}
Correctness: {modes.get("adaptive", {}).get("correctness", {}).get("verdict", "NOT RUN")}
Verdict: {modes.get("adaptive", {}).get("verdict", "NOT RUN")}

LONG CONTEXT
Configuration: {long_mode}
Prompt size: {long_data.get("prompt_size", "NOT RUN") if long_data else "NOT RUN"}
PP: {f"{long_data['pp_tps']:.2f} t/s" if long_data else "NOT RUN"}
TG: {f"{long_data['tg_tps']:.2f} t/s" if long_data else "NOT RUN"}
Acceptance: {acceptance_text(long_data)}
GTT: {gib(total_gtt_used(long_data["resources"])) if long_data else "NOT RUN"}
Correctness: {long_data.get("correctness", "NOT RUN") if long_data else "NOT RUN"}
Verdict: {long_data.get("verdict", "NOT RUN") if long_data else "NOT RUN"}

FINAL
W6.3: {state.get("verdict", "FAIL")}

WINNER:
{winner or "none"}

GAIN VS W6.2 BARE:
TG512: {gain512}
TG4096: {gain4096}

DEEP CLASSIFICATION:
{state.get("classification", "FAIL")}

ANOMALIES:
{anomaly_text}

NEXT:
{next_step}
"""


def choose_winner(modes: dict[str, dict[str, Any]]) -> tuple[str | None, str]:
    off = modes["off"]
    off512 = float(off["tg512"]["summary"]["median"])
    off4096 = float(off["tg4096"]["summary"]["median"])
    candidates: list[tuple[float, str]] = []
    for name in ("n2", "n3", "adaptive"):
        result = modes[name]
        candidate512 = float(result["tg512"]["summary"]["median"])
        candidate4096 = float(result["tg4096"]["summary"]["median"])
        noise = max(
            float(off["tg512"]["summary"]["standard_deviation"]),
            float(result["tg512"]["summary"]["standard_deviation"]),
        )
        material = candidate512 - off512 > max(noise, off512 * 0.05)
        sustained_ok = candidate4096 >= off4096 * 0.95
        if material and sustained_ok and result["correctness"]["verdict"] == "PASS":
            candidates.append((candidate512, name))
        elif abs(candidate512 - off512) <= noise:
            result["verdict"] = "NO SIGNIFICANT DIFFERENCE"
        elif not sustained_ok:
            result["verdict"] = "REJECT: TG4096 regression"
        else:
            result["verdict"] = "REJECT: no material TG512 gain"
    if not candidates:
        return None, "FAIL"
    return max(candidates)[1], "PASS"


def classify(tps: float | None) -> str:
    if tps is None or tps < 10:
        return "FAIL"
    if tps < 15:
        return "BARE-LOW"
    if tps < 20:
        return "USABLE"
    if tps < 25:
        return "GOOD"
    return "STRONG"


def main() -> int:
    timestamp = dt.datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    result_dir = RESULTS_ROOT / f"{timestamp}-w6-3-qwen3-8-deep-rescue"
    result_dir.mkdir(parents=True)
    raw_path = result_dir / "raw.jsonl"
    server_log = result_dir / "server.log"
    benchmark_log = result_dir / "benchmark.log"
    raw_path.touch()
    server_log.touch()
    benchmark_log.touch()
    state: dict[str, Any] = {
        "suite": "W6.3",
        "run_id": result_dir.name,
        "result_dir": str(result_dir),
        "started_at": now(),
        "conditions": {
            "device": DEVICE,
            "ngl": 999,
            "context": CONTEXT,
            "batch": BATCH,
            "ubatch": 1024,
            "flash_attention": "auto",
            "prompt_cache": "off",
            "temperature": TEMPERATURE,
            "seed": SEED,
            "single_stream": True,
            "modes": ["off", "n2", "n3", "adaptive"],
            "tg512": {"warmups": 1, "measured": 3, "variance_extra": 2},
            "tg4096": {"warmups": 0, "measured": 1},
            "safe_gtt_headroom_bytes": SAFE_GTT_HEADROOM,
        },
        "modes": {},
        "anomalies": [],
        "verdict": "FAIL",
    }

    def log(event: str, payload: dict[str, Any] | None = None) -> None:
        with benchmark_log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"at": now(), "event": event, "payload": payload or {}}) + "\n")

    try:
        state["gate"] = gate()
        state["model_sha256"] = sha256_file(MODEL)
        state["mtp_sha256"] = sha256_file(MTP_MODEL)
        state["mtp_provenance"] = "ggml-org/Qwen3.8-27B-GGUF: mtp-Qwen3.8-27B-Q4_0.gguf"
        state["hardware_before"] = initial_hardware()
        json_dump(result_dir / "config.json", state)
        baseline = state["hardware_before"]["resource"]
        for mode in ("off", "n2", "n3", "adaptive"):
            log("mode_start", {"mode": mode})
            state["modes"][mode] = run_mode(mode, raw_path, server_log, baseline)
            log("mode_complete", {"mode": mode})
            json_dump(result_dir / "results.json", state)
        winner, verdict = choose_winner(state["modes"])
        state["winner"] = winner
        if winner is not None:
            log("long_context_start", {"mode": winner})
            state["long_context"] = long_context(winner, raw_path, server_log, baseline)
            log("long_context_complete", {"mode": winner})
        state["verdict"] = verdict
        selected_tps = (
            float(state["modes"][winner]["tg512"]["summary"]["median"]) if winner else None
        )
        state["classification"] = classify(selected_tps)
        state["hardware_after"] = {
            "captured_at": now(),
            "resource": resource_snapshot(),
            "kernel_warnings": kernel_warnings(),
        }
        warnings = state["hardware_after"]["kernel_warnings"]["matched"]
        if warnings:
            state["anomalies"].extend(warnings)
            state["verdict"] = "FAIL"
    except (GateFailure, OSError, ValueError, json.JSONDecodeError) as exc:
        state["failure"] = str(exc)
        state["anomalies"].append(str(exc))
        state["verdict"] = "FAIL"
        state.setdefault("winner", None)
        state.setdefault("classification", "FAIL")
        state["hardware_after"] = {
            "captured_at": now(),
            "resource": resource_snapshot(),
            "kernel_warnings": kernel_warnings(),
        }
    finally:
        state["finished_at"] = now()
        state["raw_records"] = len(read_raw(raw_path))
        json_dump(
            result_dir / "hardware.json",
            {
                "before": state.get("hardware_before"),
                "after": state.get("hardware_after"),
                "gate": state.get("gate"),
            },
        )
        json_dump(result_dir / "results.json", state)
        (result_dir / "summary.md").write_text(summary_markdown(state), encoding="utf-8")
    print(result_dir)
    return 0 if state["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

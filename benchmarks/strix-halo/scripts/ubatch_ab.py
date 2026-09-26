#!/usr/bin/env python3
"""Reproducible single-variable A/B benchmark for the GENERAL profile.

Compares llama-server ``n_ubatch`` 1024 (baseline) against 2048 (challenger) for
Qwen3.6-35B-A3B under the frozen production flags. Everything else -- model,
quantization, context size, ``n_batch``, GPU layers, device, Flash Attention,
KV cache type, and MTP depth -- is held identical, so ``-ub`` is the only
variable that differs between the two arms.

This driver is deliberately isolated from production:

* It never edits ``configs/default.json``, ``scripts/llm``, the installed
  ``~/.local/bin/llm``, or any systemd unit.
* It launches its own ``llama-server`` child on a dedicated port and stops only
  that child (through the harness ``ManagedServer``); it never uses pkill.
* It fails closed on runtime/model/draft hash mismatch, port collision, OOM,
  GPU reset/device loss, CPU fallback, or a decode token-count mismatch.

Evidence is written to a new ``results/<stamp>-<model>-ubatch-ab/`` directory
containing ``summary.md``, ``results.json``, ``raw.jsonl``, ``server.log``,
``hardware.json``, ``config.json``, and the per-arm llama-bench stderr logs.

Usage::

    uv run python benchmarks/strix-halo/scripts/ubatch_ab.py --dry-run
    uv run python benchmarks/strix-halo/scripts/ubatch_ab.py
    uv run python benchmarks/strix-halo/scripts/ubatch_ab.py --blocks 2 \
        --suites tg,prefill,cache --context 65536

The ``-fa on`` flag is part of the frozen production GENERAL argv but is absent
from the bundled ``harness.server_command``; this driver installs a faithful
command builder so the recorded commands match production exactly.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

HARNESS_DIR = Path(__file__).resolve().parent
if str(HARNESS_DIR) not in sys.path:
    sys.path.insert(0, str(HARNESS_DIR))

import harness  # noqa: E402

ARMS: tuple[tuple[str, int], ...] = (("baseline", 1024), ("challenger", 2048))
DEFAULT_PORT = 18089
DEFAULT_CONTEXT = 65536
SUITE_NAMES = ("tg", "prefill", "cache", "correctness")
MTP_N = 3
PREFILL_TIMEOUT_SECONDS = 1800


def faithful_server_command(config: dict[str, Any], model: Path, mtp_n: int) -> list[str]:
    """Return the production GENERAL argv, parameterised only by ``n_ubatch``.

    Mirrors the frozen ``scripts/llm`` GENERAL arguments: ``-fa on``, prompt
    cache, MTP draft with ``n-max 3``, metrics, and the arm's ``n_ubatch``.
    """

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
        str(int(config["agent_ubatch"])),
        "-np",
        "1",
        "-fa",
        "on",
        "--cache-prompt",
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
    command.extend(
        [
            "--metrics",
            "--host",
            str(config["host"]),
            "--port",
            str(config["port"]),
        ]
    )
    return command


def prefill_command(config: dict[str, Any], model: Path, ubatch: int) -> list[str]:
    """Return the llama-bench PP command for one arm; only ``-ub`` varies."""

    return [
        str(config["bench_binary"]),
        "-m",
        str(model),
        "-dev",
        str(config["device"]),
        "-ngl",
        "999",
        "-b",
        str(config["agent_batch"]),
        "-ub",
        str(int(ubatch)),
        "-fa",
        "on",
        "-p",
        ",".join(str(item) for item in config["prefill_tokens"]),
        "-n",
        "0",
        "-r",
        str(config["measured_runs"]),
        "-o",
        "json",
    ]


def prepare_arm_config(
    base: dict[str, Any], ubatch: int, port: int, context: int
) -> dict[str, Any]:
    """Return an in-memory config copy overriding only the audited knobs."""

    config = dict(base)
    config["agent_ubatch"] = ubatch
    config["prefill_ubatch"] = ubatch
    config["port"] = port
    config["context"] = context
    return config


def parse_suites(value: str) -> tuple[str, ...]:
    requested = tuple(item.strip() for item in value.split(",") if item.strip())
    unknown = [item for item in requested if item not in SUITE_NAMES]
    if unknown:
        raise harness.GateFailure(f"unknown suites: {unknown}; allowed: {list(SUITE_NAMES)}")
    if "tg" not in requested:
        requested = ("tg", *requested)
    return requested


def install_command_builder() -> Callable[[], None]:
    """Temporarily install the production-faithful command builder."""

    original = harness.server_command
    harness.server_command = faithful_server_command

    def restore() -> None:
        harness.server_command = original

    return restore


def compare_metric(name: str, left: Sequence[float], right: Sequence[float]) -> dict[str, Any]:
    """Compare two samples with the harness noise rule (median vs larger SD)."""

    left_stats = harness.numeric_summary(left)
    right_stats = harness.numeric_summary(right)
    difference = float(right_stats["median"]) - float(left_stats["median"])
    percentage = difference / float(left_stats["median"]) * 100 if left_stats["median"] else 0.0
    noise = max(
        float(left_stats["standard_deviation"]),
        float(right_stats["standard_deviation"]),
    )
    return {
        "metric": name,
        "left_median": left_stats["median"],
        "right_median": right_stats["median"],
        "left_standard_deviation": left_stats["standard_deviation"],
        "right_standard_deviation": right_stats["standard_deviation"],
        "absolute": difference,
        "percentage": percentage,
        "observed_noise": noise,
        "verdict": "NO SIGNIFICANT DIFFERENCE"
        if abs(difference) <= noise
        else "DIFFERENCE OBSERVED",
    }


def parse_prefill_payload(payload: Any) -> dict[int, dict[str, float]]:
    """Extract ``n_prompt -> {avg_ts, stddev_ts}`` from llama-bench JSON."""

    if not isinstance(payload, list):
        raise harness.GateFailure(f"unexpected llama-bench payload: {type(payload).__name__}")
    parsed: dict[int, dict[str, float]] = {}
    for entry in payload:
        if not isinstance(entry, dict) or int(entry.get("n_gen", -1)) != 0:
            continue
        n_prompt = entry.get("n_prompt")
        avg_ts = entry.get("avg_ts")
        if not isinstance(n_prompt, int) or not isinstance(avg_ts, (int, float)):
            continue
        stddev = entry.get("stddev_ts")
        parsed[n_prompt] = {
            "avg_ts": float(avg_ts),
            "stddev_ts": float(stddev) if isinstance(stddev, (int, float)) else 0.0,
        }
    if not parsed:
        raise harness.GateFailure("llama-bench produced no prefill (n_gen=0) results")
    return parsed


def run_prefill_arm(
    config: dict[str, Any],
    model: Path,
    ubatch: int,
    raw_path: Path,
    result_dir: Path,
) -> dict[str, Any]:
    command = prefill_command(config, model, ubatch)
    completed = subprocess.run(
        command,
        capture_output=True,
        check=False,
        text=True,
        timeout=PREFILL_TIMEOUT_SECONDS,
    )
    (result_dir / f"prefill-ub{ubatch}.stderr.log").write_text(completed.stderr, encoding="utf-8")
    if completed.returncode != 0:
        raise harness.GateFailure(f"llama-bench failed with exit {completed.returncode}")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise harness.GateFailure(f"invalid llama-bench JSON: {exc}") from exc
    harness.append_raw(
        raw_path,
        {"suite": "prefill", "ubatch": ubatch, "command": command, "payload": payload},
    )
    return {"command": command, "results": parse_prefill_payload(payload)}


def run_arm(
    config: dict[str, Any],
    model: Path,
    ubatch: int,
    label: str,
    block: int,
    raw_path: Path,
    log_path: Path,
    result_dir: Path,
    suites: Sequence[str],
    warmups: int,
    measured: int,
    tg_tokens: int,
) -> dict[str, Any]:
    """Run every requested suite once for one arm; returns a per-run record."""

    run: dict[str, Any] = {
        "label": label,
        "ubatch": ubatch,
        "block": block,
        "command": faithful_server_command(config, model, MTP_N),
        "captured_at": dt.datetime.now(dt.UTC).isoformat(),
    }
    run["decode"] = harness.benchmark_decode(
        config,
        model,
        log_path,
        raw_path,
        MTP_N,
        "ubatch-ab",
        tg_tokens,
        warmups,
        measured,
    )
    if "prefill" in suites:
        run["prefill"] = run_prefill_arm(config, model, ubatch, raw_path, result_dir)
    if "cache" in suites:
        run["cache"] = harness.cache_suite(config, model, log_path, raw_path)
    if "correctness" in suites:
        run["correctness"] = harness.correctness_suite(config, model, log_path, raw_path)
    run["final_resources"] = harness.memory_snapshot()
    run["peak_resources"] = harness.peak_resources(raw_path)
    return run


def _peak(runs: Sequence[dict[str, Any]], key: str) -> int | None:
    values: list[int] = []
    for run in runs:
        peak = run.get("peak_resources", {})
        if isinstance(peak, dict) and isinstance(peak.get(key), int):
            values.append(int(peak[key]))
    return max(values) if values else None


def _peak_gtt(runs: Sequence[dict[str, Any]]) -> int | None:
    values: list[int] = []
    for run in runs:
        peak = run.get("peak_resources", {})
        entries = peak.get("gtt", []) if isinstance(peak, dict) else []
        for entry in entries:
            if isinstance(entry, dict) and isinstance(entry.get("used_bytes"), int):
                values.append(int(entry["used_bytes"]))
    return max(values) if values else None


def _tg_values(runs: Sequence[dict[str, Any]]) -> list[float]:
    values: list[float] = []
    for run in runs:
        for record in run["decode"]["measured"]:
            values.append(float(record["metrics"]["tg_tps"]))
    return values


def aggregate(runs: Sequence[dict[str, Any]]) -> dict[str, Any]:
    latency_values: list[float] = []
    draft_n = 0
    draft_accepted = 0
    contents: list[str] = []
    for run in runs:
        for record in run["decode"]["measured"]:
            metrics = record["metrics"]
            latency_values.append(float(metrics["latency_seconds"]))
            draft_n += int(metrics["draft_n"])
            draft_accepted += int(metrics["draft_n_accepted"])
            contents.append(str(record["content"]))
    prefill_samples: dict[int, list[float]] = {}
    for run in runs:
        payload = run.get("prefill")
        if not payload:
            continue
        for n_prompt, stats in payload["results"].items():
            prefill_samples.setdefault(int(n_prompt), []).append(float(stats["avg_ts"]))
    prefill = {
        str(n_prompt): harness.numeric_summary(prefill_samples[n_prompt])
        for n_prompt in sorted(prefill_samples)
    }
    cache_runs = [run["cache"] for run in runs if run.get("cache")]
    return {
        "ubatch": int(runs[0]["ubatch"]),
        "command": runs[0]["command"],
        "run_count": len(runs),
        "tg_tps": harness.numeric_summary(_tg_values(runs)),
        "latency_seconds": harness.numeric_summary(latency_values),
        "draft_n": draft_n,
        "draft_n_accepted": draft_accepted,
        "acceptance_ratio": (draft_accepted / draft_n) if draft_n else None,
        "prefill": prefill,
        "prefill_samples": {
            str(n_prompt): prefill_samples[n_prompt] for n_prompt in sorted(prefill_samples)
        },
        "cache": cache_runs[-1] if cache_runs else None,
        "ram_used_bytes": _peak(runs, "ram_used_bytes"),
        "gtt_used_bytes": _peak_gtt(runs),
        "contents": contents,
        "correctness": next(
            (run["correctness"] for run in runs if run.get("correctness")),
            None,
        ),
    }


def cross_arm_output_match(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """Report greedy-decode output equality between arms (not a hard gate)."""

    left_contents = left.get("contents", [])
    right_contents = right.get("contents", [])
    compared = min(len(left_contents), len(right_contents))
    matched = sum(1 for index in range(compared) if left_contents[index] == right_contents[index])
    first_divergence = next(
        (index for index in range(compared) if left_contents[index] != right_contents[index]),
        None,
    )
    return {
        "compared_runs": compared,
        "matched_runs": matched,
        "all_match": compared > 0 and matched == compared,
        "first_divergence_index": first_divergence,
    }


def format_value(value: float | None, suffix: str = "", digits: int = 2) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}{suffix}"


def build_summary(
    config: dict[str, Any],
    identities: dict[str, Any],
    results: dict[str, Any],
    verdict: str,
    failure: str | None,
) -> str:
    arms = results.get("arms", {})
    left = arms.get("ub1024", {})
    right = arms.get("ub2048", {})
    comparisons = results.get("comparisons", {})
    tg_comparison = comparisons.get("tg", {})
    winner = "n/a"
    why = "Both arms are within observed run noise."
    if tg_comparison.get("verdict") == "DIFFERENCE OBSERVED":
        better = "ub2048" if float(tg_comparison["absolute"]) > 0 else "ub1024"
        winner = better
        why = (
            f"{better} TG512 median is higher by "
            f"{abs(float(tg_comparison['absolute'])):.2f} t/s "
            f"({abs(float(tg_comparison['percentage'])):.2f}%), above the "
            f"{float(tg_comparison['observed_noise']):.2f} t/s noise floor."
        )
    correctness_entries = [arm.get("correctness") for arm in (left, right) if isinstance(arm, dict)]
    correctness_text = (
        "PASS"
        if correctness_entries
        and all(
            isinstance(entry, dict) and entry.get("passed") is True for entry in correctness_entries
        )
        else "NOT RUN (use --suites tg,prefill,cache,correctness)"
    )
    match = results.get("cross_arm_output_match", {})
    regressions = results.get("regressions", [])
    lines = [
        f"VERDICT: {verdict}",
        f"WINNER: {winner}",
        f"WHY: {why}",
        f"CORRECTNESS: {correctness_text}",
        "REGRESSIONS: "
        + ("; ".join(str(item) for item in regressions) if regressions else "none observed"),
        (
            f"CROSS-ARM GREEDY OUTPUT: {match.get('matched_runs', 0)}/"
            f"{match.get('compared_runs', 0)} measured runs identical"
            + (
                ""
                if match.get("all_match")
                else f" (first divergence at measured run {match.get('first_divergence_index')})"
            )
        ),
        "",
        (
            "| Runtime | Model | Quant | Context | Batch | Ubatch | MTP | TG512 median "
            "| TG sd | TTFT cold | PP512 | PP2048 | PP8192 | PP32768 | Accept | RAM GiB "
            "| GTT GiB |"
        ),
        (
            "| --- | --- | --- | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: "
            "| ---: | ---: | ---: | ---: | ---: | ---: |"
        ),
    ]
    model_name = Path(str(identities.get("model_path", "unknown"))).name
    quant_match = re.search(r"(Q\d[^.]*)", model_name)
    quant = quant_match.group(1) if quant_match else "unknown"
    runtime = str(identities.get("runtime_sha256", "unknown"))[:10]
    for key in ("ub1024", "ub2048"):
        arm = arms.get(key)
        if not arm:
            continue
        cache = arm.get("cache") or {}
        prefill = arm.get("prefill", {})
        lines.append(
            "| {runtime} | {model} | {quant} | {ctx} | {batch} | {ubatch} | n{MTP} "
            "| {tg} | {tgsd} | {cold} | {p512} | {p2048} | {p8192} | {p32768} "
            "| {accept} | {ram} | {gtt} |".format(
                runtime=runtime,
                model=model_name,
                quant=quant,
                ctx=config["context"],
                batch=config["agent_batch"],
                ubatch=arm["ubatch"],
                MTP=MTP_N,
                tg=format_value(float(arm["tg_tps"]["median"])),
                tgsd=format_value(float(arm["tg_tps"]["standard_deviation"])),
                cold=format_value(cache.get("cold_ttft_seconds"), " s"),
                p512=format_value(prefill.get("512", {}).get("median")),
                p2048=format_value(prefill.get("2048", {}).get("median")),
                p8192=format_value(prefill.get("8192", {}).get("median")),
                p32768=format_value(prefill.get("32768", {}).get("median")),
                accept=format_value(
                    None
                    if arm.get("acceptance_ratio") is None
                    else float(arm["acceptance_ratio"]) * 100,
                    "%",
                ),
                ram=format_value(
                    None
                    if arm.get("ram_used_bytes") is None
                    else float(arm["ram_used_bytes"]) / 1024**3
                ),
                gtt=format_value(
                    None
                    if arm.get("gtt_used_bytes") is None
                    else float(arm["gtt_used_bytes"]) / 1024**3
                ),
            )
        )
    lines.extend(
        [
            "",
            "## Comparisons (median difference vs larger observed sample SD)",
            "",
            "| Metric | ub1024 | ub2048 | delta abs | delta % | noise | result |",
            "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for comparison in comparisons.values():
        if not isinstance(comparison, dict):
            continue
        lines.append(
            (
                "| {metric} | {left} | {right} | {diff:+.3f} | {pct:+.2f} | {noise:.3f} "
                "| {verdict} |"
            ).format(
                metric=comparison["metric"],
                left=format_value(float(comparison["left_median"]), digits=3),
                right=format_value(float(comparison["right_median"]), digits=3),
                diff=float(comparison["absolute"]),
                pct=float(comparison["percentage"]),
                noise=float(comparison["observed_noise"]),
                verdict=comparison["verdict"],
            )
        )
    lines.extend(["", "## Arm commands (exact)", ""])
    for key in ("ub1024", "ub2048"):
        arm = arms.get(key)
        if arm:
            lines.append(f"- `{key}`: `{' '.join(arm['command'])}`")
    if verdict == "ABORTED":
        lines.extend(["", "ABORT: KeyboardInterrupt"])
    if failure is not None:
        lines.extend(["", f"FAILURE GATE: {failure}"])
    lines.append("")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="pin and print both arms; start nothing"
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="isolated benchmark port")
    parser.add_argument(
        "--context",
        type=int,
        default=DEFAULT_CONTEXT,
        help="context size (default: 65536; use 32768 for historical comparison)",
    )
    parser.add_argument(
        "--blocks", type=int, default=1, help="A/B blocks; odd/even blocks reverse order"
    )
    parser.add_argument(
        "--suites",
        default="tg,prefill",
        help="comma list from tg,prefill,cache,correctness (tg always included)",
    )
    parser.add_argument("--measured", type=int, default=None, help="measured decode runs per arm")
    parser.add_argument("--warmups", type=int, default=None, help="warmup decode runs per arm")
    parser.add_argument("--tg-tokens", type=int, default=None, help="tokens per decode measurement")
    parser.add_argument(
        "--model", default=None, help="GGUF path override (default: frozen GENERAL)"
    )
    return parser


def print_plan(
    base_config: dict[str, Any],
    model: Path,
    identities: dict[str, Any],
    suites: Sequence[str],
    args: argparse.Namespace,
) -> None:
    context = int(args.context)
    print("A/B PLAN - GENERAL n_ubatch 1024 (baseline) vs 2048 (challenger)")
    print("single variable: n_ubatch")
    print(f"suites: {', '.join(suites)}")
    print(f"blocks: {args.blocks} (order reverses each block)")
    print(f"context: {context}   batch: {base_config['agent_batch']}   MTP n-max: {MTP_N}")
    print(f"port: {args.port} (isolated; production 18080/18081/18082 untouched)")
    print(f"runtime commit: {identities['runtime_sha256']}")
    print(f"model: {model}")
    print(f"model sha256: {identities['model_sha256']}")
    print(f"draft sha256: {identities['draft_model_sha256']}")
    print("")
    for label, ubatch in ARMS:
        config = prepare_arm_config(base_config, ubatch, args.port, context)
        print(f"[{label} ub{ubatch}] {' '.join(faithful_server_command(config, model, MTP_N))}")
        if "prefill" in suites:
            print(f"[{label} ub{ubatch} PP] {' '.join(prefill_command(config, model, ubatch))}")
    print("")
    print("no server started (--dry-run); no production config or systemd unit modified")


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    base_config = harness.load_json(harness.DEFAULT_CONFIG)
    model = Path(args.model or str(base_config["main_model"])).resolve()
    suites = parse_suites(args.suites)
    context = int(args.context)
    warmups = int(args.warmups if args.warmups is not None else base_config["warmup_runs"])
    measured = int(args.measured if args.measured is not None else base_config["measured_runs"])
    tg_tokens = int(args.tg_tokens if args.tg_tokens is not None else base_config["tg_tokens"])

    try:
        identities = harness.validate_environment(base_config, model)
    except harness.GateFailure as exc:
        print(f"GATE FAILURE: {exc}", file=sys.stderr)
        return 1

    if args.dry_run:
        print_plan(base_config, model, identities, suites, args)
        return 0

    result_dir = harness.create_result_dir(model, "ubatch-ab")
    raw_path = result_dir / "raw.jsonl"
    log_path = result_dir / "server.log"
    raw_path.touch()
    log_path.touch()

    resolved = dict(base_config)
    resolved.update(
        {
            "context": context,
            "port": args.port,
            "warmup_runs": warmups,
            "measured_runs": measured,
            "tg_tokens": tg_tokens,
            "selected_model": str(model),
            "selected_model_sha256": identities["model_sha256"],
            "single_variable": "n_ubatch",
        }
    )
    results: dict[str, Any] = {
        "suite": "ubatch-ab",
        "started_at": dt.datetime.now(dt.UTC).isoformat(),
        "single_variable": "n_ubatch",
        "suites": list(suites),
        "blocks": args.blocks,
        "mtp_n": MTP_N,
        "port": args.port,
        "resolved_config": resolved,
        "arm_commands": {
            f"ub{ubatch}": faithful_server_command(
                prepare_arm_config(base_config, ubatch, args.port, context), model, MTP_N
            )
            for _, ubatch in ARMS
        },
        "identities": identities,
    }
    verdict = "FAIL"
    failure: str | None = None
    restore = install_command_builder()
    try:
        (result_dir / "hardware.json").write_text(
            json.dumps(harness.hardware_snapshot(base_config, identities), indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        (result_dir / "config.json").write_text(
            json.dumps(resolved, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

        runs: dict[int, list[dict[str, Any]]] = {ubatch: [] for _, ubatch in ARMS}
        for block in range(args.blocks):
            order = ARMS if block % 2 == 0 else tuple(reversed(ARMS))
            for label, ubatch in order:
                config = prepare_arm_config(base_config, ubatch, args.port, context)
                runs[ubatch].append(
                    run_arm(
                        config,
                        model,
                        ubatch,
                        label,
                        block,
                        raw_path,
                        log_path,
                        result_dir,
                        suites,
                        warmups,
                        measured,
                        tg_tokens,
                    )
                )

        arms = {f"ub{ubatch}": aggregate(runs[ubatch]) for _, ubatch in ARMS}
        left = arms["ub1024"]
        right = arms["ub2048"]
        comparisons: dict[str, Any] = {
            "tg": compare_metric("TG512 t/s", _tg_values(runs[1024]), _tg_values(runs[2048]))
        }
        shared_sizes = sorted(set(left["prefill_samples"]) & set(right["prefill_samples"]), key=int)
        for size in shared_sizes:
            comparisons[f"pp{size}"] = compare_metric(
                f"PP{size} t/s",
                left["prefill_samples"][size],
                right["prefill_samples"][size],
            )
        results["arms"] = arms
        results["comparisons"] = comparisons
        results["cross_arm_output_match"] = cross_arm_output_match(left, right)
        results["final_resources"] = harness.memory_snapshot()
        results["peak_resources"] = harness.peak_resources(raw_path)
        verdict = "PASS"
    except harness.GateFailure as exc:
        failure = str(exc)
        results["failure_gate"] = failure
        if "arms" not in results:
            results.setdefault("regressions", []).append(failure)
    except KeyboardInterrupt:
        verdict = "ABORTED"
        results["abort_reason"] = "KeyboardInterrupt"
    finally:
        restore()
        results["finished_at"] = dt.datetime.now(dt.UTC).isoformat()
        results["verdict"] = verdict
        (result_dir / "results.json").write_text(
            json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        if "arms" in results:
            (result_dir / "summary.md").write_text(
                build_summary(resolved, identities, results, verdict, failure),
                encoding="utf-8",
            )
        else:
            summary = [f"VERDICT: {verdict}"]
            if verdict == "ABORTED":
                summary.append("ABORT: KeyboardInterrupt")
            elif failure is not None:
                summary.append(f"FAILURE GATE: {failure}")
            (result_dir / "summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    print(result_dir)
    if verdict == "ABORTED":
        return 130
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

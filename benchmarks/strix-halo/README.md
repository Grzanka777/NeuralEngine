# Z13 Strix Halo LLM benchmark harness

This harness measures the frozen `halo-box/strix-llama.cpp` Vulkan runtime on
the ASUS ROG Flow Z13 2025 without changing GTT, power, TDP, fan, kernel, Mesa,
ROCm, or service configuration. It uses only Python's standard library and the
existing `llama-server`/`llama-bench` binaries.

## Commands

Run from this directory:

```fish
./bench-z13 smoke
./bench-z13 baseline
./bench-z13 mtp
./bench-z13 cache
./bench-z13 correctness
./bench-z13 prefill
./bench-z13 quant /path/to/existing-model.gguf
./bench-z13 full
```

`quant` never downloads a model. It computes and records the supplied GGUF's
SHA-256, then runs the same MTP/cache/correctness workloads. The configured main
and draft models and frozen runtime commit are checked against pinned hashes;
any mismatch fails closed.

`full` runs a small n3 smoke gate, the controlled TG512 OFF/n2/n3 matrix (one
warmup plus five measured runs per mode), prefix-cache checks, and correctness.
The separate `prefill` command uses the PREFILL profile (`b2048/ub2048`, FA auto)
for PP512, PP2048, PP8192, and PP32768. Interactive/server measurements use the
AGENT profile (`ctx32768`, `b2048/ub1024`, one slot, prompt cache enabled).
Standalone performance commands are provisional until a correctness suite passes;
`full` records `performance_valid=true` only after all correctness gates pass.

The comparison label `NO SIGNIFICANT DIFFERENCE` is deliberately conservative:
it is used when the median difference does not exceed the larger observed sample
standard deviation. It is a run-noise rule, not a claim of inferential statistical
significance.

## Safety and evidence

The harness binds only `127.0.0.1:18080`. It tests the bind before launch and
fails if the port is occupied. It tracks the exact child PID and stops only that
process; it never uses `pkill` or `killall`. Server logs must prove the configured
Vulkan device and complete GPU layer offload. OOM, GPU reset/device loss, corrupt
responses, invalid counters, hash mismatch, port collision, or marker leakage
stop the affected invocation.

Every invocation creates a new timestamped directory under `results/` with:

- `summary.md` — human verdict, winner, regressions, table, and comparisons;
- `results.json` — aggregated machine-readable measurements;
- `raw.jsonl` — every warmup/measured request and full server response;
- `server.log` — append-only output for every server instance started;
- `hardware.json` — read-only reproducibility snapshot;
- `config.json` — exact resolved run configuration and identities.

The comparison label `NO SIGNIFICANT DIFFERENCE` is conservative: it is emitted
when the median gap does not exceed the larger observed sample standard
deviation. It is an observed-noise rule, not a formal confidence claim.

Self-tests do not start a server:

```fish
uv run python -m unittest discover benchmarks/strix-halo/tests -v
uv run python -m py_compile benchmarks/strix-halo/bench-z13 benchmarks/strix-halo/scripts/harness.py
```

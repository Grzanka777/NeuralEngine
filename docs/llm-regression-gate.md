# LLM Fast Regression Gate

`llm-manifest.json` is the sole local model, role, endpoint, and runtime
configuration authority. `scripts/llm` loads its runtime profiles and owns
start, stop, switch, health, and identity behavior. Qwen and Pi settings are
generated projections; neither client owns runtime lifecycle. `Pi` is the
primary local/cloud harness, Qwen Code is optional compatibility support, and
OpenCode is parked without local routes.

## Run modes

```text
scripts/llm-regression-gate fast
scripts/llm-regression-gate fast --json
scripts/llm-regression-gate fast --repo-only
scripts/llm-regression-gate fast --repo-only --json
scripts/validate-llm-manifest --repo-only
scripts/sync-llm-client-projections --check
```

The fast gate is static and read-only. It checks the schema, undecided
`LOCAL_GENERAL`, `LOCAL_CODE`, and `LOCAL_VISION` assignments, explicit
`MODEL_MAX_CTX`, `RUNTIME_CTX`, `SLOT_CTX`, and `CLIENT_EFFECTIVE_CTX` layers,
manifest-derived client projections, lifecycle ownership, parked OpenCode
routes, the LOCAL_CODE Qwen3.8 qualification scope, and benchmark freeze state. It does not start a model,
query an endpoint, call a cloud model, probe a GPU, or create a listener.

`--repo-only` skips host model inventory and user-level configuration. It is
suitable for CI without model files. Full mode checks user Qwen/Pi/OpenCode
configuration and the host model artifacts. The gate validates local provider
routes while preserving Pi's built-in cloud catalog and DeepSeek default.

`scripts/sync-llm-client-projections` materializes the Qwen model/provider
catalog and the Pi model allowlist from the manifest, including each route's
context window and output-token cap. The Qwen wrapper exports the same
manifest-derived cap as `QWEN_CODE_MAX_OUTPUT_TOKENS`; Pi projects it as
`maxTokens`. It preserves unrelated settings and current cloud defaults. Use
`--check` to detect drift without writing.

## Results

Human output states `FAST_GATE` and `GATE_SCOPE`. JSON output includes the mode,
scope, duration, typed check results, and findings. Exit codes are:

| Code | Meaning |
| --- | --- |
| `0` | All checks in the requested scope passed. |
| `1` | A contract or asset check failed. |
| `2` | The manifest or command input is invalid. |

The separate runtime qualification workflow owns inference and benchmarks.
This migration keeps `R2.3=NOT_RUN` and benchmarks frozen.

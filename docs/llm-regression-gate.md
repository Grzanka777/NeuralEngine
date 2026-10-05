# LLM Fast Regression Gate

`scripts/llm-regression-gate fast` checks active LLM stack configuration against
the current repository contract. It reads repository files and, in full local
scope, checks that required host model assets are present. It does not start a
runtime or make network requests.

## Run modes

```text
scripts/llm-regression-gate fast
scripts/llm-regression-gate fast --json
scripts/llm-regression-gate fast --repo-only
scripts/llm-regression-gate fast --repo-only --json
```

The default local mode evaluates `REPO_BOUND` and `HOST_BOUND` checks. Its
`MODEL_INVENTORY` check verifies each active contract asset is a non-empty
regular file, including auxiliary assets required by that contract. Missing
host assets fail the check.

`--repo-only` evaluates only `REPO_BOUND` checks. It reports the host-bound
`MODEL_INVENTORY` check as `NOT_RUN`; this mode is suitable for CI that has no
local model files.

## What it checks

The active role, model, endpoint, and profile expectations come from
`llm-manifest.json`. The gate compares derived launcher, Qwen, and Pi
configuration against that contract. It also checks the active Command Protocol
and guard bindings and resolves references found in active configuration.
Archived, benchmark, and review evidence does not participate in active
reference resolution.

Check types are explicit in both text and JSON output:

- `REPO_BOUND` checks cover the manifest, role and endpoint matrices, host
  configuration, lifecycle ownership configuration, Command Protocol and guard
  bindings, and active reference resolution.
- `HOST_BOUND` currently covers only `MODEL_INVENTORY`.

The gate is static. It does not start a model server, query endpoints, call a
cloud model, inspect runtime identity or PIDs, probe a GPU, run inference, or
create a listener. Use a separate runtime qualification workflow for those
checks.

## Results

Human output states `FAST_GATE` and `GATE_SCOPE`. JSON output includes the mode,
scope, duration, typed check results, and findings. Exit codes are:

| Code | Meaning |
| --- | --- |
| `0` | All checks in the requested scope passed. |
| `1` | A contract or asset check failed. |
| `2` | The manifest or command input is invalid. |
| `3` | A required repository input could not be read. |

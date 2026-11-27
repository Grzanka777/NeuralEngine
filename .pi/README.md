# NeuralEngine Pi adapter

`AGENTS.md` is the canonical project policy. Pi discovers the two small skills, the Command Protocol prompt templates, and the `tool_call` guard from this directory. There is no separate Pi policy file.

`extensions/neuralengine-guard.ts` is the sole project extension entrypoint. Pi auto-loads direct TypeScript and JavaScript files in `.pi/extensions`. The host-neutral Governor core lives in `../control-plane/governor.ts`; the extension translates Pi hooks into its events. See `../docs/control-plane-governor.md` for the policy and expansion contract.

The supported GENERAL route uses Pi 1.6.1 and the manifest-backed Qwen 3.6
Q6_K projection. Launch it with `scripts/pi-local general -- PI_ARGS...`
from this checkout. The launcher selects the provider and model from
`llm-manifest.json` and explicitly loads the repository projection and Guard.
With `NEURAL_TASK_MEMORY_POLICY` set, it also loads the memory extension and
disables implicit skills, prompts and context files. See the
[Brain adoption runbook](../docs/brain-adoption-runbook.md) for exact flags.

The projection uses `scripts/llm` for the lock, runtime identity checks and
STARTED/BORROWED receipts. Only the exact STARTED PID and start ticks are
eligible for shutdown cleanup. `scripts/llm project-profile current-qwen36`
prints the route without accessing an endpoint. The retired GENERAL start and
switch commands refuse before touching a runtime.

The existing CODE and PATCH adapter paths remain available through
`scripts/pi-local code --policy PATH -- PI_ARGS...` and
`scripts/pi-local patch --policy PATH -- PI_ARGS...`. Their operators use the
legacy `scripts/pi-model status` mapping. CODE and PATCH require the matching
Governor policy. VISION remains unavailable. Use manifest projection for
GENERAL rather than the legacy status mapping.

`integrations/pi/manifest.json` continues to govern installed global
resources. The repository Qwen projection loads explicitly for the GENERAL
runner. The runner disables global extension discovery and MCP for that
session. This workflow requires no changes to the user's global Pi files.

The existing guard blocks common Brain writes and unauthorized Git operations through Pi's built-in tools. Request bounded CODE mode with `NEURAL_PI_BOUNDED_CODE=1` and provide `NEURAL_PI_POLICY_FILE=/absolute/or/repo-relative/task-policy.json`. A policy path by itself also enables bounded mode for compatibility. If bounded mode is requested without a policy, or the policy cannot be read or validated, Pi stops before accepting a prompt and rejects tool calls. With neither setting present, ordinary non-bounded workflows keep their existing behavior. The policy is loaded once per session, copied into immutable state, and its counters are stored in Pi's non-model-visible session entries. A changed policy on resume stops the task; start a new session for a new scope.

Use exact repository-relative file paths. A small policy example:

```json
{
  "RUN_ID": "named-v1-task",
  "WORKSPACE_ROOT": "/home/grzanka/Work/NeuralEngine",
  "POLICY_REVISION": 1,
  "MODE": "BOUNDED_EXECUTE",
  "ALLOWED_READ_FILES": ["src/example.py", "tests/test_example.py"],
  "ALLOWED_EDIT_FILES": ["src/example.py", "tests/test_example.py"],
  "ALLOW_NEW_FILES": false,
  "MAX_FILES_TOUCHED": 3,
  "MAX_DELETED_LINES": 100,
  "MAX_TEST_FILE_SHRINK_PERCENT": 20,
  "MAX_REPEATED_FAILURES": 2,
  "MAX_TOTAL_CORRECTIONS": 6,
  "MAX_COMPACTIONS": 1,
  "REQUIRE_TEST_AFTER_EDIT": true,
  "VALIDATION_COMMANDS": ["uv run pytest tests/test_example.py -q"],
  "TEST_COMMANDS": ["uv run pytest tests/test_example.py -q"]
}
```

Optional fields are `MAX_REWRITE_SHRINK_PERCENT` (default 20) and `AUTHORIZED_REWRITE_FILES` (default empty). `SAFE_GIT_COMMANDS` can only select from the built-in exact read-only inspection commands. Validation entries must be single read-only `uv run pytest`, `uv run ruff check`, `uv run ruff format --check`, `uv run mypy`, or `node --test` commands; shell composition and mutating Ruff options are rejected. A policy with editable files must include at least one test command. The default limits are the bounded CODE safety defaults. In bounded CODE mode, file reads, edits, and search paths must match the policy; built-in writes are checked before execution; `bash` accepts only exact configured validation commands or exact safe Git inspection commands. Other tools are blocked. Approved tool arguments are frozen against later extension mutation. Validation success is recorded from Pi tool results, not final model text. `/governor status` displays the independently computed `GREEN`, `NOT GREEN`, or `STOP` state.

The Evidence Compiler is a standard-library-only deterministic formatter. Give it a JSON object containing only established evidence; omitted or empty fields become `UNKNOWN`:

```sh
python scripts/evidence-compiler --input .agent-work/task-evidence.json
```

It writes the fixed evidence-pack sections and explicit `KNOWN`, `INFERRED`, or `UNKNOWN` status to stdout and performs no search or model call. A root cause or working hypothesis defaults to `INFERRED`. The Pi guard remains an early check, not an operating-system sandbox or a replacement for `AGENTS.md`.

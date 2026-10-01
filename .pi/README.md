# NeuralEngine Pi adapter

`AGENTS.md` is the canonical project policy. Pi discovers the two small skills, the Command Protocol prompt templates, and the `tool_call` guard from this directory. There is no separate Pi policy file.

`extensions/neuralengine-guard.ts` is the sole project extension entrypoint. Pi auto-loads direct TypeScript and JavaScript files in `.pi/extensions`. The host-neutral Governor core lives in `../control-plane/governor.ts`; the extension translates Pi hooks into its events. See `../docs/control-plane-governor.md` for the policy and expansion contract.

The verified reference host is upstream Pi `0.99.1` at `/home/grzanka/.local/bin/pi`. At the repository root Pi uses native `.pi` discovery for this extension, skills, prompts, and `settings.json`; `scripts/pi.py` is an inactive experimental launcher and is not the current entrypoint. The current root default is GENERAL/Qwen3.6. Do not treat stale prose in older launcher notes as operator authority.

The Pi model catalog is user-managed but the operator mapping is deterministic. For a task, use the thin role runner from the repository root: `scripts/pi-local general -- PI_ARGS...`, `scripts/pi-local code --policy PATH -- PI_ARGS...`, or `scripts/pi-local patch --policy PATH -- PI_ARGS...`. The runner delegates lifecycle selection to `scripts/pi-model`, passes the exact provider/model, and stops only the runtime it started. CODE requires a Governor policy whose `ROLE` is `CODE`; PATCH requires a policy whose `ROLE` is `PATCH`; this keeps writable scope explicit instead of silently running unbounded mutations. For a read-only lifecycle/mapping report use `scripts/pi-model status` (or `scripts/pi-local status`). GENERAL uses Qwen3.6, CODE uses Nemotron Q5, PATCH uses GPT-OSS, and VISION is `UNFILLED/disabled` and refused. REVIEWER and SEEK remain GENERAL roles with their respective instructions. These roles create no additional endpoints or subagents.

The switcher snapshots active ports 18080, 18081, and 18086, and treats ports 18082 and 18087 as conflict-only. Port 18082 is conflict-only while VISION is disabled. `scripts/pi-model` identifies the sole listener and its served model, delegates lifecycle actions to `scripts/llm` or `scripts/challenger`, and verifies the target is the sole active local server. `scripts/pi-model status` reports lifecycle, active role/PID/endpoint, expected and actual identity, provider/model mappings, fallback state, and fail-closed VISION. GPT-OSS is available only as the explicitly selected PATCH specialist. Its runtime profile can be selected through `scripts/pi-model GPTOSS` tuning flags; it is not added to production `scripts/llm` roles. The adapter refuses ambiguous, unknown, unhealthy, or changed listeners. Launcher ownership checks remain in force. Pi switches are serialized with an adapter lock; other lifecycle clients do not share that lock, so the adapter rechecks before actions and after startup. A refusal requires operator inspection, never a blind kill.

The active challenger state directory is `~/.local/state/neural-challenger`. Logs in the former `qwen-challenger` state directory are historical and remain untouched.

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

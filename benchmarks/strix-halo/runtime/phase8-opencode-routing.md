# Phase 8 — OpenCode default routing and repository authority

## Authority

- Authoritative NeuralEngine repository:
  `/home/grzanka/Work/NeuralEngine`
- Legacy archive/reference only:
  `/run/media/grzanka/777/projekty/NeuralEngine`

The active repository guidance now names the authoritative checkout once and
explicitly prohibits using the legacy path for project state unless requested.
The audit found one active-project occurrence of the legacy path: the stale
authority statement in `AGENTS.md`, which was updated. No historical benchmark
evidence was changed.

## OpenCode configuration

Installed OpenCode version: `1.18.29`.

The current supported global-default syntax is the top-level `model` key in
`~/.config/opencode/opencode.json`, using `provider_id/model_id`. The following
key was added while preserving the existing instructions, default agent,
autoupdate setting, and both pre-existing providers:

```json
"model": "llama-general/qwen3.6-general-local"
```

Provider configuration:

| Role | Provider/model | Base URL | Context/output |
| --- | --- | --- | --- |
| GENERAL default | `llama-general/qwen3.6-general-local` | `http://127.0.0.1:18081/v1` | 32768 / 8192 |
| CODE specialist | `llama-code/qwen3-coder-local` | `http://127.0.0.1:18080/v1` | 32768 / 8192 |

The GENERAL display name is `Qwen3.6 35B A3B Q4_K_M MTP n3`. The CODE display
name is `Qwen3-Coder 30B A3B UD-Q4_K_XL`.

The prior config was saved unchanged as
`/home/grzanka/.config/opencode/opencode.json.backup-phase8-20260913` before
the update.

## Validation

- `jq empty ~/.config/opencode/opencode.json`: passed.
- `opencode debug config`: resolved the default to
  `llama-general/qwen3.6-general-local` and retained both providers.
- `opencode models llama-general` and `opencode models llama-code`: each
  returned its configured model.
- `llm stop`, `llm general`, and `GET /v1/models` on port 18081: passed.
- A no-`--model` OpenCode connectivity request started from the authoritative
  repository and its exported session recorded provider `llama-general` and
  model `qwen3.6-general-local`.
- `llm code` and `GET /v1/models` on port 18080: passed.
- An explicit `--model llama-code/qwen3-coder-local` OpenCode connectivity
  request recorded provider `llama-code` and model `qwen3-coder-local`.
- `llm stop` and `llm status`: both reported `LLM STOPPED`.
- The saved config is identical to the final config after removing only the
  added root `model` key. `uv run ruff format .`, `uv run ruff check .`,
  `uv run mypy src tests`, and `uv run pytest` passed (`1576 passed`).

The two connectivity requests returned `OK`; no benchmark was run. No runtime
flags, model files, power/GTT, kernel, Mesa, ROCm, boot, or system-wide
configuration changed.

## Rollback

```fish
llm stop
cp /home/grzanka/.config/opencode/opencode.json.backup-phase8-20260913 /home/grzanka/.config/opencode/opencode.json
git restore --source=HEAD -- AGENTS.md
```

The `git restore` command reverts only the Phase 8 repository-authority wording
when the worktree otherwise remains as validated. Re-run `opencode debug config`
after restoring the backup to confirm the previous effective configuration.

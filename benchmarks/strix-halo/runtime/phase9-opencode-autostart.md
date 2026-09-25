# Phase 9 — OpenCode model-selection autostart

## Capability audit

Installed OpenCode is `1.18.29`. Its installed
`@opencode-ai/plugin` package is also `1.18.29`.

The installed plugin type contract exposes `chat.params`, an asynchronous,
model-aware hook whose input includes `model.providerID` and `model.id`. It is
called while OpenCode builds LLM parameters, before the provider request.
OpenCode also loads JavaScript plugins from the documented global directory
`~/.config/opencode/plugin`.

No native provider lifecycle/startup command, local-process provider, or
declarative model-selection startup setting was found in the installed CLI,
resolved config, or plugin hook contract. The `chat.params` hook is the
supported pre-request mechanism and is sufficient for activation before any
local request proceeds.

## Architecture

Native hook, no proxy and no additional service.

Created user-level plugin:

```text
/home/grzanka/.config/opencode/plugin/llm-autostart.js
```

It maps only these selected models:

| OpenCode model | Activation command |
| --- | --- |
| `llama-general/qwen3.6-general-local` | `/home/grzanka/.local/bin/llm general` |
| `llama-code/qwen3-coder-local` | `/home/grzanka/.local/bin/llm code` |

The existing `llm` launcher is idempotent for an already-active matching
service, stops the conflicting service when required, and waits for the model
endpoint before returning. A launcher failure is raised by the hook as a clear
OpenCode error. The plugin ignores all unrelated providers/models.

No OpenCode provider base URL changed: GENERAL remains
`http://127.0.0.1:18081/v1` and CODE remains
`http://127.0.0.1:18080/v1`. The Phase 8 persistent GENERAL default remains
`llama-general/qwen3.6-general-local`; no `opencode.json` change was needed
for this native global-plugin implementation.

## Startup and switching sequence

GENERAL request:

```text
OpenCode selected GENERAL -> chat.params -> llm general -> GENERAL ready on 18081 -> original request
```

CODE request:

```text
OpenCode selected CODE -> chat.params -> llm code -> GENERAL stopped if active -> CODE ready on 18080 -> original request
```

Switching back performs the symmetric CODE stop and GENERAL start. Reciprocal
systemd conflicts and launcher sequencing ensure there is never more than one
`llama-server` process.

## Validation evidence

- Starting from `llm stop`, no model process or listener on ports 18080/18081
  existed.
- An OpenCode-only default GENERAL smoke request started GENERAL automatically,
  completed successfully, and its exported session recorded provider
  `llama-general` / model `qwen3.6-general-local`.
- An OpenCode-only explicit CODE smoke request stopped GENERAL, started CODE,
  returned `OK`, left only port 18080 listening, and its session recorded
  `llama-code` / `qwen3-coder-local`.
- An OpenCode-only switch back to GENERAL stopped CODE and left exactly one
  GENERAL process listening only on 18081.
- The normal `opencode` TUI launched from the authoritative repository and
  displayed `Qwen3.6 35B A3B Q4_K_M MTP n3` with `llama-server GENERAL`.
- A reversible failure simulation used the one-process environment value
  `OPENCODE_LLM_AUTOSTART_TEST_FAIL=general`. With all services stopped,
  OpenCode emitted `Local general LLM activation failed: requested test
  failure`; no backend process started. The environment value was not retained.

The smoke prompts were `Reply with exactly: OK`; no benchmark was run.

`systemd-analyze --user verify` passed for both existing user units, and the
launcher passed `sh -n`. The final repository checks also passed: `uv run ruff
format .`, `uv run ruff check .`, `uv run mypy src tests`, and `uv run pytest`
(`1576 passed`).

## Safety and limitations

- No model/runtime flags, model files, llama.cpp binary, systemd service,
  kernel, Mesa, ROCm, GTT, TDP, power profile, or boot setting changed.
- No proxy, Docker container, system service, or new background process was
  added.
- The legacy repository was not used as authority.
- Activation intentionally occurs on the first chat request after model
  selection, not merely when the selector UI opens. The request waits for the
  selected service to become ready.
- `OPENCODE_LLM_AUTOSTART_TEST_FAIL` is a test-only environment switch; unset,
  it has no effect.

## Rollback

```fish
llm stop
rm /home/grzanka/.config/opencode/plugin/llm-autostart.js
```

Restart OpenCode after removing the plugin. No provider configuration needs
restoring because Phase 9 did not change `opencode.json`.

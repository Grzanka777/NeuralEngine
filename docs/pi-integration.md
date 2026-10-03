# Pi integration

Pi is the canonical reference host for NeuralEngine local GENERAL, CODE, and
PATCH. The integration baseline is Pi 1.0.0; check `pi --version` on the host.
The model catalog is user-managed, so installed resource packaging alone does
not prove model/provider readiness.

## Distribution and launch

Run `uv run --no-sync python scripts/sync-pi-resources` from the repository.
`integrations/pi/manifest.json` is the resource inventory. GLOBAL resources
(Command Protocol and model lifecycle extension) install into `~/.pi/agent/`.
Each must load exactly once, including outside the repository. Never put their
copies in `.pi/skills/command-protocol` or `.pi/extensions/`.
PROJECT_LOCAL `.pi/` retains Guard, local-models, development and roles skills,
prompts, settings, and the system-context adapter. Guard imports the canonical
Governor from `control-plane/`. The development skill loads
`.claude/skills/neuralengine/SKILL.md`; `AGENTS.md` remains project authority.

From the repository use `pi` for GENERAL, or the explicit runner:

```bash
scripts/pi-local general -- PI_ARGS...
scripts/pi-local code --policy PATH -- PI_ARGS...
scripts/pi-local patch --policy PATH -- PI_ARGS...
scripts/pi-model status
```

Approve project resources interactively when Pi requests approval. No
experimental project launcher is required. `.pi/settings.json` explicitly
references project skills, Guard, and prompts; the default is local GENERAL.

## Roles and provider contract

| Role | Provider | Model |
| --- | --- | --- |
| GENERAL | `neural-general` | Qwen3.6 |
| CODE | `neural-code` | Nemotron Q5 |
| PATCH | `local-gptoss` | GPT-OSS |
| VISION | none | UNFILLED, refused |

REVIEW and SEEK are GENERAL workflow overlays. CODE uses context 32768,
batch 2048, ubatch 512. CODE and PATCH require a Governor policy with matching
ROLE; UI confirmation cannot bypass bounded policy. Select local models
explicitly; a skill declaration alone does not bind a model.

Cloud escalation requires explicit operator selection and a stated reason.
Optional DeepSeek FLASH (`deepseek/deepseek-flash`) and PRO
(`deepseek/deepseek-v4-pro`) remain cloud choices, with no automatic cloud
fallback. There is no DeepSeek-only project model filter. Private `auth.json`
and environment credentials stay outside the repository. `models-store.json`
is a cached catalog, not authorization or readiness evidence. Never print,
copy, or commit credentials.

## Lifecycle ownership

The global extension reacts to actual `model_select`, calls the machine API
`scripts/pi-model switch-json ROLE`, and retains STARTED or BORROWED ownership.
On `session_shutdown` it uses `stop-owned-json --profile PROFILE --pid PID`.
Only the exact session-started runtime can stop; borrowed runtimes and
replacement PIDs remain untouched. GPTOSS cleanup uses stable profile/PID
ownership, with two identity revalidations before stop. Unknown, conflicting,
or changed runtime identity fails closed. `scripts/pi-local` also guarantees
owned cleanup on exit. Neither path grants arbitrary process termination.

## Command Protocol and safety

Project prompts live in `.pi/prompts/`. GLOBAL packaged Command Protocol
references must equal canonical `docs/command-protocol/` sources. `REVIEW` is a
workflow state; `CHECKPOINT` and `RECHECK` are controls. Adapters do not redefine
semantics or grant mutation authority.

Guard preserves current-main protected commands: Git mutations, selected
Brain writes, sudo, and recursive removal. Outside bounded execution it asks
for explicit one-command authorization interactively and blocks recognized
protected commands in non-interactive runs. In bounded execution, Governor
policy is enforced independently of confirmation. The guard is defense in
depth, not a shell parser or operating-system sandbox; obfuscated commands
still require normal review. Brain writes and Git mutations remain separately
authorized. Pi does not automatically persist learning or durable records.

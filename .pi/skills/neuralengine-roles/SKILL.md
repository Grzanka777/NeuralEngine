---
name: neuralengine-roles
description: Select GENERAL, bounded CODE, or bounded PATCH for NeuralEngine Pi work; cloud escalation requires explicit operator selection.
---

# NeuralEngine Pi roles

Follow `AGENTS.md` and `.claude/skills/neuralengine/SKILL.md`. Roles are
capabilities underneath the canonical Command Protocol; they do not redefine
commands, controls, workflow states, or authorization.

## Model mapping

| Role | Pi provider | Model | Position |
| --- | --- | --- | --- |
| GENERAL | `neural-general` | Qwen3.6 | Default local reasoning |
| CODE | `neural-code` | Nemotron Q5 | Bounded implementation |
| PATCH | `local-gptoss` | GPT-OSS | Explicit bounded patch specialist |
| VISION | none | UNFILLED | Fail closed |

REVIEW and SEEK are workflow overlays on GENERAL. SEEK remains read-only.
Use GENERAL for analysis, review, architecture, and task scoping. CODE uses
context 32768, batch 2048, ubatch 512. PATCH is not an automatic CODE substitute.

## Selection and lifecycle

Use `scripts/pi-local general -- PI_ARGS...`, or
`scripts/pi-local code --policy PATH -- PI_ARGS...` / `scripts/pi-local patch
--policy PATH -- PI_ARGS...`. CODE policies declare ROLE=CODE and PATCH
policies ROLE=PATCH. A skill declaration does not itself bind the active model.
The runner selects provider/model explicitly. The global lifecycle extension
reacts to actual Pi `model_select`, acquires STARTED or BORROWED identity, and
cleans up only the exact STARTED profile/PID on shutdown. A changed or unknown
runtime fails closed; never kill an unrelated listener.

## Explicit cloud escalation

When local capability or evidence is insufficient, report the reason and stop
for explicit operator selection. Optional cloud choices are FLASH
(`deepseek/deepseek-flash`) for mechanical follow-through and PRO
(`deepseek/deepseek-v4-pro`) for difficult architecture, persistence, security,
or critical review. There is no automatic cloud fallback or silent cloud
selection. No model or role grants Brain writes or Git mutation authority.

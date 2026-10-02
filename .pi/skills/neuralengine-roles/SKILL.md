---
name: neuralengine-roles
description: Select the NeuralEngine Pi execution role (FLASH or PRO) for a task and decide when to escalate. Use when starting, scoping, or escalating NeuralEngine work in Pi.
---

# NeuralEngine Pi roles

This skill is execution guidance underneath the repository-owned Command
Protocol. It does not define, rename, or reinterpret any command, preset,
gate, or lifecycle semantic. Follow `AGENTS.md` and the canonical
`.claude/skills/neuralengine/SKILL.md` first. Do not redefine Command
Protocol commands here; roles only describe which model an authorized task
warrants.

## Model mapping

| Role | Pi model reference | Position |
| --- | --- | --- |
| FLASH | `deepseek/deepseek-flash` | Default execution role |
| PRO | `deepseek/deepseek-v4-pro` | Escalation role |

Both models belong to the project-allowed `deepseek/*` provider scope.

## FLASH

Default role. Use it for:

- `//SEEK`, `//ANALYSE`, and other read-only investigation
- standard `//FIX` and bounded implementation
- tests, debugging, and documentation
- mechanical, repetitive, or well-specified work

FLASH must escalate instead of guessing when a task crosses a critical
boundary. It must not bluff past uncertainty or invent project state.

## PRO

Escalation role. Use it for:

- architecture and cross-layer design
- Brain-related reasoning
- persistence, migrations, and durable state
- security-sensitive changes
- public API or persisted schema changes
- critical review of high-risk work
- difficult ambiguity or root-cause analysis

## Escalation

Escalate FLASH -> PRO when the task touches any PRO boundary above. State the
reason for the escalation explicitly. Prefer PRO for review of work that
itself changed an architectural, persistence, security, or public-API
boundary.

Returning from PRO to FLASH for mechanical follow-through is allowed once the
critical decision is settled.

## Runtime limitation

Pi does not bind a model to a skill or role declaration, and this project
does not enable an automatic model router or silently switch models during a
task. Roles are model-selection guidance only. The operator selects the model
with `/model`, `pi --provider deepseek --model <id>`, or a saved default; the
role contract tells the operator and the model which model a task warrants.

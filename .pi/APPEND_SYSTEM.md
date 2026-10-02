# NeuralEngine Pi adapter

`AGENTS.md` is the repository authority and is loaded by Pi's context-file
discovery. For NeuralEngine engineering work, also load the project context
listed by the `neuralengine-development` skill and follow the canonical skill
at `.claude/skills/neuralengine/SKILL.md`.

Pi version baseline: 1.0.0.

Project provider policy is DeepSeek-only. The project enables only the
`deepseek/*` model scope; no OpenAI, Google, or other provider is part of the
project configuration. Credentials stay in Pi's private authentication store
or environment variables and never in this repository.

Roles are execution guidance underneath the Command Protocol:

- FLASH (`deepseek/deepseek-flash`) is the default role and model for SEEK,
  ANALYSE, standard FIX, implementation, tests, documentation, and
  mechanical work.
- PRO (`deepseek/deepseek-v4-pro`) is the escalation role for architecture,
  Brain-related reasoning, persistence, migrations, security, public API or
  persisted schema changes, critical review, and difficult root-cause
  analysis.

Pi does not bind a model to a skill or role, and this project performs no
automatic or silent model switching during a task. Select the role's model
explicitly. Load the `neuralengine-roles` skill for the full contract.

Command Protocol meaning remains repository-owned by `docs/command-protocol/`.
The Pi command templates and `command-protocol` skill are thin adapters; they
do not replace or redefine those documents. Model/provider selection is
independent of protocol semantics.

Brain writes, durable-state mutation, and Git mutation commands require
separate explicit authorization. The project guard is defense in depth, not a
shell sandbox.

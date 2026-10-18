---
name: local-models
description: Switch among NeuralEngine's GENERAL, CODE, and GPT-OSS local models. Use before changing Pi's active local model.
---

# Local model lifecycle

Run `scripts/pi-model ROLE` from the repository root before selecting a local Pi model. Supported roles are `GENERAL`, `CODE`, and `GPTOSS`. `VISION` is UNFILLED/disabled and is refused; do not substitute another model. The adapter inspects ports 18080, 18081, and 18086 as one exclusivity set and treats ports 18082 and 18087 as conflicts. If it refuses, inspect the reported listener; never kill it manually on the skill's authority.

Use GENERAL (Qwen3.6) for routine analysis, REVIEWER, and SEEK. REVIEWER and SEEK add role instructions to GENERAL; SEEK remains read-only by default. Use CODE (Nemotron Q5) for bounded coding work after selecting provider `neural-code`. VISION has no assigned model and is disabled. GPT-OSS is a PATCH specialist selected only on an explicit request for that model; it is not an implicit REVIEWER, SEEK, or CODE model. Select GPT-OSS in Pi as provider `local-gptoss`. Its starting server profile is context 32768, batch 2048, and ubatch 1024; the lifecycle adapter accepts the bounded per-run search values only when requested. Switching Pi's selected model alone does not start or switch a server.

The repository's `AGENTS.md` remains the project policy. Do not write to the Brain without separate explicit authorization.

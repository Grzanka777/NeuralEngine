---
name: local-models
description: Switch among NeuralEngine's GENERAL, CODE, and GPT-OSS local models. Use before changing Pi's active local model.
---

# Local model lifecycle

Use `scripts/pi-local general -- PI_ARGS...` for GENERAL, REVIEWER and SEEK.
The launcher selects the manifest-backed Qwen3.6 Q6_K endpoint and acquires
process ownership through the existing launcher. SEEK remains read-only.
The legacy GENERAL switch route refuses. Check the exact deployment with
`scripts/llm project-profile current-qwen36`.

Use CODE (Nemotron Q5) for bounded coding work and GPT-OSS only for an
explicit PATCH request. Those paths retain their existing role runner and
Governor policy. VISION is UNFILLED/disabled. A conflicting or unverified
listener requires operator inspection.

The repository's `AGENTS.md` remains the project policy. Do not write to the Brain without separate explicit authorization.

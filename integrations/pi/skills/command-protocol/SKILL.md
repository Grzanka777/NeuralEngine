---
name: command-protocol
description: Interpret NeuralEngine Command Protocol tokens, workflow gates, and review roles. Use for // commands, CHECKPOINT, RECHECK, and SEEK.
---

# Command Protocol adapter for Pi

The canonical protocol files are bundled in this skill's `references/` directory. They are byte-for-byte copies of the repository authorities in `docs/command-protocol/`; that directory remains the semantic source of truth.

Read `references/COMMAND_CORE_v1.2.md`, `references/COMMAND_PROTOCOL_v1.2.md`, and `references/ENGINEERING_WORKFLOW_v1.1.md` as needed. Preserve `AGENTS.md` authority. `//SEEK` uses GENERAL with read-only adversarial instructions; findings go to TRIAGE and do not authorize edits. `REVIEWER` uses GENERAL with independent review instructions. GLM, Q38, and GPT-OSS remain explicitly selected challengers, never implicit role routing. `CHECKPOINT` binds evidence to the reviewed state. `RECHECK` yields exactly one of PROCEED, REVISE, or STOP; an explicit launch is required after PROCEED. No command grants commit, push, Brain write, or destructive authority.

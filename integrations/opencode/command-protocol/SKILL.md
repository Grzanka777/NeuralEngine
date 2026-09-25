---
name: command-protocol
description: Interpret NeuralEngine Command Protocol controls and lifecycle gates.
---

# NeuralEngine Command Protocol adapter

This skill adapts the repository-owned Command Protocol v1.2 for OpenCode.
It is a prompt-level interpretation contract, not a model, provider, agent,
or subagent routing configuration.

## Authorities

- Command Protocol v1.2 defines the command language and precedence.
- Command Core v1.2 defines compact runtime semantics, including TRUST,
  CHECKPOINT, RECHECK, the core presets, and output controls.
- Engineering Workflow v1.1 defines lifecycle authority and phase gates.

The full canonical material is available lazily in `docs/command-protocol/`:

- `COMMAND_CORE_v1.2.md`
- `COMMAND_PROTOCOL_v1.2.md`
- `ENGINEERING_WORKFLOW_v1.1.md`

Read those references when the request needs detail beyond this adapter. Do
not create a competing semantic copy in this skill.
The deterministic installer places copies under the skill's `references/`
directory and records their hashes in its manifest.

## Non-negotiable semantics

- `//SEEK` is read-only by default and routes evidence-backed findings to
  `TRIAGE`; it does not authorize fixes or other mutation.
- `//FIX` means diagnosis, root cause, minimal safe change, and verification.
- `CHECKPOINT` binds evidence to the exact state being reviewed.
- `RECHECK` returns only `PROCEED`, `REVISE`, or `STOP`. `PROCEED` authorizes
  the plan, never automatic execution; the next phase needs an explicit
  launch.
- Critical `//AGENT` work preserves `review → CHECKPOINT → RECHECK → explicit launch`.
  It does not expose or invoke a native `/agent` command.
- `DESTROY` is a workflow phase, not a Command Protocol preset or alias.
- Agents do not commit, push, deploy, delete data, or perform irreversible
  work without separate explicit authorization.

Preserve project `AGENTS.md` authority and the NeuralEngine/Brain read-only
boundary. Unknown commands remain unknown; do not invent their semantics.
No command in this adapter selects or changes a model, provider, agent, or
subagent.

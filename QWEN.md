# Qwen Code project adapter

This file is a short entry point for Qwen Code. The repository rules remain
canonical in [`AGENTS.md`](AGENTS.md) and the [NeuralEngine Development skill](.claude/skills/neuralengine/SKILL.md).
Before engineering work, read those instructions and the relevant project
context: `VISION.md`, `CONTEXT.md`, `memory/project-state.md`,
`docs/architecture.md`, and `docs/conventions.md`.

## Command Protocol

Use these sources as the sole authority for protocol meaning:

- [Command Core v1.2](docs/command-protocol/COMMAND_CORE_v1.2.md)
- [Command Protocol v1.2](docs/command-protocol/COMMAND_PROTOCOL_v1.2.md)
- [Engineering Workflow v1.1](docs/command-protocol/ENGINEERING_WORKFLOW_v1.1.md)

Preserve the principle: **Trust is earned by evidence. Control creates
evidence. Evidence allows trust.** Preserve the defined lifecycle and critical
gate. A `PROCEED` RECHECK permits the next plan; the next phase still requires
an explicit launch. Do not create a generic `//ANALYSE` command or fork protocol
semantics in a skill or agent.

## Scope and evidence boundary

- The user's explicitly requested target defines the scope root. Operate only
  within that root. Do not inspect, cite, analyze, or use state outside it
  unless the task requires an external dependency or the user explicitly
  authorizes scope expansion.
- For a narrow file or directory target, bind evidence to its exact paths,
  contents, inventory, hashes, and observed target-specific output. Do not
  substitute branch/HEAD, repository status or diffs, unrelated worktree state,
  or Brain state for target evidence.
- Obtain requested hashes from an actual hash-tool result on the exact in-scope
  files and copy the values verbatim. If that result is unavailable, report the
  hashes as `UNVERIFIED`; never invent or reconstruct them.
- Follow the user's requested response format exactly. When specific fields are
  requested, use those labels and return only those fields.
- For `SEEK`, `REVIEW`, `CHECKPOINT`, `RECHECK`, and `VERIFY`, follow the
  corresponding adapter in `.qwen/skills/<command>/SKILL.md`.
- Before returning a requested SHA-256 value, call the shell tool with
  `sha256sum -- <exact in-scope paths>` and copy each returned value verbatim.
  A hash without that observed command result is `UNVERIFIED`; do not answer
  with a guessed or generated value.
- If external state appears necessary, STOP, explain why, and request explicit
  authorization before expanding scope. If requested evidence is unavailable
  within scope, report `UNVERIFIED`; do not infer it.

## Repository constraints

- Make the smallest safe change within the requested scope.
- Tests and specifications are authoritative. Never rewrite tests to fit an
  unavailable runner; use a non-mutating check and report the limitation.
- Do not install packages without explicit approval.
- Do not commit or push.
- Treat the NeuralEngine Brain as read-only unless the user separately
  authorizes a specific Brain write.
- Report observed evidence and validation accurately; do not infer success.

## Brain and Knowledge

- Qwen may read existing Brain and Knowledge context and use it for the task.
- Never write Brain state, create a DecisionReview, promote Review to
  Experience, or create Knowledge automatically. Each durable action requires
  separate explicit user authorization and the existing NeuralEngine
  mechanism.

## Frozen Qwen integration boundary

Qwen Code is a thin NeuralEngine client. Use `qg` → LOCAL GENERAL (65536),
`qc` → LOCAL CODE (65536), and `qv` → LOCAL VISION (32768) with the existing
NeuralEngine `scripts/llm` lifecycle.

Do not create another router or runtime manager, change runtime/model
configuration, modify OpenCode, or redesign Brain or Knowledge promotion.
Brain and Knowledge may be read; durable writes require separate explicit
authorization, as above.

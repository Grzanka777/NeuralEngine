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

## Local role integration boundary

Qwen Code uses only three local roles through scripts/llm:
GENERAL = Nemotron Q5 on port 18081; CODE = Qwen3-Coder UD-Q4_K_XL on
port 18080; VISION = Gemma 4 Q4 with mmproj on port 18082. All baseline
contexts are 32768. VISION explicitly disables reasoning and MTP.
The Gemma catalog entry declares `generationConfig.modalities.image = true`;
use `qv --prompt "@/path/to/image.png Describe the visible content."` to
attach a local image through Qwen's image input pipeline.

qg, qc, and qv select model and endpoint and append the corresponding
project agent instruction body to the main session prompt. Model binding and
instruction binding are separate contracts. Wrapper arguments cannot replace
routing, role instructions, advisor, or fallback policy. There is no cloud
fallback. Direct CLI and Desktop use the local GENERAL default, but do not
own runtime lifecycle; use qg/qc/qv for automatic owned start/stop.

scripts/llm is the sole local runtime manager. One profile may run at a time.
Wrappers preserve borrowed processes and stop only their exact owned PID and
profile on normal exit. Command Protocol and Brain authorization boundaries
above remain unchanged. Pi handles explicitly requested cloud work separately.

---
name: command-protocol
description: >-
  Interpret NeuralEngine Command Protocol tokens, workflow gates, and review roles.
  Use when prompts reference // commands (e.g. //SEEK, //BRUTAL, //ARCH, //SHIP, //FIX,
  //AGENT, //WARROOM, //RESEARCH, //OPTIMIZE, //KILL), CHECKPOINT, or RECHECK.
---

# NeuralEngine Command Protocol adapter for Antigravity CLI

This skill is a thin instruction-level entry point for the Antigravity CLI (`agy`). The canonical protocol documents in this repository define all command semantics and remain the sole authoritative source of truth:

- `../../../docs/command-protocol/COMMAND_CORE_v1.2.md`
- `../../../docs/command-protocol/COMMAND_PROTOCOL_v1.2.md`
- `../../../docs/command-protocol/ENGINEERING_WORKFLOW_v1.1.md`

## Operational Guidance & Scope Boundary

Command Protocol provides operational guidance for agent planning, analysis rigor, and review phases.

**Security and Boundary Disclaimers:**
- Command Protocol does **NOT** install, activate, or enforce the NeuralEngine Governor.
- It does **NOT** configure security hooks (`hooks.json`) or pre-tool interceptors.
- It does **NOT** establish NeuralEngine Brain connectivity or mutate durable Brain state (`$NEURAL_HOME/brain`).
- This integration is strictly prompt-/instruction-level guidance; it does **NOT** provide deterministic policy enforcement.
- Repository authority in `AGENTS.md` and repository instructions strictly take precedence. No command authorizes `git add`, `git commit`, `git push`, staging, deletion, deployment, or NeuralEngine Brain mutations without separate explicit user authorization.

## Operating Rules & Supported Tokens

When a prompt contains Command Protocol syntax or control tokens, consult `docs/command-protocol/COMMAND_CORE_v1.2.md`:

### Reliability & Truth Anchor
- **`TRUST`**: Zero material guessing. Separate facts from hypotheses, expose meaningful uncertainty, challenge unsupported assumptions, and verify claims. Never invent evidence, tests, APIs, CLI flags, benchmarks, files, citations, or source results.

### Phase Control & State Snapshots
- **`CHECKPOINT`**: Authoritative evidence snapshot for the exact state being reviewed. Record sufficient identity and evidence to re-establish state (host, repository, branch, revision/HEAD, changed paths, validation, scope audit, blockers, deviations). A checkpoint is valid only for the state it references and becomes stale upon material change.
- **`RECHECK`**: Compares the proposed next phase against the latest authoritative checkpoint, current repository/system state, current requirements, unresolved blockers, scope, exclusions, and validation needs.
  - Returns exactly one of: `PROCEED`, `REVISE`, or `STOP`.
  - `PROCEED` authorizes the plan, **NOT** automatic execution; the next phase must still be launched explicitly.
  - `REVISE` must provide the corrected next-phase scope or prompt.
  - `STOP` must identify the blocking reason.

### Core Presets
- **`//BRUTAL`**: High-rigor decision analysis (`TRUST + MAX + FIRSTPRINCIPLES + ASSUMPTIONS + REDTEAM + TRADEOFFS + DECIDE`). Concrete recommendation, main trade-off, and condition that would change the decision.
- **`//WARROOM`**: Maximum justified rigor for high-cost-of-error decisions (`TRUST + MAX + EVIDENCE + FIRSTPRINCIPLES + ASSUMPTIONS + REDTEAM + FAILUREMODES + SECONDORDER + TRADEOFFS + CROSSCHECK + DECIDE`).
- **`//ARCH`**: Architecture and contract analysis prioritizing domain invariants, boundaries, data integrity, and backwards compatibility.
- **`//SHIP`**: Readiness gate returning `GO`, `GO WITH CONDITIONS`, or `NO-GO` with evidence.
- **`//SEEK`**: Post-SHIP adversarial inspection (`TRUST + CODEAUDIT + REDTEAM + EDGECASES + FAILUREMODES + EVIDENCE + VERIFY`). **Read-only by default.** Actively search for evidence-backed defects, contract drift, risks. Findings go to TRIAGE; discovery never authorizes modification, fixing, refactoring, or deletion.
- **`//FIX`**: Root-cause troubleshooting (`read-only diagnosis → hypothesis → confirmation → minimal safe change → verification`).
- **`//AGENT`**: Prepare or govern agent task (`CLASSIFY + REPOAUTH + SURGEON + TESTPLAN + NOCOMMIT`). Multi-phase critical work requires `phase → review → CHECKPOINT → RECHECK(next phase) → explicit launch`.
- **`//RESEARCH`**: Current evidence-first research preferring primary sources.
- **`//OPTIMIZE`**: Workflow performance optimization (`eliminate → automate → delegate → optimize manually`).
- **`//KILL`**: Test whether the work should exist; evaluate cost/risk/benefit.

### Output Controls & Composition
- **`ELI10`**: Explain simply without sacrificing technical correctness.
- **`NEXT`**: Return the single best concrete next action.
- Commands compose (e.g. `//RESEARCH + DECIDE <task>`); modifiers extend presets without removing requirements.
- Note: `ANALYSE` is a workflow phase, not a preset (`//ANALYSE` does not exist).
- Instruction precedence: (1) safety and data integrity; (2) `TRUST`; (3) explicit task requirements; (4) preset semantics; (5) additional modifiers; (6) output format.

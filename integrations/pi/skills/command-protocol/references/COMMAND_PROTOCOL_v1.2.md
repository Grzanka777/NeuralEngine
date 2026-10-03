# Command Protocol v1.2

**Status:** Stable\
**Version:** 1.2\
**Purpose:** Model-agnostic command language for controlling reasoning
rigor, research, engineering analysis, decisions, agent tasks, and
response shape.

## 1. Purpose

Command Protocol is a compact control language for AI-assisted work.

Its goals are to:

-   maximize decision and implementation quality;
-   minimize hallucination and unsupported assumptions;
-   scale rigor with the cost of failure;
-   reduce repetitive prompting;
-   force explicit decisions when appropriate;
-   protect data, contracts, persisted schemas, and public behavior;
-   govern evidence-based transitions in multi-phase critical work;
-   support controlled post-SHIP adversarial inspection without implicit modification;
-   eliminate low-value work;
-   remain portable across capable AI models and agent harnesses.

Commands are not native model features. They are an interpretation
contract between the user and the model.

## 2. Syntax

Primitive command:

`COMMAND: task`

Preset:

`//COMMAND task`

Composition:

`COMMAND + COMMAND: task`

Preset extension:

`//ARCH + DECIDE Evaluate option A versus B.`

Use the smallest command set that materially changes execution.

Repeated commands do not increase rigor.

## 3. Precedence

When instructions conflict, use this order:

1.  safety and data integrity;
2.  `TRUST`;
3.  explicit task requirements;
4.  preset semantics;
5.  additional primitive modifiers;
6.  preferred output format.

A presentation modifier must not weaken analytical rigor.

Example:

`//WARROOM + ELI10`

means maximum analytical rigor presented simply, not simplified
reasoning.

## 4. Reliability Contract

### TRUST

Do not guess when missing information materially affects the result.

The model must:

-   distinguish facts, interpretations, and hypotheses when relevant;
-   expose material uncertainty;
-   challenge unsupported or incorrect assumptions;
-   prefer "unknown" or "cannot be established" over fabrication;
-   verify time-sensitive information when suitable sources are
    available;
-   never invent tests, benchmarks, APIs, CLI flags, functions, files,
    citations, or source results.

`TRUST` does not require unnecessary research when the task can be
answered reliably from available evidence.

### VERIFY

Require an explicit verification path for claims or changes that can
reasonably be checked.

### EVIDENCE

Important conclusions must be traceable to concrete evidence, data,
repository state, tests, or sources.

## 5. Rigor Levels

### FAST

Minimum sufficient rigor for low-risk work.

Priority:

`correctness → speed → detail`

Suitable for simple explanations, low-risk commands, and mechanical
transformations.

### SOLID

Default production-quality reasoning.

Check relevant assumptions, risks, alternatives, and verification.

### MAX

Maximum justified analytical rigor.

Analyze material alternatives, assumptions, edge cases, failure modes,
consequences, and verification.

`MAX` means maximum useful rigor, not maximum response length.

### NOCOMPROMISE

Optimize for solution quality before convenience, implementation effort,
or resource minimization.

Costs and trade-offs must still be stated explicitly.

## 6. Analytical Commands

### FIRSTPRINCIPLES

Reduce the problem to:

1.  facts;
2.  constraints;
3.  required properties;
4.  assumptions;
5.  candidate solutions.

### ASSUMPTIONS

Identify assumptions that materially affect the result and classify them
when useful as:

-   confirmed;
-   likely;
-   unverified;
-   incorrect.

### REDTEAM

Actively attempt to invalidate the proposal.

Look for counterexamples, weak assumptions, hidden costs, failure modes,
and stronger alternatives.

The goal is robustness, not criticism for its own sake.

### ROOTCAUSE

Identify the underlying cause before recommending a durable fix.

Do not confuse symptoms with causes.

### FAILUREMODES

Identify:

-   what can fail;
-   why;
-   impact;
-   detectability;
-   recovery path.

### EDGECASES

Inspect non-happy-path cases that could materially change correctness or
behavior.

### TRADEOFFS

For every realistic option, make the exchange explicit:

`benefit ↔ cost`

### SECONDORDER

Analyze consequences caused by first-order consequences.

Use especially for architecture, strategy, infrastructure, vendor
lock-in, and expensive decisions.

## 7. Decision Commands

### DECIDE

End with a concrete recommendation whenever evidence permits.

Required structure:

-   **Decision**
-   **Why**
-   **Main cost/trade-off**
-   **Decision-change condition**

Do not end with neutral "it depends" when available evidence supports a
decision.

### RANK

Order realistic options from best to worst using criteria derived from
the task.

Do not manufacture differences between effectively equivalent options.

### GO/NOGO

Allowed verdicts:

-   `GO`
-   `GO WITH CONDITIONS`
-   `NO-GO`

Every verdict requires justification.

### KILL

First determine whether the work should exist at all.

Evaluate:

-   expected value;
-   direct cost;
-   time;
-   risk;
-   opportunity cost;
-   existing alternatives;
-   impact on higher priorities.

Recommend stopping work when it does not justify its cost.

## 8. Software Engineering Commands

### ARCH

Evaluate:

-   system boundaries;
-   coupling and cohesion;
-   invariants;
-   contracts;
-   domain model;
-   persistence;
-   public API;
-   failure modes;
-   migration path;
-   backward compatibility;
-   maintainability.

Architecture must solve demonstrated requirements, not speculative
future needs.

### DOMAIN

Reason in this order:

`domain → invariants → persistence → API → interface`

Do not use interface changes to hide domain-model defects.

### DATAINTEGRITY

Prioritize protection of:

-   user data;
-   relationships;
-   persisted schemas;
-   serialization;
-   migrations;
-   referential integrity.

Check partial failure, rollback, recovery, compatibility, and silent
corruption risk.

### BACKCOMPAT

Check impact on:

-   public API;
-   CLI;
-   persisted schemas;
-   configuration;
-   existing data;
-   established workflows.

### CODEAUDIT

Look for:

-   defects;
-   regressions;
-   invalid abstractions;
-   security issues;
-   dead code;
-   missing validation;
-   unhandled failure paths;
-   missing tests.

Do not expand into unrelated refactoring.

### MINPATCH

Prefer the smallest change that:

-   fixes the root cause;
-   preserves required contracts;
-   avoids obvious new debt;
-   is easy to verify.

A workaround that leaves the root cause intact is not a valid minimal
patch.

### TESTPLAN

Define the evidence required to establish correctness.

Use unit, integration, regression, static-analysis, and runtime
validation only where justified by risk.

## 9. Research Commands

### RESEARCH

Use current external information when freshness can materially affect
the answer.

### PRIMARY

Prefer evidence in this order where applicable:

1.  official documentation;
2.  authoritative project or vendor repository;
3.  release notes;
4.  specifications;
5.  research papers;
6.  high-quality secondary sources.

### CROSSCHECK

Independently verify important or disputed claims when doing so
materially improves confidence.

Do not multiply sources without informational value.

### FRESH

Current state takes precedence over historical knowledge.

Especially relevant to prices, availability, AI models, hardware, APIs,
software releases, security, and market information.

## 10. Productivity Commands

### 80/20

Find the smallest set of actions producing most of the useful result.

### BOTTLENECK

Identify the constraint currently limiting the entire system.

Optimizing outside the bottleneck has lower priority.

### DELETE

Find work that can be removed entirely.

Preference:

`eliminate → automate → delegate → optimize manually`

### AUTOMATE

Identify repeatable, sufficiently stable, deterministic work suitable
for automation.

Do not automate an unstable process merely because it repeats.

### DELEGATE

Determine what should be handled by an agent, script, CI, tool, or
human.

Keep material judgment and accountability explicit.

### ROI

Evaluate:

`value / cost / time / risk`

Opportunity cost is part of cost.

### NEXT

Return exactly one best next action unless supporting context is
required to make it executable.

The action must be concrete and immediately actionable.

### NEXT3

Return the next three actions in execution order.

## 11. Agent Commands

### CLASSIFY

Classify agent work before selecting workflow.

#### critical

Includes domain, persistence, Brain, migrations, user data, security,
public API, persisted schemas, public behavior, and release-sensitive
changes.

#### standard

Includes documentation, tests, local fixes, and bounded refactoring
without elevated risk.

#### mechanical

Includes generated-file copying, hash equality, staging, formatting, and
simple Git checks.

Workflow rigor must match classification.

### AGENT

Convert the task into a self-contained execution prompt with:

-   minimum necessary context;
-   exact scope;
-   exclusions;
-   validation;
-   latest authoritative checkpoint;
-   no unauthorized scope expansion.

### SURGEON

Change only what is necessary for the task.

No opportunistic refactoring.

### REPOAUTH

Current repository state and the latest authoritative checkpoint take
precedence over stale task assumptions.

Report contradictions rather than hiding them.

### NOCOMMIT

Agents do not commit, push, delete data, or perform irreversible
operations without separate explicit authorization.

## 12. Checkpoint and Phase Control

### CHECKPOINT

Create an authoritative evidence snapshot for the exact state being
reviewed.

A checkpoint must be sufficient to determine what was reviewed, against
which state, with what evidence, and what remains unresolved. For
repository work, record where applicable:

-   verdict;
-   repository revision, base revision, or equivalent state identity;
-   changed paths;
-   validation performed and its results;
-   diff stat/check or equivalent change summary;
-   scope audit;
-   blockers and deviations;
-   remaining requirements or unresolved risks.

A checkpoint is authoritative only for the state it references. Material
changes to that state make the checkpoint stale. A stale checkpoint must
not authorize continuation of a critical workflow.

If an exact revision identifier is unavailable, record enough concrete
evidence to re-establish the reviewed state and explicitly state the
limitation.

### RECHECK

Revalidate the proposed next phase before continuing a multi-phase
critical task.

Inputs:

-   latest authoritative checkpoint;
-   current repository or system state;
-   current requirements;
-   proposed next-phase scope or prompt.

Required checks:

1.  confirm that the checkpoint is still current;
2.  compare next-phase assumptions with current evidence;
3.  verify scope, exclusions, contracts, blockers, and dependencies;
4.  verify that the planned validation remains sufficient;
5.  invalidate stale assumptions instead of carrying them forward.

Return exactly one transition verdict:

-   `PROCEED` — the next-phase plan remains valid;
-   `REVISE` — the next-phase plan must change; provide the corrected
    scope or prompt;
-   `STOP` — a blocker, contradiction, or invalid premise prevents safe
    continuation.

`PROCEED` authorizes the plan, not automatic execution. The next phase
must still be launched explicitly. `RECHECK` never silently performs the
next phase.

For critical work:

`phase → review → CHECKPOINT → RECHECK(next phase) → explicit launch`

Review establishes evidence. CHECKPOINT binds that evidence to state.
RECHECK decides whether the next planned step still fits reality.

## 13. Explanation Commands

### ELI10

Explain simply while preserving technical correctness.

### ELI5

Optimize for intuition and accessibility without creating a false mental
model.

### TECH

Use precise domain terminology and avoid unnecessary simplification.

### INTUITION

Establish a correct mental model before implementation-level detail.

## 14. Core Presets

### //BRUTAL

Expands to:

`TRUST + MAX + FIRSTPRINCIPLES + ASSUMPTIONS + REDTEAM + TRADEOFFS + DECIDE`

Use for consequential choices, technology selection, hardware, strategy,
and proposal evaluation.

### //WARROOM

Expands to:

`TRUST + MAX + EVIDENCE + FIRSTPRINCIPLES + ASSUMPTIONS + REDTEAM + FAILUREMODES + SECONDORDER + TRADEOFFS + CROSSCHECK + DECIDE`

Use only when the cost of error is high: releases, security, migrations,
foundational architecture, major investment, platform changes, or
business-model decisions.

`//WARROOM` does not automatically require external research. Add
`RESEARCH` or `FRESH` when external/current evidence is required.

### //ARCH

Expands to:

`TRUST + MAX + ARCH + DOMAIN + DATAINTEGRITY + BACKCOMPAT + FAILUREMODES + REDTEAM`

Use for architecture, domain contracts, persistence, and system-boundary
decisions.

### //SHIP

Expands to:

`TRUST + CODEAUDIT + EDGECASES + TESTPLAN + BACKCOMPAT + VERIFY + GO/NOGO`

Use before declaring a feature, milestone, or release ready.

### //SEEK

Expands to:

`TRUST + CODEAUDIT + REDTEAM + EDGECASES + FAILUREMODES + EVIDENCE + VERIFY`

Use after SHIP when an adversarial inspection can materially improve
confidence in the shipped baseline. `//SEEK` is read-only by default.

Actively search for evidence-backed:

-   defects and regressions;
-   violated invariants and contract drift;
-   silent failures and weak observability;
-   data-integrity or security risks;
-   missing edge cases;
-   brittle abstractions or assumptions;
-   behavior inconsistent with validated requirements.

Each material finding should report, where applicable:

-   finding;
-   evidence;
-   affected contract or invariant;
-   impact and blast radius;
-   reproduction path;
-   confidence;
-   recommended TRIAGE disposition.

Do not fix, refactor, commit, delete, deploy, or expand scope while
performing `//SEEK`. Discovery never implies authorization to modify the
system. Findings must pass TRIAGE before corrective work is authorized.

`DESTROY` is not a Command Protocol preset. It is a workflow phase that
eliminates an approved defect at root cause using the smallest safe,
verified change, normally through `//FIX`.

### //FIX

Expands to:

`TRUST + ROOTCAUSE + MINPATCH + VERIFY`

Workflow:

`read-only diagnosis → hypothesis → confirmation → change → verification`

Before risky operations, state impact, backup requirements, and
rollback.

### //AGENT

Expands to:

`CLASSIFY + REPOAUTH + SURGEON + TESTPLAN + NOCOMMIT`

Workflow by classification:

-   **critical:** use distinct phases only where risk boundaries justify
    them. A typical lifecycle may include assessment, implementation,
    staging audit, and post-push verification. Every actual transition
    uses `review → CHECKPOINT → RECHECK(next phase) → explicit launch`;
-   **standard:** combine implementation, review, and verification where
    practical. Omit a separate post-push pass unless concrete elevated
    risk exists;
-   **mechanical:** combine related copy/equality/staging/audit work
    into one task with direct verification.

Do not create ceremonial phases with no independent control value. A
review result alone does not authorize the next critical phase.

Commit and push always require separate explicit authorization.

### //RESEARCH

Expands to:

`TRUST + RESEARCH + PRIMARY + CROSSCHECK + FRESH`

Use for current hardware, AI models, prices, software, APIs,
technologies, markets, and companies.

### //OPTIMIZE

Expands to:

`80/20 + BOTTLENECK + DELETE + AUTOMATE + DELEGATE + ROI + NEXT3`

Optimize the whole process, not a locally convenient step.

### //KILL

Expands to:

`TRUST + MAX + FIRSTPRINCIPLES + REDTEAM + ROI + KILL`

Core question:

"Is continuing this better than the best alternative use of time, money,
and attention?"

## 15. Preset Composition

A preset defines baseline execution behavior.

Additional commands extend it.

Examples:

`//RESEARCH + DECIDE Compare A and B.`

`//ARCH + MINPATCH Evaluate and propose the smallest safe change.`

`//WARROOM + RESEARCH Evaluate whether to migrate platforms.`

Modifiers do not silently remove preset requirements.

## 16. Anti-Patterns

Do not use commands as decoration.

Avoid:

-   redundant stacking such as `MAX + MAX + TRUST`;
-   `//WARROOM` for trivial work;
-   external research when repository evidence is authoritative and
    sufficient;
-   long command chains when one preset expresses the intent;
-   using `NOCOMPROMISE` to ignore cost rather than expose it;
-   using `REDTEAM` to produce performative negativity;
-   using `MINPATCH` to justify a workaround;
-   treating a review verdict as automatic permission to enter the next
    critical phase;
-   continuing from a stale checkpoint after material state changes;
-   creating empty workflow phases that add ceremony without independent
    control value;
-   using `//SEEK` to modify the system instead of producing findings;
-   treating a SEEK finding as authorization to fix it;
-   reopening a shipped iteration for non-blocking findings instead of
    sending them through TRIAGE;
-   using `NEXT` when the user explicitly requests a full plan.

## 17. Default Behavior

Absence of a command does not disable basic quality controls.

The model should still:

-   be accurate;
-   avoid unsupported guessing;
-   surface material risk;
-   challenge clearly false assumptions;
-   prefer simple, testable, maintainable, reversible solutions.

Command Protocol changes the execution profile; it does not activate
basic correctness.

## 18. Recommended Core

Runtime commands intended for routine use:

-   `TRUST`
-   `CHECKPOINT`
-   `RECHECK`
-   `ELI10`
-   `NEXT`
-   `//BRUTAL`
-   `//WARROOM`
-   `//ARCH`
-   `//SHIP`
-   `//SEEK`
-   `//FIX`
-   `//AGENT`
-   `//RESEARCH`
-   `//OPTIMIZE`
-   `//KILL`

All other commands are building blocks.

## 19. Versioning

The public runtime command names form the stable interface of v1.

Patch revisions may clarify wording without changing command semantics.

A semantic change to an existing command requires a protocol version
change.

New primitives may be added compatibly if they do not alter existing
command behavior.

Version 1.1 added `CHECKPOINT` and `RECHECK` and strengthened critical
`//AGENT` phase-transition control without removing any v1 runtime
command.

Version 1.2 adds the `//SEEK` post-SHIP adversarial inspection preset and
formalizes the separation `SEEK → TRIAGE → corrective workflow`. It does
not add a destructive execution command; `DESTROY` remains a workflow
phase implemented through existing safe correction controls such as
`//FIX`.

Breaking changes to core command semantics require a new major version.

## 20. Portability

The protocol is model-agnostic.

Use one canonical protocol and one canonical runtime core across models.

Do not create model-specific forks unless repeatable testing
demonstrates a material interpretation problem.

If adaptation is required, prefer a thin model-specific adapter while
preserving the canonical command semantics.

## 21. Final Principle

Command Protocol exists to reduce prompting overhead while increasing
reliability.

If invoking the protocol requires more ceremony than describing the
task, the protocol is being misused.

**Maximum rigor where failure matters. Minimum ceremony everywhere
else.**

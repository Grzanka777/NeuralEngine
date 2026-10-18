# Engineering Workflow v1.1

**Status:** Stable\
**Protocol:** Command Protocol v1.2\
**Role:** Evidence-gated lifecycle for engineering and agent work.

This document defines **when work may advance**. Command Protocol defines
**how a task is executed**. The two are complementary and should not be
collapsed into one oversized command language.

## 1. Core Principle

**Trust is earned by evidence.\
Control creates evidence.\
Evidence allows trust.**

The workflow exists to create enough control to produce trustworthy
evidence without turning low-risk work into ceremony.

## 2. Canonical Lifecycle

`CREATE → ANALYSE → FIX → REVIEW → REFACTOR → VERIFY → IMPROVE → SHIP → SEEK → TRIAGE`

TRIAGE then branches to `FALSE POSITIVE`, `ACCEPTED RISK`,
`NEXT ITERATION`, or `HOTFIX → DESTROY`.

This is a lifecycle model, not a requirement to instantiate every phase
for every task. Skip or combine phases when doing so does not remove a
meaningful control boundary. Post-SHIP SEEK is used when adversarial
inspection has material value; it is not mandatory ceremony for every
mechanical or low-risk task.

### CREATE

Produce the smallest coherent implementation, artifact, or solution that
meets the current scope. Avoid speculative expansion.

### ANALYSE

Evaluate the current result against requirements, evidence, assumptions,
contracts, risks, and known constraints.

`ANALYSE` is a workflow phase, not a required Command Protocol preset.
Use the smallest protocol commands that materially improve the analysis.

### FIX

Correct demonstrated defects, broken assumptions, regressions, or
contract violations. Prefer root-cause repair and minimal safe change.

### REVIEW

Perform an independent or explicitly separated inspection against the
actual scope and current state. Review is evidence generation, not
automatic permission to continue.

### REFACTOR

Improve structure only where evidence shows material maintainability,
clarity, duplication, coupling, or correctness benefit. No opportunistic
refactoring. Preserve behavior unless behavior change is explicitly in
scope.

### VERIFY

Execute the validation required to establish correctness at the relevant
risk level. Prefer concrete tests, static analysis, runtime evidence,
repository state, or source evidence over assertions.

### IMPROVE

Apply remaining high-value improvements that are justified by evidence
and still fit the current scope. Do not turn polish into scope creep.

### SHIP

Apply the readiness gate. `SHIP` means the work is ready for the intended
release or handoff according to evidence. It does not itself authorize
commit, push, deployment, deletion, or another irreversible action.

### SEEK

Perform a post-SHIP adversarial inspection of the verified baseline. The
goal is to discover hidden defects, regressions, violated invariants,
contract drift, silent failures, weak assumptions, security or
data-integrity risks, and materially missing edge cases.

SEEK is read-only by default. It generates evidence-backed findings; it
does not authorize fixes, refactoring, commit, push, deployment, deletion,
or scope expansion. Use `//SEEK` when the dedicated preset is useful.

### TRIAGE

Evaluate every material SEEK finding before corrective work begins.
Consider severity, evidence quality, blast radius, data/security impact,
public behavior, reproducibility, fix cost, regression risk, and
opportunity cost.

Use one disposition:

-   `FALSE POSITIVE` — evidence does not establish a defect;
-   `ACCEPTED RISK` — valid issue, but correction is not justified now;
-   `NEXT ITERATION` — validated issue should enter the next controlled
    cycle;
-   `HOTFIX` — severity justifies reopening corrective work immediately.

A SEEK finding is evidence, not authorization. TRIAGE is the decision
gate.

### DESTROY

Eliminate an approved defect at its root cause with the smallest safe,
verified change. `DESTROY` is a workflow phase, not a Command Protocol
preset and never means uncontrolled deletion or destructive action.

Normally implement DESTROY through `//FIX`:

`verified finding → ROOTCAUSE → MINPATCH → VERIFY`

For a critical finding, use the critical workflow controls, including
review, CHECKPOINT, RECHECK where another phase follows, and explicit
authorization for commit, push, deployment, data deletion, or other
irreversible actions.

### NEXT ITERATION

Start a new controlled cycle from the highest-value validated finding or
requirement. Do not silently append new work to the completed iteration.

Non-blocking post-SHIP findings normally enter NEXT ITERATION rather than
reopening the shipped baseline.

### Post-SHIP SEEK AND DESTROY Loop

The canonical adversarial loop is:

`SHIP → SEEK → FINDINGS → TRIAGE`

Then branch by disposition:

-   `FALSE POSITIVE` → close the finding;
-   `ACCEPTED RISK` → record the decision and rationale;
-   `NEXT ITERATION` → queue for the next controlled cycle;
-   `HOTFIX` → `DESTROY → REVIEW/VERIFY → SHIP` using rigor proportional
    to risk.

Post-SHIP inspection must not create an endless release loop. SHIP
establishes a verified baseline; SEEK attacks that baseline; TRIAGE
separates signal from noise; DESTROY removes only defects that survive
scrutiny and are authorized for correction.

## 3. Workflow by Risk Classification

### mechanical

Default:

`TASK → VERIFY → DONE`

Examples include copy/equality checks, formatting, staging, generated-file
work, and simple Git inspection. Combine related checks when safe.

Do not manufacture CREATE/ANALYSE/REVIEW phases when direct verification
provides sufficient evidence.

### standard

Default:

`CREATE or FIX → REVIEW + VERIFY → DONE`

Use separate REFACTOR or IMPROVE phases only when review evidence shows
a material need. Add post-push verification only when a concrete elevated
risk justifies it.

### critical

Critical work includes Brain, domain, persistence, migrations, user data,
security, public API, persisted schemas, public behavior, and
release-sensitive changes.

Use distinct phases only where they create independent control value. A
typical lifecycle may include assessment, implementation, staging audit,
and post-push verification, but the exact phases are task-dependent.

Every actual transition follows:

`PHASE N → REVIEW → CHECKPOINT → RECHECK(PHASE N+1) → EXPLICIT LAUNCH`

The next phase must never start automatically.

## 4. Critical Phase Gate

After each critical phase:

1.  perform review against the current scope and actual repository or
    system state;
2.  create a CHECKPOINT tied to that exact state;
3.  RECHECK the proposed next phase against:
    - current requirements;
    - latest authoritative checkpoint;
    - current repository or system state;
    - previous-phase evidence;
    - unresolved blockers and deviations;
    - scope and exclusions;
    - planned validation;
4.  return `PROCEED`, `REVISE`, or `STOP`;
5.  launch the next phase only through a separate explicit task.

Meaning:

-   `PROCEED` — the plan is still valid;
-   `REVISE` — regenerate the next-phase scope or prompt from current
    evidence;
-   `STOP` — do not continue until the blocker or contradiction is
    resolved.

A review verdict alone is never a phase-transition authorization.

## 5. Checkpoint Contract

For critical repository work, the checkpoint should contain at minimum:

-   verdict;
-   checkpoint or state identity;
-   changed paths;
-   validation performed and results;
-   diff stat/check;
-   per-file hunk summary;
-   scope audit;
-   blockers and deviations;
-   remaining requirements or risks.

For a diff larger than 500 lines, prefer SHA-256 plus per-file hunk
summary instead of copying the full diff into the review artifact.

A checkpoint is authoritative only for the state against which it was
produced. Material repository changes make it stale. A stale checkpoint
must be regenerated or explicitly revalidated before another critical
phase can be authorized.

## 6. Agent Task Contract

One task uses one fresh agent session unless the task explicitly requires
continuation in the same stateful session.

Each agent prompt must be self-contained and contain only what is needed:

-   one scope;
-   minimum necessary files and context;
-   explicit exclusions;
-   validation requirements;
-   latest authoritative review/checkpoint when relevant;
-   no unauthorized scope expansion.

Do not instruct an agent to read the entire repository or repository
history without demonstrated need. Current repository state and the
latest authoritative checkpoint override stale prompt assumptions.

Agents do not commit, push, delete data, deploy, or perform irreversible
actions without separate explicit authorization.

## 7. Agent Review Contract

A review should report, where applicable:

-   verdict;
-   checkpoint/state identity;
-   changed paths;
-   validation;
-   diff stat/check;
-   per-file hunk summary;
-   scope audit;
-   blockers/deviations.

The review should distinguish verified evidence from assumptions and
should not hide contradictions between the prompt and actual repository
state.

## 8. Phase Economy

Use the minimum ceremony that preserves control.

Before adding another agent or phase, ask whether the same control can be
obtained with:

1.  manual read-only commands;
2.  a lighter model;
3.  a combined standard/mechanical task;
4.  an existing authoritative checkpoint.

Do not reduce control around Brain, data, migrations, security, persisted
schemas, public behavior, or release merely to save tokens.

## 9. Relationship to Command Protocol

Command Protocol controls execution semantics. Engineering Workflow
controls lifecycle and transitions.

Examples:

- `//FIX` can implement the FIX phase;
- `//SHIP` can implement the SHIP readiness gate;
- `//SEEK` can implement the read-only SEEK phase;
- `//FIX` can implement an approved DESTROY phase;
- `//AGENT` can prepare a phase task;
- `CHECKPOINT` binds review evidence to state;
- `RECHECK` governs the next critical phase.

Do not create a generic `//ANALYSE` preset merely because ANALYSE exists
as a workflow phase. Select analytical primitives or presets according to
the actual problem.

## 10. Anti-Patterns

Avoid:

-   treating every task as critical;
-   running the full lifecycle for mechanical work;
-   using review as automatic permission to continue;
-   executing the next critical phase in the same task that performs its
    RECHECK;
-   carrying stale prompts forward after repository reality changes;
-   keeping a checkpoint authoritative after material state changes;
-   refactoring unrelated code during a bounded fix;
-   creating phases whose only output is ceremony;
-   reopening a shipped iteration for non-blocking SEEK findings instead
    of triaging them into the next iteration;
-   modifying code or data during SEEK instead of producing findings;
-   treating discovery as authorization for DESTROY;
-   interpreting DESTROY as permission for uncontrolled deletion or other
    irreversible actions.

## 11. Final Rule

**Maximum rigor where failure matters. Minimum ceremony everywhere else.**

**Trust is earned by evidence.\
Control creates evidence.\
Evidence allows trust.**

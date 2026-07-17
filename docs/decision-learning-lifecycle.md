# Decision Learning Lifecycle Design

## Purpose

NeuralEngine should become its own first real user by recording development
decisions, their execution, their results, and the reviewed lessons that follow.
The design extends durable memory from observations into explicit decision
history without replacing the existing Observation-to-Playbook learning chain.

The target workflow is:

```text
development event
-> Observation
-> Decision context
-> selected Decision
-> DecisionAction
-> DecisionOutcome
-> Experience
-> Knowledge
-> Playbook improvement
```

## Scope

This document defines implemented Decision foundation boundaries and future
boundaries for:

* recording a decision problem, alternatives, proposed selection, and rationale,
* explicitly accepting a proposed decision,
* recording actions, outcomes, and reviews as separate immutable records,
* referencing development evidence without ingesting large files,
* deriving decision lifecycle state,
* connecting reviewed outcomes to existing learning and Playbook evolution,
* dogfooding the workflow during NeuralEngine development,
* preventing duplicate capture, and
* sketching future CLI and implementation milestones.

`NeuralPaths.DECISIONS`, `NeuralPaths.DECISION_ACCEPTANCES`, and
`NeuralPaths.DECISION_ACTIONS` provide separate persistence directories. The
Decision, DecisionAcceptance, and DecisionAction foundations now
implement immutable domain records, persistence-focused ports, JSON adapters,
application services, container wiring, proposal/acceptance/action commands,
relation history, and the minimal canonical lifecycle projection. Later records
remain unimplemented.

## Implemented Decision Foundation

The implemented slice contains:

```text
Decision
EvidenceReference (embedded value only)
DecisionRepository
JsonDecisionRepository
DecisionService
Container wiring
neural decision add/list/show
```

`Decision` stores all fields listed in the Decision section below. Required
text is trimmed and must remain non-blank. Alternatives are trimmed, must contain
at least two values, reject case-insensitive duplicates, and the proposed option
must exactly match one stored alternative. Observation IDs must be unique.
Tags are trimmed and case-insensitive duplicates are removed while preserving
first-seen order. Decision and evidence timestamps are UTC-aware.

EvidenceReference is immutable and embedded in Decision JSON. `kind` and
`locator` are required, trimmed, non-blank, and bounded to 64 and 2048
characters respectively. Optional evidence text is trimmed, bounded, and may
not be blank when supplied. No evidence repository, service, or CLI exists.

`DecisionService.add()` validates referenced Observations through the
ObservationRepository port and validates that an optional superseded Decision
exists in the same project. The service loads all Decisions for idempotency,
persists only after validation, creates no other record, and performs no
lifecycle transition.

## Implemented DecisionAcceptance Foundation

The implemented acceptance slice contains:

```text
DecisionAcceptance
DecisionAcceptanceRepository
JsonDecisionAcceptanceRepository
DecisionAcceptanceService
Container wiring
neural decision accept/acceptance-history
```

`DecisionAcceptance` is immutable and stores `id`, `accepted_at`, `decision_id`,
`accepted_by`, `reason`, embedded `evidence_references`, `idempotency_key`, and
`tags`. The Decision UUID is validated; required text is trimmed and non-blank;
timestamps are normalized to UTC; tags use Decision normalization; and evidence
reuses the existing immutable `EvidenceReference`. It has no lifecycle status
and cannot embed or mutate the Decision payload.

`DecisionAcceptanceService.accept()` verifies the Decision, then loads
acceptance records through the persistence-focused repository. The first
acceptance is eligible. An equivalent replay under
`(decision_id, "decision_acceptance", idempotency_key)` returns the existing
record; the same key with a different semantic payload fails; and a second key
for an already accepted Decision fails. Identity, acceptance time, and evidence
capture times are excluded from semantic equivalence. Validation completes
before persistence, and Decision is never mutated.

`list_for_decision()` verifies the Decision and filters `load_all()` results in
the application layer while preserving repository order. `show()` owns explicit
acceptance not-found behavior. No relation-specific repository query exists.
Supersession does not invalidate acceptance: it creates a separate proposal and
introduces no rejection, withdrawal, reversal, reopening, cancellation, or
replacement transition.

The currently derivable projection is only:

```text
Decision without acceptance -> proposed
Decision with one valid acceptance -> accepted
```

Execution and reviewed states remain unavailable until later foundations exist.

## Implemented DecisionAction Foundation

`DecisionAction` records work actually performed under an accepted Decision. It
stores `id`, `recorded_at`, `decision_id`, `acceptance_id`, bounded
`action_type`, `summary`, `performed_by`, `started_at`, optional `completed_at`,
embedded evidence, optional `playbook_run_id`, `idempotency_key`, and normalized
tags. It is immutable, all timestamps are UTC-aware, and completion cannot
precede start. It has no mutable status and does not claim success, validation,
an outcome, review, or learning.

`DecisionActionService.add()` verifies the Decision, loads the exact acceptance,
requires that acceptance to belong to the Decision, and validates an optional
PlaybookRun exists before constructing or persisting the action. The current
PlaybookRun and Playbook schemas expose no project key, so no stronger project
compatibility assertion is currently derivable. Multiple distinct actions are
allowed. Idempotency is scoped by
`(decision_id, "decision_action", idempotency_key)` and excludes generated
action ID/time and evidence capture times from semantic equivalence.

The repository remains persistence-focused, while `list_for_decision()` filters
`load_all()` in the application layer and preserves repository order. The CLI
supports action add/history/show without executing commands or opening evidence.

`DecisionLifecycleService` is the only lifecycle projection owner. It validates
persisted relations and derives only `proposed`, `accepted`, or `in_progress`.
Repository order does not define state; the presence of valid semantic relations
does. Invalid action-to-acceptance relations and multiple persisted acceptances
fail visibly.

## Non-Goals

This foundation does not implement:

* DecisionOutcome or DecisionReview,
* file ingestion, git integration, or command execution,
* automatic Observation, Experience, Knowledge, or Playbook creation,
* automatic decision acceptance, execution, review, or evolution,
* Playbook mutation or PlaybookRevision materialization,
* Consigliere integration,
* Handbook generation or synchronization, or
* new dependencies.

## Terminology

**Development event** is an external fact from project work, such as an agent
prompt, review finding, validation run, commit, push, or Handbook sync.

**Decision** is an immutable proposal that captures one bounded problem,
alternatives considered, a proposed selection, rationale, provenance, and the
observations that established its context. Creation means `proposed`; it does
not mean accepted or executed.

**DecisionAcceptance** is an immutable manual or external-system confirmation
that a proposed Decision may be executed. It is separate because recommendation
and authority are different concerns.

**DecisionAction** is an immutable record of work performed under an accepted
Decision. More than one action may belong to one Decision.

**DecisionOutcome** is an immutable factual account of what happened after one
or more DecisionActions, including validation results and evidence references.

**DecisionReview** is an immutable assessment of one or more outcomes. It
records whether the decision was effective, review findings, and candidate
lessons. It does not itself create Experience, Knowledge, or Playbook changes.

**EvidenceReference** is a small immutable value embedded in a record. It points
to evidence and identifies it without copying the evidence body into
NeuralEngine.

**Derived lifecycle state** is a read model calculated from the immutable
records for a Decision. It is not a mutable status field on Decision.

## Proposed Records

The recommended sequence is deliberately staged:

```text
Decision
-> DecisionAcceptance
-> DecisionAction (one or more)
-> DecisionOutcome
-> DecisionReview
```

These should be separate records rather than one aggregate that accumulates
context, mutable status, actions, validation, review, and learning. Each future
repository should remain persistence-focused, and application services should
own cross-record validation and relation navigation.

### Decision

Recommended conceptual fields:

```text
id
created_at
project_key
title
objective
context_summary
alternatives
proposed_option
rationale
observation_ids
evidence_references
proposed_by
supersedes_decision_id
idempotency_key
tags
```

`alternatives` should preserve the options that were genuinely considered,
including significant risks or trade-offs. `proposed_option` is a recommendation
until a separate acceptance exists. A correction that materially changes the
problem, alternatives, selection, or rationale should create a new Decision
linked through `supersedes_decision_id`; the older record remains unchanged.

### DecisionAcceptance

Recommended conceptual fields:

```text
id
accepted_at
decision_id
accepted_by
reason
evidence_references
idempotency_key
tags
```

The initial model supports one acceptance per Decision. Rejection means the
proposal remains unaccepted; a replacement proposal is a new Decision. This
keeps the first lifecycle monotonic. Reopen, withdrawal, and reversal semantics
should not be introduced until a real workflow requires them.

### DecisionAction

Recommended conceptual fields:

```text
id
recorded_at
decision_id
acceptance_id
action_type
summary
performed_by
started_at
completed_at
evidence_references
playbook_run_id
idempotency_key
tags
```

The implemented `action_type` is a bounded string rather than a premature enum.
A `playbook_run_id` may be supplied when an existing PlaybookRun is relevant,
but it is not required for ad hoc development work.

### DecisionOutcome

Recommended conceptual fields:

```text
id
recorded_at
decision_id
action_ids
summary
result
validation_summary
evidence_references
idempotency_key
```

The outcome records facts: what completed, what failed, and what validation
reported. It must not infer generalized lessons or silently create downstream
learning records.

### DecisionReview

Recommended conceptual fields:

```text
id
reviewed_at
decision_id
outcome_ids
effectiveness
findings
corrective_decision_ids
lesson_candidates
reviewed_by
evidence_references
idempotency_key
```

Corrective work should be represented by a new Decision linked from the review,
not by rewriting the original Decision or Outcome. `lesson_candidates` are
review input only; promotion to Experience or Knowledge requires an explicit
later use case.

## Invariants

1. All decision workflow records are immutable after persistence.
2. Decision creation means proposed, not accepted or executed.
3. Acceptance must be explicit and attributable to a human or authorized
   external system.
4. Actions require an accepted Decision.
5. Outcomes reference existing actions for the same Decision.
6. Reviews reference existing outcomes for the same Decision.
7. Validation completes before any record is persisted.
8. Corrections append records; they do not rewrite history.
9. Evidence references identify provenance but do not imply that referenced
   content was ingested or verified.
10. Derived state has one canonical application-service owner.
11. Repository ports expose persistence operations, not lifecycle queries.
12. CLI handlers only translate input and render service results.
13. No record automatically creates Observation, Experience, Knowledge,
    Playbook, EvolutionProposal, or revision lifecycle artifacts.
14. No Consigliere recommendation is accepted merely because it exists.
15. No hidden mutation or automatic evolution is allowed.

## Lifecycle And State Derivation

The currently implemented lifecycle projection is monotonic:

```text
proposed -> accepted -> in_progress
```

The canonical `DecisionLifecycleService` derives state as follows:

* `proposed`: the Decision exists and no DecisionAcceptance exists,
* `accepted`: a valid DecisionAcceptance exists and no DecisionAction exists,
* `in_progress`: a valid DecisionAcceptance and at least one valid
  DecisionAction exist.

No `executed`, `completed`, `succeeded`, `failed`, or `reviewed` state is
available. Those require future DecisionOutcome or DecisionReview records.

The first model should not replay a generic status-event stream. Acceptance,
action, outcome, and review records already provide the authoritative events;
duplicating them as lifecycle events would create two sources of truth. If later
requirements introduce withdrawal, reopening, cancellation, or reversal, add a
dedicated immutable lifecycle event model and centralize replay in one service,
following the ownership lesson from `PlaybookRevisionActivationService`.

Repository order alone should not define chronology. Future projections should
use validated timestamps plus deterministic record IDs or explicit sequence
fields where ordering matters.

## Relationship To The Existing Domain Chain

Decision tracking complements the current chain; it does not replace any stage.

| Existing concept | Decision-learning relationship |
| --- | --- |
| Observation | Captures raw development facts. Decision references one or more observations as context. |
| Experience | Captures interpreted operational learning from reviewed outcomes. It is not a DecisionOutcome. |
| Knowledge | Generalizes one or more Experiences into reusable truth. It does not store decision history. |
| Playbook | Encodes a repeatable procedure supported by Knowledge. It is not mutated by a DecisionReview. |
| PlaybookRun | May be referenced by DecisionAction when an existing Playbook guided the work. |
| PlaybookEvaluation | Assesses that PlaybookRun and may use DecisionOutcome evidence without becoming a decision review. |
| EvolutionProposal | Proposes a Playbook improvement after explicit learning and evaluation. DecisionReview does not create it automatically. |
| PlaybookRevision | Holds an explicit immutable candidate snapshot resulting from an accepted proposal. |
| PlaybookRevisionActivation | Records lifecycle selection for a revision; it is unrelated to acceptance of a development Decision. |
| PlaybookRevisionApplication | Records revision application intent; it is not a DecisionAction and does not materialize content. |

The learning and Playbook-evolution bridges are explicit and separate:

```text
DecisionOutcome
-> DecisionReview
-> Experience
-> Knowledge

Knowledge -> new explicitly created Playbook

DecisionAction
-> referenced PlaybookRun
-> PlaybookEvaluation
-> EvolutionProposal
-> PlaybookRevision
-> PlaybookRevisionActivation
-> PlaybookRevisionApplication
```

Knowledge created from reviewed outcomes may later be selected explicitly as
supporting provenance for a PlaybookRevision. It does not bypass the existing
PlaybookRun, PlaybookEvaluation, and EvolutionProposal requirements for
improving an existing Playbook.

A future Experience provenance extension may reference DecisionOutcome IDs.
That schema change must be designed and reviewed separately. Until then, shared
Observation IDs and EvidenceReferences can preserve traceability without
claiming a direct implemented relation.

## Self-Observation Dogfooding Workflow

The first NeuralEngine development workflow should be:

| Step | Capture policy | Durable record or summary |
| --- | --- | --- |
| Prompt received | Automatic candidate; manual confirmation before persistence | Observation plus prompt EvidenceReference |
| Agent execution | Automatic candidate summary | No Decision state change; possible Observation references |
| Review finding | Automatic candidate; human confirms material findings | Observation plus review EvidenceReference |
| Decision or correction | Manual selection and rationale | Decision, then DecisionAcceptance |
| Implementation | Agent may prepare capture; caller confirms | One or more DecisionAction records |
| Validation | Command output may be summarized automatically; caller confirms association | DecisionOutcome evidence and validation summary |
| Commit | Automatic ingestion candidate after commit exists | EvidenceReference on Outcome or Review |
| Push | Automatic ingestion candidate after remote confirmation | EvidenceReference on Outcome or Review |
| Post-work lesson | Human or external review | DecisionReview, then explicit Experience creation |

Automatic candidates may discover paths, hashes, changed-file summaries, and
validation metadata. They must remain pending input until a user or authorized
external workflow explicitly asks NeuralEngine to persist them. Derived
summaries are replaceable views and must never be treated as source evidence.

The corrective architecture example maps cleanly:

```text
Observation: application service duplicated active-revision derivation
Decision: activation service remains the canonical owner
DecisionAction: remove local replay and inject/delegate to activation service
DecisionOutcome: validation passed with 537 tests
DecisionReview: ownership is explicit and repository replay is no longer duplicated
Experience: centralizing lifecycle derivation prevented architectural drift
Knowledge: lifecycle state derivation must have one canonical owner
Playbook improvement: architecture review checks responsibility ownership
```

## Consigliere Boundary

```text
Consigliere = reasoning and advisory layer
NeuralEngine = durable memory, audit, decisions, outcomes, learning, and playbooks
```

Consigliere may later analyze context, generate alternatives, assess risks,
recommend an option, or identify candidate lessons. Its output is external
recommendation evidence. NeuralEngine owns persistence, provenance, explicit
acceptance, actions, results, and reviewed promotion into Experience, Knowledge,
and Playbook evolution.

No Consigliere response may directly mutate NeuralEngine records, accept a
Decision, create learning artifacts, or apply a Playbook revision. Integration
requires a separate adapter and explicit application use cases in a future task.

## Evidence And Provenance Model

Use an embedded `EvidenceReference` value in Decision workflow records for the
initial design. Do not create a separately persisted evidence aggregate until
evidence itself needs lifecycle, access control, retention, or ingestion.

Recommended conceptual fields:

```text
kind
locator
repository_or_project
content_hash
captured_at
source
summary
```

Supported future `kind` values may include:

```text
agent_prompt
agent_review
git_commit
git_push
validation_run
changed_file_summary
handbook_sync
manual_decision
external_recommendation
```

`locator` should be a bounded identifier such as a repository-relative path,
commit hash, remote ref, review path, or validation-run key. It must not contain
file bodies or unrestricted command output. `content_hash` identifies the
referenced version when available; it does not prove authenticity by itself.

Observation remains the durable raw-fact record. Its current `source`,
`content`, and `tags` fields are too small to own all development provenance.
Decision records should reference Observation IDs and carry EvidenceReferences
for decision-specific traceability rather than copying observations or files.

## Idempotency Policy

Every future write service should accept an explicit non-blank idempotency key.
The initial duplicate policy is deterministic within a record type and project:

```text
(project_key, record_type, idempotency_key)
```

Recommended source keys are:

* prompt or review: normalized repository-relative path plus content hash,
* commit: repository identity plus full commit hash,
* push: repository identity plus remote, ref, and full commit hash,
* validation: command identity plus source commit or worktree fingerprint plus
  output hash,
* changed-file summary: source commit or worktree fingerprint plus sorted path
  hash,
* Handbook sync: source commit plus Handbook commit or generated artifact hash.

Repeated ingestion with the same key and equivalent payload should return the
existing record. The same key with a different payload should fail visibly; it
must not overwrite the first record. Path alone is insufficient because file
content can change. Commit hash is authoritative only for committed content and
must not identify an uncommitted validation run.

The first implementation should detect duplicates by loading and filtering in
the application service, matching current repository conventions. No
idempotency-specific repository query is justified initially.

## CLI And Future Sketch

The proposal, acceptance, action, and state commands are implemented:

```bash
neural decision add
neural decision list
neural decision show DECISION_UUID
neural decision accept DECISION_UUID --accepted-by OWNER --reason REASON --idempotency-key KEY
neural decision acceptance-history DECISION_UUID
neural decision action add DECISION_UUID
neural decision action-history DECISION_UUID
neural decision action-show ACTION_UUID
neural decision state DECISION_UUID
```

`decision add` uses repeatable options for collections. Evidence references use
repeatable bounded JSON values and are not ingested:

```bash
neural decision add \
  --project-key NeuralEngine \
  --title "Canonical lifecycle ownership" \
  --objective "Keep active revision derivation in one service" \
  --context-summary "Application service duplicated lifecycle replay" \
  --alternative "Delegate to activation service" \
  --alternative "Keep local replay" \
  --proposed-option "Delegate to activation service" \
  --rationale "One owner prevents semantic drift" \
  --proposed-by architecture-review \
  --idempotency-key decision-active-revision-owner \
  --observation-id OBSERVATION_UUID \
  --evidence '{"kind":"agent_review","locator":".agent-work/reviews/review.md"}' \
  --tag architecture
```

`decision accept` also supports repeatable bounded JSON `--evidence` and
repeatable `--tag` values. `acceptance-history` is read-only and renders a
controlled empty state when an existing Decision has no acceptance.

Action add requires acceptance ID, action type, summary, performer, ISO-8601
start time, and idempotency key. Completion time, PlaybookRun, evidence, and tags
are optional.

The following commands remain future-only and do not exist:

```bash
neural decision outcome add DECISION_UUID
neural decision review add DECISION_UUID

neural project ingest-review REVIEW_PATH
neural project ingest-commit COMMIT_HASH
```

The implemented handlers resolve application services from the container,
translate input, and render output. Outcome, review, and project ingestion
belong to later slices.

## First Implementation Milestone

The first slice is completed:

```text
Decision foundation
+ DecisionRepository port
+ JSON adapter using the existing NeuralPaths.DECISIONS directory
+ DecisionService add/list/show
+ thin neural decision add/list/show CLI
+ focused tests and documentation
```

This remains smaller than implementing the full decision workflow. It is
immediately useful for recording real NeuralEngine architecture decisions,
establishes provenance and idempotency conventions, and leaves acceptance, actions,
outcomes, reviews, ingestion, and learning for separately reviewed slices.

The milestone keeps Decision immutable, requires one bounded objective, at
least two meaningful alternatives, one proposed option that matches an
alternative, non-blank rationale, explicit provenance, and an idempotency key.
It does not automatically create Observations or downstream learning records.

The DecisionAcceptance and DecisionAction foundations are also complete. The
next recommended controlled slice is DecisionOutcome foundation only. It must
remain separate from DecisionReview.

## Risks And Rejected Alternatives

**One large Decision aggregate** was rejected because appending actions,
validation, outcomes, review, and lessons would require mutation or replacement
of an ever-growing record and would blur ownership.

**A mutable Decision status** was rejected because it loses transition history
and duplicates facts already represented by acceptance, action, outcome, and
review records.

**A generic lifecycle event stream in the first slice** was rejected because
semantic records already establish the monotonic lifecycle. Add replay only if
real reversible transitions require it.

**Decision as a replacement for Observation or Experience** was rejected.
Observation captures facts; Decision captures choice; Outcome captures result;
Experience captures interpreted operational learning.

**Embedding prompts, reviews, diffs, or validation logs** was rejected because
it would produce large unstable records and duplicate authoritative sources.

**A dedicated Evidence repository now** was rejected as premature. Embedded
references are sufficient until evidence has independent lifecycle needs.

**Automatic ingestion and learning** were rejected because they would hide
persistence decisions, weaken provenance, and cross the human-control boundary.

**Using Consigliere as durable storage** was rejected because advisory reasoning
and authoritative memory have different responsibilities.

## Handbook Synchronization Policy

Handbook synchronization remains a separate repository workflow:

```text
major NeuralEngine milestone
-> commit and push NeuralEngine
-> synchronize NeuralEngine-Handbook separately
-> generate the Handbook SKILL.md
-> copy the generated SKILL.md back to NeuralEngine
-> commit and push that synchronization separately
```

Agents working on NeuralEngine must not manually edit generated Handbook
artifacts. This design task does not perform any Handbook synchronization.

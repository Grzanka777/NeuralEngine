---
name: NeuralEngine Development
description: Apply this skill to every engineering task inside the NeuralEngine repository.
---

# NeuralEngine Development

## Mandatory first actions

1. Read `AGENTS.md`.
2. Read `.agent-work/project-state.md` when present.
3. Run baseline validation before changes.
4. Inspect relevant code and tests.
5. Keep scope minimal.

## Core rules

# NeuralEngine Constitution

## Mission

Build an engine that transforms observations into reusable knowledge, executable playbooks, evaluated outcomes, and controlled evolution.

## Core principles

1. Correctness before speed.
2. Domain before persistence.
3. Explicit dependencies before convenience.
4. Architecture before implementation shortcuts.
5. Deterministic behavior where practical.
6. Validation before persistence.
7. Small coherent changes.
8. Tests as executable specifications.
9. Review evidence before success claims.
10. No commits or pushes by agents.

## Forbidden

- Business logic in CLI handlers.
- Business logic in infrastructure adapters.
- Hidden dependencies.
- Global mutable state.
- Silent validation failure.
- Scope expansion.
- Unrelated refactoring.
- Repository interfaces used as service APIs.
- Manual edits to generated handbook outputs.

## Architecture

# Architecture

NeuralEngine follows a hexagonal architecture.

## Layers

- Domain
- Application
- Ports
- Infrastructure
- CLI

## Dependency rules

- Domain depends on no outer layer.
- Application depends on domain and ports.
- Infrastructure implements ports.
- CLI invokes application services.
- Dependency construction belongs in the container.
- Infrastructure must never depend on CLI.

## Responsibility rules

- Entities and value objects own domain invariants.
- Application services own use cases.
- Repository ports define persistence contracts.
- Adapters implement persistence contracts.
- CLI translates input and renders output.
- Relationship navigation should be composed in services when it does not belong in persistence.

## Revision lifecycle and application boundary

The current end of the domain chain is deliberately split across three immutable records:

```text
PlaybookRevision
→ PlaybookRevisionActivation
→ PlaybookRevisionApplication
```

`PlaybookRevision` is a candidate snapshot. `PlaybookRevisionActivation` records lifecycle and
audit decisions. `PlaybookRevisionApplication` records application intent and audit state.
Activation does not imply application.

`PlaybookRevisionActivationService.get_active_revision_for_playbook(playbook_id)` is the canonical
owner of active-revision resolution. `PlaybookRevisionApplicationService` delegates to it and must
not duplicate activation-history replay.

The application foundation has a domain model, repository port, JSON adapter at
`NeuralPaths.PLAYBOOK_REVISION_APPLICATIONS`, and container wiring for both repository and service.
`PlaybookRevisionApplicationService.add(...)` validates that the Playbook, revision, and proposal
exist; the proposal is still accepted; the revision belongs to the supplied Playbook and proposal;
an optional source activation exists and matches the same relation; and the requested revision is
currently active.

Read-only application navigation verifies the source entity, calls
`PlaybookRevisionApplicationRepository.load_all()`, filters in the application layer, and preserves
repository order. No relation-specific repository query methods exist.

Activation inspection and lifecycle-write CLI commands exist. Application CLI commands do not.
Records created by the current application service have `content_changed=False`; there is no
Playbook content mutation, revision materialization, proposal mutation or application, proposal
status change, or automatic evolution.

This architecture snapshot corresponds to source commit `88921c5` (`feat: add playbook revision
application foundation`). Source validation for that milestone reported 537 passing tests; this is
a milestone snapshot, not a timeless guarantee.

## Decision Learning boundary

Source commit `18788adacf75ff7f11d0dd6f28e5da8cf143081b` preserves the separate immutable
`Decision`, `DecisionAcceptance`, `DecisionAction`, `DecisionOutcome`, and `DecisionReview`
records, persistence-focused ports and JSON adapters, application services, container wiring,
thin proposal/acceptance/action/outcome/review CLI commands, and the canonical
`DecisionLifecycleService`. An action records work performed; only a linked outcome records
factual results and validation evidence; a review records authorized interpretation.

`DecisionOutcome` links one Decision, its acceptance, and one or more ordered unique actions. Its
result is exactly `succeeded`, `failed`, `partial`, or `unknown`; scalar metrics are immutable.
Multiple outcomes form history, and the non-persisted `DecisionOutcomeSummary` derives counts and
the latest outcome using `(validated_at, outcome.id)` rather than repository order.
`DecisionReview` targets an explicit ordered non-empty set of outcomes for one Decision and
acceptance. Multiple reviews form immutable history ordered by `(reviewed_at, review.id)`.

The same checkpoint implements explicit Review-to-Experience promotion. One Experience may embed
optional immutable `DecisionReviewPromotion` provenance containing ordered copied Review
statements. `ExperienceService` uses the validated Review service boundary and existing Experience
repository; no promotion aggregate, repository, adapter, path, Brain collection, or automatic
learning exists. Old and ordinary Experiences remain compatible.

The checkpoint also hardens the existing explicit Knowledge slice. `KnowledgeService` depends on
the narrow application-facing `ExperienceReader.get_by_id()` protocol, and the container supplies
`ExperienceService` as its implementation. Knowledge creation and returned Knowledge relations
therefore reuse `ExperienceService.get_by_id()` as the single owner of persisted Review-promotion
provenance validation. The dependency remains acyclic because `ExperienceService` has no
KnowledgeService dependency.

`KnowledgeService.add()` rejects empty evidence before relation reads, validates IDs in caller
order, preserves duplicates, and writes only after every read succeeds. `add_from_experience()`
uses the same boundary. Complete list and present single-item reads validate every stored
Experience relation; the scoped Experience navigation validates its requested Experience and all
relations of matching Knowledge records while leaving unrelated records outside the query.
Missing Experiences retain `ExperienceNotFoundError`, while canonical DecisionReview and
promotion errors propagate unchanged.

The canonical lifecycle states remain exactly `proposed`, `accepted`, `in_progress`, `succeeded`,
`failed`, `partial`, and `outcome_unknown`. Review is orthogonal append-only history; there is no
`reviewed`, `promoted`, or `learned` state. Outcome or review creation does not create learning;
only the explicit promotion use case creates an Experience, which remains distinct from Knowledge.
There is no execution engine, lifecycle reversal, ingestion, automatic learning or evolution,
generic event replay, or
Consigliere integration. The authoritative implemented contract and future boundary are defined
in `handbook/architecture/decision-learning.md`. Generic Knowledge creation is already explicit;
`neural experience knowledge` is read-only navigation. Storing Knowledge alone does not prove
later use or improvement.

## Durable operational Knowledge use and feedback

Durable Playbook-scoped Knowledge use and Run feedback already exist:

```text
PlaybookRun -> zero or one PlaybookRevision
PlaybookRevision -> zero or many PlaybookRuns
authority -> explicit Run caller
```

Run write validation requires actions, then the base Playbook, then a supplied revision, then
same-Playbook revision ownership; only then may one Run be saved. `get_by_id()`, complete lists,
Playbook-scoped lists, and revision-scoped lists validate linked revision existence and ownership.
Corrupt linked provenance fails closed, while old Run JSON without `revision_id` loads as `None`
without migration, backfill, or inference.

```text
Knowledge
→ Playbook.knowledge_ids
→ PlaybookRun(playbook_id, revision_id?)
→ PlaybookEvaluation.run_id
→ EvolutionProposal(playbook_id, evaluation_ids)
```

The caller explicitly selects exact Knowledge UUIDs into a Playbook, declares that the Playbook
was manually or externally applied by recording a Run, and may additionally declare zero or one
exact immutable PlaybookRevision whose content was used. The Run caller is the authority for that
optional declaration. The caller then evaluates that exact Run and may create an EvolutionProposal
from exact Evaluation IDs. `EvolutionProposalService` verifies that every referenced Evaluation's
Run belongs to the target Playbook.

The exact persisted feedback path is:

```text
PlaybookEvaluation.run_id
→ PlaybookRun(revision_id?, playbook_id)
→ Playbook.knowledge_ids
→ Knowledge.id
```

Decision learning provides an optional persisted bridge:

```text
DecisionOutcome.action_ids
→ DecisionAction.playbook_run_id?
→ PlaybookRun(revision_id?, playbook_id)
→ Playbook.knowledge_ids
```

The bridge is optional because `DecisionAction.playbook_run_id` is optional. A DecisionOutcome
references exact DecisionAction IDs, but an action without a Run relation supplies no Playbook or
Knowledge-use provenance.

These relations provide feedback at Playbook and declared Knowledge-set scope and preserve an
explicit Run revision relation transitively. Evaluation, EvolutionProposal, and DecisionAction do
not store a revision ID directly. The relations do not record durable retrieval history or
recommendation events, prove that one Knowledge item caused an outcome, attribute contributions
within a multi-Knowledge Playbook, or demonstrate causal or comparative improvement.

Revision provenance is never inferred from current active revision, activation history,
repository order, timestamps, `PlaybookRevisionApplication`, or application-intent records. A
revision need not be active or applied for the caller to truthfully declare that its content was
used. `revision_id=None` covers base Playbook execution, legacy records, and unknown revision
provenance and makes no revision-specific claim. Selection, Run recording, Evaluation, Proposal
creation, and decision linkage remain explicit caller actions; none triggers automatic learning,
mutation, materialization, activation, application, or evolution.

## Decision Learning architecture

# Decision Learning Architecture

## Status and purpose

NeuralEngine source commit `18788adacf75ff7f11d0dd6f28e5da8cf143081b` implements the Decision,
DecisionAcceptance, DecisionAction, DecisionOutcome, and DecisionReview foundations plus the
canonical `DecisionLifecycleService` projection. They record an immutable proposed choice,
explicit authorization, work performed under that authorization, factual results, and authorized
interpretation, plus explicit promotion of selected Review statements into an existing Experience.
Each foundation persists its durable records, exposes application use cases, is wired through the
container, and provides a thin CLI.

The wider Decision Learning lifecycle remains accepted future architecture. Decision tracking
complements the existing Observation-to-Playbook chain; it does not replace it.

## Implemented foundation

The implemented foundations are exactly:

```text
Decision
EvidenceReference
DecisionAcceptance
DecisionAction
DecisionOutcome
DecisionReview
DecisionReviewPromotion
DecisionReviewPromotionSourceStatement
DecisionRepository
DecisionAcceptanceRepository
DecisionActionRepository
DecisionOutcomeRepository
DecisionReviewRepository
JsonDecisionRepository
JsonDecisionAcceptanceRepository
JsonDecisionActionRepository
JsonDecisionOutcomeRepository
JsonDecisionReviewRepository
DecisionService
DecisionAcceptanceService
DecisionActionService
DecisionOutcomeService
DecisionOutcomeSummary
DecisionReviewService
ExperienceService.add_from_decision_review
ExperienceReader
KnowledgeService
DecisionLifecycleService
container wiring
neural decision add/list/show
neural decision accept
neural decision acceptance-history
neural decision action add
neural decision action-history
neural decision action-show
neural decision outcome add
neural decision outcome-history
neural decision outcome-show
neural decision outcome-summary
neural decision review add
neural decision review history
neural decision review show
neural experience from-review
neural knowledge add/list/show
neural knowledge from-experience
neural experience knowledge
neural decision state
```

Creating a Decision records a proposal. Creating a DecisionAcceptance explicitly authorizes that
proposal for possible future work. Creating a DecisionAction records work performed under that
acceptance. Creating a DecisionOutcome records factual results and validation evidence for one or
more linked actions. Creating a DecisionReview records authorized interpretation over an explicit
ordered outcome set. None of these operations automatically creates learning.
Only the separate authorized Review-to-Experience promotion use case creates one Experience from
selected copied Review interpretation; that Experience remains distinct from Knowledge.

## Decision model

`Decision` is an immutable domain model with these implemented fields:

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

Its implemented invariants are:

1. Required text is trimmed and non-blank.
2. At least two meaningful alternatives are required.
3. Alternatives reject case-insensitive duplicates.
4. `proposed_option` exactly matches one stored alternative.
5. Observation IDs are unique.
6. An optional superseded Decision must not equal the new Decision.
7. Tags are trimmed; case-insensitive duplicates are removed while first-seen order is preserved.
8. `created_at` is timezone-aware and normalized to UTC.
9. The model is immutable.
10. No mutable lifecycle status exists.

A material correction creates another Decision linked through `supersedes_decision_id`; it does
not rewrite the earlier record.

## EvidenceReference

`EvidenceReference` is an implemented immutable value embedded in a Decision,
DecisionAcceptance, DecisionAction, DecisionOutcome, or DecisionReview:

```text
kind
locator
repository_or_project
content_hash
captured_at
source
summary
```

`kind` and `locator` are required, trimmed, non-blank, and bounded. Optional text is trimmed,
bounded, and cannot be blank when supplied. `captured_at` is timezone-aware and normalized to UTC.
The complete value is serialized inside Decision JSON.

There is no Evidence repository, service, or CLI. A locator is retained as provenance only: the
Decision CLI does not open it, verify it, or ingest its content.

## DecisionAcceptance foundation

`DecisionAcceptance` is an immutable domain model with these implemented fields:

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

Its implemented invariants are:

1. `decision_id` is a valid UUID.
2. `accepted_by` is trimmed and non-blank.
3. `reason` is trimmed and non-blank.
4. `idempotency_key` is trimmed and non-blank.
5. `accepted_at` is timezone-aware and normalized to UTC.
6. Tags are trimmed, reject blanks, and remove case-insensitive duplicates while preserving
   first-seen order.
7. Evidence references reuse the existing immutable `EvidenceReference`.
8. The model is immutable.
9. No mutable lifecycle status exists.
10. Acceptance does not embed or mutate the Decision payload.

The semantic boundary is exact:

```text
Decision
= proposed choice

DecisionAcceptance
= explicit authorization for possible future execution
```

Acceptance does not mean execution occurred, a DecisionAction exists, a DecisionOutcome exists, a
DecisionReview exists, or learning was created.

## DecisionAction foundation

`DecisionAction` is an immutable domain model with these exact implemented fields:

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

Its implemented invariants are:

1. Decision and acceptance IDs are valid UUIDs.
2. `action_type`, `summary`, `performed_by`, and `idempotency_key` are trimmed and non-blank.
3. `action_type` is bounded to 64 characters.
4. `recorded_at`, `started_at`, and optional `completed_at` are timezone-aware and normalized to
   UTC.
5. `completed_at` cannot precede `started_at`.
6. Tags are normalized like Decision tags.
7. Evidence reuses immutable embedded `EvidenceReference`.
8. Optional `playbook_run_id` is a UUID.
9. The model is immutable.
10. No mutable status field exists.
11. Decision and DecisionAcceptance payloads are not embedded or mutated.

The semantic boundary is exact:

```text
DecisionAction
= work was performed under an explicitly accepted Decision
```

It does not mean the work succeeded, validation passed, an intended result occurred,
DecisionOutcome exists, DecisionReview exists, or learning was created. `completed_at` means only
that the described work interval ended. It does not by itself produce a `completed`, `executed`,
or `succeeded` lifecycle state.

## DecisionOutcome foundation

`DecisionOutcome` is an immutable factual result and validation record with these exact
implemented fields:

```text
id
recorded_at
decision_id
acceptance_id
action_ids
result
summary
validated_by
validated_at
evidence_references
metrics
idempotency_key
tags
```

Its implemented invariants are:

1. Decision, acceptance, and action IDs are valid UUIDs.
2. At least one action ID is required; action IDs are ordered and unique.
3. `result` is exactly `succeeded`, `failed`, `partial`, or `unknown`.
4. `summary`, `validated_by`, and `idempotency_key` are trimmed and non-blank.
5. `recorded_at` and `validated_at` are timezone-aware and normalized to UTC.
6. Metrics contain at most 100 scalar `int | float | str | bool` values.
7. Metric keys are trimmed, non-blank, at most 64 characters, and case-insensitively unique.
8. Float metrics are finite, string metrics are bounded to 1000 characters, and nested values are
   rejected.
9. The metric mapping is immutable and serialized in deterministic key order.
10. Tags and evidence use the existing normalization and immutable `EvidenceReference` rules.
11. The model is immutable and has no mutable lifecycle status.

One Decision may have multiple outcomes. Each outcome appends factual history and may link one or
more actions; no outcome replaces or mutates an earlier record. An outcome does not mean review,
Experience, Knowledge, Playbook change, or automatic learning occurred.

## DecisionReview foundation

`DecisionReview` is an immutable, append-only authorized interpretation record with these exact
implemented fields:

```text
id
recorded_at
decision_id
acceptance_id
outcome_ids
reviewed_by
reviewed_at
assessment
summary
findings
candidate_lessons
evidence_references
confidence
idempotency_key
tags
```

Assessment is exactly `sound`, `flawed`, `mixed`, or `inconclusive`; confidence is exactly `low`,
`medium`, or `high`. Assessment is not the outcome result vocabulary: successful factual outcomes
may support a flawed review, and failed outcomes may support a sound review.

`outcome_ids` is ordered, unique, and non-empty. Findings are required ordered text; findings and
candidate lessons each allow at most 100 case-insensitively unique entries of at most 1000
characters. Candidate lessons may be empty and have no promotion authority. Reviewer is bounded to
255 characters and summary to 1000; required text is trimmed and non-blank. Tags preserve
first-seen order while removing case-insensitive duplicates. UTC-aware timestamps are normalized
to UTC, and `reviewed_at` cannot be later than `recorded_at`.

Every outcome must exist and belong to the same Decision and acceptance. Review time cannot
precede the latest `validated_at` among selected outcomes. Action IDs are not persisted: provenance
is transitive through `DecisionReview → DecisionOutcome[] → DecisionAction[]`. Multiple reviews
may cover one Decision, outcome, or ordered outcome set under different keys. Corrections append;
there is no replacement, supersession, deletion, or persisted `current` behavior.

## DecisionReview-to-Experience promotion foundation

At source commit `1b45beb`, `Experience` has optional immutable
`decision_review_promotion: DecisionReviewPromotion | None`. Plain direct and
Observation-derived Experiences retain `None`. Promotion contains exactly one Review ID, ordered
non-empty immutable source statements, promoter, reason, and idempotency key. Each statement stores
exactly `kind`, zero-based non-negative `index`, and exact copied `text`; kind is exactly `finding`
or `candidate_lesson`, and `(kind, index)` pairs are unique.

Promoter and key are bounded to 255 characters; reason and copied text are bounded to 1000. All are
trimmed and non-blank. Reviewer and promoter are separate explicit authorities. Promotion copies no
Decision, acceptance, action, outcome, reviewer, assessment, confidence, or evidence fields into
Experience. One Experience references one Review and one or more selected statements; one Review
and one source statement may produce multiple Experiences under different keys. Corrections append.

The implemented chain is:

```text
Observation
→ Decision
→ DecisionAcceptance
→ DecisionAction
→ DecisionOutcome
→ DecisionReview
→ explicitly promoted Experience
→ separately and explicitly created Knowledge
```

Review save does not promote. Promotion does not create Knowledge or change Decision lifecycle.
`DecisionReview.assessment`, `DecisionOutcome.result`, and `Experience.result` remain distinct.

## Persistence

The persistence-focused `DecisionRepository` port implements only:

```text
save()
load_all()
get_by_id()
```

No relation, project, or idempotency query was added. `JsonDecisionRepository` stores one JSON
file per Decision under `NeuralPaths.DECISIONS`. UUIDs, UTC-aware timestamps, embedded evidence,
and optional values round-trip through the domain model. `load_all()` sorts file names for
deterministic order. Malformed stored data surfaces domain validation errors; the adapter does not
silently repair it. No migration, evidence ingestion, file ingestion, or git ingestion behavior
exists.

The persistence-focused `DecisionAcceptanceRepository` likewise implements only:

```text
save()
load_all()
get_by_id()
```

It has no relation, project, or idempotency query methods. Relation and eligibility filtering
belong to `DecisionAcceptanceService`. `JsonDecisionAcceptanceRepository` stores one JSON file per
acceptance under `NeuralPaths.DECISION_ACCEPTANCES`, and Brain initialization creates that
directory. `load_all()` sorts file names for deterministic order. UUIDs, UTC-aware timestamps,
embedded evidence, and normalized tags round-trip through domain validation. Malformed stored data
surfaces validation errors. No migration or ingestion behavior exists.

The persistence-focused `DecisionActionRepository` implements only:

```text
save()
load_all()
get_by_id()
```

It has no relation, idempotency, or lifecycle query methods. Filtering and relation validation
remain in application services. `JsonDecisionActionRepository` stores one JSON file per action
under `NeuralPaths.DECISION_ACTIONS`, and Brain initialization creates that directory.
`load_all()` sorts file names for deterministic order. The complete domain record round-trips
through validation, and malformed stored data fails visibly. The adapter performs no migration,
ingestion, or command execution.

The persistence-focused `DecisionOutcomeRepository` also implements only:

```text
save()
load_all()
get_by_id()
```

It has no relation, idempotency, latest-outcome, summary, or lifecycle query methods.
`JsonDecisionOutcomeRepository` stores one deterministic JSON file per outcome under
`NeuralPaths.DECISION_OUTCOMES`, and Brain initialization creates that directory. Complete records
and immutable scalar metrics round-trip through domain validation; malformed data fails visibly.
The adapter performs no relation filtering, lifecycle projection, review, learning, migration, or
ingestion.

The persistence-focused `DecisionReviewRepository` implements only:

```text
save()
load_all()
get_by_id()
```

It has no relation, idempotency, chronology, or lifecycle query methods.
`JsonDecisionReviewRepository` stores one deterministic sorted-key JSON file per review under
`NeuralPaths.DECISION_REVIEWS`, and Brain initialization creates that directory. `load_all()` sorts
filenames and every record round-trips through domain validation. Filtering, relation validation,
history ordering, ambiguity detection, and semantic comparison remain in the application service.

The existing `ExperienceRepository` also remains limited to:

```text
save()
load_all()
get_by_id()
```

`JsonExperienceRepository` continues to store one JSON file per Experience under
`NeuralPaths.EXPERIENCES` and round-trips the optional embedded promotion through domain
validation. Old JSON without the field loads with `None`. No migration, new path, Brain directory,
link record, promotion repository, second write, or production adapter rewrite was introduced.
Idempotency and Review integrity remain application policy.

The existing `KnowledgeRepository` remains limited to:

```text
save()
load_all()
get_by_id()
```

No Knowledge relation or provenance query was added. `JsonKnowledgeRepository` and the Knowledge
JSON schema are unchanged. Knowledge membership filtering and relation validation remain
application policy.

## Application service

`DecisionService` implements:

```text
add()
list_decisions()
show()
```

`add()` constructs an immutable Decision candidate first, validates every referenced Observation,
then validates an optional superseded Decision. A superseded Decision must exist and have the same
`project_key`. Only after these checks does the service perform idempotency detection and, when
needed, persist the candidate. It creates no other record, performs no lifecycle transition, and
does not trigger learning.

The implemented idempotency scope is:

```text
(project_key, "decision", idempotency_key)
```

The `"decision"` record type is implicit because the operation is owned by `DecisionService`.
Detection uses `DecisionRepository.load_all()` followed by application-layer filtering; there is
no repository idempotency query.

```text
same key + equivalent semantic payload
→ return existing Decision

same key + different semantic payload
→ visible conflict, no write
```

Semantic equivalence excludes generated identity and time values:

```text
Decision.id
Decision.created_at
EvidenceReference.captured_at
```

`list_decisions()` preserves repository order. Its optional project filter is trimmed and applied
in the application layer; a blank filter fails visibly. `show()` loads by UUID and raises the
existing explicit not-found error when no Decision exists.

### DecisionAcceptanceService

`DecisionAcceptanceService` implements:

```text
accept()
list_for_decision()
show()
```

`accept()` validates that the referenced Decision exists, constructs an immutable candidate, loads
all acceptance records, handles an equivalent idempotent replay, rejects conflicting key reuse,
rejects a second distinct acceptance, and persists only after validation. It does not mutate the
Decision and creates no action, outcome, review, or learning record.

The initial monotonic eligibility rule is:

```text
Decision exists
and no DecisionAcceptance exists
→ eligible for first acceptance
```

Only one acceptance per Decision is allowed. A superseding Decision does not invalidate an
existing acceptance. There is no rejection, withdrawal, reversal, reopening, cancellation, or
replacement behavior.

The implemented idempotency scope is:

```text
(decision_id, "decision_acceptance", idempotency_key)
```

```text
same scoped key + equivalent semantic payload
→ return existing DecisionAcceptance

same scoped key + different semantic payload
→ visible idempotency conflict, no write

different key + Decision already accepted
→ visible already-accepted conflict, no write
```

Semantic equivalence excludes:

```text
DecisionAcceptance.id
DecisionAcceptance.accepted_at
EvidenceReference.captured_at
```

`list_for_decision()` validates Decision existence, loads all acceptance records, filters in the
application layer, and preserves repository order without adding a repository query. `show()`
raises an explicit acceptance not-found error.

### DecisionActionService

`DecisionActionService` implements:

```text
add()
list_for_decision()
show()
```

`add()` validates Decision existence, acceptance existence, and that the acceptance belongs to the
same Decision. It validates an optional PlaybookRun exists, constructs an immutable candidate,
performs idempotency detection, returns an equivalent replay, rejects conflicting key reuse,
allows multiple distinct actions, and persists only after every validation. It mutates neither
Decision nor DecisionAcceptance and creates no Outcome, Review, Experience, Knowledge, Playbook,
or EvolutionProposal.

The current PlaybookRun limitation is explicit:

```text
PlaybookRun and Playbook currently expose no project_key,
so only existence can be validated without a separately reviewed schema change.
```

Action idempotency is scoped by:

```text
(decision_id, "decision_action", idempotency_key)
```

```text
same scoped key + equivalent semantic payload
→ return existing DecisionAction

same scoped key + different semantic payload
→ visible conflict, no write

different key
→ another action may be recorded
```

Semantic equivalence excludes:

```text
DecisionAction.id
DecisionAction.recorded_at
EvidenceReference.captured_at
```

`list_for_decision()` validates the Decision, filters `load_all()` in the application layer, and
preserves repository order. `show()` raises an explicit action-not-found error.

### DecisionOutcomeService

`DecisionOutcomeService` implements:

```text
add()
list_for_decision()
show()
summary_for_decision()
```

`add()` validates Decision existence, acceptance existence and ownership, at least one unique
action, and every action's Decision and acceptance relations. `validated_at` cannot precede the
earliest linked action start. Only after relation validation does the service construct and save
the immutable outcome. It mutates no related record and creates no Review or learning artifact.

Outcome idempotency is scoped by:

```text
(decision_id, "decision_outcome", idempotency_key)
```

```text
same scoped key + equivalent semantic payload
→ return existing DecisionOutcome

same scoped key + different semantic payload
→ visible conflict, no write

more than one persisted scoped match
→ `DecisionOutcomeIdempotencyAmbiguityError`, no arbitrary selection, no write

different key
→ another outcome may be recorded
```

Semantic equivalence excludes `DecisionOutcome.id`, `DecisionOutcome.recorded_at`, and embedded
`EvidenceReference.captured_at`. It includes the linked relations, result, validation data,
metrics, and other caller-supplied semantic fields.

`list_for_decision()` validates the Decision, filters `load_all()` in the application layer, and
preserves repository order so the complete multiple-outcome history remains visible. `show()`
raises an explicit outcome-not-found error.

`DecisionOutcomeSummary` is an immutable, non-persisted application read model returned by
`summary_for_decision()`. It reports outcome count, latest result and validation time, distinct
linked-action count, counts for each result value, and success/failure presence. Summary derivation
validates every persisted outcome-to-acceptance/action relation. Latest selection is deterministic
by `(validated_at, outcome.id)` and never depends on repository order. The summary is derived on
demand and is neither persisted nor cached.

More than one matching persisted outcome always raises ambiguity before selecting or semantically
comparing a record. This is independent of repository enumeration order and applies to equivalent
and different duplicate payloads. Zero matches follows normal creation; exactly one match retains
the equivalent-replay or conflict behavior. This hardening changes no outcome fields, vocabulary,
relations, ordering, summary, CLI, stored schema, or lifecycle behavior.

### DecisionReviewService

`DecisionReviewService` implements:

```text
add()
list_for_decision()
show()
```

`add()` constructs the candidate first, so local domain validation precedes repository reads. It
then requires the Decision, validates the acceptance belongs to it, loads every caller-ordered
outcome by ID, validates Decision and acceptance ownership, and requires `reviewed_at` to be at or
after the latest selected outcome validation. Missing or mismatched relations and invalid time all
fail before persistence.

Review idempotency is scoped by:

```text
(decision_id, "decision_review", idempotency_key)
```

```text
zero scoped matches
→ save the validated candidate

exactly one equivalent match
→ validate persisted relations and return existing DecisionReview

exactly one different match
→ `DecisionReviewIdempotencyConflictError`, no write

more than one persisted scoped match
→ `DecisionReviewIdempotencyAmbiguityError`, no arbitrary selection or comparison, no write
```

The ambiguity error carries Decision ID, idempotency key, and match count. Ambiguity is independent
of repository order and applies to semantically equivalent or different duplicates. For exactly
one match, semantic equivalence excludes generated review ID and recording time and embedded
evidence capture times; it includes every caller-supplied semantic field. Ordered outcome IDs,
findings, candidate lessons, evidence, and tags therefore remain order sensitive.

`list_for_decision()` requires the Decision, validates every persisted relation, and sorts by
`(reviewed_at, review.id)`. `show()` loads by ID and validates its relations. Controlled errors
cover missing Decision, acceptance, outcome, or review; acceptance/Decision mismatch;
outcome/Decision or outcome/acceptance mismatch; review before outcome; idempotency conflict; and
duplicate-key ambiguity. No failing path writes.

DecisionReview and DecisionOutcome share the reusable fail-closed invariant that multiple matches
for a scoped idempotency key must be surfaced, never resolved through `next()`, first-match
selection, repository order, or comparison with an arbitrarily chosen record. Their scopes and
ambiguity error types remain separate.

### ExperienceService Review promotion

`ExperienceService.add_from_decision_review(...)` validates selectors and bounded authority
metadata before calling `DecisionReviewService.show()`. It then copies caller-ordered exact Review
items, validates optional Observations, constructs one promoted Experience, loads all Experiences,
and applies this scope:

```text
(decision_review_id, "review_experience_promotion", idempotency_key)
```

```text
zero matches
→ save and return one promoted Experience

exactly one equivalent match
→ validate its provenance and return original ID/timestamp, no write

exactly one different match
→ `DecisionReviewPromotionIdempotencyConflictError`, no write

more than one match
→ `DecisionReviewPromotionIdempotencyAmbiguityError`, no selection or comparison, no write
```

Equivalence excludes only generated `Experience.id` and `Experience.timestamp`; every ordinary
Experience field, optional Observation ID, tag, and ordered promotion value remains semantic.
Ambiguity is repository-order independent.

Replay, `get_by_id()`, complete list, and Observation-linked list revalidate the referenced Review
graph, selector bounds, and exact copied text. Missing or malformed provenance fails closed without
repair or skipping; plain records bypass promotion validation. The use case owns no Knowledge,
Playbook, evolution, lifecycle, evidence, or Consigliere behavior.

### KnowledgeService validated Experience boundary

The existing generic `KnowledgeService` implements:

```text
add()
add_from_experience()
list_knowledge()
list_for_experience()
get_by_id()
```

It depends on `KnowledgeRepository` and the application-facing `ExperienceReader.get_by_id()`
protocol defined beside the service. `ExperienceService` implements the protocol, so
`ExperienceService.get_by_id()` remains the single owner of persisted Review graph, promotion
selector, and copied-text validation. KnowledgeService no longer reads `ExperienceRepository`
directly, loads DecisionReview, or duplicates another service's validation. ExperienceService has
no KnowledgeService dependency, so the graph is acyclic.

`add()` rejects empty evidence before relation reads, validates supplied Experience IDs in caller
order, preserves duplicates, and saves only after every validation succeeds.
`add_from_experience()` validates its source through the same reader and performs no save when it
is missing or corrupt.

`list_knowledge()` validates every Experience relation of every loaded record in repository and
relation order and fails closed without partial results. `get_by_id()` performs no Experience read
when Knowledge is absent and validates every relation of a present record.
`list_for_experience()` validates the requested Experience first, filters Knowledge in repository
order, validates every relation of every matching record, and deliberately leaves unrelated
Knowledge records outside this scoped validation.

Missing relations continue to raise `ExperienceNotFoundError`. Existing `DecisionReviewError` and
`DecisionReviewPromotionError` instances propagate unchanged. The five affected CLI surfaces
render those failures as controlled nonzero errors without tracebacks. Validation is exactly the
existing ExperienceService read contract; it does not recursively revalidate every Observation or
DecisionAction ancestry relation.

This hardening changes no Knowledge or Experience schema, authority, cardinality, duplicate-ID
behavior, Knowledge idempotency, repository, adapter, JSON format, command, or automatic behavior.
It performs one validated Experience read per stored relation, including duplicates. The linear
read amplification is accepted in favor of fail-closed integrity; no caching, batching, or
deduplication was added.

### Canonical DecisionLifecycleService

`DecisionLifecycleService` is the only canonical owner of the current lifecycle projection. It
depends on:

```text
DecisionRepository
DecisionAcceptanceRepository
DecisionActionRepository
DecisionOutcomeRepository
```

It derives exactly:

```text
Decision exists, no acceptance
→ proposed

Decision exists, one valid acceptance, no action
→ accepted

Decision exists, one valid acceptance, at least one valid action
→ in_progress

latest valid outcome has result succeeded
→ succeeded

latest valid outcome has result failed
→ failed

latest valid outcome has result partial
→ partial

latest valid outcome has result unknown
→ outcome_unknown
```

No mutable status is written and no generic event stream exists. The latest outcome is selected by
`(validated_at, outcome.id)`, never repository order. Multiple persisted acceptances fail visibly,
as do invalid action or outcome relations. Multiple valid actions with no outcome derive
`in_progress`; multiple outcomes retain history while the latest valid one drives the projection.
There is no generic `executed`, `completed`, `resolved`, or `reviewed` state.

## Container

The composition root constructs and connects:

```text
JsonDecisionRepository
JsonObservationRepository
DecisionService
JsonDecisionAcceptanceRepository
DecisionAcceptanceService
JsonDecisionActionRepository
JsonPlaybookRunRepository
DecisionActionService
JsonDecisionOutcomeRepository
DecisionOutcomeService
JsonDecisionReviewRepository
DecisionReviewService
JsonExperienceRepository
ExperienceService
JsonKnowledgeRepository
KnowledgeService
DecisionLifecycleService
```

`DecisionAcceptanceService` receives `JsonDecisionAcceptanceRepository` and
`JsonDecisionRepository`. The CLI resolves services from the container. It does not construct
repositories or own validation, relation checks, persistence, eligibility, or idempotency policy.

`DecisionActionService` receives `JsonDecisionActionRepository`, `JsonDecisionRepository`,
`JsonDecisionAcceptanceRepository`, and `PlaybookRunService` as a validated `PlaybookRunReader`.
`PlaybookEvaluationService` and `EvolutionProposalService` use the same validated Run boundary.
`PlaybookRunService` receives JSON Run, Playbook, and PlaybookRevision repositories, with no
activation or application dependency. `DecisionOutcomeService`
receives `JsonDecisionOutcomeRepository` plus Decision, acceptance, and action repositories.
`DecisionLifecycleService` receives the Decision, acceptance, action, and outcome repositories.
`DecisionReviewService` receives `JsonDecisionReviewRepository` plus Decision, acceptance, and
outcome repositories. `Container.decision_review_repository()` and
`Container.decision_review_service()` expose the review composition. CLI handlers resolve services
from the container and construct no repositories.
`Container.experience_service()` injects `JsonExperienceRepository`,
`JsonObservationRepository`, and that validated `DecisionReviewService` boundary into
`ExperienceService`; the container owns no promotion policy.
`Container.knowledge_service()` injects `JsonKnowledgeRepository` and the constructed
`ExperienceService` as `ExperienceReader`; it does not supply a raw `JsonExperienceRepository` to
KnowledgeService.

## Implemented CLI

These commands exist at commit `1b45beb`:

```text
neural decision add
neural decision list
neural decision show DECISION_UUID
neural decision accept DECISION_UUID
neural decision acceptance-history DECISION_UUID
neural decision action add DECISION_UUID
neural decision action-history DECISION_UUID
neural decision action-show ACTION_UUID
neural decision outcome add DECISION_UUID
neural decision outcome-history DECISION_UUID
neural decision outcome-show OUTCOME_UUID
neural decision outcome-summary DECISION_UUID
neural decision review add DECISION_UUID
neural decision review history DECISION_UUID
neural decision review show REVIEW_UUID
neural experience add
neural experience from-observation OBSERVATION_UUID
neural experience from-review REVIEW_UUID
neural experience list
neural experience show EXPERIENCE_UUID
neural experience knowledge EXPERIENCE_UUID
neural knowledge add
neural knowledge from-experience EXPERIENCE_UUID
neural knowledge list
neural knowledge show KNOWLEDGE_UUID
neural observation experiences OBSERVATION_UUID
neural decision state DECISION_UUID
```

The current source checkpoint `18788ad` additionally exposes explicit revision execution
provenance through:

```text
neural run add --revision-id REVISION_UUID ...
neural run list
neural run show RUN_UUID
neural revision runs REVISION_UUID
```

Run list and show output render the revision ID or `-` when absent. CLI handlers delegate relation
validation to `PlaybookRunService` and render missing or cross-Playbook provenance as controlled
exit-code-1 errors.

`neural decision add` requires these scalar options:

```text
--project-key
--title
--objective
--context-summary
--proposed-option
--rationale
--proposed-by
--idempotency-key
```

It accepts these repeatable options:

```text
--alternative
--observation-id
--evidence
--tag
```

The optional supersession argument is:

```text
--supersedes-decision-id
```

Evidence is supplied as a bounded JSON value, for example:

```bash
neural decision add \
  --project-key NeuralEngine \
  --title "Canonical lifecycle ownership" \
  --objective "Choose one active-revision owner" \
  --context-summary "Two services could derive the same state" \
  --alternative "Activation service owns derivation" \
  --alternative "Application service replays records" \
  --proposed-option "Activation service owns derivation" \
  --rationale "One owner prevents semantic drift" \
  --proposed-by architecture-review \
  --idempotency-key decision-active-revision-owner \
  --evidence '{"kind":"agent_review","locator":".agent-work/reviews/review.md"}'
```

The CLI parses and validates this JSON value as `EvidenceReference`. It does not read the locator
or ingest any referenced file content.

`neural decision list --project PROJECT_KEY` filters through the service and renders:

```text
ID
Created
Project
Title
Proposed option
Proposed by
```

`neural decision show DECISION_UUID` renders the full Decision details, including alternatives,
Observation IDs, embedded evidence references, optional supersession, idempotency key, and tags.

### Decision acceptance commands

`neural decision accept DECISION_UUID` requires:

```text
DECISION_UUID
--accepted-by
--reason
--idempotency-key
```

It accepts repeatable optional values:

```text
--evidence
--tag
```

For example:

```bash
neural decision accept DECISION_UUID \
  --accepted-by architecture-owner \
  --reason "Approved after architecture review" \
  --idempotency-key decision-acceptance-1 \
  --evidence '{"kind":"manual_decision","locator":"approval:architecture-review"}' \
  --tag architecture
```

The CLI parses and validates `EvidenceReference`, but does not read the locator or ingest locator
content. Business rules remain in `DecisionAcceptanceService`. Success prints the stored
acceptance ID.

`neural decision acceptance-history DECISION_UUID` validates the Decision through the service and
renders:

```text
ID
Accepted
Decision ID
Accepted by
Reason
```

An existing Decision with no acceptance produces a controlled empty state.

### Decision action commands

`neural decision action add DECISION_UUID` requires:

```text
--acceptance-id
--action-type
--summary
--performed-by
--started-at
--idempotency-key
```

It accepts these optional values; evidence and tags are repeatable:

```text
--completed-at
--playbook-run-id
--evidence
--tag
```

The CLI parses timestamps as ISO-8601 values and parses evidence as embedded
`EvidenceReference` values. It does not execute commands or open evidence locators. Business rules
remain in `DecisionActionService`, and success prints the stored action ID.

`neural decision action-history DECISION_UUID` renders:

```text
ID
Recorded
Action type
Performed by
Started
Completed
Summary
```

An existing Decision with no actions produces a controlled empty state.
`neural decision action-show ACTION_UUID` renders every DecisionAction field.

### Decision outcome and state commands

`neural decision outcome add DECISION_UUID` requires:

```text
--acceptance-id
--action-id (one or more)
--result
--summary
--validated-by
--validated-at
--idempotency-key
```

Repeated `--evidence`, `--metric KEY=VALUE`, and `--tag` values are optional. Result accepts only
`succeeded`, `failed`, `partial`, or `unknown`. Metrics parse unambiguous booleans, integers, and
finite floats; other values remain strings and domain validation enforces the scalar bounds. The
CLI reads no evidence locator and executes no referenced command.

`neural decision outcome-history DECISION_UUID` renders all matching outcomes in repository order,
including their result, validation time, linked action IDs, validator, and summary. An existing
Decision with no outcomes produces a controlled empty state. `outcome-show OUTCOME_UUID` renders
every stored field, including evidence, metrics, idempotency key, and tags.

`neural decision outcome-summary DECISION_UUID` renders the derived count, deterministic latest
result/time, distinct linked-action count, counts by result, and success/failure presence. It does
not persist the summary.

### Decision review commands

`neural decision review add DECISION_UUID` requires:

```text
--acceptance-id
--outcome-id (one or more, repeatable and ordered)
--reviewed-by
--reviewed-at
--assessment
--summary
--finding (one or more, repeatable and ordered)
--confidence
--idempotency-key
```

Optional repeatable inputs are `--candidate-lesson`, `--evidence` JSON, and `--tag`. Assessment
accepts `sound`, `flawed`, `mixed`, or `inconclusive`; confidence accepts `low`, `medium`, or
`high`. The CLI parses ISO-8601 review time and embedded evidence but never opens evidence
locators. Validation errors render their first message; `ValueError` and controlled
`DecisionReviewError` failures render visibly and exit nonzero. Success prints the stored review ID
and every review field.

`neural decision review history DECISION_UUID` renders deterministic service history with columns
`ID`, `Reviewed`, `Reviewed by`, `Assessment`, `Confidence`, `Outcome IDs`, and `Summary`. An
existing Decision with no reviews renders `No review history found for Decision: ...`.
`neural decision review show REVIEW_UUID` renders every field after persisted relation validation.

### Review-to-Experience promotion command

`neural experience from-review REVIEW_UUID` requires repeatable ordered `--source`, plus:

```text
--promoted-by
--promotion-reason
--idempotency-key
--title
--context
--action
--outcome
--result
```

Optional repeatable inputs are `--observation-id` and `--tag`. Selectors use exact syntax such as
`--source finding:1 --source candidate_lesson:2`. CLI ordinals are positive and one-based; they
become durable zero-based indexes `0` and `1` without caller-supplied text. Invalid selector syntax,
kind, ordinal, Review, source index, Observation, conflict, ambiguity, or read integrity renders a
controlled error.

Success and equivalent replay print the stored Experience ID and complete auditable Experience
details. Promotion source rendering shows kind, user ordinal, stored index, and copied text, plus
promoter, reason, and key. Reviewer and promoter remain separate authorities.

Ordinary Experience commands keep their existing contracts. Direct `add` requires title, context,
action, outcome, and result; `from-observation` derives context from the required Observation and
requires title, action, outcome, and result. Observation IDs and tags remain optional where already
supported. List, show, Experience-to-Knowledge navigation, and Observation-to-Experience navigation
remain read-only. Ordinary Experience creation requires no promotion metadata or idempotency key.

### Knowledge commands and controlled integrity failures

`neural knowledge add` and `neural knowledge from-experience EXPERIENCE_UUID` are the existing
explicit creation paths. They accept caller-supplied Knowledge content and do not infer, promote,
or automatically create it. `neural experience knowledge EXPERIENCE_UUID` is read-only navigation.

All five Knowledge-to-Experience surfaces are protected by the validated reader:

```text
neural knowledge add
neural knowledge from-experience EXPERIENCE_UUID
neural knowledge list
neural knowledge show KNOWLEDGE_UUID
neural experience knowledge EXPERIENCE_UUID
```

Missing Experience and canonical DecisionReview/promotion-integrity errors render controlled
messages and exit nonzero without a traceback. No Knowledge-specific promotion error taxonomy,
new command, or success-output change exists.

`neural decision state DECISION_UUID` renders exactly one of:

```text
proposed
accepted
in_progress
succeeded
failed
partial
outcome_unknown
```

## Review and learning boundary

The record family remains deliberately separate:

```text
Decision
→ DecisionAcceptance
→ DecisionAction
→ DecisionOutcome
→ DecisionReview
```

- `Decision` is the implemented proposed choice.
- `DecisionAcceptance` is the implemented explicit authorization for possible future execution.
- `DecisionAction` is the implemented record of work performed under an accepted Decision.
- `DecisionOutcome` is the implemented factual result and validation evidence record.
- `DecisionReview` is the implemented authorized interpretation over explicit ordered outcomes.

All five decision records and the explicit Review-to-Experience promotion use case exist. Records
remain immutable semantic records rather than fields on a mutable
Decision or a duplicate generic event stream. A proposed option is not an acceptance, acceptance
is not execution, an outcome is not a review or Experience, and review findings or candidate
lessons are not Experience until promotion succeeds and are never automatically Knowledge or a
Playbook change.

Explicit Knowledge capture is a later, separate act through the existing generic Knowledge
commands. Its durable transitive provenance is:

```text
Knowledge.experience_ids
→ Experience.decision_review_promotion
→ DecisionReview
```

The Review provenance is not copied into Knowledge. `neural experience knowledge` only navigates
this relation; it does not create or promote Knowledge. Storing Knowledge proves explicit durable
capture, not that the Knowledge was used in, or improved, a later Decision.

The currently derivable projection is only:

```text
Decision without acceptance
→ proposed

Decision with one valid acceptance
→ accepted

Decision with one valid acceptance and at least one valid action
→ in_progress

latest valid outcome succeeded
→ succeeded

latest valid outcome failed
→ failed

latest valid outcome partial
→ partial

latest valid outcome unknown
→ outcome_unknown
```

The lifecycle projection uses the latest valid outcome selected by `(validated_at, outcome.id)`.
There is no generic executed, completed, resolved, or reviewed state and no generic full lifecycle
event replay service.

## Relationship to the domain chain

The implemented Decision may reference existing Observations as context. The implemented path and
future learning bridge remain explicit:

```text
Observation
→ Decision
→ DecisionAcceptance
→ DecisionAction
→ DecisionOutcome
→ DecisionReview
→ explicitly promoted Experience
→ separately and explicitly created Knowledge
```

DecisionAction may optionally reference an existing PlaybookRun, with existence-only validation
because PlaybookRun and Playbook expose no project key. `DecisionOutcome` remains distinct from
Experience. The promotion use case copies selected Review text into optional immutable Experience
provenance and never mutates a Playbook.

At source commit `18788adacf75ff7f11d0dd6f28e5da8cf143081b`, the implemented operational path is:

```text
Knowledge
→ Playbook.knowledge_ids
→ PlaybookRun(playbook_id, revision_id?)
→ PlaybookEvaluation.run_id
→ EvolutionProposal(playbook_id, evaluation_ids)
```

Knowledge exists before use. A caller explicitly selects exact Knowledge UUIDs into a Playbook,
explicitly declares manual or external Playbook application by recording a Run, evaluates that
exact Run, and may create a Proposal from exact Evaluation IDs. The same Run caller may declare
zero or one exact immutable PlaybookRevision whose content was used. Omission covers base Playbook
execution, legacy data, or unknown provenance and makes no revision-specific claim.
`EvolutionProposalService` verifies every referenced Evaluation's Run belongs to the target
Playbook.

Exact persisted feedback provenance is:

```text
PlaybookEvaluation.run_id
→ PlaybookRun(revision_id?, playbook_id)
→ Playbook.knowledge_ids
→ Knowledge.id
```

The optional decision-learning bridge is:

```text
DecisionOutcome.action_ids
→ DecisionAction.playbook_run_id?
→ PlaybookRun(revision_id?, playbook_id)
→ Playbook.knowledge_ids
```

It is optional because `playbook_run_id` is optional. `DecisionOutcome` preserves provenance
through exact DecisionAction IDs, but an action without the Run relation provides no Playbook or
Knowledge-use provenance.

## Self-observation and Consigliere boundaries

The future dogfooding flow remains a design direction:

```text
prompt
→ agent execution
→ review finding
→ decision/correction
→ implementation
→ validation
→ commit
→ push
→ post-work lesson
```

Commit `1b45beb` does not capture or ingest those events automatically. Automatic candidates and
manual confirmation remain future concepts; no automatic persistence, ingestion, or learning
exists.

Consigliere also remains future-only. It may later advise. No Consigliere integration exists, and
no recommendation can directly mutate NeuralEngine or authorize a durable record.

## Current non-behavior

Commit `18788ad` does not implement:

```text
execution engine
command/shell execution
rejection
withdrawal
reversal
reopening
cancellation
replacement
executed/completed/resolved/reviewed states
file ingestion
git ingestion
automatic Observation creation
automatic Experience creation
automatic Knowledge creation
special DecisionReview-to-Knowledge promotion
durable Knowledge retrieval history
durable recommendation events
per-Knowledge contribution attribution
causal or comparative proof of improvement
automatic Playbook creation or mutation
automatic evolution
Consigliere integration
automatic active-revision selection
Run-to-PlaybookRevisionApplication binding
Playbook materialization
revision content execution
Run idempotency
mixed or partial revision execution
multiple revisions per Run
automatic activation or application
```

It also does not execute commands referenced by evidence, open locators, automatically accept
Decisions, materialize Playbook revisions, or infer outcomes from `completed_at`. Explicit user
requests are required to create Decision, DecisionAcceptance, DecisionAction, DecisionOutcome, or
DecisionReview records and to promote Review statements into Experience.

## Remaining learning-loop limits

Durable Playbook-scoped Knowledge use and Run feedback already exist. The remaining limits are
Knowledge-specific causal attribution, per-Knowledge contribution attribution within a
multi-Knowledge Playbook, durable retrieval or recommendation events, and demonstrated causal or
comparative improvement.

`PlaybookRun` references exactly one base Playbook and may reference zero or one exact
PlaybookRevision. A supplied relation is the Run caller's factual declaration, not a lifecycle
projection. Reads validate revision existence and same-Playbook ownership and fail closed for
corrupt linked provenance; old Runs without the field remain valid.
`PlaybookRevisionApplication` records application intent and audit with
`content_changed=False`; it is not execution and is not bound to a Run. The implementation never
infers revision provenance from active-revision state, activation or application history,
co-existence, timestamps, tags, text similarity, or repository order. A revision need not be
active or applied for the caller to declare that its content was used. All selection, Run,
Evaluation, Proposal, and decision-link writes require explicit caller action and trigger no
automatic learning, mutation, materialization, activation, application, or evolution.

## Handbook synchronization policy

Generated Handbook outputs are rebuilt from source documents and templates and are never edited
manually. Copying the generated skill back to NeuralEngine is outside this synchronization task.

## Domain chain

# Domain Chain

The confirmed NeuralEngine chain is:

`Observation`
→ `Experience`
→ `Knowledge`
→ `Playbook`
→ `PlaybookRun`
→ `PlaybookEvaluation`
→ `EvolutionProposal`
→ `PlaybookRevision`
→ `PlaybookRevisionActivation`
→ `PlaybookRevisionApplication`

The final three stages are separate records with separate responsibilities:

- `PlaybookRevision` is an immutable candidate snapshot.
- `PlaybookRevisionActivation` is an immutable lifecycle and audit decision.
- `PlaybookRevisionApplication` is an immutable application-intent and audit record.

Creating a revision does not activate or apply it. Activation does not imply application.
The current application foundation records intent only: it does not materialize revision
content into a Playbook or mutate any related record.

## Relationship ownership

Relationship navigation belongs in application services unless persistence itself owns the concern.

Confirmed example:

- `PlaybookRevisionService.list_for_playbook(UUID)` owns playbook revision navigation.
- `PlaybookRevisionActivationService` owns activation navigation and canonical active-revision
  derivation through `get_active_revision_for_playbook(playbook_id)`.
- `PlaybookRevisionApplicationService` owns application-record navigation and delegates active
  revision resolution to `PlaybookRevisionActivationService`.
- `PlaybookRunService` owns optional explicit Run-to-Revision validation and reverse
  `list_for_revision(UUID)` navigation without consulting activation or application state.
- Repository interfaces remain persistence-focused.
- `PlaybookService` should not gain unrelated persistence dependencies.

## Complementary Decision Learning chain

The implemented Decision, DecisionAcceptance, DecisionAction, DecisionOutcome, and DecisionReview
foundations record a bounded proposed choice, explicit authorization, work performed, factual
results, and authorized interpretation after Observation context:

```text
Observation
→ Decision
→ DecisionAcceptance
→ DecisionAction
→ DecisionOutcome
→ DecisionReview
→ explicitly promoted Experience
→ separately and explicitly created Knowledge
```

This is a complementary provenance path, not a replacement for the canonical domain chain.
DecisionOutcome is factual; DecisionReview is authorized interpretation; Experience captures
explicitly promoted operational learning; Knowledge is separately generalized; Playbook remains a
separately created repeatable procedure. A Decision may have multiple immutable outcomes and
reviews, and one Review may explicitly produce multiple Experiences under different promotion
keys. A promoted Experience selects ordered Review statements and cannot combine Reviews. Review
action provenance remains transitive through explicit outcomes; promoted Experience provenance
remains transitive through its one Review. These records exist at source commit `12097fe`; no
Review save, promotion, lifecycle transition, or later Knowledge record in this path is automatic.

At source commit `1b45beb`, explicit Knowledge capture keeps its existing durable relation:

```text
Knowledge.experience_ids
→ Experience.decision_review_promotion
→ DecisionReview
```

KnowledgeService traverses every returned or newly supplied Experience relation through the
validated `ExperienceService.get_by_id()` boundary. This preserves transitive Review provenance
without copying it into Knowledge. `neural knowledge add` and `neural knowledge from-experience`
create explicit Knowledge; `neural experience knowledge` only navigates the relation. Durable
capture is not a durable record that Knowledge informed or improved a later decision.

## Workflow

# Development Workflow

## Before work

1. Read `AGENTS.md`.
2. Read `.agent-work/project-state.md` when present.
3. Run `./scripts/validate.sh`.
4. Inspect affected code and tests.
5. Define the smallest complete scope.
6. Create a task prompt under `.agent-work/prompts/`.

## During work

- Implement a coherent vertical slice.
- Follow current patterns.
- Add tests with implementation.
- Preserve public behavior unless explicitly changing it.
- Preserve persisted schemas unless explicitly changing them.
- Avoid unrelated cleanup.

## After work

1. Run `./scripts/validate.sh`.
2. Create a review file under `.agent-work/reviews/`.
3. Include validation output, diff stat, diff check, git status, and full diff.
4. Stop without committing or pushing.

## Future self-observation workflow

NeuralEngine development is intended to become a dogfooding source through:

```text
prompt
→ agent execution
→ review finding
→ decision/correction
→ implementation
→ validation
→ commit
→ push
→ post-work lesson
```

Automatic capture produces candidates only. Manual confirmation authorizes durable records;
immutable records preserve the audit trail; derived summaries remain replaceable views. No
automatic persistence, ingestion, or learning exists.

## Handbook synchronization

```text
major NeuralEngine milestone
→ commit/push NeuralEngine
→ sync NeuralEngine-Handbook
→ generate SKILL.md
→ copy generated SKILL.md back to NeuralEngine
→ commit/push skill sync
```

Each repository change is separate and reviewable. Generated outputs are rebuilt from Handbook
sources and are never edited manually. Publishing the generated skill back to NeuralEngine is a
later separate repository task; a Handbook synchronization task must not perform that publication
unless it is explicitly included in scope.

## Agent assignment

# Agent Assignment Policy

## Codex GPT-5.5 medium

Use for:

- new features,
- domain models,
- vertical slices,
- ports and adapters,
- repositories and services,
- dependency injection,
- CLI additions,
- persisted schema changes,
- public behavior changes,
- validation-order changes,
- provenance decisions,
- architectural documentation.

## DeepSeek

Use only for small controlled post-review fixes, normally one to three files:

- one concrete bug,
- targeted regression tests,
- Ruff or MyPy corrections,
- small message, type, validation, or CLI-option fixes,
- minor refactors without behavior change.

Every DeepSeek prompt must begin with reading `AGENTS.md`.

Required scope guard:

> Do not add features. Do not broaden scope. Do not change architecture, persisted schemas, public behavior, validation order, or provenance rules. Modify only the files required for the specified fix.

## Validation

# Validation Policy

Preferred command:

```bash
./scripts/validate.sh
```

Required checks:

```bash
ruff format --check .
ruff check .
mypy src tests
pytest
```

Never claim success unless all required checks pass.

When validation fails:

- show the failing command,
- include relevant output,
- identify whether the failure is pre-existing,
- do not bypass or suppress the failure.

## Definition of Done

# Definition of Done

A task is complete only when:

- requested behavior is implemented,
- scope has not expanded,
- architectural boundaries are preserved,
- tests cover the change,
- all required validation passes,
- prompt and review artifacts exist,
- review includes complete evidence,
- no commit or push was performed.

## Review checklist

# Review Checklist

- Is the requested scope complete?
- Were unrelated changes avoided?
- Are layer responsibilities preserved?
- Is business logic in the correct layer?
- Are repository interfaces persistence-focused?
- Are tests sufficient?
- Did validation pass?
- Does the review include diff stat, diff check, git status, and full diff?
- Were persisted schemas or public behavior changed?
- Was any commit or push performed?

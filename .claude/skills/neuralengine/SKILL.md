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

Source commit `62c0dcb` accepts a future self-observation and Decision Learning architecture based
on separate immutable `Decision`, `DecisionAcceptance`, `DecisionAction`, `DecisionOutcome`, and
`DecisionReview` records. Lifecycle state is derived from these semantic records rather than a
mutable status or duplicate generic event stream.

Decision tracking complements the existing domain chain. Consigliere remains a future advisory
layer, while NeuralEngine remains the durable system of record. The full design, evidence model,
dogfooding workflow, future-only CLI sketch, implementation milestone, and explicit non-behavior
are defined in `handbook/architecture/decision-learning.md`.

## Decision Learning architecture

# Decision Learning Architecture

## Status and purpose

This is accepted future architecture synchronized from NeuralEngine source commit `62c0dcb`.
It defines how NeuralEngine may become its own first real user by recording development choices,
their execution, factual results, and reviewed lessons. It does not describe implemented Decision
production behavior.

The intended learning path is:

```text
development event
→ Observation
→ Decision context
→ selected Decision
→ DecisionAction
→ DecisionOutcome
→ DecisionReview
→ Experience
→ Knowledge
→ Playbook improvement
```

Decision tracking complements the existing domain chain. It does not replace Observation,
Experience, Knowledge, Playbook, or any revision lifecycle concept.

## Staged immutable record family

The future record family is deliberately separated:

```text
Decision
→ DecisionAcceptance
→ DecisionAction
→ DecisionOutcome
→ DecisionReview
```

- `Observation` is a raw fact.
- `Decision` is a bounded choice with alternatives, proposed option, rationale, and provenance.
- `DecisionAcceptance` is explicit authorization to execute.
- `DecisionAction` is work performed under an accepted Decision.
- `DecisionOutcome` is the factual result and validation outcome.
- `DecisionReview` is an assessment with candidate lessons.
- `Experience` is interpreted operational learning.
- `Knowledge` is generalized reusable truth.
- `Playbook` is a repeatable procedure.

These responsibilities must remain separate. In particular, a proposed option is not accepted,
an outcome is not an Experience, and candidate lessons are not automatically Knowledge or a
Playbook change.

The initial Decision should conceptually include:

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

A material correction creates a new Decision linked through `supersedes_decision_id`; it does not
rewrite the earlier record.

## Invariants

1. Every record in the Decision workflow is immutable after persistence.
2. Creating a Decision means `proposed`, not accepted or executed.
3. Acceptance is explicit and attributable to a human or authorized external system.
4. Actions require an accepted Decision.
5. Outcomes reference existing actions for the same Decision.
6. Reviews reference existing outcomes for the same Decision.
7. Validation completes before persistence.
8. Corrections append records rather than rewriting history.
9. Evidence references preserve provenance without implying ingestion or verification.
10. Derived state has one canonical application-service owner.
11. Repository ports remain persistence-focused and gain no lifecycle query methods.
12. CLI handlers only translate input and render application-service results.
13. No Decision record automatically creates Observation, Experience, Knowledge, Playbook,
    EvolutionProposal, or revision lifecycle records.
14. A Consigliere recommendation is never accepted merely because it exists.
15. Hidden mutation and automatic evolution remain forbidden.

## Lifecycle projection

The initial future lifecycle is monotonic:

```text
proposed
→ accepted
→ executed
→ reviewed
```

State is a derived projection over the semantic immutable records, not a mutable
`Decision.status`:

- `proposed`: a Decision exists without a DecisionAcceptance.
- `accepted`: an acceptance exists without a DecisionAction.
- `executed`: at least one valid DecisionAction and DecisionOutcome exist.
- `reviewed`: a DecisionReview exists for a DecisionOutcome.

An action without an outcome is execution in progress, not `executed`. Repository order alone
must not define chronology; validated timestamps and deterministic IDs or explicit sequence fields
should resolve ordering where needed.

The initial design must not add a generic lifecycle event stream. The semantic records already
provide the authoritative facts. A canonical replay/state owner may be designed later only if real
requirements introduce withdrawal, reopening, cancellation, or reversal.

## Relationship to the existing domain chain

The existing chain remains authoritative for learning and Playbook evolution:

| Existing concept | Decision Learning relationship |
| --- | --- |
| Observation | Captures raw development facts referenced as Decision context. |
| Experience | Interprets operational learning from reviewed outcomes; it is not a DecisionOutcome. |
| Knowledge | Generalizes Experiences into reusable truth; it does not store decision history. |
| Playbook | Encodes a repeatable procedure; a DecisionReview does not mutate it. |
| PlaybookRun | May be referenced by a DecisionAction when a Playbook guided the work. |
| PlaybookEvaluation | Assesses that run and remains distinct from DecisionReview. |
| EvolutionProposal | Proposes improvement after explicit learning and evaluation; it is not created automatically. |
| PlaybookRevision | Holds an explicit immutable candidate snapshot. |
| PlaybookRevisionActivation | Selects a revision and is unrelated to DecisionAcceptance. |
| PlaybookRevisionApplication | Records revision application intent and is not a DecisionAction. |

The bridges remain explicit:

```text
DecisionOutcome
→ DecisionReview
→ Experience
→ Knowledge

DecisionAction
→ referenced PlaybookRun
→ PlaybookEvaluation
→ EvolutionProposal
→ PlaybookRevision
→ PlaybookRevisionActivation
→ PlaybookRevisionApplication
```

Any future direct Experience provenance to DecisionOutcome requires a separately reviewed schema
change. Shared Observation IDs and `EvidenceReference` values can preserve traceability until then.

## Self-observation and dogfooding

The intended NeuralEngine development workflow is:

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

Capture must distinguish four things:

- Automatic candidates may identify paths, hashes, changed-file summaries, and validation
  metadata, but are not persisted automatically.
- Manual confirmations authorize durable writes and associations.
- Immutable audit records preserve accepted facts and actions.
- Derived summaries are replaceable views, never source evidence.

The architecture-correction example is:

```text
Observation:
PlaybookRevisionApplicationService duplicated active-revision derivation.

Decision:
PlaybookRevisionActivationService remains the canonical owner.

DecisionAction:
Remove local lifecycle replay and delegate to activation service.

DecisionOutcome:
Validation passed with 537 tests.

DecisionReview:
Ownership became explicit and duplicated replay was removed.

Experience:
Centralized lifecycle derivation prevented architectural drift.

Knowledge:
Lifecycle derivation must have one canonical owner.

Playbook improvement:
Architecture review checks responsibility ownership, not only passing tests.
```

No automatic persistence or ingestion exists.

## Consigliere boundary

```text
Consigliere
= reasoning and advisory layer

NeuralEngine
= durable memory, audit, accepted decisions, actions, outcomes, reviewed learning, playbooks
```

Consigliere may later generate options, assess risks, recommend a choice, or identify candidate
lessons. It must not directly mutate NeuralEngine records, automatically accept Decisions,
automatically create learning artifacts, automatically apply Playbook revisions, or act as
authoritative durable storage. No Consigliere integration exists.

## Evidence and provenance

The future bounded embedded value is `EvidenceReference`, conceptually containing:

```text
kind
locator
repository_or_project
content_hash
captured_at
source
summary
```

Potential future kinds are:

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

Large prompts, reviews, diffs, and validation logs must not be embedded. References point to
authoritative sources through bounded locators and optional hashes. A hash identifies referenced
content but does not by itself prove authenticity. No file ingestion, git ingestion, or separate
Evidence repository is implemented.

## Idempotency direction

The recommended future uniqueness key is:

```text
(project_key, record_type, idempotency_key)
```

An equivalent repeated write should return the existing record. Reusing the same key with a
different payload must fail visibly and must not overwrite the first record. Initial duplicate
detection should use the current application-service load-and-filter convention. No repository
query methods should be invented for it.

## Future CLI sketch

The following commands are design direction only and do not exist:

```text
neural decision add
neural decision list
neural decision show DECISION_UUID

neural decision accept DECISION_UUID
neural decision action add DECISION_UUID
neural decision outcome add DECISION_UUID
neural decision review add DECISION_UUID

neural project ingest-review REVIEW_PATH
neural project ingest-commit COMMIT_HASH
```

Only `decision add`, `decision list`, and `decision show` belong to the recommended initial
implementation slice. All other commands require later, separately reviewed milestones.

## Recommended first implementation milestone

```text
Decision foundation
+ immutable Decision domain model
+ DecisionRepository port
+ JSON adapter using NeuralPaths.DECISIONS
+ DecisionService add/list/show
+ thin neural decision add/list/show CLI
+ tests
+ docs
```

The initial Decision should require one bounded objective, at least two meaningful alternatives,
a proposed option matching an alternative, non-blank rationale, explicit provenance, and an
idempotency key. This milestone must follow existing constructor injection, persistence-focused
port, JSON adapter, service-owned load-and-filter, thin CLI, and validation-before-persistence
patterns.

It must not implement DecisionAcceptance, DecisionAction, DecisionOutcome, DecisionReview, file or
git ingestion, automatic Observation, Experience, Knowledge, or Playbook creation, automatic
evolution, or Consigliere integration.

## Explicit non-goals and current non-behavior

This architecture does not add production code, schemas, domain classes, repositories, services,
CLI commands, dependencies, file or git ingestion, automatic learning, automatic persistence,
Playbook mutation, revision materialization, or Consigliere integration. `NeuralPaths.DECISIONS`
is only a pre-existing reserved directory in the synchronized source milestone.

## Handbook synchronization policy

Major milestones synchronize through separate, reviewable repository changes:

```text
major NeuralEngine milestone
→ commit/push NeuralEngine
→ sync NeuralEngine-Handbook
→ generate SKILL.md
→ copy generated SKILL.md back to NeuralEngine
→ commit/push skill sync
```

Generated Handbook outputs must never be edited manually. Copying the generated skill back to
NeuralEngine is outside this synchronization task.

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
- Repository interfaces remain persistence-focused.
- `PlaybookService` should not gain unrelated persistence dependencies.

## Complementary Decision Learning chain

Future Decision tracking records the bounded choice between Observation and reviewed learning:

```text
Observation
→ Decision
→ DecisionAcceptance
→ DecisionAction
→ DecisionOutcome
→ DecisionReview
→ Experience
→ Knowledge
```

This is a complementary provenance path, not a replacement for the canonical domain chain.
DecisionOutcome is factual; Experience is interpreted; Knowledge is generalized; Playbook remains
a separately created repeatable procedure. No transition in this path is automatic.

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
sources and are never edited manually.

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

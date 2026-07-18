# Project State

Last updated: 2026-07-17

## Current implementation

Neural Engine has a first Observation vertical slice:

* Domain model: `neural_engine.domain.Observation`
* Application service: `ObservationService`
* Port: `ObservationRepository`
* Infrastructure implementation: `JsonObservationRepository`
* Dependency wiring: `application/container.py`
* CLI commands: `neural observe`, `neural list`, `neural show UUID`,
  `neural observation experiences UUID`, and `neural search`

Observations are stored as JSON files in the local Neural Engine brain
observation directory. Observation list output includes IDs, and
`neural show UUID` displays all fields for one observation.
`neural observation experiences UUID` lists experiences linked to one existing
observation. `neural observe` warns when exact duplicate content already exists,
but still stores the new observation.

Neural Engine also has a minimal Experience vertical slice:

* Domain model: `neural_engine.domain.Experience`
* Result enum: `neural_engine.domain.ExperienceResult`
* Application service: `ExperienceService`
* Port: `ExperienceRepository`
* Infrastructure implementation: `JsonExperienceRepository`
* Dependency wiring: `application/container.py`
* CLI commands: `neural experience add`, `neural experience from-observation`,
  `neural experience list`, `neural experience show UUID`, and
  `neural experience knowledge UUID`

Experiences are stored as one JSON file per experience under
`NeuralPaths.EXPERIENCES`. Experience creation validates any supplied
observation IDs through the `ObservationRepository` port before saving.
`ExperienceService.add_from_observation()` creates an experience from one
existing observation by copying `Observation.content` exactly into the
experience context.

Neural Engine now has a minimal Knowledge vertical slice:

* Domain model: `neural_engine.domain.Knowledge`
* Confidence enum: `neural_engine.domain.KnowledgeConfidence`
* Application service: `KnowledgeService`
* Port: `KnowledgeRepository`
* Infrastructure implementation: `JsonKnowledgeRepository`
* Dependency wiring: `application/container.py`
* CLI commands: `neural knowledge add`, `neural knowledge from-experience`,
  `neural knowledge list`, `neural knowledge show UUID`, and
  `neural knowledge playbooks UUID`, and `neural knowledge revisions UUID`

Knowledge is a durable rule, lesson, or conclusion derived from one or more
experiences. `KnowledgeService.add()` requires at least one experience ID and
validates every referenced experience through the `ExperienceRepository` port
before creating or saving knowledge. Missing evidence raises
`KnowledgeEvidenceRequiredError`; a missing experience raises
`ExperienceNotFoundError` with the missing experience UUID. Knowledge is stored
as one JSON file per knowledge item under `NeuralPaths.KNOWLEDGE`.
The Knowledge CLI only records explicit user-supplied statements, rationale,
confidence, experience IDs, and tags; it does not generate or infer knowledge.
`KnowledgeService.add_from_experience()` creates knowledge linked to one
existing experience after loading that experience through the
`ExperienceRepository` port.
`KnowledgeService.list_for_experience()` verifies one existing experience and
returns knowledge items linked to it.
`neural knowledge revisions UUID` delegates to
`PlaybookRevisionService.list_for_knowledge()` to verify the Knowledge item
exists and list PlaybookRevision records that reference it. The service verifies
the Knowledge item through `KnowledgeRepository`, loads revisions through
`PlaybookRevisionRepository.load_all()`, filters by membership in
`revision.knowledge_ids` in the application layer, and preserves repository
order. The repository does not gain a knowledge-specific query method. This is
read-only relation navigation only: it does not mutate Knowledge, activate a
revision, mutate a Playbook, change proposal status, apply a proposal, or
perform automatic evolution.

Neural Engine now has a minimal Playbook vertical slice:

* Domain model: `neural_engine.domain.Playbook`
* Application service: `PlaybookService`
* Port: `PlaybookRepository`
* Infrastructure implementation: `JsonPlaybookRepository`
* Dependency wiring: `application/container.py`
* CLI commands: `neural playbook add`, `neural playbook list`,
  `neural playbook show UUID`, `neural playbook runs UUID`,
  `neural playbook proposals UUID`, and `neural playbook revisions UUID`

A Playbook is an explicit operational procedure that applies one or more
Knowledge items to a class of situations. `PlaybookService.add()` requires at
least one knowledge ID and at least one step, validates every referenced
Knowledge item through the `KnowledgeRepository` port before saving, and stores
Playbooks as one JSON file per playbook under `NeuralPaths.PLAYBOOKS`.
The Playbook CLI only records explicit user-supplied operational procedures.
Playbooks are not executed, inferred, or generated automatically.
`PlaybookService.list_for_knowledge()` verifies one existing Knowledge item and
returns Playbooks linked to it.
`neural playbook runs UUID` delegates to `PlaybookRunService.list_for_playbook()`
to list PlaybookRun records linked to one existing Playbook.
`neural playbook proposals UUID` delegates to
`EvolutionProposalService.list_for_playbook()` to list manually or externally
supplied EvolutionProposal records linked to one existing Playbook without
modifying that Playbook.
`neural playbook revisions UUID` delegates to
`PlaybookRevisionService.list_for_playbook()` to verify the Playbook exists and
list PlaybookRevision records assigned to it. The service loads all revisions
through `PlaybookRevisionRepository.load_all()` and filters by `playbook_id` in
the application layer. This is read-only navigation only: it does not activate a
revision, choose a current version, modify the Playbook, apply a proposal, or
perform automatic evolution.

Neural Engine now has a minimal PlaybookRun vertical slice:

* Domain model: `neural_engine.domain.PlaybookRun`
* Application service: `PlaybookRunService`
* Port: `PlaybookRunRepository`
* Infrastructure implementation: `JsonPlaybookRunRepository`
* Dependency wiring: `application/container.py`
* CLI commands: `neural run add`, `neural run list`, and
  `neural run show UUID`, and `neural run evaluations UUID`

A PlaybookRun is an explicit record of manually or externally applying one
existing Playbook to a concrete situation. `PlaybookRunService.add()` requires
at least one action taken, validates the referenced Playbook through the
`PlaybookRepository` port before saving, and stores runs as one JSON file per
run under `NeuralPaths.PLAYBOOK_RUNS`. PlaybookRun records outcomes; Neural
Engine does not execute Playbooks or evaluate runs automatically. `neural run
add` records an already performed manual or external application.
`PlaybookRunService.list_for_playbook()` verifies one existing Playbook and
returns only runs whose `playbook_id` matches it.
`neural run evaluations UUID` delegates to
`PlaybookEvaluationService.list_for_run()` to list manual or external
PlaybookEvaluation records linked to one existing PlaybookRun.

Neural Engine now has a minimal PlaybookEvaluation vertical slice:

* Domain model: `neural_engine.domain.PlaybookEvaluation`
* Effectiveness enum: `neural_engine.domain.PlaybookEffectiveness`
* Application service: `PlaybookEvaluationService`
* Port: `PlaybookEvaluationRepository`
* Infrastructure implementation: `JsonPlaybookEvaluationRepository`
* Dependency wiring: `application/container.py`
* CLI commands: `neural evaluation add`, `neural evaluation list`,
  `neural evaluation show UUID`, and `neural evaluation proposals UUID`

A PlaybookEvaluation is an explicit human or external-system assessment of one
existing PlaybookRun. `PlaybookEvaluationService.add()` requires at least one
finding, validates the referenced PlaybookRun through the
`PlaybookRunRepository` port before saving, and stores evaluations as one JSON
file per evaluation under `NeuralPaths.PLAYBOOK_EVALUATIONS`. PlaybookEvaluation
records effectiveness, findings, improvements, evidence, notes, and tags
supplied by the caller. Neural Engine does not evaluate runs automatically,
modify Playbooks or PlaybookRuns, create Knowledge or Playbooks, or create
automatic evolution proposals.
The Evaluation CLI delegates to the application service, lets Typer parse UUIDs
and `PlaybookEffectiveness`, and only renders explicit user-supplied or
external-system evaluation records.
`PlaybookEvaluationService.list_for_run()` verifies one existing PlaybookRun and
returns only evaluations whose `run_id` matches it.
`neural evaluation proposals UUID` delegates to
`EvolutionProposalService.list_for_evaluation()` to list manually or externally
supplied EvolutionProposal records that reference one existing PlaybookEvaluation.

Neural Engine now has a minimal EvolutionProposal vertical slice:

* Domain model: `neural_engine.domain.EvolutionProposal`
* Status enum: `neural_engine.domain.EvolutionProposalStatus`
* Application service: `EvolutionProposalService`
* Port: `EvolutionProposalRepository`
* Infrastructure implementation: `JsonEvolutionProposalRepository`
* Dependency wiring: `application/container.py`
* CLI commands: `neural proposal add`, `neural proposal list`,
  `neural proposal show UUID`, `neural proposal status UUID --status STATUS`,
  and `neural proposal revisions UUID`

An EvolutionProposal is an explicit human or external-system proposal to improve
one existing Playbook based on one or more existing PlaybookEvaluation records.
`EvolutionProposalService.add()` requires at least one evaluation ID and at
least one proposed change, validates the referenced Playbook, validates every
referenced evaluation, loads each evaluation's PlaybookRun, and confirms each
run belongs to the proposal Playbook before saving. EvolutionProposal records
summary, rationale, proposed changes, expected benefits, risks, status, notes,
and tags supplied by the caller. Neural Engine does not modify Playbooks, apply
proposals, approve or reject proposals automatically, rank proposals, or perform
automatic evolution.
The Proposal CLI delegates to the application service, lets Typer parse UUIDs
and `EvolutionProposalStatus`, and only renders manually or externally supplied
proposal records.
`EvolutionProposalService.set_status()` records a manually or externally
supplied status decision for one existing EvolutionProposal. It loads the
proposal through the `EvolutionProposalRepository` port, preserves every field
except `status`, saves the updated proposal through the same port, and returns
it. Accepted status does not apply proposal changes to a Playbook.
`EvolutionProposalService.list_for_playbook()` verifies one existing Playbook
through the `PlaybookRepository` port, loads proposals through the
`EvolutionProposalRepository` port, and returns only proposals whose
`playbook_id` matches it. This is read-only relation navigation; proposals do
not modify Playbooks and Neural Engine does not perform automatic evolution.
`EvolutionProposalService.list_for_evaluation()` verifies one existing
PlaybookEvaluation through the `PlaybookEvaluationRepository` port, loads
proposals through the `EvolutionProposalRepository` port, and returns only
proposals whose `evaluation_ids` contain it. This is read-only relation
navigation; proposals are supplied manually or externally, proposal status is
not changed, and proposals do not modify Playbooks.
`neural proposal revisions UUID` delegates to
`PlaybookRevisionService.list_for_proposal()` to verify the EvolutionProposal
exists and list PlaybookRevision records assigned to it. The service verifies
the proposal through `EvolutionProposalRepository`, loads revisions through
`PlaybookRevisionRepository.load_all()`, filters by `proposal_id` in the
application layer, and preserves repository order. The repository does not gain
a proposal-specific query method. This is read-only relation navigation only:
it does not change proposal status, activate a revision, mutate a Playbook,
apply a proposal, or perform automatic evolution.

Neural Engine now has a minimal PlaybookRevision vertical slice:

* Domain model: `neural_engine.domain.PlaybookRevision`
* Application service: `PlaybookRevisionService`
* Port: `PlaybookRevisionRepository`
* Infrastructure implementation: `JsonPlaybookRevisionRepository`
* Dependency wiring: `application/container.py`
* CLI commands: `neural revision add`, `neural revision list`,
  `neural revision show UUID`, and `neural revision activate UUID`

A PlaybookRevision is an immutable candidate snapshot of revised Playbook
content supplied manually or by an external system. `PlaybookRevisionService.add()`
requires at least one step and at least one success criterion, validates the
referenced EvolutionProposal (exists, accepted status, belongs to the target
Playbook), validates the referenced Playbook, then validates each
referenced Knowledge item in supplied order before saving. Proposal-level
failures are detected before any Playbook or Knowledge read. PlaybookRevision
records do not modify or replace Playbooks, do not change proposal status, do
not infer revised content, and do not perform automatic evolution.
The Revision CLI records explicitly supplied revised content only. Accepted
EvolutionProposal status remains a recorded decision; creating a revision is a
separate action and still does not activate a revision, apply changes to a
Playbook, or introduce automatic evolution.
`docs/playbook-revision-lifecycle.md` records the lifecycle design decision for
the next revision step. The design recommends a future separate
`PlaybookRevisionActivation` artifact for explicit manual or external-system
activation decisions instead of storing activation state on Playbook or
PlaybookRevision. This preserves immutable revision snapshots, avoids implicit
Playbook mutation, keeps accepted proposal status separate from application,
and keeps automatic evolution out of scope.

Neural Engine now has a PlaybookRevisionActivation application service
foundation:

* Domain model: `neural_engine.domain.PlaybookRevisionActivation`
* Decision enum: `neural_engine.domain.PlaybookRevisionActivationDecision`
* Application service: `PlaybookRevisionActivationService`
* Port: `PlaybookRevisionActivationRepository`
* Infrastructure implementation: `JsonPlaybookRevisionActivationRepository`
* Path constant: `NeuralPaths.PLAYBOOK_REVISION_ACTIVATIONS`
* Dependency wiring: `Container.playbook_revision_activation_repository()`
  and `Container.playbook_revision_activation_service()`

The domain model validates local lifecycle decision invariants such as required
reason, non-blank optional text and tags, required previous revision for
`superseded`, and no previous revision for `rejected`.
`PlaybookRevisionActivationService.add()` records explicit manual or
external-system lifecycle decisions. It verifies the Playbook, PlaybookRevision,
and EvolutionProposal exist, confirms the revision belongs to the supplied
Playbook and proposal, verifies same-Playbook previous revision linkage for
`superseded`, rejects previous revision linkage for `rejected`, saves through
the `PlaybookRevisionActivationRepository` port, and returns the created
activation. It does not validate Knowledge existence because activation acts on
an existing revision. It also does not require or change proposal status.
`PlaybookRevisionActivationService.list_for_playbook()` verifies one existing
Playbook, loads activation records through
`PlaybookRevisionActivationRepository.load_all()`, filters by `playbook_id` in
the application layer, and preserves repository order.
`PlaybookRevisionActivationService.list_for_revision()` verifies one existing
PlaybookRevision through `PlaybookRevisionRepository.get_by_id()`, loads
activation records through `PlaybookRevisionActivationRepository.load_all()`,
filters by `revision_id` in the application layer, and preserves repository
order.
`PlaybookRevisionActivationService.list_for_proposal()` verifies one existing
EvolutionProposal through `EvolutionProposalRepository.get_by_id()`, loads
activation records through `PlaybookRevisionActivationRepository.load_all()`,
filters by `proposal_id` in the application layer, and preserves repository
order.
`PlaybookRevisionActivationService.get_active_revision_for_playbook()` verifies
one existing Playbook, derives the current active revision from activation
records in repository order, loads only the final derived revision through
`PlaybookRevisionRepository.get_by_id()`, and verifies that revision still
belongs to the Playbook. Inspection is read-only and does not validate
EvolutionProposal status or Knowledge existence.
`neural playbook revision-history UUID` delegates to
`PlaybookRevisionActivationService.list_for_playbook()` and displays lifecycle
activation records for one Playbook in service order.
`neural playbook active-revision UUID` delegates to
`PlaybookRevisionActivationService.get_active_revision_for_playbook()` and
displays the current active PlaybookRevision when one exists. Both commands are
read-only lifecycle inspection only.
`neural revision activation-history UUID` delegates to
`PlaybookRevisionActivationService.list_for_revision()` and displays activation
records linked to one existing PlaybookRevision in service order.
`neural proposal activation-history UUID` delegates to
`PlaybookRevisionActivationService.list_for_proposal()` and displays activation
records linked to one existing EvolutionProposal in service order. Both
relation navigation commands are read-only lifecycle inspection only.
`neural revision activate UUID --playbook PLAYBOOK_UUID --proposal
PROPOSAL_UUID --reason TEXT` delegates to
`PlaybookRevisionActivationService.add()` and records an explicit lifecycle
activation decision. It supports `--decision`, `--previous-revision`,
`--decided-by`, `--notes`, and repeated `--tag` values. It writes only a
`PlaybookRevisionActivation` record.
`neural revision supersede NEW_REVISION_UUID --playbook PLAYBOOK_UUID
--proposal PROPOSAL_UUID --previous-revision OLD_REVISION_UUID --reason TEXT`
delegates to `PlaybookRevisionActivationService.add()` with the fixed
`superseded` decision. `neural revision reject REVISION_UUID --playbook
PLAYBOOK_UUID --proposal PROPOSAL_UUID --reason TEXT` delegates to the same
service with the fixed `rejected` decision and does not expose
`--previous-revision`. Both commands support `--decided-by`, `--notes`, and
repeated `--tag` values. They write only `PlaybookRevisionActivation` records.
There is no lifecycle mutation, Playbook mutation, PlaybookRevision mutation,
EvolutionProposal mutation, proposal application, proposal status change,
repository query method, automatic evolution, or materialization of revision
content into Playbook content.
The explicit PlaybookRevision materialization/apply boundary has been designed
in `docs/playbook-revision-lifecycle.md` and summarized in
`docs/architecture.md`. The recommended future concept is
`PlaybookRevisionApplication`, a separate explicit application/audit artifact
that would be distinct from `PlaybookRevisionActivation`. This design-only
update does not add production behavior, CLI behavior, repository ports,
schemas, tests, Playbook mutation, proposal status changes, proposal
application, or automatic evolution.

Neural Engine now has a PlaybookRevisionApplication foundation slice:

* Domain model: `neural_engine.domain.PlaybookRevisionApplication`
* Application service: `PlaybookRevisionApplicationService`
* Port: `PlaybookRevisionApplicationRepository`
* Infrastructure implementation: `JsonPlaybookRevisionApplicationRepository`
* Path constant: `NeuralPaths.PLAYBOOK_REVISION_APPLICATIONS`
* Dependency wiring: `Container.playbook_revision_application_repository()`
  and `Container.playbook_revision_application_service()`

`PlaybookRevisionApplication` is an immutable audit record for explicit
application intent. It records Playbook, PlaybookRevision, and
EvolutionProposal IDs, reason, `applied_at`, optional `applied_by`, notes, tags,
source activation ID, idempotency key, and `content_changed`. The foundation
defaults `content_changed` to `False` and does not mutate Playbook content.
`PlaybookRevisionApplicationService.add()` verifies the Playbook,
PlaybookRevision, and EvolutionProposal exist, requires the proposal to still
be `accepted`, confirms the revision belongs to the supplied Playbook and
proposal, validates an optional source activation record belongs to the same
Playbook/revision/proposal relation, delegates active revision resolution to
`PlaybookRevisionActivationService.get_active_revision_for_playbook()`, requires
the requested revision to match that active revision, saves only the application
audit record, and returns it. The service does not mutate Playbook,
PlaybookRevision, EvolutionProposal, or PlaybookRevisionActivation records and
does not call their save methods. `list_for_playbook()`, `list_for_revision()`, and
`list_for_proposal()` verify the source entity exists, load all application
records through `PlaybookRevisionApplicationRepository.load_all()`, filter in
the application layer, preserve repository order, and do not add repository
query methods. No CLI apply or application-history commands were added.

The self-observation and development decision tracking boundary is now designed
in `docs/decision-learning-lifecycle.md` and summarized in
`docs/architecture.md`. The accepted direction is a staged immutable record
family:

```text
Decision
-> DecisionAcceptance
-> DecisionAction
-> DecisionOutcome
-> DecisionReview
```

Decision complements rather than replaces Observation and Experience.
Development evidence is referenced through bounded embedded
`EvidenceReference` values instead of ingesting large prompts, reviews, diffs,
or validation logs. Initial lifecycle state is a monotonic projection over the
semantic records, not a mutable status field or duplicate generic event stream.
Consigliere remains a future advisory layer; NeuralEngine owns durable accepted
context, decisions, actions, outcomes, provenance, and reviewed promotion into
Experience, Knowledge, and Playbook evolution.

NeuralEngine now has a Decision foundation vertical slice:

* immutable `Decision` domain model,
* immutable embedded `EvidenceReference` value,
* persistence-focused `DecisionRepository`,
* `JsonDecisionRepository` using `NeuralPaths.DECISIONS`,
* `DecisionService` with `add()`, `list_decisions()`, and `show()`,
* container repository/service wiring,
* `neural decision add`, `neural decision list`, and
  `neural decision show DECISION_UUID`.

Decision validates non-blank required text, at least two trimmed unique
alternatives, exact proposed-option membership, unique Observation IDs,
non-self supersession, normalized tags, bounded evidence kind/locator, and
UTC-aware timestamps. The service validates referenced Observations and
same-project supersession before persistence. Idempotency is scoped by
`(project_key, "decision", idempotency_key)`: equivalent semantic replay returns
the existing Decision, while a conflicting payload fails without a write.
Generated Decision identity/time and generated evidence capture times are not
part of semantic equivalence. Duplicate detection uses
`DecisionRepository.load_all()`; no query methods were added.

Evidence values are embedded references only and the CLI accepts them as
repeatable bounded JSON `--evidence` values. No locator is read or ingested.
NeuralEngine now also has a DecisionAcceptance foundation vertical slice:

* immutable `DecisionAcceptance` with ID, UTC acceptance time, Decision ID,
  accepting actor, reason, embedded evidence, idempotency key, and normalized
  tags,
* persistence-focused `DecisionAcceptanceRepository`,
* one-file-per-record `JsonDecisionAcceptanceRepository` under
  `NeuralPaths.DECISION_ACCEPTANCES`,
* `DecisionAcceptanceService` with `accept()`, `list_for_decision()`, and
  `show()`,
* container repository/service wiring,
* `neural decision accept DECISION_UUID`,
* `neural decision acceptance-history DECISION_UUID`.

Acceptance validates Decision existence and uses repository `load_all()` for
idempotency and eligibility. The scope is
`(decision_id, "decision_acceptance", idempotency_key)`: equivalent semantic
replay returns the existing acceptance, a conflicting payload fails without a
write, and a second acceptance with another key also fails. Relation filtering
stays in the service and preserves repository order. Supersession does not
invalidate acceptance because it creates a separate immutable Decision rather
than a reversal transition.

NeuralEngine now also has a DecisionAction foundation vertical slice:

* immutable `DecisionAction` with Decision/acceptance relations, action type,
  summary, performer, UTC timestamps, evidence, optional PlaybookRun,
  idempotency key, and normalized tags,
* persistence-focused `DecisionActionRepository`,
* `JsonDecisionActionRepository` under `NeuralPaths.DECISION_ACTIONS`,
* `DecisionActionService` with `add()`, `list_for_decision()`, and `show()`,
* canonical `DecisionLifecycleService`,
* container repository/service/projection wiring,
* `neural decision action add`, `action-history`, `action-show`, and `state`.

Action creation requires an existing Decision and an acceptance belonging to
that Decision. Optional PlaybookRun references must exist; the current
PlaybookRun/Playbook schema has no project key, so stronger project-context
compatibility cannot yet be derived. Multiple distinct actions are allowed.
Idempotency is scoped by `(decision_id, "decision_action", idempotency_key)`;
equivalent replay returns the existing action and conflicting reuse fails
without a write.

NeuralEngine now also has a DecisionOutcome vertical slice:

* immutable `DecisionOutcome` with Decision, acceptance, and ordered action
  relations; bounded result; validation actor/time; evidence; immutable scalar
  metrics; idempotency key; and normalized tags,
* persistence-focused `DecisionOutcomeRepository` and deterministic
  `JsonDecisionOutcomeRepository` under `NeuralPaths.DECISION_OUTCOMES`,
* `DecisionOutcomeService` with `add()`, `list_for_decision()`, `show()`, and
  `summary_for_decision()`,
* immutable non-persisted `DecisionOutcomeSummary`,
* container and Brain path wiring,
* `neural decision outcome add`, `outcome-history`, `outcome-show`, and
  `outcome-summary`.

Outcome creation validates the Decision, acceptance ownership, every linked
action's Decision and acceptance, unique action IDs, and validation time against
the earliest action start. Result is exactly `succeeded`, `failed`, `partial`,
or `unknown`. Metrics allow at most 100 immutable scalar values with bounded,
case-insensitively unique keys and deterministic serialization.

Idempotency is scoped by
`(decision_id, "decision_outcome", idempotency_key)`. Equivalent replay excludes
generated outcome identity/time and evidence capture times; conflicting reuse
fails without a write. Summary and lifecycle select latest by
`(validated_at, outcome.id)` and validate relations rather than hiding corrupt
records.

`DecisionLifecycleService` remains the only projection owner and derives
exactly `proposed`, `accepted`, `in_progress`, `succeeded`, `failed`, `partial`,
or `outcome_unknown`. It persists no status and derives no review or learning.

This slice adds no DecisionReview, command execution, reversal, ingestion,
automatic Observation, Experience, Knowledge, Playbook, PlaybookEvaluation, or
EvolutionProposal creation, automatic evolution, Consigliere integration,
dependencies, or generated Handbook changes.

## Validation

Latest validation passed:

* `uv run ruff format .`
* `uv run ruff check .`
* `uv run mypy src tests`
* `uv run pytest`

Pytest collected 731 tests.

## Notes for next work

The next recommended controlled milestone is exactly DecisionReview foundation.
It may record candidate lessons but must not automatically create Experience,
Knowledge, Playbook, PlaybookEvaluation, or EvolutionProposal records.

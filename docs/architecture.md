# Architecture

Neural Engine follows Clean Architecture.

## Layers

Domain:

* Owns core concepts such as `Decision`, `DecisionAcceptance`, `DecisionAction`,
  `DecisionOutcome`, `DecisionReview`, `Observation`,
  `Experience`, `Knowledge`, `Playbook`, `PlaybookRun`, `PlaybookEvaluation`,
  `EvolutionProposal`, and `PlaybookRevision`.
* Owns the domain foundation for `PlaybookRevisionActivation`, which represents
  an explicit lifecycle decision for a PlaybookRevision.
* Owns the domain foundation for `PlaybookRevisionApplication`, which
  represents an explicit application audit record without mutating Playbook
  content in the current foundation slice.
* Has no dependency on infrastructure.

Application:

* Coordinates use cases such as adding, listing, and showing Decisions,
  explicitly accepting Decisions, recording actions, factual outcomes, and
  authorized reviews, inspecting their history, adding,
  listing, and searching observations,
  adding, listing, and retrieving experiences, and adding, listing, and
  retrieving knowledge, playbooks, playbook runs, playbook evaluations, and
  evolution proposals and playbook revisions, and adding playbook revision
  activation decisions and inspecting playbook revision activation state, and
  recording playbook revision application audit records.
* Depends on ports instead of concrete infrastructure implementations.

Ports:

* Define repository interfaces required by application services.

Infrastructure:

* The current Decision repository stores one JSON file per Decision.
* The current Decision acceptance repository stores one JSON file per
  DecisionAcceptance.
* The current Decision action repository stores one JSON file per DecisionAction.
* The current Decision outcome repository stores one JSON file per DecisionOutcome.
* The current Decision review repository stores one JSON file per DecisionReview.
* Implements ports using concrete storage mechanisms.
* The current observation repository stores one JSON file per observation.
* The current experience repository stores one JSON file per experience.
* The current knowledge repository stores one JSON file per knowledge item.
* The current playbook repository stores one JSON file per playbook.
* The current playbook run repository stores one JSON file per playbook run.
* The current playbook evaluation repository stores one JSON file per playbook
  evaluation.
* The current evolution proposal repository stores one JSON file per evolution
  proposal.
* The current playbook revision repository stores one JSON file per playbook
  revision.
* The current playbook revision activation repository stores one JSON file per
  playbook revision activation decision.
* The current playbook revision application repository stores one JSON file per
  playbook revision application audit record.

CLI:

* Remains thin.
* Creates no business rules.
* Resolves application services through `application/container.py`.

## Neural Home Path Resolution

`src/neural_engine/core/paths.py` owns the single public path-selection
contract. Each resolver call returns one immutable `NeuralPaths` value. When
`NEURAL_HOME` is absent, its home is exactly `Path.home() / ".neural"`. When
the variable is present, it must name one non-blank absolute existing
accessible directory; invalid or unavailable values fail without default
fallback. Strictly resolvable symlink roots are supported.

No environment-derived operational path is fixed at module import. Brain,
projects, logs, config, version, and every record-store directory derive from
the same resolved home. `Container` passes one resolved path set through each
constructed dependency graph. JSON adapters resolve their no-argument
defaults at construction and revalidate configured-root and Brain
availability before I/O. Explicit `directory=...` adapter injection remains
available for tests and alternate infrastructure composition.

`Brain` owns read-only initialization state and approved home initialization.
Default init may create `~/.neural`; override init requires its selected root
to pre-exist and creates children only below it. Missing individual stores
under an available Brain retain their existing empty-read behavior. A missing
configured root fails before repository use, so it cannot be interpreted as an
empty Brain or recursively recreated by a default adapter write.

These rules add no domain concept, repository-port method, record schema,
mount management, migration, backup, synchronization, locking, or multi-host
coordination.

`neural doctor` adds one read-only diagnostic path across this selection
boundary. `NeuralDoctorService` derives readiness states from the resolved
`NeuralPaths` and a narrow `NeuralDoctorProbe` port;
`LocalNeuralDoctorProbe` performs local access and content inspection. The
canonical 15-store topology remains owned by `NeuralPaths` and is shared with
Brain initialization, avoiding a second directory list.

Doctor also projects the optional `BrainTrustInspection` produced by the
application `BrainTrustInspector`. `Container` wires one inspector with the
read-only `LocalBrainTrustProbe`; status renders the same classification as an
additive `Brain Trust state` field. Trust classification remains independent of
structural readiness, and neither command changes readiness or exit-code
semantics because a pre-trust Brain is `UNADOPTED`.

The package release version and persisted Brain format version are separate
contracts. `BRAIN_FORMAT_VERSION` is the single supported-format value used by
both `Brain.initialize()` and `NeuralDoctorService`; package-only upgrades do
not rewrite `VERSION` unless the persisted format itself changes.

The probe reads each `*.json` candidate once, hashes those exact bytes, decodes
UTF-8, validates JSON through the store's domain model, and checks filename
UUID, payload identity, and per-store duplicate IDs. The service builds the
aggregate manifest from sorted Brain-relative POSIX paths, so its digest is
independent of the selected mount path. Doctor never calls repositories or
writers and exposes no repair, initialization, migration, expected-manifest,
relation-graph, mount, process, locking, or coordination behavior.

## Observation Flow

`neural observe` calls the application container, receives an
`ObservationService`, and asks it to add an observation. The service creates a
domain `Observation` and persists it through the `ObservationRepository` port.
Before saving, the service loads existing observations through the same port and
returns any exact content duplicate IDs for the CLI to display as a warning.
Duplicate detection does not block persistence. The JSON repository is the
current infrastructure implementation of that port.

`neural list` retrieves all observations through the same service and
repository stack and displays the observation ID, timestamp, content, and tags.

`neural show UUID` retrieves a single observation through
`ObservationService.get_by_id()` and displays all observation fields.

`neural observation experiences UUID` delegates to
`ExperienceService.list_for_observation()`. The service verifies the
observation exists through the `ObservationRepository` port, loads experiences
through the `ExperienceRepository` port, and returns only experiences linked to
that observation ID.

`neural search QUERY` reuses `ObservationService.search()` to find observations
whose content matches the given query (case-insensitive substring match).

## Experience Flow

`neural experience add` calls the application container, receives an
`ExperienceService`, and asks it to add an experience. The service validates
referenced observation IDs through the `ObservationRepository` port before it
creates a domain `Experience` or persists it through the `ExperienceRepository`
port. The JSON repository is the current infrastructure implementation and
stores one file per experience under `NeuralPaths.EXPERIENCES`.

`neural experience list` retrieves all experiences through the same service and
repository stack.

`neural experience show UUID` retrieves a single experience through
`ExperienceService.get_by_id()`.

`neural experience from-observation OBSERVATION_UUID` delegates to
`ExperienceService.add_from_observation()`. The service loads the observation
through the `ObservationRepository` port, copies `Observation.content` exactly
into the experience context, links the new experience to that observation ID,
and persists it through the `ExperienceRepository` port.

`neural experience from-review REVIEW_UUID` delegates to
`ExperienceService.add_from_decision_review()`. Ordered `--source
finding:ORDINAL` and `--source candidate_lesson:ORDINAL` values use explicit
1-based CLI ordinals and become durable zero-based indexes. The service loads
the Review through `DecisionReviewService.show()`, so existing persisted
Decision/acceptance/outcome relation validation remains canonical. It copies
the exact normalized Review text and stores one Experience with optional
embedded `DecisionReviewPromotion` provenance. No link aggregate, repository,
Brain directory, or second write exists.

Promotion idempotency is scoped by `(decision_review_id,
"review_experience_promotion", idempotency_key)`. Scanning remains in the
application layer: zero matches writes, one equivalent match replays, one
different match conflicts, and multiple matches fail as ambiguity without
repository-order selection. Equivalence excludes only generated Experience ID
and timestamp. Promoted Experience reads revalidate the Review and copied
source text; malformed relations, invalid indexes, or changed text fail closed.
Plain and Observation-derived Experiences remain compatible, including old
JSON without the optional field.

`neural experience knowledge EXPERIENCE_UUID` delegates to
`KnowledgeService.list_for_experience()`. The service verifies the experience
through the validated `ExperienceService` read boundary, loads knowledge through
the `KnowledgeRepository` port, and returns only knowledge linked to that
experience ID. Before returning, it validates every Experience relation of each
matching Knowledge item. Unrelated Knowledge records are not relation-validated
by this scoped query. This command is read-only navigation and does not create
Knowledge.

## Knowledge Flow

`neural knowledge add` calls the application container, receives a
`KnowledgeService`, and asks it to add knowledge from explicit user-supplied
statement, rationale, confidence, experience IDs, and optional tags. The CLI does
not generate, infer, summarize, or modify knowledge. The service rejects an empty
evidence list, then verifies each referenced experience through the
application-facing `ExperienceReader` protocol implemented by
`ExperienceService.get_by_id()` before it creates or saves a domain `Knowledge`
item. This retains one owner for DecisionReview promotion provenance validation.
Validation follows caller order, preserves duplicate IDs, stops on the first
missing or corrupt Experience, and does not persist Knowledge when validation
fails.

`neural knowledge list` retrieves all knowledge through the same service and
repository stack, then validates every linked Experience of every record before
returning the list. It fails closed rather than skipping, repairing, filtering,
or partially returning invalid records.

`neural knowledge from-experience EXPERIENCE_UUID` delegates to
`KnowledgeService.add_from_experience()`. The service loads the source
experience through the validated Experience read boundary once, rejects a
missing or corrupt source, and creates knowledge linked to that single
experience ID using only the statement, rationale, confidence, and tags supplied
by the caller.

`neural knowledge show UUID` retrieves a single knowledge item through
`KnowledgeService.get_by_id()`, validates every linked Experience when the item
exists, and displays all knowledge fields. A missing Knowledge item still
returns no record without an Experience read.

`neural knowledge search QUERY` delegates to `KnowledgeService.search()`. It
loads Knowledge through the repository, validates every linked Experience, and
returns items in repository load order when the query is a case-insensitive
substring of their statement or rationale. This is read-only filtering: it does
not rank results, perform semantic or cross-record retrieval, create records,
or change persistence.

`KnowledgeService` propagates the existing `DecisionReviewError` and
`DecisionReviewPromotionError` families from their canonical owners. It does
not inspect promotion fields or duplicate Review validation. Missing Experience
relations retain the Knowledge-layer `ExperienceNotFoundError`. The container
injects `ExperienceService` rather than a raw Experience repository, preserving
the acyclic dependency graph `KnowledgeService -> ExperienceService ->
ExperienceRepository + ObservationRepository + DecisionReviewService`.
The guarantee is exactly the existing `ExperienceService.get_by_id()` contract;
it does not add recursive validation of Observation or DecisionAction relations.

This hardening adds no Knowledge or Experience field, repository method, JSON
format, authority field, idempotency behavior, creation command, or automatic
learning. Knowledge may still mix ordinary and promoted Experiences, combine
different Reviews, and contain repeated Experience IDs. Persisting a
generalization alone is not evidence of later operational use or improved
decisions. The existing Playbook, Run, Evaluation, and Proposal records provide
durable Playbook-scoped use and feedback; they do not provide
Knowledge-specific causal attribution or demonstrated improvement.

## Controlled Brain Mutation Boundary

The supported paths-backed single-record CREATE mutations are routed through
the Brain Trust transition coordinator. Package 1 covers `neural knowledge
add`, `neural knowledge from-experience`, `neural run add`, and `neural
revision add`. The remaining protected paths are `neural observe`,
`neural experience add`, `neural experience from-observation`, `neural
experience from-review`, `neural playbook add`, `neural evaluation add`,
`neural proposal add`, `neural revision activate`, `neural revision supersede`,
`neural revision reject`, the `PlaybookRevisionApplicationService.add()`
writer path, and the Decision family commands `decision add`, `decision
accept`, `decision action add`, `decision outcome add`, and `decision review
add`. Activation, supersession, and rejection append to the same activation
store; the three Experience paths append to the same Experience store.

The composition root supplies every listed service with its JSON adapter as a
controlled-target writer and the one existing coordinator; direct repository
construction remains a local/test adapter capability, not the supported
production writer boundary. The coordinator accepts only a
`TRUSTED_CURRENT` Brain and performs one ordinary create using the frozen
ordering: durable pending marker, exact target bytes, generation `N+1`
metadata, bounded target and metadata verification, external binding `N+1`,
and marker cleanup last. A pending transition therefore remains fail-closed;
the next ordinary mutation does not retry or repair it implicitly.

Each listed writer publishes exactly one authoritative Brain-relative JSON
file with `CREATE`, no before hash, and the SHA-256 of the validated exact
durable bytes. Repository-owned filename/payload identity, relation checks,
duplicate/replay behavior, and conflict errors remain in force; a conflicting
file is never silently replaced and no secondary authoritative write is
introduced. The marker stores only the normalized relative path, action, and
exact before/after SHA-256 evidence through the existing `TargetDescriptor`
contract; it does not duplicate the record payload.

Bounded `neural brain recover` supports the same S1-S4 evidence contract for
all 15 canonical JSON stores: observations, experiences, knowledge, playbooks,
playbook evaluations, evolution proposals, revision activations, revision
applications, playbook runs, playbook revisions, decisions, decision
acceptances, decision actions, decision outcomes, and decision reviews. S1 is
deliberately rejected with `S1_REJECTED_INSUFFICIENT_EVIDENCE`; S2, S3, and S4
are completed only after exact target bytes, current payload/path identity,
metadata, and binding evidence are verified. Recovery remains fail-closed for
unsupported, malformed, foreign, stale, rollback, ahead, and other pending
states, and never runs from status, doctor, startup, or ordinary retry.

M12 now protects `neural proposal status` as one single-record `REPLACE` of
the exact `evolution-proposals/<uuid>.json` target. The marker carries both
the literal durable BEFORE hash and the exact replacement AFTER hash. The
transition verifies BEFORE immediately after marker persistence, publishes
the exact AFTER bytes, advances metadata, verifies, advances the binding,
verifies, and clears the marker last. A stale preimage fails closed without
overwriting the proposal or advancing metadata or binding.

Bounded REPLACE recovery is limited to `ordinary_mutation`, exactly one
`REPLACE`, and the `evolution-proposals` store. R1 is rejected when the target
is still BEFORE because the marker contains hashes, not enough durable payload
evidence to reconstruct AFTER; R2, R3, and R4 complete only the forward
metadata/binding/marker suffix after exact AFTER and proposal identity checks.
No generic REPLACE recovery exists. M23 development-evidence apply remains
unprotected, and `WRITER_COVERAGE_BLOCKED` remains until that separate
multi-record boundary is resolved. The bounded scope still excludes REMOVE,
multi-target operations, adoption, restore, clone, rebind, Model B, a central
repository guard, a generic transaction/recovery engine, and real Brain writes.

Knowledge create-once and same-ID conflict semantics remain owned by
`JsonKnowledgeRepository`.

`neural knowledge playbooks UUID` delegates to
`PlaybookService.list_for_knowledge()`. The service verifies the knowledge item
exists through the `KnowledgeRepository` port, loads playbooks through the
`PlaybookRepository` port, and returns only playbooks linked to that knowledge
ID.

`neural knowledge revisions UUID` delegates to
`PlaybookRevisionService.list_for_knowledge()`. The service verifies the
Knowledge item exists through the `KnowledgeRepository` port, loads revisions
through `PlaybookRevisionRepository.load_all()`, and filters in the application
layer by membership in `revision.knowledge_ids`. Repository order is preserved.
The repository does not expose `find_by_knowledge_id()`. This is read-only
relation navigation: it does not mutate Knowledge, activate a revision, modify
a Playbook, change proposal status, apply a proposal, or perform automatic
evolution.

The JSON repository is the current infrastructure implementation and stores one
file per knowledge item under `NeuralPaths.KNOWLEDGE`. Under supported
repository writes, one Knowledge UUID binds to one complete payload. Publication
uses a local create-once operation that cannot replace the final UUID path.
Replaying the same UUID and identical complete payload is a no-op that preserves
the existing bytes; reusing the UUID for any different modeled field raises a
persistence conflict. Existing malformed data and filename/payload UUID
mismatches fail visibly without repair or replacement. Valid files written by
the earlier adapter remain readable and require no migration. Direct filesystem
mutation remains out-of-band corruption; this contract adds neither
tamper-evidence nor Knowledge versioning.

## Playbook Flow

`neural playbook add` calls the application container, receives a
`PlaybookService`, and asks it to add a playbook from explicit user-supplied
title, situation, objective, steps, success criteria, knowledge IDs, optional
constraints, and optional tags. The service rejects an empty knowledge list,
rejects an empty step list, then verifies each referenced knowledge item through
the `KnowledgeRepository` port before it creates or saves a domain `Playbook`.
Validation stops on the first missing knowledge item and does not persist a
playbook when validation fails.

`neural playbook list` retrieves all playbooks through the same service and
repository stack.

`neural playbook show UUID` retrieves a single playbook through
`PlaybookService.get_by_id()` and displays all playbook fields.

`neural playbook runs UUID` delegates to
`PlaybookRunService.list_for_playbook()`. The service verifies the playbook
exists through the `PlaybookRepository` port, loads playbook runs through the
`PlaybookRunRepository` port, and returns only runs linked to that playbook ID.

`neural playbook proposals UUID` delegates to
`EvolutionProposalService.list_for_playbook()`. The service verifies the
playbook exists through the `PlaybookRepository` port, loads evolution proposals
through the `EvolutionProposalRepository` port, and returns only proposals
linked to that playbook ID.

`neural playbook revisions UUID` delegates to
`PlaybookRevisionService.list_for_playbook()`. The service first verifies the
Playbook exists through the `PlaybookRepository` port, loads all revisions
through the `PlaybookRevisionRepository.load_all()` port, and filters matching
`playbook_id` values in the application layer. Repository order is preserved.
The repository does not expose `find_by_playbook_id()`. This is read-only
relation navigation: it does not activate any revision, choose a current
version, modify the Playbook, apply a proposal, or perform automatic evolution.

The JSON repository is the current infrastructure implementation and stores one
file per playbook under `NeuralPaths.PLAYBOOKS`.

Playbooks are stored procedures only. Neural Engine does not execute playbook
steps, orchestrate workflows, or generate playbooks automatically.

## Playbook Run Flow

`neural run add` calls the application container, receives a
`PlaybookRunService`, and records explicit user-supplied or external-system data
about an already performed application of one existing playbook to a concrete
situation. The service rejects an empty action list, verifies the referenced
playbook through the `PlaybookRepository` port, then validates an optional
caller-supplied PlaybookRevision exists and belongs to that Playbook before it
creates and saves a domain `PlaybookRun`. It does not inspect activation or
application records.

`neural run list` retrieves all playbook runs through the same service and
repository stack.

`neural run show UUID` retrieves a single playbook run through
`PlaybookRunService.get_by_id()` and displays all run fields, including explicit
revision provenance or `-` when no revision-specific claim exists. Complete,
Playbook-scoped, and single reads fail closed on missing or cross-Playbook
revision provenance. `neural revision runs UUID` validates one revision and
lists only Runs that explicitly reference it in repository order.

`neural run evaluations UUID` delegates to
`PlaybookEvaluationService.list_for_run()`. The service verifies the playbook
run exists through the `PlaybookRunRepository` port, loads evaluations through
the `PlaybookEvaluationRepository` port, and returns only evaluations linked to
that run ID.

Playbook runs record manual or external application and do not duplicate
playbook data. They store the playbook ID, optional exact revision ID,
situation, actions taken, outcome, success flag, optional evidence, optional
notes, and optional tags. Old JSON without the revision relation remains valid.
The relation is caller authority, zero-or-one, and never inferred from active
revision or `PlaybookRevisionApplication`. Neural Engine does not execute
playbooks or evaluate runs automatically.

## Playbook Evaluation Flow

`neural evaluation add` calls the application container, receives a
`PlaybookEvaluationService`, and records explicit human-supplied or
external-system assessment data about one existing playbook run. The service
rejects an empty findings list, verifies the referenced run through the
`PlaybookRunRepository` port, then creates and saves a domain
`PlaybookEvaluation` through the `PlaybookEvaluationRepository` port.
Validation stops before run lookup when findings are missing and before
construction or persistence when the run does not exist.

`neural evaluation list` retrieves all playbook evaluations through the same
service and repository stack.

`neural evaluation show UUID` retrieves a single playbook evaluation through
`PlaybookEvaluationService.get_by_id()` and displays all evaluation fields.

`PlaybookEvaluationService.list_for_run()` verifies one existing playbook run
and returns evaluations linked to it. Evaluations remain manual or external
records; this relation lookup does not evaluate the run or infer findings.

`neural evaluation proposals UUID` delegates to
`EvolutionProposalService.list_for_evaluation()`. The service verifies the
playbook evaluation exists through the `PlaybookEvaluationRepository` port,
loads evolution proposals through the `EvolutionProposalRepository` port, and
returns only proposals that reference that evaluation ID.

Playbook evaluations are supplied manually or externally. They store the run ID,
effectiveness judgment, findings, optional improvements, optional evidence,
optional notes, and optional tags. Neural Engine does not evaluate runs
automatically, modify playbooks or runs, create knowledge or playbooks, or
create automatic evolution proposals.

## Evolution Proposal Flow

`neural proposal add` calls the application container, receives an
`EvolutionProposalService`, and records explicit human-supplied or
external-system proposal data for improving one existing playbook based on one
or more existing playbook evaluations. The service rejects an empty evaluation
list, rejects an empty proposed change list, verifies the referenced playbook,
then verifies each referenced evaluation in supplied order. For every
evaluation, the service loads the referenced playbook run and confirms the run
belongs to the proposal playbook. Validation stops before persistence on the
first missing playbook, missing evaluation, missing referenced run, or
evaluation/playbook mismatch.

`neural proposal list` retrieves all evolution proposals through the same
service and repository stack.

`neural proposal show UUID` retrieves a single evolution proposal through
`EvolutionProposalService.get_by_id()` and displays all proposal fields.

`neural proposal status UUID --status STATUS` delegates to
`EvolutionProposalService.set_status()`. The service loads one existing
proposal through the `EvolutionProposalRepository` port, creates an updated
proposal preserving every field except status, saves it through the same port,
and returns the updated proposal. The status is supplied manually or externally;
accepted status does not apply proposal changes to a playbook.

`neural proposal revisions UUID` delegates to
`PlaybookRevisionService.list_for_proposal()`. The service verifies the
EvolutionProposal exists through the `EvolutionProposalRepository` port, then
loads revisions through `PlaybookRevisionRepository.load_all()` and filters
matching `proposal_id` values in the application layer. Repository order is
preserved. The repository does not expose `find_by_proposal_id()`. This is
read-only relation navigation: it does not change proposal status, activate a
revision, modify a Playbook, apply a proposal, or perform automatic evolution.

`EvolutionProposalService.list_for_playbook()` verifies one existing playbook
and returns proposals linked to it. Proposals remain supplied manually or
externally; this relation lookup does not infer proposal content, apply
proposals, or modify playbooks.

`EvolutionProposalService.list_for_evaluation()` verifies one existing playbook
evaluation and returns proposals that reference it. Proposals remain supplied
manually or externally; this relation lookup does not infer proposal content,
change proposal status, apply proposals, or modify playbooks.

Evolution proposals are supplied manually or externally. They store the
playbook ID, evaluation IDs, summary, rationale, proposed changes, expected
benefits, optional risks, status, optional notes, and optional tags. Neural
Engine does not modify playbooks, apply proposals, approve or reject proposals
automatically, infer proposal status, rank proposals, or perform automatic
evolution.

## Durable Operational Knowledge Use And Feedback

Knowledge persistence, operational selection, application, evaluation, and
proposal provenance are distinct declarations:

1. `Knowledge` records an explicit generalization from Experience.
2. A caller selects one or more exact Knowledge UUIDs into
   `Playbook.knowledge_ids`.
3. A caller records that the Playbook was manually or externally applied
   through the exact `PlaybookRun.playbook_id` relation.
4. A human or external system evaluates that exact Run through
   `PlaybookEvaluation.run_id`.
5. A caller may use one or more exact Evaluation UUIDs to support an
   `EvolutionProposal` for one exact Playbook.

The persisted feedback provenance is:

```text
PlaybookEvaluation.run_id
-> PlaybookRun.playbook_id
-> Playbook.knowledge_ids
-> Knowledge.id
```

`EvolutionProposal` stores both `playbook_id` and `evaluation_ids`.
`EvolutionProposalService` loads every referenced Evaluation and its Run and
rejects the proposal if any Run belongs to a different Playbook. Feedback is
therefore attached to the Playbook and its declared Knowledge set, not inferred
from co-existence, timestamps, tags, text similarity, or repository order.

The decision-learning chain has a separate optional bridge:

```text
DecisionOutcome.action_ids
-> DecisionAction.playbook_run_id?
-> PlaybookRun.playbook_id
-> Playbook.knowledge_ids
```

`DecisionOutcome.action_ids` contains exact DecisionAction UUIDs.
`DecisionAction.playbook_run_id` is optional, so this provenance exists only
for actions that explicitly reference a validated PlaybookRun. An Outcome
without such an Action link has no Playbook or Knowledge-use provenance.

These contracts provide durable Playbook-scoped Knowledge use and Run
feedback. They do not record durable Knowledge retrieval history or
recommendation events, prove that one Knowledge item caused an outcome,
attribute contributions inside a multi-Knowledge Playbook, or demonstrate
causal or comparative improvement. `PlaybookRun` has no
`playbook_revision_id`, so it cannot identify which PlaybookRevision was
executed. `PlaybookRevisionApplication` records application intent/audit with
`content_changed=False`; it is not execution. All creation and feedback remain
explicit caller actions: Neural Engine neither infers use nor mutates learning
records automatically.

## Playbook Revision Flow

`PlaybookRevisionService.add()` records explicit manually supplied or
external-system supplied revised Playbook content as an immutable candidate
snapshot. Validation runs in the following order:

1. local content invariants: rejects empty `steps` or empty `success_criteria`,
2. loads the referenced EvolutionProposal,
3. rejects a missing EvolutionProposal,
4. requires the proposal status to be `accepted`,
5. confirms the proposal belongs to the target Playbook,
6. verifies the referenced Playbook exists,
7. verifies every referenced Knowledge item in supplied order,
8. saves the `PlaybookRevision`.

Validation is ordered so that proposal-level failures (missing, wrong status,
wrong Playbook) are detected before any Playbook or Knowledge read. All
validation steps complete before `save()` is called.

Playbook revisions store the original Playbook ID, accepted proposal ID, revised
title, situation, objective, steps, success criteria, knowledge IDs, optional
notes, and optional tags supplied by the caller. A revision does not replace or
modify the original Playbook, does not change proposal status, does not infer or
generate revised content, and does not perform automatic evolution.

The JSON Revision repository enforces create-once persistence under supported
writes: one UUID binds to one complete validated modeled payload. It publishes
new UUID paths without replacement, treats an identical same-ID replay as a
byte-preserving no-op, and rejects any different same-ID payload without
modifying the stored bytes. Malformed or invalid stored data, non-UUID
filenames, and filename/request-to-payload identity mismatches fail visibly
without repair. Existing valid JSON remains readable without migration.

This makes exact Revision UUID relations in Runs and their downstream
Evaluations and Proposals, plus activation and application records, stable
going forward under supported repository writes. It does not deeply freeze
in-memory lists, reconstruct earlier history, or add snapshots, hashes,
versioning, tamper evidence, or protection from direct filesystem mutation.

The next lifecycle step for revisions is defined in
`docs/playbook-revision-lifecycle.md`. The design recommends a future separate
`PlaybookRevisionActivation` artifact for explicit manual or external-system
activation decisions. Activation state should not be stored on Playbook or
PlaybookRevision, and accepting a proposal or creating a revision must still
not mutate Playbook content, change proposal status, apply a proposal, or
perform automatic evolution.

`neural revision add` delegates to `PlaybookRevisionService.add()`. All revised
content fields are supplied explicitly by the caller. The command does not copy
content from the Playbook, does not transform proposal changes, and does not
activate or apply the revision.

`neural revision list` delegates to `PlaybookRevisionService.list_revisions()`
and displays stored revision summaries in repository order.

`neural revision show UUID` delegates to `PlaybookRevisionService.get_by_id()`
and displays the full stored revision snapshot.

`PlaybookRevisionService.list_revisions()` retrieves all playbook revisions
through the same service and repository stack.

`PlaybookRevisionService.get_by_id()` retrieves one playbook revision through
the `PlaybookRevisionRepository` port.

## Playbook Revision Activation Flow

`PlaybookRevisionActivationService.add()` records an explicit manual or
external-system lifecycle decision for one existing PlaybookRevision. Validation
runs in the following order:

1. verifies the referenced Playbook exists,
2. verifies the referenced PlaybookRevision exists,
3. verifies the referenced EvolutionProposal exists,
4. confirms the revision belongs to the supplied Playbook,
5. confirms the revision belongs to the supplied EvolutionProposal,
6. for `superseded`, requires an existing previous revision that belongs to the
   same Playbook,
7. for `rejected`, rejects any previous revision reference,
8. saves the `PlaybookRevisionActivation`.

The service validates only existence and linkage. It does not require the
proposal to be accepted, does not validate Knowledge items, does not mutate
Playbook content, does not mutate PlaybookRevision content, does not change
EvolutionProposal status, does not apply proposals, and does not perform
automatic evolution.

`PlaybookRevisionActivationService.list_for_playbook()` verifies one existing
Playbook, loads activation records through the
`PlaybookRevisionActivationRepository.load_all()` port, filters matching
`playbook_id` values in the application layer, and preserves repository order.

`PlaybookRevisionActivationService.list_for_revision()` verifies one existing
PlaybookRevision through the `PlaybookRevisionRepository` port, loads all
activation records through `PlaybookRevisionActivationRepository.load_all()`,
filters matching `revision_id` values in the application layer, and preserves
repository order. It does not validate Playbook, EvolutionProposal, or
Knowledge records during inspection.

`PlaybookRevisionActivationService.list_for_proposal()` verifies one existing
EvolutionProposal through the `EvolutionProposalRepository` port, loads all
activation records through `PlaybookRevisionActivationRepository.load_all()`,
filters matching `proposal_id` values in the application layer, and preserves
repository order. It does not validate Playbook, PlaybookRevision, or Knowledge
records during inspection.

`PlaybookRevisionActivationService.get_active_revision_for_playbook()` verifies
one existing Playbook and derives the current active revision from that
Playbook's activation records in repository order. Later records override
earlier records: `active` selects a revision, `superseded` can move selection
from a previous revision to a new revision, and `rejected` clears the current
selection only when it targets the currently active revision. The service loads
only the final derived revision through `PlaybookRevisionRepository.get_by_id()`
and verifies it belongs to the Playbook. It does not validate EvolutionProposal
or Knowledge records during inspection.

`neural playbook revision-history UUID` delegates to
`PlaybookRevisionActivationService.list_for_playbook()` and displays stored
activation decisions in service order.

`neural playbook active-revision UUID` delegates to
`PlaybookRevisionActivationService.get_active_revision_for_playbook()` and
displays the derived active PlaybookRevision when one exists.

`neural revision activation-history UUID` delegates to
`PlaybookRevisionActivationService.list_for_revision()` and displays stored
activation decisions linked to one PlaybookRevision in service order.

`neural proposal activation-history UUID` delegates to
`PlaybookRevisionActivationService.list_for_proposal()` and displays stored
activation decisions linked to one EvolutionProposal in service order.

These inspection commands are read-only. They do not create activation records,
add repository query methods, mutate Playbook content, mutate PlaybookRevision
content, mutate EvolutionProposal content, change proposal status, apply
proposals, or perform automatic evolution.

`neural revision activate REVISION_UUID --playbook PLAYBOOK_UUID --proposal
PROPOSAL_UUID --reason TEXT` delegates to `PlaybookRevisionActivationService.add()`
and records an explicit lifecycle decision. The command supports `--decision`,
`--previous-revision`, `--decided-by`, `--notes`, and repeated `--tag` values.
It writes only a `PlaybookRevisionActivation` record. It does not materialize
revision content into the Playbook, mutate Playbook content, mutate
PlaybookRevision content, mutate EvolutionProposal content, change proposal
status, apply proposals, or perform automatic evolution.

`neural revision supersede NEW_REVISION_UUID --playbook PLAYBOOK_UUID
--proposal PROPOSAL_UUID --previous-revision OLD_REVISION_UUID --reason TEXT`
is a convenience wrapper for recording a `superseded` lifecycle decision through
`PlaybookRevisionActivationService.add()`. It accepts optional `--decided-by`,
`--notes`, and repeated `--tag` values.

`neural revision reject REVISION_UUID --playbook PLAYBOOK_UUID --proposal
PROPOSAL_UUID --reason TEXT` is a convenience wrapper for recording a
`rejected` lifecycle decision through `PlaybookRevisionActivationService.add()`.
It accepts optional `--decided-by`, `--notes`, and repeated `--tag` values and
does not expose `--previous-revision`.

Both convenience commands write only `PlaybookRevisionActivation` records. They
do not materialize revision content into the Playbook, mutate Playbook content,
mutate PlaybookRevision content, mutate EvolutionProposal content, change
proposal status, apply proposals, or perform automatic evolution.

## Playbook Revision Application Foundation

`PlaybookRevisionApplication` is the explicit boundary for recording that a
selected PlaybookRevision reached the application stage. Activation does not
imply application: `PlaybookRevisionActivation` remains lifecycle and audit
state only, while application is a separate audit artifact with its own domain
record, application service, repository port, validation, and JSON adapter.

`PlaybookRevisionApplicationService.add()` records an application audit record
only after validation. It verifies that the Playbook, PlaybookRevision, and
EvolutionProposal exist; requires the proposal to still be `accepted`; confirms
the revision belongs to the supplied Playbook and proposal; validates an
optional source activation record belongs to the same Playbook, revision, and
proposal; and requires the revision to be currently active.
`PlaybookRevisionApplicationService` delegates active revision resolution to
`PlaybookRevisionActivationService.get_active_revision_for_playbook()`. The
saved record sets `content_changed` to `False`.

`PlaybookRevisionApplicationService.list_for_playbook()`,
`list_for_revision()`, and `list_for_proposal()` verify the source entity
exists, load all application records through
`PlaybookRevisionApplicationRepository.load_all()`, filter in the application
layer, and preserve repository order. The repository port intentionally exposes
only `save()`, `load_all()`, and `get_by_id()`; no relation-specific query
methods were added.

The current foundation does not implement CLI apply commands or application
history commands. It does not materialize revision content into Playbook
content, mutate Playbook records, mutate PlaybookRevision records, mutate
EvolutionProposal records, change proposal status, apply proposals, or perform
automatic evolution.

## Decision Learning Design

The self-observation and development decision architecture is defined in
`docs/decision-learning-lifecycle.md`. The accepted direction uses a staged
family of immutable records rather than one mutable workflow aggregate:

```text
Decision
-> DecisionAcceptance
-> DecisionAction
-> DecisionOutcome
-> DecisionReview
```

Decision tracking complements the existing Observation-to-Playbook chain.
Observation stores development facts, Decision stores a bounded choice and its
rationale, DecisionOutcome stores what happened, Experience stores interpreted
operational learning, Knowledge stores generalized truth, and Playbook stores
repeatable procedure. Promotion between these stages remains explicit.

Future development evidence should be referenced through small embedded
`EvidenceReference` values containing bounded locators and optional hashes, not
by embedding prompts, reviews, diffs, or validation logs. Consigliere remains a
future reasoning and advisory layer; NeuralEngine remains the authoritative
store for accepted context, decisions, actions, outcomes, and reviewed learning.

The first Decision foundation is implemented. `Decision` and its embedded
`EvidenceReference` value are immutable. `DecisionRepository` exposes only
`save()`, `load_all()`, and `get_by_id()`, and `JsonDecisionRepository` stores
one JSON file per Decision under the existing `NeuralPaths.DECISIONS` path.
`DecisionService` owns Observation validation, same-project supersession
validation, project filtering, not-found behavior, and idempotency.

Idempotency is scoped by `(project_key, "decision", idempotency_key)`. An
equivalent semantic replay returns the existing Decision; generated Decision ID
and creation time and generated evidence capture times are excluded from the
comparison. Reusing the key with a different semantic payload fails without a
write. Duplicate detection loads and filters through the repository port; no
query method was added.

The thin CLI exposes:

```text
neural decision add
neural decision list [--project PROJECT_KEY]
neural decision show DECISION_UUID
```

`decision add` accepts repeated `--alternative`, `--observation-id`, `--tag`,
and `--evidence` options. Each `--evidence` value is a bounded JSON object such
as `{"kind":"agent_review","locator":".agent-work/reviews/review.md"}`.
Evidence is embedded by reference only; the CLI does not read the locator.

The DecisionAcceptance foundation is implemented as a separate immutable
authorization record with `id`, `accepted_at`, `decision_id`, `accepted_by`,
`reason`, embedded `evidence_references`, `idempotency_key`, and normalized
`tags`. Required text is trimmed and non-blank, timestamps are UTC-aware,
evidence reuses `EvidenceReference`, and no mutable status or Decision payload
is stored.

`DecisionAcceptanceRepository` exposes only `save()`, `load_all()`, and
`get_by_id()`. `JsonDecisionAcceptanceRepository` stores one deterministic JSON
file per record under `NeuralPaths.DECISION_ACCEPTANCES`.
`DecisionAcceptanceService` validates Decision existence, owns application-layer
filtering, and implements `accept()`, `list_for_decision()`, and `show()`.

Eligibility is monotonic: an existing Decision with no acceptance is proposed;
its first acceptance makes it accepted. A distinct second acceptance is
rejected. Supersession does not invalidate an acceptance because it is an
immutable Decision relation, not a lifecycle reversal. Idempotency is scoped by
`(decision_id, "decision_acceptance", idempotency_key)`. Equivalent semantic
replay returns the existing record; reuse with a different payload fails
without a write. Generated acceptance identity/time and evidence capture times
are excluded from equivalence.

The thin CLI additionally exposes:

```text
neural decision accept DECISION_UUID --accepted-by TEXT --reason TEXT --idempotency-key KEY
neural decision acceptance-history DECISION_UUID
```

Repeated `--evidence` and `--tag` values are supported, and evidence locators
are never read. Acceptance authorizes possible future execution; it does not
itself execute the Decision or create actions, outcomes, reviews, or learning.

The DecisionAction foundation records work performed under one accepted
Decision. `DecisionAction` is immutable and stores `id`, `recorded_at`,
`decision_id`, `acceptance_id`, bounded `action_type`, `summary`,
`performed_by`, `started_at`, optional `completed_at`, embedded evidence,
optional `playbook_run_id`, `idempotency_key`, and normalized tags. All
timestamps are UTC-aware, and completion cannot precede start. The record has
no mutable status and expresses no success, validation, outcome, or review.

`DecisionActionRepository` exposes only `save()`, `load_all()`, and
`get_by_id()`. `JsonDecisionActionRepository` stores deterministic one-file-per-
record JSON under `NeuralPaths.DECISION_ACTIONS`. `DecisionActionService`
requires the Decision and acceptance to exist, requires the acceptance to
belong to that Decision, validates an optional PlaybookRun exists, and owns
application-layer history filtering. The current PlaybookRun/Playbook model has
no project key, so existence is the only compatible project-context check that
can be derived without a separate schema change.

Action idempotency is scoped by
`(decision_id, "decision_action", idempotency_key)`. Generated action identity,
recording time, and evidence capture times are excluded from semantic
equivalence. Equivalent replay returns the existing action; conflicting reuse
fails without a write. Multiple distinct actions are allowed.

The DecisionOutcome foundation adds immutable factual validation records with
Decision, acceptance, and one-or-more action relations. Its exact fields are
`id`, `recorded_at`, `decision_id`, `acceptance_id`, ordered unique
`action_ids`, `result`, `summary`, `validated_by`, `validated_at`, embedded
evidence, immutable scalar `metrics`, `idempotency_key`, and normalized tags.
Result is bounded to `succeeded`, `failed`, `partial`, or `unknown`.

Metrics contain at most 100 trimmed, bounded, case-insensitively unique keys and
only bool, int, finite float, or bounded string values. Nested structures are
rejected. The mapping is immutable and serialized with deterministic key order.
`DecisionOutcomeRepository` exposes only persistence operations, while
`DecisionOutcomeService` owns relation validation, history/show behavior,
idempotency, and the non-persisted immutable `DecisionOutcomeSummary` read
model. Outcome idempotency is scoped by
`(decision_id, "decision_outcome", idempotency_key)` and excludes generated ID,
recording time, and evidence capture times from semantic comparison.

`DecisionLifecycleService` remains the single canonical projection owner. It
checks persisted acceptance/action/outcome relations and derives exactly:

```text
no acceptance -> proposed
acceptance, no action -> accepted
acceptance and at least one valid action -> in_progress
latest valid outcome succeeded -> succeeded
latest valid outcome failed -> failed
latest valid outcome partial -> partial
latest valid outcome unknown -> outcome_unknown
```

Latest outcome and summary selection use `validated_at` followed by outcome UUID
as a stable tie-breaker, never repository order. The summary reports outcome
count, latest result/time, distinct linked actions, result counts, and whether
success or failure exists. It is derived on demand and never persisted.

The CLI additionally exposes `neural decision outcome add`, `outcome-history`,
`outcome-show`, and `outcome-summary`. Repeated `--metric KEY=VALUE` values are
parsed as unambiguous bool/int/float values or retained as strings. The CLI
executes no commands and reads no evidence locators.

The DecisionReview foundation adds a separate immutable authorized
interpretation record over one Decision, its acceptance, and one or more
explicit ordered DecisionOutcome records. Action lineage remains transitive
through outcomes. `DecisionReviewRepository` exposes only `save()`,
`load_all()`, and `get_by_id()`, and `JsonDecisionReviewRepository` stores one
deterministic JSON file per review under `NeuralPaths.DECISION_REVIEWS`.

`DecisionReviewService.add()` validates every relation and requires
`reviewed_at` to be at or after the latest referenced `validated_at` before
writing. Idempotency is scoped by
`(decision_id, "decision_review", idempotency_key)`, ignores generated review
identity/time and evidence capture times, returns equivalent replay, and rejects
conflicts. Different keys append reviews; earlier reviews are never mutated or
replaced. History validates persisted relations and sorts by
`(reviewed_at, review.id)`, independent of repository order.

Review assessment is exactly `sound`, `flawed`, `mixed`, or `inconclusive`;
confidence is exactly `low`, `medium`, or `high`. Findings and candidate lessons
remain interpretive statements and do not constitute learning. The CLI exposes
`neural decision review add`, `review history`, and `review show` without
opening evidence locators.

`DecisionLifecycleService` remains unchanged and does not depend on reviews.
There is no `reviewed` or composite lifecycle state: `neural decision state`
continues to return `proposed`, `accepted`, `in_progress`, `succeeded`,
`failed`, `partial`, or `outcome_unknown` from acceptance/action/outcome facts.
No review automatically creates Experience, Knowledge, Playbook,
PlaybookEvaluation, PlaybookRevision, EvolutionProposal, or any other learning
artifact. Execution, lifecycle reversal, ingestion, Consigliere integration,
automatic learning/evolution, and Handbook synchronization remain unimplemented
outside the bounded local evidence flow described below. Explicit
Review-to-Experience promotion is a separate use case:
Review statements are not Experience until it succeeds, and the resulting
Experience is still not Knowledge. One Review may produce multiple Experiences
under distinct promotion keys. Reviewer and promoter are separate authorities;
promotion changes no Decision lifecycle state. The next downstream learning
step remains a separate explicit decision.

The bounded local development-evidence dogfooding flow is documented in
`docs/development-evidence-ingestion.md`. It adds a specialized local source
adapter and application orchestrator, not a persisted evidence or candidate
aggregate. The adapter owns repository-local Markdown and Git reading; the
orchestrator owns correlation, non-persisted preview, explicit revalidated
apply, deterministic replay identity, and dependency-order calls into the
existing Decision-family services. The CLI remains a parsing and rendering
surface.

## Authority-Aware Planner Context

`PlannerContextService.prepare()` is a read-only application use case for one
planner assessment. It coordinates five narrow reader ports for verified
repository metadata, a fixed current-document inventory, caller-selected Brain
Knowledge UUIDs, a fixed review inventory, and caller-supplied bounded
historical or frozen-release evidence. The returned immutable package always
contains its seven authority-labelled categories and never allows supporting or
historical evidence to override a verified live checkout.

The use case has no CLI, persistence model, writer port, cache, source
registry, filesystem discovery, prompt execution, semantic retrieval, or Brain
write. Current-source reads verify the supplied repository checkpoint before
and after reading; a mismatch produces no `CURRENT` assertion.

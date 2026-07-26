# PlaybookRevision Lifecycle Design

## Current State

`PlaybookRevision` is an immutable candidate snapshot of revised Playbook
content. It is created from explicit user-supplied or external-system supplied
content and references:

* one existing Playbook,
* one accepted EvolutionProposal,
* one or more existing Knowledge items.

Creating a revision does not modify the Playbook, apply the proposal, activate
the revision, or perform automatic evolution.

Current read-only relation navigation for revisions is owned by
`PlaybookRevisionService`:

* `neural playbook revisions UUID`
* `neural proposal revisions UUID`
* `neural knowledge revisions UUID`

Each relation verifies the source entity exists, loads revisions through
`PlaybookRevisionRepository.load_all()`, filters in the application layer,
preserves repository order, and avoids persistence-specific query methods.

## Problem

Candidate revisions are inspectable but do not yet answer which revision, if
any, is the active or selected version for a Playbook. NeuralEngine needs a
lifecycle design before implementing activation behavior, because activation
could easily blur important boundaries:

* accepted EvolutionProposal status must not apply changes,
* Playbooks must not be mutated implicitly,
* revisions must remain explicit candidate snapshots,
* automatic evolution must not be introduced by accident.

The lifecycle model must record an explicit manual or external-system decision
without turning candidate creation into Playbook mutation.

## Options

### Option A - Active Revision Stored On Playbook

Example:

```text
Playbook.active_revision_id
```

This makes current-version lookup simple because the Playbook directly points
to the active revision. It is less suitable now because it mutates the Playbook
schema, couples Playbook persistence to revision lifecycle, and risks making
activation feel like a Playbook update instead of a separate decision. It also
does not naturally record why a revision became active, who decided, what it
replaced, or when rollback happened.

### Option B - Activation Stored On PlaybookRevision

Example:

```text
PlaybookRevision.status = candidate | active | superseded | rejected
```

This keeps lifecycle state close to the revision artifact. It is less suitable
now because `PlaybookRevision` currently represents an immutable content
snapshot. Updating status would either mutate the revision record or require a
separate event-like interpretation of a mutable field. Activating one revision
would also require coordinated transitions for other revisions for the same
Playbook, which makes validation and persistence more complex.

### Option C - Separate Lifecycle Artifact

Example:

```text
PlaybookRevisionActivation
```

or:

```text
PlaybookVersionSelection
```

This records activation as its own explicit artifact. It preserves immutable
Playbook and PlaybookRevision content while creating an audit trail for the
decision. It fits NeuralEngine's existing pattern of representing important
decisions as durable records rather than implicit side effects.

The tradeoff is that it adds a new vertical slice: a domain model, repository
port, JSON adapter, application service, CLI commands, and relation navigation.
That cost is justified because lifecycle decisions are first-class historical
events, not incidental metadata.

### Option D - No Activation Concept Yet

This keeps the system as candidate-only. Users can inspect revisions and
manually copy useful content elsewhere outside NeuralEngine. It preserves all
current invariants but limits the usefulness of the evolution chain because the
system cannot answer which revised candidate is currently selected for use.

This option is acceptable as the temporary implementation state, but it should
not be the target design.

## Recommendation

Recommend Option C: introduce a separate lifecycle artifact named
`PlaybookRevisionActivation`.

NeuralEngine should have an explicit active/current revision concept, but the
state should live in a dedicated activation artifact, not on Playbook and not on
PlaybookRevision. Activation should mean "this revision was explicitly selected
for this Playbook at this time for this reason." It must not mean the Playbook
record was rewritten or the revision content became mutable.

This option best fits the current architecture because:

* domain records remain explicit and inspectable,
* Playbook content stays stable unless a future separate Playbook-editing use
  case explicitly changes it,
* PlaybookRevision remains an immutable candidate snapshot,
* accepted EvolutionProposal status remains only a proposal decision,
* activation becomes a separate manual or external-system decision,
* application services can own lifecycle validation,
* repository ports can remain persistence contracts.

The lifecycle domain foundation now exists: `PlaybookRevisionActivation`, its
decision enum, local domain validation, and focused domain tests. The
persistence foundation also exists: `PlaybookRevisionActivationRepository`,
`JsonPlaybookRevisionActivationRepository`,
`NeuralPaths.PLAYBOOK_REVISION_ACTIVATIONS`, and container repository wiring.
The application service foundation also exists:
`PlaybookRevisionActivationService` creates and persists explicit lifecycle
decisions after validating Playbook, PlaybookRevision, EvolutionProposal, and
same-Playbook supersession linkage. It also provides read-only lifecycle
inspection for listing activation records for one Playbook, one
PlaybookRevision, or one EvolutionProposal, and deriving the current active
revision from activation records in repository order. These foundations include
read-only CLI inspection through
`neural playbook revision-history UUID` and
`neural playbook active-revision UUID`, `neural revision activation-history
UUID`, and `neural proposal activation-history UUID`, plus the record-only
activation write command `neural revision activate REVISION_UUID --playbook
PLAYBOOK_UUID --proposal PROPOSAL_UUID --reason TEXT`, and convenience write
commands `neural revision supersede NEW_REVISION_UUID --playbook PLAYBOOK_UUID
--proposal PROPOSAL_UUID --previous-revision OLD_REVISION_UUID --reason TEXT`
and `neural revision reject REVISION_UUID --playbook PLAYBOOK_UUID --proposal
PROPOSAL_UUID --reason TEXT`. They do not add Playbook mutation, proposal
application, automatic evolution, or repository query methods.

Rejected options are less suitable now because they store lifecycle state by
mutating existing records. That is simpler at first, but it weakens the audit
trail and makes activation look like a schema update rather than a separate
decision in the evolution chain.

## Invariants

The lifecycle design must preserve these invariants:

1. No automatic evolution.
2. No implicit Playbook mutation.
3. PlaybookRevision records remain explicit user-supplied or external-system
   supplied candidate snapshots.
4. Accepted EvolutionProposal status does not apply changes.
5. Activation is a separate explicit user-supplied or external-system supplied
   decision.
6. Activating a revision does not modify the Playbook content.
7. Activating a revision does not modify the PlaybookRevision content.
8. Activating a revision does not change EvolutionProposal status.
9. CLI remains a thin input and rendering layer.
10. Application services own lifecycle use cases and validation.
11. Repository ports remain persistence contracts, not service APIs.
12. Validation happens before persistence.
13. Agents do not commit or push.

## Proposed CLI

These commands describe the lifecycle CLI surface implemented so far.

### First Command To Implement

```bash
neural revision activate REVISION_UUID --playbook PLAYBOOK_UUID --proposal PROPOSAL_UUID --reason TEXT
```

Behavior:

* write command,
* exit `0` when activation is recorded,
* exit `1` for missing revision, missing referenced Playbook, invalid proposal
  relationship, or invalid lifecycle transition,
* exit `2` for invalid UUID or invalid CLI input,
* delegates to an application service,
* persists a `PlaybookRevisionActivation` record only after validation.
* implemented.

It must not modify Playbook content, modify PlaybookRevision content, change
proposal status, apply a proposal, infer revised content, or perform automatic
evolution.

### Read Current Selection

```bash
neural playbook active-revision PLAYBOOK_UUID
```

Behavior:

* read-only command,
* exit `0` when the Playbook exists, including when no active revision exists,
* exit `1` when the Playbook is missing,
* exit `2` for invalid UUID,
* renders the latest active activation decision and referenced revision summary
  if one exists.

It must not create activation state or change any existing record.

### Read Lifecycle History

```bash
neural playbook revision-history PLAYBOOK_UUID
```

Behavior:

* read-only command,
* exit `0` when the Playbook exists,
* exit `1` when the Playbook is missing,
* exit `2` for invalid UUID,
* renders activation, supersession, and rejection decisions in repository order
  or a documented service order.

It must not infer missing decisions, activate revisions, or mutate records.

### Supersede An Active Revision

```bash
neural revision supersede NEW_REVISION_UUID \
  --playbook PLAYBOOK_UUID \
  --proposal PROPOSAL_UUID \
  --previous-revision OLD_REVISION_UUID \
  --reason TEXT
```

Behavior:

* write command,
* exit `0` when a supersession decision is recorded,
* exit `1` for missing revisions, cross-Playbook supersession, or invalid
  lifecycle transition,
* exit `2` for invalid UUID or invalid CLI input,
* delegates to `PlaybookRevisionActivationService.add(...)`,
* records an explicit `superseded` lifecycle decision.

It must not delete or rewrite older activation records.

### Reject A Candidate Revision

```bash
neural revision reject REVISION_UUID \
  --playbook PLAYBOOK_UUID \
  --proposal PROPOSAL_UUID \
  --reason TEXT
```

Behavior:

* write command,
* exit `0` when a rejection decision is recorded,
* exit `1` for missing revision or invalid lifecycle transition,
* exit `2` for invalid UUID or invalid CLI input,
* delegates to `PlaybookRevisionActivationService.add(...)`,
* records an explicit `rejected` lifecycle decision.

It must not change EvolutionProposal status and must not delete the candidate
revision.

## Persistence Design

Recommended future domain name:

```text
PlaybookRevisionActivation
```

Recommended status or decision enum:

```text
PlaybookRevisionActivationDecision = active | superseded | rejected
```

The domain foundation implements this model and enum. The repository and JSON
adapter foundation implements basic `save()`, `load_all()`, and `get_by_id()`
persistence only. Service and CLI behavior remain future work.

Recommended fields:

```text
id
timestamp
playbook_id
revision_id
proposal_id
decision
reason
previous_revision_id
decided_by
notes
tags
```

Field notes:

* `playbook_id` duplicates the revision's Playbook relation intentionally so
  activation history can be listed by Playbook without loading every revision
  first.
* `proposal_id` should match the revision's proposal and supports provenance.
* `previous_revision_id` is optional and should be required for supersession
  decisions when a previous active revision is known.
* `decided_by` is a manual or external-system source string, not an autonomous
  agent claim.
* `reason` is required for write decisions so activation is auditable.

Recommended repository port:

```text
PlaybookRevisionActivationRepository
```

Recommended persistence path concept:

```text
NeuralPaths.PLAYBOOK_REVISION_ACTIVATIONS
```

The JSON adapter should store one activation decision per file, matching the
current repository pattern for other durable artifacts.

Required validation rules:

* decision requires a non-empty reason,
* referenced revision must exist,
* referenced Playbook must exist,
* referenced proposal must exist through the revision and must still belong to
  the same Playbook,
* activation must verify that `revision.playbook_id == playbook_id`,
* activation must verify that `revision.proposal_id == proposal_id`,
* supersession must verify both revisions belong to the same Playbook,
* rejection must not target a revision that has already been superseded by a
  later active decision unless a clear transition rule is introduced,
* all validation must finish before persistence.

Initial relation navigation needs:

* list activation decisions for one Playbook,
* get latest active revision selection for one Playbook,
* list lifecycle decisions for one PlaybookRevision,
* optionally list lifecycle decisions for one EvolutionProposal.

The PlaybookRevision and EvolutionProposal relation navigation now exists as
read-only application service methods:
`PlaybookRevisionActivationService.list_for_revision(UUID)` and
`PlaybookRevisionActivationService.list_for_proposal(UUID)`. Each method
verifies the source entity exists, loads activation records through
`PlaybookRevisionActivationRepository.load_all()`, filters in the application
layer, preserves repository order, and avoids repository query methods.

Repository ports should initially expose simple persistence operations such as
`save()`, `load_all()`, and `get_by_id()`. Application services should compose
relation navigation by loading and filtering until a persistence-specific
query is justified by scale.

## PlaybookRevisionApplication Foundation

Activation and application must remain separate concepts.

Activation means a lifecycle or audit decision was recorded for a
PlaybookRevision. It answers which revision was selected, superseded, or
rejected, when, and why. Activation does not change Playbook content.

Application now has a foundation audit artifact,
`PlaybookRevisionApplication`, with its own repository port, JSON adapter, path
constant, container wiring, and application service. In this foundation slice,
application records explicit intent/audit only: saved records set
`content_changed` to `False` and do not change Playbook content. Future
materialization of revision content into a Playbook remains a separate design
and implementation step. Application must not be triggered automatically by
activation state.

### Recommended Concept Name

The concept name is `PlaybookRevisionApplication`.

This name is better than `PlaybookRevisionMaterialization` or
`PlaybookRevisionApply` because application describes a deliberate domain
action. It avoids implying automatic synchronization between a revision and a
Playbook, matches the idea of applying a selected candidate, and can naturally
carry audit metadata about who applied it, when, and why.

### Application Invariants

Application behavior must preserve these invariants:

1. `PlaybookRevision` remains immutable.
2. `PlaybookRevisionActivation` remains audit and lifecycle state only.
3. Applying a revision must be explicit.
4. Applying a revision must not be triggered automatically by `active`,
   `superseded`, or `rejected` decisions.
5. Only the currently active revision should be eligible for application unless
   a future explicit override is designed.
6. Rejected revisions must not be applicable.
7. Superseded previous revisions must not be applicable unless they are
   re-activated by a later explicit lifecycle decision.
8. Applying a revision must preserve auditability.
9. Applying a revision must be idempotency-aware.
10. Applying a revision must record who, when, and why.
11. Applying a revision must not silently change EvolutionProposal status.

### Application Validation

`PlaybookRevisionApplicationService` completes validation before any
application record is persisted. Because this foundation slice does not mutate
Playbook content, the saved audit record explicitly reports
`content_changed = False`.

Current validation includes:

* Playbook exists.
* PlaybookRevision exists.
* EvolutionProposal exists and is still `accepted`.
* Revision belongs to the supplied Playbook.
* Revision belongs to the expected EvolutionProposal.
* Optional source activation exists when supplied.
* Optional source activation belongs to the same Playbook/revision/proposal
  relation.
* Revision is currently active according to
  `PlaybookRevisionActivationService.get_active_revision_for_playbook()`.

The conservative proposal status policy is that application should require the
proposal to still be `accepted`, matching revision creation. The foundation
implements that policy without changing proposal status. If a future workflow
needs proposal status updates, that must be a separate explicit command or
service action.

### Audit Trail

The current application record contains enough information to reconstruct the
audit decision without relying on mutable Playbook state alone.

Recommended fields:

* application id,
* timestamp,
* playbook id,
* revision id,
* proposal id,
* source activation id, when available,
* applied_by,
* reason,
* whether Playbook content changed (`False` in this foundation),
* idempotency key,
* notes,
* tags.

Future before/after metadata can be added only with an explicit materialization
design that proves which Playbook content was replaced and which revision
content became current.

### Repository Boundary

The repository port is:

```text
PlaybookRevisionApplicationRepository
```

Methods stay persistence-focused:

```text
save(application)
load_all()
get_by_id(application_id)
```

No query methods are added. Relation navigation such as
applications for one Playbook or one PlaybookRevision should first be composed
in `PlaybookRevisionApplicationService` by loading and filtering records in the
application layer.

### Run execution provenance

`PlaybookRun` separately owns the caller's factual declaration about manual or
external execution. A Run may reference zero or one exact PlaybookRevision.
`PlaybookRunService` validates that a supplied revision exists and belongs to
the Run's Playbook, and reverse navigation loads and filters Runs in repository
order.

The relation is never derived from current activation state or from
`PlaybookRevisionApplication`. A revision need not be active or have an
application-intent record for the caller to record the factual content used.
Old Runs without the relation remain valid and make no revision-specific claim.

### Application Service Boundary

The service is:

```text
PlaybookRevisionApplicationService
```

Current methods:

```text
add(playbook_id, revision_id, proposal_id, reason, applied_by=None, notes=None, tags=(), source_activation_id=None, idempotency_key=None)
list_for_playbook(playbook_id)
list_for_revision(revision_id)
list_for_proposal(proposal_id)
```

`add(...)` records the application audit artifact only. It is not allowed to
change Playbook content in this foundation slice. The read-only methods follow
the existing load-and-filter relation navigation pattern. The service delegates
active revision resolution to
`PlaybookRevisionActivationService.get_active_revision_for_playbook()` and does
not replay activation history itself.

### Future CLI/API Sketch

These commands are proposed future behavior only. They are not implemented.

```bash
neural revision apply REVISION_UUID \
  --playbook PLAYBOOK_UUID \
  --proposal PROPOSAL_UUID \
  --reason "Apply selected active revision"
```

Read-only application history commands could be:

```bash
neural playbook application-history PLAYBOOK_UUID
neural revision application-history REVISION_UUID
```

Existing activation commands remain unchanged:

```text
neural revision activate
neural revision supersede
neural revision reject
```

They still record lifecycle decisions only. They do not apply, materialize, or
copy revision content into Playbook content.

### Application Non-Goals

This design does not implement:

* Playbook mutation,
* PlaybookRevision materialization,
* an apply command,
* schemas,
* CLI application history commands,
* proposal status changes,
* automatic evolution.

## Future Implementation Sequence

1. Add lifecycle domain foundation:
   `PlaybookRevisionActivation`, decision enum, domain tests, and documentation
   updates. Do not add CLI behavior yet. Completed.
2. Add lifecycle repository port and JSON adapter:
   `PlaybookRevisionActivationRepository`,
   `JsonPlaybookRevisionActivationRepository`, path constant, repository tests,
   and container wiring. Completed.
3. Add activation application service:
   validation for missing revision, missing Playbook, proposal mismatch,
   same-Playbook supersession, required reason, and no persistence before
   validation completes. Completed.
4. Add read-only lifecycle inspection:
   service methods for lifecycle history and active revision derivation.
   Completed for the application service and read-only CLI inspection.
5. Add activation write command:
   `neural revision activate REVISION_UUID --playbook PLAYBOOK_UUID --proposal
   PROPOSAL_UUID --reason TEXT`, delegating to the application service.
   Completed.
6. Add supersession and rejection decisions:
   service methods and CLI for `neural revision supersede ...` and
   `neural revision reject ...`. Completed for CLI convenience commands that
   delegate to `PlaybookRevisionActivationService.add(...)`.
7. Add relation navigation:
   lifecycle decisions by revision and by proposal, owned by the lifecycle
   application service. Completed for read-only service and CLI inspection.
8. Design explicit PlaybookRevision application/materialization boundary.
   Completed in this document. Activation remains separate from application.
9. Add `PlaybookRevisionApplication` domain, service, repository, and relation
   navigation foundation. Completed for audit records, JSON persistence,
   container wiring, service validation, load/filter relation navigation, and
   tests. No CLI behavior or Playbook content mutation was added.
10. Add future CLI inspection and record commands only after this foundation is
    accepted. That future implementation must still avoid Playbook mutation
    unless an explicit materialization design is reviewed.

## Non-Goals

This design still does not implement:

* persistence schemas,
* migrations,
* proposal application,
* Playbook mutation,
* PlaybookRevision materialization,
* proposal status changes,
* automatic evolution,
* LLM-generated revision content.

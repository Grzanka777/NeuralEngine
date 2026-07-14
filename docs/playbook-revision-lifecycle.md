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
decision enum, local domain validation, and focused domain tests. This
foundation does not add CLI behavior, persistence, activation behavior, or
broad relation navigation.

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

These commands are proposed for future implementation only. They are not part
of the current design task.

### First Command To Implement

```bash
neural revision activate REVISION_UUID --reason TEXT
```

Behavior:

* write command,
* exit `0` when activation is recorded,
* exit `1` for missing revision, missing referenced Playbook, invalid proposal
  relationship, or invalid lifecycle transition,
* exit `2` for invalid UUID or invalid CLI input,
* delegates to an application service,
* persists a `PlaybookRevisionActivation` record only after validation.

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
neural revision supersede REVISION_UUID --by OTHER_REVISION_UUID --reason TEXT
```

Behavior:

* write command,
* exit `0` when a supersession decision is recorded,
* exit `1` for missing revisions, cross-Playbook supersession, or invalid
  lifecycle transition,
* exit `2` for invalid UUID or invalid CLI input,
* records an explicit lifecycle decision.

It must not delete or rewrite older activation records.

### Reject A Candidate Revision

```bash
neural revision reject REVISION_UUID --reason TEXT
```

Behavior:

* write command,
* exit `0` when a rejection decision is recorded,
* exit `1` for missing revision or invalid lifecycle transition,
* exit `2` for invalid UUID or invalid CLI input.

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

The domain foundation implements this model and enum only. Repository,
persistence, service, and CLI behavior remain future work.

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

Repository ports should initially expose simple persistence operations such as
`save()`, `load_all()`, and `get_by_id()`. Application services should compose
relation navigation by loading and filtering until a persistence-specific
query is justified by scale.

## Future Implementation Sequence

1. Add lifecycle domain foundation:
   `PlaybookRevisionActivation`, decision enum, domain tests, and documentation
   updates. Do not add CLI behavior yet.
2. Add lifecycle repository port and JSON adapter:
   `PlaybookRevisionActivationRepository`,
   `JsonPlaybookRevisionActivationRepository`, path constant, repository tests,
   and container wiring.
3. Add activation application service:
   validation for missing revision, missing Playbook, proposal mismatch,
   same-Playbook supersession, required reason, and no persistence before
   validation completes.
4. Add read-only lifecycle inspection:
   service methods and CLI for `neural playbook active-revision UUID` and
   `neural playbook revision-history UUID`.
5. Add activation write command:
   `neural revision activate REVISION_UUID --reason TEXT`, delegating to the
   application service.
6. Add supersession and rejection decisions:
   service methods and CLI for `neural revision supersede ...` and
   `neural revision reject ...`.
7. Add relation navigation:
   lifecycle decisions by revision and by proposal, owned by the lifecycle
   application service.
8. Review whether a current Playbook materialization use case is needed:
   if needed, design it separately and keep it explicit rather than making
   activation mutate Playbook content.

## Non-Goals

This design does not implement:

* production code,
* tests,
* CLI commands,
* persistence schemas,
* migrations,
* revision activation,
* proposal application,
* Playbook mutation,
* proposal status changes,
* automatic evolution,
* LLM-generated revision content.

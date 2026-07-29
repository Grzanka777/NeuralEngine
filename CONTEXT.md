# Current Context

## Current Focus

Close the documentation-defined NeuralEngine 1.0 release boundary without
adding product behavior.

The canonical capability scope, interpretive limits, non-goals, writer
assumptions, and release evidence gate are defined in
[`docs/1-0-scope-and-release-gate.md`](docs/1-0-scope-and-release-gate.md).

## Current State

- The explicit core chain is implemented from Observation through
  EvolutionProposal, including immutable PlaybookRevision snapshots, explicit
  activation, record-only application intent, Run provenance, and evaluation.
- The Decision family is implemented from Decision through DecisionReview,
  with optional explicit Review-derived Experience promotion.
- Local development evidence supports no-write preview, fresh revalidation,
  explicit declarative authority confirmation, and apply through existing
  Decision-family services.
- Knowledge, PlaybookRevision, and PlaybookRun repositories have explicit
  create-once, identical same-ID replay, conflict, and stored-identity
  integrity contracts. Those guarantees do not extend implicitly to every
  repository.
- The latest committed checkpoint is
  `6303abe56e8362478f7cc60dc9d841658ee815d8`
  (`fix: enforce playbook run create-once persistence`).

## 1.0 Closure State

- No new feature or implementation milestone is required by the accepted 1.0
  readiness assessment.
- The package remains `0.0.1a1`; an exact package-version and Git-tag decision
  is a separate release action.
- Publication of the current Handbook-generated NeuralEngine skill remains a
  separate required documentation task. The skill is not copied or regenerated
  in this milestone.
- Live operational evidence is present through Knowledge selection into a
  Playbook and for Decision/development-evidence dogfooding. Live Revision,
  activation, application, Run, Evaluation, and EvolutionProposal evidence is
  still absent; this is an evidence gap, not an implementation blocker.

## Current Priority

1. Complete this documentation-only closure and its validation evidence.
2. Publish the current generated skill byte-for-byte in a separately authorized
   task.
3. Record the remaining operational evidence inventory and exact release
   version/tag decision before release.

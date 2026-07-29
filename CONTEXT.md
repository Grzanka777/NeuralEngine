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
  `cbfd2185437a2cad38e6059bb14ad177ea9753ae`
  (`docs: publish current NeuralEngine generated skill`).

## 1.0 Closure State

- No new feature or implementation milestone is required by the accepted 1.0
  readiness assessment.
- The package version is `1.0.0`.
- Publication of the current Handbook-generated NeuralEngine skill is complete
  at commit `cbfd2185437a2cad38e6059bb14ad177ea9753ae`.
- Live operational evidence is present through Knowledge selection into a
  Playbook and for Decision/development-evidence dogfooding. Live Revision,
  activation, application, Run, Evaluation, and EvolutionProposal evidence is
  still absent. The release owner explicitly accepts these six evidence gaps
  and their documented residual risk; no synthetic Brain records or additional
  implementation are required.
- The intended Git tag is annotated `v1.0.0` with message
  `NeuralEngine 1.0.0`. It has not been created.
- This task prepares the versioned release candidate only. The candidate still
  requires review, commit, push, and revalidation before the separate tag step.

## Current Priority

1. Review and commit the bounded `1.0.0` release candidate.
2. Push and revalidate the exact version commit with `HEAD == origin/main`.
3. In a separate authorized step, create annotated tag `v1.0.0` with message
   `NeuralEngine 1.0.0`, then verify and push it.

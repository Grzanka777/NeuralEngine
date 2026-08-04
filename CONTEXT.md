# Current Context

## Current Focus

Maintain the post-`v1.1.0` current-state record while preserving the canonical
NeuralEngine 1.0 capability boundary as historical release documentation.

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
- Neural home selection is opt-in through `NEURAL_HOME`. The exact default
  remains `Path.home() / ".neural"`; a supplied override must resolve to one
  existing accessible absolute directory and fails closed without local
  fallback. All operational paths derive from one immutable resolved home.
  This is path selection only, not migration, synchronization, backup,
  locking, or mount management.
- `neural doctor` provides bounded read-only operational-readiness evidence for
  the selected home: home/Brain access, version/config files, all 15 stores,
  record readability and domain integrity, identity/duplicate checks, counts,
  and a deterministic relative-path manifest. It does not initialize, repair,
  migrate, configure, or write state.
- `neural knowledge search QUERY` is merged. It is read-only, preserves
  repository load order, and performs case-insensitive substring matching
  against Knowledge statements and rationales only.
- Package version `1.1.0` and annotated tag `v1.1.0` exist at release commit
  `f9b74c652b2000e1d5eedf16fc1e3427a6ff3b2b`. Knowledge-search implementation
  commit `22918f4f6897e05f7e695dd3de3f0cac3b0bd6bc` was merged to `main` by
  merge commit `7f276b2bc20391a182a94163cedaac574a9b196a`. Agent-governance
  hardening implementation commit `5c34c4f14282ae2a6415d83de4715d733f0f025c`
  was merged to `main` by merge commit `bf437f89b3a32dc87490ea4ebb6a93a5d713c8f4`.
- The historical 1.0 release commit is
  `dd90164ee6842c3dbc0b68cd6b290cfcbc712d4e`
  (`release: prepare NeuralEngine 1.0.0`).
- `v1.0.0` remains an invariant historical annotated tag that peels to that
  release commit; it is not the current package or release state.

## 1.0 Closure State

- No new feature or implementation milestone is required by the accepted 1.0
  readiness assessment.
- The package version and release state recorded here are historical `1.0.0`;
  the current package version is `1.1.0`.
- Publication of the current Handbook-generated `NEURAL_HOME` skill is
  complete at commit `73b90efb8785b8c5202a28fd9de09b7939ee3670`.
- One bounded real retrospective operational-validation chain is complete:
  Playbook `62da1509-c12a-474c-a08d-4ba041f71ca1` -> PlaybookRun
  `8046aaa3-2689-4822-97e1-5b6b20c2b573` -> PlaybookEvaluation
  `bbe16b37-c461-4cf3-a25d-760459fe7674`.
- The Evaluation is `effective`, records no improvements, and is the endpoint
  of the chain. An EvolutionProposal was not justified and was not created.
  PlaybookRevision, PlaybookRevisionActivation,
  PlaybookRevisionApplication, and EvolutionProposal stores each contain
  0 records.
- This single retrospective scenario does not establish general effectiveness,
  independent third-party validation, authenticated evaluator identity,
  statistical generalizability, revision-bearing execution,
  Activation/Application evidence, or a changed-Playbook feedback cycle.
- Brain persistence is host-local under `~/.neural/brain`; Git does not
  synchronize it. The selected authoritative host contains the verified
  22-entry Brain. Durable Brain writes remain restricted to that host until an
  explicit migration and operating policy exists. `NEURAL_HOME` has not been
  configured on the host, and no portable Neural home has been created.

## Current Priority

No release-finalization task remains. The `v1.1.0` release, merged Knowledge
search, and post-release agent-governance hardening are current repository
history. Any further product or persistence work requires separate
authorization and must preserve the documented 1.0 boundary.

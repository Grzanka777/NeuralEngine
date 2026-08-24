# NeuralEngine 1.0 Scope and Release Evidence Gate

## Status and Authority

This document is the canonical NeuralEngine 1.0 capability boundary and release
evidence gate.

It defines what the existing source supports, how that behavior must be
interpreted, and what evidence is required before release. It does not declare
that 1.0 has been released, change package versioning, add product behavior, or
turn future designs and hardening candidates into requirements.

The scope is grounded in source checkpoint:

```text
6303abe56e8362478f7cc60dc9d841658ee815d8
fix: enforce playbook run create-once persistence
```

## Supported Capability Scope

NeuralEngine 1.0 is a local, explicit, human- or external-system-directed
recording and inspection system. Application services validate relations and
delegate persistence through ports; the CLI remains an input and rendering
surface.

### Core Records and Evolution Chain

The supported chain is:

```text
Observation
-> Experience
-> Knowledge
-> Playbook
-> PlaybookRevision
-> PlaybookRevisionActivation
-> PlaybookRevisionApplication
-> PlaybookRun
-> PlaybookEvaluation
-> EvolutionProposal
```

The supported behavior at each boundary is:

| Capability | Supported 1.0 behavior |
|---|---|
| Observation | Capture, list, show, search, and navigate to explicitly related Experiences. Exact duplicate content produces a warning but remains a distinct Observation. |
| Experience | Create directly or from an existing Observation; validate referenced Observations; list, show, and navigate to Knowledge. |
| Knowledge | Explicitly create a caller-supplied rule or lesson from one or more existing Experiences; validate Experience provenance on supported reads; list, show, and navigate to Playbooks and Revisions. |
| Playbook | Explicitly create a stored operational procedure with ordered Knowledge IDs, steps, and success criteria; list, show, and inspect related Runs, Proposals, Revisions, and activation state. |
| PlaybookRevision | Explicitly create an immutable candidate content snapshot from an accepted EvolutionProposal for the same Playbook, with caller-supplied ordered Knowledge IDs and revised content. |
| PlaybookRevisionActivation | Explicitly record activation, supersession, or rejection decisions and derive the current active Revision from lifecycle history without mutating Playbook or Revision content. |
| PlaybookRevisionApplication | Through the application service, explicitly record validated application intent/audit for the active Revision with `content_changed=False`. No application CLI or materialization behavior is included. |
| PlaybookRun | Explicitly record that a caller manually or externally applied a Playbook. A Run may declare one exact Revision belonging to that Playbook or make no Revision-specific claim. |
| PlaybookEvaluation | Explicitly record a human- or external-system-supplied assessment of one existing Run, including effectiveness, findings, and optional improvement evidence. |
| EvolutionProposal | Explicitly record proposed Playbook changes based on Evaluations whose Runs belong to that Playbook, and explicitly update proposal status. Accepted status does not create or apply a Revision. |

### Decision Lifecycle

The supported Decision family is:

```text
Decision
-> DecisionAcceptance
-> DecisionAction
-> DecisionOutcome
-> DecisionReview
-> optional explicit DecisionReview-derived Experience
```

- Decision records one bounded choice, alternatives, rationale, provenance, and
  optional Observation relations.
- DecisionAcceptance is a separate immutable authorization record for one
  Decision.
- DecisionAction records work performed under one accepted Decision and may
  reference an existing PlaybookRun.
- DecisionOutcome records factual validation over one or more exact Actions.
- DecisionReview records authorized interpretation over exact Outcomes.
- Decision lifecycle state is a non-persisted projection over Acceptance,
  Action, and Outcome facts. Review does not add a `reviewed` state.
- Selected Review findings or candidate lessons may be promoted explicitly
  into an Experience. The service copies exact Review text and provenance;
  promotion is idempotent within its explicit key and remains a separate
  authority from Review.

### Local Development Evidence

The supported dogfooding flow is deliberately bounded:

```text
one NeuralEngine worktree
+ one explicitly selected repository-relative prompt
+ one explicitly selected repository-relative review
+ one exact full non-merge commit
-> validated no-write preview
-> fresh source re-read and revalidation
-> explicit apply with declarative authority confirmation
-> existing Decision-family services
-> optional existing Review-to-Experience service
```

- The local source adapter reads and normalizes the selected Markdown and Git
  evidence.
- Preview constructs and validates a non-persisted candidate and performs no
  durable write.
- Apply immediately re-reads and revalidates source identities and rejects a
  stale or contradictory candidate.
- `--confirm-authority` is required at the application boundary.
- Durable records are created only through existing domain application
  services; the orchestrator does not duplicate their persistence or relation
  rules.
- Apply is non-transactional. A partial failure may leave a valid prefix of
  records.
- Exact rerun can resume only because each durable step used by this workflow
  has a proven semantic idempotency, create-once, conflict, uniqueness, or
  equivalent duplicate-effect boundary.

## Interpretive Limits

The following distinctions are part of the 1.0 contract:

1. Selecting a Knowledge ID into `Playbook.knowledge_ids` is not evidence that
   the Playbook was used.
2. Recording a PlaybookRun establishes caller-declared manual or external use;
   it does not prove that one Knowledge item caused the result.
3. Multi-Knowledge Playbook feedback applies at Playbook and declared
   Knowledge-set scope. It does not attribute individual causal contribution.
4. Review findings and candidate lessons are interpretation, not Experience.
   Explicit Review-derived Experience does not automatically create Knowledge.
5. Knowledge creation records a generalized statement linked to Experience; it
   does not prove efficacy, causal improvement, or later use.
6. Proposal acceptance, Revision creation, activation, application, execution,
   evaluation, and later proposal creation are separate explicit actions.
7. Activation is a lifecycle selection decision, not application.
8. `PlaybookRevisionApplication` is record-only intent/audit with unchanged
   content. It is not execution, Playbook mutation, or Revision
   materialization.
9. PlaybookRun records externally or manually performed execution provenance.
   NeuralEngine does not execute Playbook steps.
10. Revision provenance on a Run is caller-declared and never inferred from
    activation or application records.
11. An identical same-ID repository replay is not ordinary service or CLI
    semantic replay. Normal service/CLI creation may construct a fresh record
    identity even when content resembles an earlier record.
12. `--confirm-authority` is a declarative application-level confirmation. It
    is not authentication, authorization, principal identity, RBAC, or a
    signature.
13. Preview plus fresh revalidation protects visibility and source freshness;
    it does not by itself provide transactionality or resumability.
14. Safe retry after a partial apply depends on a duplicate-effect boundary at
    every durable step. Adding a step without such a boundary invalidates a
    safe-replay claim for the sequence.
15. Evidence references are bounded locators and hashes. Their presence does
    not prove external authenticity and does not authorize opening or executing
    the referenced material outside the owning use case.

## Persistence, Writer, and Concurrency Assumptions

The supported 1.0 operating model is:

- local filesystem-backed JSON persistence under the NeuralEngine Brain;
- writes performed through supported application-service and CLI boundaries;
- application services as owners of domain and relation validation;
- repository ports and their adapters as owners of storage behavior;
- a local workflow with no promise of concurrent multi-process semantic
  uniqueness unless a specific repository contract proves it;
- direct filesystem creation, replacement, deletion, or corruption outside
  NeuralEngine as out-of-band behavior;
- no distributed writer, locking, transaction, or consensus guarantee.

Create-once guarantees apply only where the repository explicitly implements
them:

- Knowledge;
- PlaybookRevision;
- PlaybookRun.

For those repositories, supported same-ID writes validate the complete model,
preserve an identical existing payload without replacement, reject a different
payload as conflict, and reject malformed or identity-mismatched stored data.
This is not backup, migration, versioning, historical reconstruction,
cryptographic tamper evidence, or protection from direct filesystem mutation.

Other UUID-addressed repositories do not inherit this contract by analogy.
EvolutionProposal status replacement is a separate protected M12 use case: it
publishes one exact JSON target with literal BEFORE/AFTER hashes and bounded
forward-only recovery. M23 development-evidence apply remains outside the
Brain Trust boundary. NeuralEngine 1.0 does not promise universal create-once
persistence or cross-process uniqueness.

## Explicit 1.0 Non-Goals

NeuralEngine 1.0 does not include:

- automatic Observation-to-Experience, Experience-to-Knowledge,
  Knowledge-to-Playbook, or Review-to-Experience promotion;
- automatic learning, inference, ranking, efficacy attribution, or feedback
  interpretation;
- a Playbook execution or workflow engine;
- automatic Run evaluation;
- automatic EvolutionProposal generation, acceptance, or rejection;
- automatic Revision creation, activation, application, or evolution;
- Playbook content mutation or Revision materialization through
  `PlaybookRevisionApplication`;
- inference of Run Revision provenance from lifecycle or application records;
- authenticated authorization, RBAC, principal verification, or signatures;
- transactionality across development-evidence apply;
- a universal Preview-Revalidate-Apply rule for every operation;
- universal create-once conversion;
- distributed or concurrent multi-writer guarantees;
- schemas or migrations as a release requirement;
- backup, disaster recovery, historical reconstruction, or cryptographic
  tamper evidence unless separately selected and authorized;
- GitHub, CI, webhook, watcher, hosted-service, or multi-repository
  development-evidence ingestion;
- Consigliere integration or persona-policy changes;
- an application/materialization CLI that source does not implement.

These non-goals are boundaries, not missing features.

## Historical Release-Gate Evidence Inventory

At release preparation, the evidence classification was:

| Area | Release-preparation evidence |
|---|---|
| Decision-family dogfooding | Strong: live Decision, Acceptance, Action, Outcome, and Review records exist. |
| Development-evidence preview/apply/replay | Strong: accepted reviews record no-write preview, fresh revalidation, authority-confirmed apply, exact replay, and store-invariance checks. |
| Review-derived Experience | Present in live records. |
| Experience-derived Knowledge | Present in live records. |
| Knowledge selection into Playbook | Present in one live Playbook with persisted Knowledge ordering. |
| PlaybookRevision | No live record yet. |
| PlaybookRevisionActivation | No live record yet. |
| PlaybookRevisionApplication | No live record yet. |
| PlaybookRun | No live record yet. |
| PlaybookEvaluation | No live record yet. |
| EvolutionProposal | No live record yet. |

Missing live records are operational evidence gaps, not implementation blockers.
They must not be created merely to make the release inventory appear complete.
The inventory must be refreshed before release and may explicitly retain a gap
when the release owner accepts that evidence level.

The release owner explicitly accepts the six gaps for `PlaybookRevision`,
`PlaybookRevisionActivation`, `PlaybookRevisionApplication`, `PlaybookRun`,
`PlaybookEvaluation`, and `EvolutionProposal`. The downstream end-to-end
operator experience, real cross-record integration, and practical usefulness
of the evaluation/evolution loop have not yet been exercised against the
durable Brain. Source and tests cover the bounded mechanics. No additional real
operational exercise is mandatory before release, and no synthetic record is
required or authorized. Real post-1.0 evidence collection remains recommended.

### Current Post-1.0 Operational Evidence

After the release gate, one bounded real retrospective operational-validation
chain was completed:

- Playbook: `62da1509-c12a-474c-a08d-4ba041f71ca1`
- PlaybookRun: `8046aaa3-2689-4822-97e1-5b6b20c2b573`
- PlaybookEvaluation: `bbe16b37-c461-4cf3-a25d-760459fe7674`

The Evaluation is `effective`, records no improvements, and is the endpoint of
the chain. An EvolutionProposal was not justified and was not created. Current
PlaybookRevision, PlaybookRevisionActivation, PlaybookRevisionApplication, and
EvolutionProposal stores each contain 0 records.

This closes one bounded retrospective scenario only. It does not establish
general effectiveness, independent third-party validation, authenticated
evaluator identity, statistical generalizability, revision-bearing execution,
Activation/Application evidence, or a changed-Playbook feedback cycle.

Brain persistence is host-local under `~/.neural/brain`; Git does not
synchronize Brain records. The selected authoritative host contains the
verified 22-entry Brain. Durable Brain writes remain restricted to that host
until an explicit synchronization, export, or import policy exists.

## Release Evidence Gate

The gate uses the existing local validation workflow. It creates no new CI
system or release framework.

Every item below is required before the release is declared:

### 1. Repository and Scope Preconditions

- the release candidate is on the intended branch;
- `HEAD == origin/main`;
- tracked and staged Git state is clean;
- the changed-path inventory for the release is reviewed and contains no
  unrelated work;
- the canonical scope and current project context match the release candidate;
- no explicit non-goal is presented as implemented behavior.

### 2. Static Validation

Run from the repository root:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m ruff format --check .
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m ruff check .
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m mypy src tests
```

All commands must exit zero. A formatter check is used at the release gate so
validation does not rewrite the candidate.

### 3. Full Isolated Test Suite

Create a temporary isolated directory, run:

```bash
HOME=<temporary isolated directory> \
XDG_CONFIG_HOME=<temporary isolated directory>/.config \
GIT_CONFIG_GLOBAL=/dev/null \
GIT_CONFIG_NOSYSTEM=1 \
PYTHONDONTWRITEBYTECODE=1 \
.venv/bin/python -m pytest -p no:cacheprovider
```

The full suite must exit zero. Remove the temporary directory afterward.

### 4. Durable Brain Invariance

Before and after validation:

- record every Brain store count;
- record a sorted SHA-256 manifest of every Brain file;
- require exact count and manifest equality.

Validation must not create, update, delete, or repair a durable Brain record.

### 5. Generated Skill Publication

Before release, complete the separately authorized documentation publication
step:

- copy the current
  `NeuralEngine-Handbook/outputs/claude-skill/SKILL.md` directly to
  `NeuralEngine/.claude/skills/neuralengine/SKILL.md`;
- do not regenerate or manually edit either file during the copy step;
- prove byte-for-byte equality with `cmp -s`;
- prove matching SHA-256 values.

This publication was completed byte-for-byte at NeuralEngine commit
`cbfd2185437a2cad38e6059bb14ad177ea9753ae`. The equality requirement remains
part of final release evidence.

### 6. Operational Evidence

- record the operational evidence inventory using the categories above;
- distinguish absent live evidence from implementation failure;
- record any accepted evidence gap and release risk explicitly;
- do not create synthetic durable records solely to satisfy the gate.

### 7. Version and Tag Decision

The release owner selected:

```text
package version: 1.0.0
tag: v1.0.0
tag type: annotated
tag message: NeuralEngine 1.0.0
operational evidence gaps: explicitly accepted
```

The versioned release candidate subsequently converged at
`dd90164ee6842c3dbc0b68cd6b290cfcbc712d4e`. `HEAD` and `origin/main` both
resolve to that commit, and the annotated `v1.0.0` tag peels to the same
commit. Release convergence is complete. The sequencing above remains the
historical authorization record rather than current pending work.

### 8. Final Evidence

Record:

```text
git status --short --untracked-files=all
git diff --check
git diff --stat
git diff --name-only
git diff --cached --exit-code
git rev-parse HEAD
git rev-parse origin/main
git log -1 --oneline
```

Also retain exact static-validation output, full-test output, Brain before/after
proof, generated-skill equality proof, operational inventory, and the
version/tag decision.

## Gate Interpretation

The gate is evidence for the bounded capability set, not permission to broaden
it. A useful hardening candidate, absent aspirational feature, or missing live
record does not become a release blocker unless it contradicts this supported
contract or produces a concrete integrity or safety failure.

Any such observed failure must be assessed narrowly. Implementation work
requires separate authorization.

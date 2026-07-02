# Architecture

Neural Engine follows Clean Architecture.

## Layers

Domain:

* Owns core concepts such as `Observation`, `Experience`, `Knowledge`,
  `Playbook`, `PlaybookRun`, `PlaybookEvaluation`, `EvolutionProposal`, and
  `PlaybookRevision`.
* Has no dependency on infrastructure.

Application:

* Coordinates use cases such as adding, listing, and searching observations,
  adding, listing, and retrieving experiences, and adding, listing, and
  retrieving knowledge, playbooks, playbook runs, playbook evaluations, and
  evolution proposals and playbook revisions.
* Depends on ports instead of concrete infrastructure implementations.

Ports:

* Define repository interfaces required by application services.

Infrastructure:

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

CLI:

* Remains thin.
* Creates no business rules.
* Resolves application services through `application/container.py`.

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

`neural experience knowledge EXPERIENCE_UUID` delegates to
`KnowledgeService.list_for_experience()`. The service verifies the experience
exists through the `ExperienceRepository` port, loads knowledge through the
`KnowledgeRepository` port, and returns only knowledge linked to that experience
ID.

## Knowledge Flow

`neural knowledge add` calls the application container, receives a
`KnowledgeService`, and asks it to add knowledge from explicit user-supplied
statement, rationale, confidence, experience IDs, and optional tags. The CLI does
not generate, infer, summarize, or modify knowledge. The service rejects an empty
evidence list, then verifies each referenced experience through the
`ExperienceRepository` port before it creates or saves a domain `Knowledge`
item. Validation stops on the first missing experience and does not persist
knowledge when validation fails.

`neural knowledge list` retrieves all knowledge through the same service and
repository stack.

`neural knowledge from-experience EXPERIENCE_UUID` delegates to
`KnowledgeService.add_from_experience()`. The service loads the source
experience through the `ExperienceRepository` port once, rejects a missing
experience, and creates knowledge linked to that single experience ID using only
the statement, rationale, confidence, and tags supplied by the caller.

`neural knowledge show UUID` retrieves a single knowledge item through
`KnowledgeService.get_by_id()` and displays all knowledge fields.

`neural knowledge playbooks UUID` delegates to
`PlaybookService.list_for_knowledge()`. The service verifies the knowledge item
exists through the `KnowledgeRepository` port, loads playbooks through the
`PlaybookRepository` port, and returns only playbooks linked to that knowledge
ID.

The JSON repository is the current infrastructure implementation and stores one
file per knowledge item under `NeuralPaths.KNOWLEDGE`.

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

The JSON repository is the current infrastructure implementation and stores one
file per playbook under `NeuralPaths.PLAYBOOKS`.

Playbooks are stored procedures only. Neural Engine does not execute playbook
steps, orchestrate workflows, or generate playbooks automatically.

## Playbook Run Flow

`neural run add` calls the application container, receives a
`PlaybookRunService`, and records explicit user-supplied or external-system data
about an already performed application of one existing playbook to a concrete
situation. The service rejects an empty action list, verifies the referenced
playbook through the `PlaybookRepository` port, then creates and saves a domain
`PlaybookRun`. Validation stops before construction or persistence when actions
are missing or the playbook does not exist.

`neural run list` retrieves all playbook runs through the same service and
repository stack.

`neural run show UUID` retrieves a single playbook run through
`PlaybookRunService.get_by_id()` and displays all run fields.

`neural run evaluations UUID` delegates to
`PlaybookEvaluationService.list_for_run()`. The service verifies the playbook
run exists through the `PlaybookRunRepository` port, loads evaluations through
the `PlaybookEvaluationRepository` port, and returns only evaluations linked to
that run ID.

Playbook runs record manual or external application and do not duplicate
playbook data. They store the playbook ID, situation, actions taken, outcome,
success flag, optional evidence, optional notes, and optional tags. Neural
Engine does not execute playbooks or evaluate runs automatically.

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

`PlaybookRevisionService.list_revisions()` retrieves all playbook revisions
through the same service and repository stack.

`PlaybookRevisionService.get_by_id()` retrieves one playbook revision through
the `PlaybookRevisionRepository` port.

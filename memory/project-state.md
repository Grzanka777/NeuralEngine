# Project State

Last updated: 2026-07-01

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
  `neural knowledge playbooks UUID`

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

Neural Engine now has a minimal Playbook vertical slice:

* Domain model: `neural_engine.domain.Playbook`
* Application service: `PlaybookService`
* Port: `PlaybookRepository`
* Infrastructure implementation: `JsonPlaybookRepository`
* Dependency wiring: `application/container.py`
* CLI commands: `neural playbook add`, `neural playbook list`,
  `neural playbook show UUID`, `neural playbook runs UUID`, and
  `neural playbook proposals UUID`

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
* CLI commands: `neural proposal add`, `neural proposal list`, and
  `neural proposal show UUID`

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

## Validation

Latest validation passed:

* `uv run ruff format .`
* `uv run ruff check .`
* `uv run mypy src tests`
* `uv run pytest`

Pytest collected 260 tests.

## Notes for next work

The next logical step is to keep expanding read-only relation navigation where
it improves inspectability, without adding automatic evolution.

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
* CLI commands: `neural playbook add`, `neural playbook list`, and
  `neural playbook show UUID`, and `neural playbook runs UUID`

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

Neural Engine now has a minimal PlaybookRun vertical slice:

* Domain model: `neural_engine.domain.PlaybookRun`
* Application service: `PlaybookRunService`
* Port: `PlaybookRunRepository`
* Infrastructure implementation: `JsonPlaybookRunRepository`
* Dependency wiring: `application/container.py`
* CLI commands: `neural run add`, `neural run list`, and
  `neural run show UUID`

A PlaybookRun is an explicit record of manually or externally applying one
existing Playbook to a concrete situation. `PlaybookRunService.add()` requires
at least one action taken, validates the referenced Playbook through the
`PlaybookRepository` port before saving, and stores runs as one JSON file per
run under `NeuralPaths.PLAYBOOK_RUNS`. PlaybookRun records outcomes; Neural
Engine does not execute Playbooks or evaluate runs automatically. `neural run
add` records an already performed manual or external application.
`PlaybookRunService.list_for_playbook()` verifies one existing Playbook and
returns only runs whose `playbook_id` matches it.

## Validation

Latest validation passed:

* `uv run ruff format .`
* `uv run ruff check .`
* `uv run mypy src tests`
* `uv run pytest`

Pytest collected 159 tests.

## Notes for next work

The next logical step is to continue adding read-only relation commands where
they expose useful navigation without adding execution or automatic evaluation.

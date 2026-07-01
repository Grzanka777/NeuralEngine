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
  `neural knowledge list`, and `neural knowledge show UUID`

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

## Validation

Latest validation passed:

* `uv run ruff format .`
* `uv run ruff check .`
* `uv run mypy src tests`
* `uv run pytest`

Pytest collected 91 tests.

## Notes for next work

The next logical step is to decide how Knowledge should feed future Playbook
creation without adding automatic generation.

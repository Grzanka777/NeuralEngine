# Project State

Last updated: 2026-06-30

## Current implementation

Neural Engine has a first Observation vertical slice:

* Domain model: `neural_engine.domain.Observation`
* Application service: `ObservationService`
* Port: `ObservationRepository`
* Infrastructure implementation: `JsonObservationRepository`
* Dependency wiring: `application/container.py`
* CLI commands: `neural observe`, `neural list`, and `neural search`

Observations are stored as JSON files in the local Neural Engine brain
observation directory.

Neural Engine also has a minimal Experience vertical slice:

* Domain model: `neural_engine.domain.Experience`
* Result enum: `neural_engine.domain.ExperienceResult`
* Application service: `ExperienceService`
* Port: `ExperienceRepository`
* Infrastructure implementation: `JsonExperienceRepository`
* Dependency wiring: `application/container.py`
* CLI commands: `neural experience add`, `neural experience from-observation`,
  `neural experience list`, and `neural experience show UUID`

Experiences are stored as one JSON file per experience under
`NeuralPaths.EXPERIENCES`. Experience creation validates any supplied
observation IDs through the `ObservationRepository` port before saving.
`ExperienceService.add_from_observation()` creates an experience from one
existing observation by copying `Observation.content` exactly into the
experience context.

## Validation

Latest validation passed:

* `uv run ruff format .`
* `uv run ruff check .`
* `uv run mypy src tests`
* `uv run pytest`

Pytest collected 34 tests.

## Notes for next work

The next logical step is to decide how linked observations should be displayed
or summarized in experience workflows before adding automatic
Observation-to-Experience conversion.

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

Neural Engine also has a minimal Experience vertical slice without CLI commands:

* Domain model: `neural_engine.domain.Experience`
* Result enum: `neural_engine.domain.ExperienceResult`
* Application service: `ExperienceService`
* Port: `ExperienceRepository`
* Infrastructure implementation: `JsonExperienceRepository`
* Dependency wiring: `application/container.py`

Experiences are stored as one JSON file per experience under
`NeuralPaths.EXPERIENCES`.

## Validation

Latest validation passed:

* `uv run ruff format .`
* `uv run ruff check .`
* `uv run mypy src tests`
* `uv run pytest`

Pytest collected 18 tests.

## Notes for next work

The next logical step is to decide how experiences should be surfaced through
interfaces before adding CLI commands or any automatic Observation-to-Experience
conversion.

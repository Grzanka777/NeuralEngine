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

## Validation

Latest validation passed:

* `uv run ruff format .`
* `uv run ruff check .`
* `uv run mypy src tests`
* `uv run pytest`

Pytest collected 7 tests.

## Notes for next work

The next logical step is to define the Experience layer and the rule for turning
observations into experiences without coupling domain logic to storage.

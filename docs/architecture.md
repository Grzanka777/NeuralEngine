# Architecture

Neural Engine follows Clean Architecture.

## Layers

Domain:

* Owns core concepts such as `Observation` and `Experience`.
* Has no dependency on infrastructure.

Application:

* Coordinates use cases such as adding, listing, and searching observations,
  and adding, listing, and retrieving experiences.
* Depends on ports instead of concrete infrastructure implementations.

Ports:

* Define repository interfaces required by application services.

Infrastructure:

* Implements ports using concrete storage mechanisms.
* The current observation repository stores one JSON file per observation.
* The current experience repository stores one JSON file per experience.

CLI:

* Remains thin.
* Creates no business rules.
* Resolves application services through `application/container.py`.

## Observation Flow

`neural observe` calls the application container, receives an
`ObservationService`, and asks it to add an observation. The service creates a
domain `Observation` and persists it through the `ObservationRepository` port.
The JSON repository is the current infrastructure implementation of that port.

`neural list` retrieves all observations through the same service and
repository stack.

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

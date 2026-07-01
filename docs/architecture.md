# Architecture

Neural Engine follows Clean Architecture.

## Layers

Domain:

* Owns core concepts such as `Observation`, `Experience`, and `Knowledge`.
* Has no dependency on infrastructure.

Application:

* Coordinates use cases such as adding, listing, and searching observations,
  adding, listing, and retrieving experiences, and adding, listing, and
  retrieving knowledge.
* Depends on ports instead of concrete infrastructure implementations.

Ports:

* Define repository interfaces required by application services.

Infrastructure:

* Implements ports using concrete storage mechanisms.
* The current observation repository stores one JSON file per observation.
* The current experience repository stores one JSON file per experience.
* The current knowledge repository stores one JSON file per knowledge item.

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

The JSON repository is the current infrastructure implementation and stores one
file per knowledge item under `NeuralPaths.KNOWLEDGE`.

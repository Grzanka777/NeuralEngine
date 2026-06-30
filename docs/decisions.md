# Architecture Decisions

## 0001. Store observations through an application service and repository port

Status: Accepted

Observation capture is implemented as a vertical slice across the existing Clean
Architecture layers.

The CLI only parses user input and delegates to `ObservationService`.
`ObservationService` depends on the `ObservationRepository` port. The concrete
JSON storage implementation lives in infrastructure and is wired in
`application/container.py`.

This keeps the first persistence mechanism replaceable while preserving a thin
CLI and infrastructure-free domain model.

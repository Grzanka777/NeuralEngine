from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from neural_engine.domain import Observation
from neural_engine.ports.brain_trust_transition import (
    BrainTrustMutationCoordinator,
    ControlledCreateWriter,
)
from neural_engine.ports.observation_repository import ObservationRepository


@dataclass(frozen=True)
class AddObservationResult:
    """Result of adding an observation."""

    observation: Observation
    duplicate_ids: list[UUID]


class ObservationService:
    """Application service for observations."""

    def __init__(
        self,
        repository: ObservationRepository,
        controlled_writer: ControlledCreateWriter[Observation] | None = None,
        mutation_coordinator: BrainTrustMutationCoordinator | None = None,
    ) -> None:
        if (controlled_writer is None) != (mutation_coordinator is None):
            raise ValueError(
                "Controlled Observation writer and coordinator must be configured together."
            )
        self._repository = repository
        self._controlled_writer = controlled_writer
        self._mutation_coordinator = mutation_coordinator

    def add(
        self,
        content: str,
        tags: list[str] | None = None,
    ) -> AddObservationResult:
        existing_observations = self._repository.load_all()
        duplicate_ids = [
            observation.id
            for observation in existing_observations
            if observation.content == content
        ]

        observation = Observation(
            content=content,
            tags=tags or [],
        )

        if self._controlled_writer is not None and self._mutation_coordinator is not None:
            self._mutation_coordinator.execute(
                self._controlled_writer.controlled_create_target(observation)
            )
        else:
            self._repository.save(observation)

        return AddObservationResult(
            observation=observation,
            duplicate_ids=duplicate_ids,
        )

    def list_observations(self) -> list[Observation]:
        return self._repository.load_all()

    def get_by_id(self, observation_id: UUID) -> Observation | None:
        return self._repository.get_by_id(observation_id)

    def search(self, query: str) -> list[Observation]:
        results = []

        observations = self._repository.load_all()

        for observation in observations:
            if query.lower() in observation.content.lower():
                results.append(observation)

        return results

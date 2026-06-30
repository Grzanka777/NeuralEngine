from __future__ import annotations

from uuid import UUID

from neural_engine.domain import Observation
from neural_engine.ports.observation_repository import ObservationRepository


class ObservationService:
    """Application service for observations."""

    def __init__(
        self,
        repository: ObservationRepository,
    ) -> None:
        self._repository = repository

    def add(
        self,
        content: str,
        tags: list[str] | None = None,
    ) -> Observation:
        observation = Observation(
            content=content,
            tags=tags or [],
        )

        self._repository.save(observation)

        return observation

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

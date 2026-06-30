from __future__ import annotations

from uuid import UUID

from neural_engine.domain import Experience, ExperienceResult
from neural_engine.ports.experience_repository import ExperienceRepository
from neural_engine.ports.observation_repository import ObservationRepository


class ObservationNotFoundError(Exception):
    """Raised when an experience references an unknown observation."""

    def __init__(self, observation_id: UUID) -> None:
        self.observation_id = observation_id
        super().__init__(f"Observation not found: {observation_id}")


class ExperienceService:
    """Application service for experiences."""

    def __init__(
        self,
        experience_repository: ExperienceRepository,
        observation_repository: ObservationRepository,
    ) -> None:
        self._experience_repository = experience_repository
        self._observation_repository = observation_repository

    def add(
        self,
        title: str,
        context: str,
        action: str,
        outcome: str,
        result: ExperienceResult,
        observation_ids: list[UUID] | None = None,
        tags: list[str] | None = None,
    ) -> Experience:
        validated_observation_ids = observation_ids or []
        self._validate_observation_ids(validated_observation_ids)

        experience = Experience(
            title=title,
            context=context,
            action=action,
            outcome=outcome,
            result=result,
            observation_ids=validated_observation_ids,
            tags=tags or [],
        )

        self._experience_repository.save(experience)

        return experience

    def add_from_observation(
        self,
        observation_id: UUID,
        title: str,
        action: str,
        outcome: str,
        result: ExperienceResult,
        tags: list[str] | None = None,
    ) -> Experience:
        observation = self._observation_repository.get_by_id(observation_id)

        if observation is None:
            raise ObservationNotFoundError(observation_id)

        experience = Experience(
            title=title,
            context=observation.content,
            action=action,
            outcome=outcome,
            result=result,
            observation_ids=[observation.id],
            tags=tags or [],
        )

        self._experience_repository.save(experience)

        return experience

    def list_experiences(self) -> list[Experience]:
        return self._experience_repository.load_all()

    def get_by_id(self, experience_id: UUID) -> Experience | None:
        return self._experience_repository.get_by_id(experience_id)

    def _validate_observation_ids(self, observation_ids: list[UUID]) -> None:
        for observation_id in observation_ids:
            if self._observation_repository.get_by_id(observation_id) is None:
                raise ObservationNotFoundError(observation_id)

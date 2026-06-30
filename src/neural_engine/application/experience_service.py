from __future__ import annotations

from uuid import UUID

from neural_engine.domain import Experience, ExperienceResult
from neural_engine.ports.experience_repository import ExperienceRepository


class ExperienceService:
    """Application service for experiences."""

    def __init__(
        self,
        repository: ExperienceRepository,
    ) -> None:
        self._repository = repository

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
        experience = Experience(
            title=title,
            context=context,
            action=action,
            outcome=outcome,
            result=result,
            observation_ids=observation_ids or [],
            tags=tags or [],
        )

        self._repository.save(experience)

        return experience

    def list_experiences(self) -> list[Experience]:
        return self._repository.load_all()

    def get_by_id(self, experience_id: UUID) -> Experience | None:
        return self._repository.get_by_id(experience_id)

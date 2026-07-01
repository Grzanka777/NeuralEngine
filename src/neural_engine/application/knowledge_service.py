from __future__ import annotations

from uuid import UUID

from neural_engine.domain import Knowledge, KnowledgeConfidence
from neural_engine.ports.experience_repository import ExperienceRepository
from neural_engine.ports.knowledge_repository import KnowledgeRepository


class ExperienceNotFoundError(Exception):
    """Raised when knowledge references an unknown experience."""

    def __init__(self, experience_id: UUID) -> None:
        self.experience_id = experience_id
        super().__init__(f"Experience not found: {experience_id}")


class KnowledgeEvidenceRequiredError(Exception):
    """Raised when knowledge is created without experience evidence."""

    def __init__(self) -> None:
        super().__init__("Knowledge requires at least one experience ID.")


class KnowledgeService:
    """Application service for knowledge."""

    def __init__(
        self,
        knowledge_repository: KnowledgeRepository,
        experience_repository: ExperienceRepository,
    ) -> None:
        self._knowledge_repository = knowledge_repository
        self._experience_repository = experience_repository

    def add(
        self,
        statement: str,
        rationale: str,
        confidence: KnowledgeConfidence,
        experience_ids: list[UUID],
        tags: list[str] | None = None,
    ) -> Knowledge:
        self._validate_experience_ids(experience_ids)

        knowledge = Knowledge(
            statement=statement,
            rationale=rationale,
            confidence=confidence,
            experience_ids=experience_ids,
            tags=tags or [],
        )

        self._knowledge_repository.save(knowledge)

        return knowledge

    def list_knowledge(self) -> list[Knowledge]:
        return self._knowledge_repository.load_all()

    def get_by_id(self, knowledge_id: UUID) -> Knowledge | None:
        return self._knowledge_repository.get_by_id(knowledge_id)

    def _validate_experience_ids(self, experience_ids: list[UUID]) -> None:
        if not experience_ids:
            raise KnowledgeEvidenceRequiredError()

        for experience_id in experience_ids:
            if self._experience_repository.get_by_id(experience_id) is None:
                raise ExperienceNotFoundError(experience_id)

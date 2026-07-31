from __future__ import annotations

from typing import Protocol
from uuid import UUID

from neural_engine.domain import Experience, Knowledge, KnowledgeConfidence
from neural_engine.ports.knowledge_repository import KnowledgeRepository


class ExperienceReader(Protocol):
    """Validated application read boundary for Experience evidence."""

    def get_by_id(self, experience_id: UUID) -> Experience | None: ...


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
        experience_reader: ExperienceReader,
    ) -> None:
        self._knowledge_repository = knowledge_repository
        self._experience_reader = experience_reader

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

    def add_from_experience(
        self,
        experience_id: UUID,
        statement: str,
        rationale: str,
        confidence: KnowledgeConfidence,
        tags: list[str] | None = None,
    ) -> Knowledge:
        experience = self._require_experience(experience_id)

        knowledge = Knowledge(
            statement=statement,
            rationale=rationale,
            confidence=confidence,
            experience_ids=[experience.id],
            tags=tags or [],
        )

        self._knowledge_repository.save(knowledge)

        return knowledge

    def list_knowledge(self) -> list[Knowledge]:
        knowledge_items = self._knowledge_repository.load_all()
        for knowledge in knowledge_items:
            self._validate_knowledge_relations(knowledge)
        return knowledge_items

    def list_for_experience(self, experience_id: UUID) -> list[Knowledge]:
        self._require_experience(experience_id)

        knowledge_items = self._knowledge_repository.load_all()
        linked_items = [
            knowledge for knowledge in knowledge_items if experience_id in knowledge.experience_ids
        ]
        for knowledge in linked_items:
            self._validate_knowledge_relations(knowledge)
        return linked_items

    def get_by_id(self, knowledge_id: UUID) -> Knowledge | None:
        knowledge = self._knowledge_repository.get_by_id(knowledge_id)
        if knowledge is not None:
            self._validate_knowledge_relations(knowledge)
        return knowledge

    def search(self, query: str) -> list[Knowledge]:
        query_lower = query.lower()
        knowledge_items = self._knowledge_repository.load_all()
        for knowledge in knowledge_items:
            self._validate_knowledge_relations(knowledge)
        return [
            knowledge
            for knowledge in knowledge_items
            if query_lower in knowledge.statement.lower()
            or query_lower in knowledge.rationale.lower()
        ]

    def _validate_experience_ids(self, experience_ids: list[UUID]) -> None:
        if not experience_ids:
            raise KnowledgeEvidenceRequiredError()

        for experience_id in experience_ids:
            self._require_experience(experience_id)

    def _require_experience(self, experience_id: UUID) -> Experience:
        experience = self._experience_reader.get_by_id(experience_id)
        if experience is None:
            raise ExperienceNotFoundError(experience_id)
        return experience

    def _validate_knowledge_relations(self, knowledge: Knowledge) -> None:
        for experience_id in knowledge.experience_ids:
            self._require_experience(experience_id)

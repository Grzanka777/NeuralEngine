from __future__ import annotations

from uuid import UUID

from neural_engine.domain import Playbook
from neural_engine.ports.knowledge_repository import KnowledgeRepository
from neural_engine.ports.playbook_repository import PlaybookRepository


class PlaybookKnowledgeRequiredError(Exception):
    """Raised when a playbook is created without linked knowledge."""

    def __init__(self) -> None:
        super().__init__("Playbook requires at least one knowledge ID.")


class PlaybookStepsRequiredError(Exception):
    """Raised when a playbook is created without steps."""

    def __init__(self) -> None:
        super().__init__("Playbook requires at least one step.")


class KnowledgeNotFoundError(Exception):
    """Raised when a playbook references an unknown knowledge item."""

    def __init__(self, knowledge_id: UUID) -> None:
        self.knowledge_id = knowledge_id
        super().__init__(f"Knowledge not found: {knowledge_id}")


class PlaybookService:
    """Application service for playbooks."""

    def __init__(
        self,
        playbook_repository: PlaybookRepository,
        knowledge_repository: KnowledgeRepository,
    ) -> None:
        self._playbook_repository = playbook_repository
        self._knowledge_repository = knowledge_repository

    def add(
        self,
        title: str,
        situation: str,
        objective: str,
        steps: list[str],
        success_criteria: list[str],
        knowledge_ids: list[UUID],
        constraints: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> Playbook:
        self._validate(knowledge_ids, steps)

        playbook = Playbook(
            title=title,
            situation=situation,
            objective=objective,
            steps=steps,
            success_criteria=success_criteria,
            constraints=constraints or [],
            knowledge_ids=knowledge_ids,
            tags=tags or [],
        )

        self._playbook_repository.save(playbook)

        return playbook

    def list_playbooks(self) -> list[Playbook]:
        return self._playbook_repository.load_all()

    def list_for_knowledge(self, knowledge_id: UUID) -> list[Playbook]:
        if self._knowledge_repository.get_by_id(knowledge_id) is None:
            raise KnowledgeNotFoundError(knowledge_id)

        playbooks = self._playbook_repository.load_all()

        return [playbook for playbook in playbooks if knowledge_id in playbook.knowledge_ids]

    def get_by_id(self, playbook_id: UUID) -> Playbook | None:
        return self._playbook_repository.get_by_id(playbook_id)

    def _validate(self, knowledge_ids: list[UUID], steps: list[str]) -> None:
        if not knowledge_ids:
            raise PlaybookKnowledgeRequiredError()

        if not steps:
            raise PlaybookStepsRequiredError()

        for knowledge_id in knowledge_ids:
            if self._knowledge_repository.get_by_id(knowledge_id) is None:
                raise KnowledgeNotFoundError(knowledge_id)

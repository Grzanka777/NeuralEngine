from abc import ABC, abstractmethod
from uuid import UUID

from neural_engine.domain import PlaybookRevision


class PlaybookRevisionRepository(ABC):
    """Port for storing playbook revisions."""

    @abstractmethod
    def save(self, revision: PlaybookRevision) -> None:
        """Persist a playbook revision."""

    @abstractmethod
    def load_all(self) -> list[PlaybookRevision]:
        """Load all playbook revisions."""

    @abstractmethod
    def get_by_id(self, revision_id: UUID) -> PlaybookRevision | None:
        """Load one playbook revision by id."""

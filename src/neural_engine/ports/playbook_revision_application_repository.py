from abc import ABC, abstractmethod
from uuid import UUID

from neural_engine.domain import PlaybookRevisionApplication


class PlaybookRevisionApplicationRepository(ABC):
    """Port for storing playbook revision application audit records."""

    @abstractmethod
    def save(self, application: PlaybookRevisionApplication) -> None:
        """Persist a playbook revision application record."""

    @abstractmethod
    def load_all(self) -> list[PlaybookRevisionApplication]:
        """Load all playbook revision application records."""

    @abstractmethod
    def get_by_id(self, application_id: UUID) -> PlaybookRevisionApplication | None:
        """Load one playbook revision application record by id."""

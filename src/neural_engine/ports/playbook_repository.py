from abc import ABC, abstractmethod
from uuid import UUID

from neural_engine.domain import Playbook


class PlaybookRepository(ABC):
    """Port for storing playbooks."""

    @abstractmethod
    def save(self, playbook: Playbook) -> None:
        """Persist a playbook."""

    @abstractmethod
    def load_all(self) -> list[Playbook]:
        """Load all playbooks."""

    @abstractmethod
    def get_by_id(self, playbook_id: UUID) -> Playbook | None:
        """Load one playbook by id."""

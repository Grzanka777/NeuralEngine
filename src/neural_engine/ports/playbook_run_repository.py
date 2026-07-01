from abc import ABC, abstractmethod
from uuid import UUID

from neural_engine.domain import PlaybookRun


class PlaybookRunRepository(ABC):
    """Port for storing playbook runs."""

    @abstractmethod
    def save(self, run: PlaybookRun) -> None:
        """Persist a playbook run."""

    @abstractmethod
    def load_all(self) -> list[PlaybookRun]:
        """Load all playbook runs."""

    @abstractmethod
    def get_by_id(self, run_id: UUID) -> PlaybookRun | None:
        """Load one playbook run by id."""

from abc import ABC, abstractmethod
from uuid import UUID

from neural_engine.domain import PlaybookRevisionActivation


class PlaybookRevisionActivationRepository(ABC):
    """Port for storing playbook revision activations."""

    @abstractmethod
    def save(self, activation: PlaybookRevisionActivation) -> None:
        """Persist a playbook revision activation."""

    @abstractmethod
    def load_all(self) -> list[PlaybookRevisionActivation]:
        """Load all playbook revision activations."""

    @abstractmethod
    def get_by_id(self, activation_id: UUID) -> PlaybookRevisionActivation | None:
        """Load one playbook revision activation by id."""

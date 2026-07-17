from abc import ABC, abstractmethod
from uuid import UUID

from neural_engine.domain import DecisionAction


class DecisionActionRepository(ABC):
    """Port for storing Decision action records."""

    @abstractmethod
    def save(self, action: DecisionAction) -> None:
        """Persist a Decision action."""

    @abstractmethod
    def load_all(self) -> list[DecisionAction]:
        """Load all Decision actions."""

    @abstractmethod
    def get_by_id(self, action_id: UUID) -> DecisionAction | None:
        """Load one Decision action by ID."""

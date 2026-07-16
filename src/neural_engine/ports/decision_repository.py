from abc import ABC, abstractmethod
from uuid import UUID

from neural_engine.domain import Decision


class DecisionRepository(ABC):
    """Port for storing decisions."""

    @abstractmethod
    def save(self, decision: Decision) -> None:
        """Persist a decision."""

    @abstractmethod
    def load_all(self) -> list[Decision]:
        """Load all decisions."""

    @abstractmethod
    def get_by_id(self, decision_id: UUID) -> Decision | None:
        """Load one decision by ID."""

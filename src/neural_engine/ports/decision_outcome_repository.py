from abc import ABC, abstractmethod
from uuid import UUID

from neural_engine.domain import DecisionOutcome


class DecisionOutcomeRepository(ABC):
    """Port for storing Decision outcome records."""

    @abstractmethod
    def save(self, outcome: DecisionOutcome) -> None:
        """Persist a Decision outcome."""

    @abstractmethod
    def load_all(self) -> list[DecisionOutcome]:
        """Load all Decision outcomes."""

    @abstractmethod
    def get_by_id(self, outcome_id: UUID) -> DecisionOutcome | None:
        """Load one Decision outcome by ID."""

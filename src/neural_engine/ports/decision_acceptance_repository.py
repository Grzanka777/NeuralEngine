from abc import ABC, abstractmethod
from uuid import UUID

from neural_engine.domain import DecisionAcceptance


class DecisionAcceptanceRepository(ABC):
    """Port for storing Decision acceptance records."""

    @abstractmethod
    def save(self, acceptance: DecisionAcceptance) -> None:
        """Persist a Decision acceptance."""

    @abstractmethod
    def load_all(self) -> list[DecisionAcceptance]:
        """Load all Decision acceptances."""

    @abstractmethod
    def get_by_id(self, acceptance_id: UUID) -> DecisionAcceptance | None:
        """Load one Decision acceptance by ID."""

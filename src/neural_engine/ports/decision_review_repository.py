from abc import ABC, abstractmethod
from uuid import UUID

from neural_engine.domain import DecisionReview


class DecisionReviewRepository(ABC):
    """Port for storing Decision review records."""

    @abstractmethod
    def save(self, review: DecisionReview) -> None:
        """Persist a Decision review."""

    @abstractmethod
    def load_all(self) -> list[DecisionReview]:
        """Load all Decision reviews."""

    @abstractmethod
    def get_by_id(self, review_id: UUID) -> DecisionReview | None:
        """Load one Decision review by ID."""

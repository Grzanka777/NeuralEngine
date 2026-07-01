from abc import ABC, abstractmethod
from uuid import UUID

from neural_engine.domain import PlaybookEvaluation


class PlaybookEvaluationRepository(ABC):
    """Port for storing playbook evaluations."""

    @abstractmethod
    def save(self, evaluation: PlaybookEvaluation) -> None:
        """Persist a playbook evaluation."""

    @abstractmethod
    def load_all(self) -> list[PlaybookEvaluation]:
        """Load all playbook evaluations."""

    @abstractmethod
    def get_by_id(self, evaluation_id: UUID) -> PlaybookEvaluation | None:
        """Load one playbook evaluation by id."""

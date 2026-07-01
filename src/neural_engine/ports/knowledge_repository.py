from abc import ABC, abstractmethod
from uuid import UUID

from neural_engine.domain import Knowledge


class KnowledgeRepository(ABC):
    """Port for storing knowledge."""

    @abstractmethod
    def save(self, knowledge: Knowledge) -> None:
        """Persist knowledge."""

    @abstractmethod
    def load_all(self) -> list[Knowledge]:
        """Load all knowledge."""

    @abstractmethod
    def get_by_id(self, knowledge_id: UUID) -> Knowledge | None:
        """Load one knowledge item by id."""

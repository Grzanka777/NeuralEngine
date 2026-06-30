from abc import ABC, abstractmethod
from uuid import UUID

from neural_engine.domain import Experience


class ExperienceRepository(ABC):
    """Port for storing experiences."""

    @abstractmethod
    def save(self, experience: Experience) -> None:
        """Persist an experience."""

    @abstractmethod
    def load_all(self) -> list[Experience]:
        """Load all experiences."""

    @abstractmethod
    def get_by_id(self, experience_id: UUID) -> Experience | None:
        """Load one experience by id."""

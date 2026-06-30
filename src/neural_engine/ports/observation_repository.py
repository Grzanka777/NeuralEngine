from abc import ABC, abstractmethod

from neural_engine.domain import Observation


class ObservationRepository(ABC):
    """Port for storing observations."""

    @abstractmethod
    def save(self, observation: Observation) -> None:
        """Persist an observation."""

    @abstractmethod
    def load_all(self) -> list[Observation]:
        """Load all observations."""

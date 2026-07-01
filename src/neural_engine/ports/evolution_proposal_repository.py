from abc import ABC, abstractmethod
from uuid import UUID

from neural_engine.domain import EvolutionProposal


class EvolutionProposalRepository(ABC):
    """Port for storing evolution proposals."""

    @abstractmethod
    def save(self, proposal: EvolutionProposal) -> None:
        """Persist an evolution proposal."""

    @abstractmethod
    def load_all(self) -> list[EvolutionProposal]:
        """Load all evolution proposals."""

    @abstractmethod
    def get_by_id(self, proposal_id: UUID) -> EvolutionProposal | None:
        """Load one evolution proposal by id."""

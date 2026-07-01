from pathlib import Path
from uuid import UUID

from neural_engine.core.paths import NeuralPaths
from neural_engine.domain import EvolutionProposal
from neural_engine.ports.evolution_proposal_repository import (
    EvolutionProposalRepository,
)


class JsonEvolutionProposalRepository(EvolutionProposalRepository):
    """Stores evolution proposals as JSON files."""

    def __init__(self, directory: Path = NeuralPaths.EVOLUTION_PROPOSALS) -> None:
        self._directory = directory

    def save(self, proposal: EvolutionProposal) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)

        path = self._directory / f"{proposal.id}.json"

        path.write_text(
            proposal.model_dump_json(indent=2),
            encoding="utf-8",
        )

    def load_all(self) -> list[EvolutionProposal]:
        if not self._directory.exists():
            return []

        proposals: list[EvolutionProposal] = []

        for path in sorted(self._directory.glob("*.json")):
            proposals.append(
                EvolutionProposal.model_validate_json(path.read_text(encoding="utf-8"))
            )

        return proposals

    def get_by_id(self, proposal_id: UUID) -> EvolutionProposal | None:
        path = self._directory / f"{proposal_id}.json"

        if not path.exists():
            return None

        return EvolutionProposal.model_validate_json(path.read_text(encoding="utf-8"))

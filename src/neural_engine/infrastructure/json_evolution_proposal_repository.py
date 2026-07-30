from pathlib import Path
from uuid import UUID

from neural_engine.core.paths import NeuralPaths
from neural_engine.domain import EvolutionProposal
from neural_engine.infrastructure.repository_paths import RepositoryPath
from neural_engine.ports.evolution_proposal_repository import (
    EvolutionProposalRepository,
)


class JsonEvolutionProposalRepository(EvolutionProposalRepository):
    """Stores evolution proposals as JSON files."""

    def __init__(
        self,
        directory: Path | None = None,
        *,
        paths: NeuralPaths | None = None,
    ) -> None:
        self._path = RepositoryPath.build(
            directory,
            paths,
            lambda value: value.EVOLUTION_PROPOSALS,
        )
        self._directory = self._path.directory

    def save(self, proposal: EvolutionProposal) -> None:
        self._path.prepare_for_write()

        path = self._directory / f"{proposal.id}.json"

        path.write_text(
            proposal.model_dump_json(indent=2),
            encoding="utf-8",
        )

    def load_all(self) -> list[EvolutionProposal]:
        self._path.guard(operation="read")
        if not self._directory.exists():
            return []

        proposals: list[EvolutionProposal] = []

        for path in sorted(self._directory.glob("*.json")):
            proposals.append(
                EvolutionProposal.model_validate_json(path.read_text(encoding="utf-8"))
            )

        return proposals

    def get_by_id(self, proposal_id: UUID) -> EvolutionProposal | None:
        self._path.guard(operation="read")
        path = self._directory / f"{proposal_id}.json"

        if not path.exists():
            return None

        return EvolutionProposal.model_validate_json(path.read_text(encoding="utf-8"))

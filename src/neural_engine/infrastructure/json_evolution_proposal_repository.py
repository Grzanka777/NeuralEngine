from pathlib import Path
from uuid import UUID

from neural_engine.core.paths import NeuralPaths
from neural_engine.domain import EvolutionProposal
from neural_engine.infrastructure.controlled_create import (
    build_controlled_create_target,
    publish_create_once,
)
from neural_engine.infrastructure.repository_paths import RepositoryPath
from neural_engine.ports.brain_trust_transition import ControlledMutationTarget
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

    def controlled_create_target(self, proposal: EvolutionProposal) -> ControlledMutationTarget:
        candidate, serialized = self._candidate_bytes(proposal)
        path = self._directory / f"{candidate.id}.json"
        return build_controlled_create_target(
            self._path.paths,
            path,
            serialized,
            lambda: publish_create_once(path, serialized, self._path.prepare_for_write),
        )

    @staticmethod
    def _candidate_bytes(proposal: EvolutionProposal) -> tuple[EvolutionProposal, bytes]:
        candidate = EvolutionProposal.model_validate_json(proposal.model_dump_json(indent=2))
        return candidate, candidate.model_dump_json(indent=2).encode("utf-8")

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

import hashlib
import stat
from pathlib import Path
from uuid import UUID

from neural_engine.application.brain_trust_transition import (
    BrainTrustMutationPreparationError,
)
from neural_engine.core.paths import NeuralPaths
from neural_engine.domain import EvolutionProposal
from neural_engine.infrastructure.controlled_create import (
    build_controlled_create_target,
    publish_create_once,
)
from neural_engine.infrastructure.controlled_replace import (
    build_controlled_replace_target,
    publish_replace_if_unchanged,
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

    def controlled_replace_target(
        self,
        current: EvolutionProposal,
        replacement: EvolutionProposal,
    ) -> ControlledMutationTarget:
        paths = self._path.paths
        if paths is None:
            raise ValueError("Controlled REPLACE targets require NeuralPaths-backed storage.")
        if current.id != replacement.id:
            raise ValueError("Controlled proposal replacement must preserve the proposal ID.")

        path = self._directory / f"{current.id}.json"
        try:
            self._reject_symlink_components(path)
            target_stat = path.lstat()
            if not stat.S_ISREG(target_stat.st_mode):
                raise ValueError("target is not a regular file")
            before_bytes = path.read_bytes()
            stored = EvolutionProposal.model_validate_json(before_bytes)
        except Exception as error:
            if isinstance(error, BrainTrustMutationPreparationError):
                raise
            raise BrainTrustMutationPreparationError(
                "current EvolutionProposal bytes cannot be validated"
            ) from error
        if stored.id != current.id:
            raise BrainTrustMutationPreparationError(
                "EvolutionProposal filename and payload IDs differ"
            )
        if stored != current:
            raise BrainTrustMutationPreparationError(
                "current EvolutionProposal changed before replacement preparation"
            )

        candidate, after_bytes = self._candidate_bytes(replacement)
        if candidate.id != current.id:
            raise BrainTrustMutationPreparationError(
                "controlled proposal replacement must preserve the proposal ID"
            )
        before_sha256 = hashlib.sha256(before_bytes).hexdigest()
        return build_controlled_replace_target(
            paths,
            path,
            before_sha256,
            after_bytes,
            lambda: publish_replace_if_unchanged(
                path,
                path.relative_to(paths.BRAIN).as_posix(),
                before_sha256,
                after_bytes,
                self._path.prepare_for_write,
            ),
        )

    def _reject_symlink_components(self, path: Path) -> None:
        if self._path.paths is None:
            return
        current = self._path.paths.BRAIN
        try:
            relative = path.relative_to(current)
        except ValueError as error:
            raise ValueError("Evolution proposal path must remain below Brain.") from error
        for component in relative.parts:
            current /= component
            try:
                mode = current.lstat().st_mode
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(mode):
                raise ValueError("Evolution proposal path must not traverse symbolic links.")

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

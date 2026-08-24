from pathlib import Path
from uuid import UUID

from pydantic import ValidationError

from neural_engine.core.brain_trust import TargetAction
from neural_engine.core.paths import NeuralPaths
from neural_engine.domain import PlaybookRevision
from neural_engine.infrastructure.durability import create_once_bytes
from neural_engine.infrastructure.repository_paths import RepositoryPath
from neural_engine.ports.brain_trust_transition import ControlledMutationTarget
from neural_engine.ports.playbook_revision_repository import (
    PlaybookRevisionIdentityMismatchError,
    PlaybookRevisionPersistenceConflictError,
    PlaybookRevisionRepository,
    PlaybookRevisionStoredDataError,
)


class JsonPlaybookRevisionRepository(PlaybookRevisionRepository):
    """Stores playbook revisions as JSON files."""

    def __init__(
        self,
        directory: Path | None = None,
        *,
        paths: NeuralPaths | None = None,
    ) -> None:
        self._path = RepositoryPath.build(
            directory,
            paths,
            lambda value: value.PLAYBOOK_REVISIONS,
        )
        self._directory = self._path.directory

    def save(self, revision: PlaybookRevision) -> None:
        candidate, serialized = self._candidate_bytes(revision)
        self._publish_candidate(self._directory / f"{revision.id}.json", candidate, serialized)

    def controlled_create_target(self, revision: PlaybookRevision) -> ControlledMutationTarget:
        """Prepare one Revision create for deferred Brain Trust publication."""

        if self._path.paths is None:
            raise ValueError(
                "Controlled PlaybookRevision targets require NeuralPaths-backed storage."
            )

        candidate, serialized = self._candidate_bytes(revision)
        path = self._directory / f"{revision.id}.json"
        relative_path = path.relative_to(self._path.paths.BRAIN).as_posix()
        return ControlledMutationTarget(
            relative_path=relative_path,
            action=TargetAction.CREATE,
            after_bytes=serialized,
            publish=lambda: self._publish_candidate(path, candidate, serialized),
        )

    def _publish_candidate(
        self,
        path: Path,
        candidate: PlaybookRevision,
        serialized: bytes,
    ) -> None:
        self._path.prepare_for_write()
        try:
            create_once_bytes(path, serialized)
        except FileExistsError:
            existing = self._load_path(path, candidate.id)
            if existing != candidate:
                raise PlaybookRevisionPersistenceConflictError(candidate.id) from None

    @staticmethod
    def _candidate_bytes(revision: PlaybookRevision) -> tuple[PlaybookRevision, bytes]:
        candidate = PlaybookRevision.model_validate_json(revision.model_dump_json(indent=2))
        return candidate, candidate.model_dump_json(indent=2).encode("utf-8")

    def load_all(self) -> list[PlaybookRevision]:
        self._path.guard(operation="read")
        if not self._directory.exists():
            return []

        revisions: list[PlaybookRevision] = []

        for path in sorted(self._directory.glob("*.json")):
            try:
                expected_id = UUID(path.stem)
            except ValueError as error:
                raise PlaybookRevisionStoredDataError(path.stem) from error
            revisions.append(self._load_path(path, expected_id))

        return revisions

    def get_by_id(self, revision_id: UUID) -> PlaybookRevision | None:
        self._path.guard(operation="read")
        path = self._directory / f"{revision_id}.json"

        if not path.exists():
            return None

        return self._load_path(path, revision_id)

    @staticmethod
    def _load_path(path: Path, expected_id: UUID) -> PlaybookRevision:
        try:
            revision = PlaybookRevision.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError) as error:
            raise PlaybookRevisionStoredDataError(str(expected_id)) from error

        if revision.id != expected_id:
            raise PlaybookRevisionIdentityMismatchError(expected_id, revision.id)

        return revision

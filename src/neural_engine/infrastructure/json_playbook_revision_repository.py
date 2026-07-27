import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import UUID

from pydantic import ValidationError

from neural_engine.core.paths import NeuralPaths
from neural_engine.domain import PlaybookRevision
from neural_engine.ports.playbook_revision_repository import (
    PlaybookRevisionIdentityMismatchError,
    PlaybookRevisionPersistenceConflictError,
    PlaybookRevisionRepository,
    PlaybookRevisionStoredDataError,
)


class JsonPlaybookRevisionRepository(PlaybookRevisionRepository):
    """Stores playbook revisions as JSON files."""

    def __init__(self, directory: Path = NeuralPaths.PLAYBOOK_REVISIONS) -> None:
        self._directory = directory

    def save(self, revision: PlaybookRevision) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)

        path = self._directory / f"{revision.id}.json"
        serialized = revision.model_dump_json(indent=2)
        candidate = PlaybookRevision.model_validate_json(serialized)
        temporary_path: Path | None = None

        try:
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self._directory,
                prefix=f".{revision.id}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                temporary_file.write(candidate.model_dump_json(indent=2))
                temporary_file.flush()
                os.fsync(temporary_file.fileno())

            try:
                os.link(temporary_path, path)
            except FileExistsError:
                existing = self._load_path(path, revision.id)
                if existing != candidate:
                    raise PlaybookRevisionPersistenceConflictError(revision.id) from None
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def load_all(self) -> list[PlaybookRevision]:
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

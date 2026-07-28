import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import UUID

from pydantic import ValidationError

from neural_engine.core.paths import NeuralPaths
from neural_engine.domain import PlaybookRun
from neural_engine.ports.playbook_run_repository import (
    PlaybookRunIdentityMismatchError,
    PlaybookRunPersistenceConflictError,
    PlaybookRunRepository,
    PlaybookRunStoredDataError,
)


class JsonPlaybookRunRepository(PlaybookRunRepository):
    """Stores playbook runs as JSON files."""

    def __init__(self, directory: Path = NeuralPaths.PLAYBOOK_RUNS) -> None:
        self._directory = directory

    def save(self, run: PlaybookRun) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)

        path = self._directory / f"{run.id}.json"
        serialized = run.model_dump_json(indent=2)
        candidate = PlaybookRun.model_validate_json(serialized)
        temporary_path: Path | None = None

        try:
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self._directory,
                prefix=f".{run.id}.",
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
                existing = self._load_path(path, run.id)
                if existing != candidate:
                    raise PlaybookRunPersistenceConflictError(run.id) from None
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def load_all(self) -> list[PlaybookRun]:
        if not self._directory.exists():
            return []

        runs: list[PlaybookRun] = []

        for path in sorted(self._directory.glob("*.json")):
            try:
                expected_id = UUID(path.stem)
            except ValueError as error:
                raise PlaybookRunStoredDataError(path.stem) from error
            runs.append(self._load_path(path, expected_id))

        return runs

    def get_by_id(self, run_id: UUID) -> PlaybookRun | None:
        path = self._directory / f"{run_id}.json"

        if not path.exists():
            return None

        return self._load_path(path, run_id)

    @staticmethod
    def _load_path(path: Path, expected_id: UUID) -> PlaybookRun:
        try:
            run = PlaybookRun.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError) as error:
            raise PlaybookRunStoredDataError(str(expected_id)) from error

        if run.id != expected_id:
            raise PlaybookRunIdentityMismatchError(expected_id, run.id)

        return run

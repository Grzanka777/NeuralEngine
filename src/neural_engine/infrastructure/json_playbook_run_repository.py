from pathlib import Path
from uuid import UUID

from pydantic import ValidationError

from neural_engine.core.brain_trust import TargetAction
from neural_engine.core.paths import NeuralPaths
from neural_engine.domain import PlaybookRun
from neural_engine.infrastructure.durability import create_once_bytes
from neural_engine.infrastructure.repository_paths import RepositoryPath
from neural_engine.ports.brain_trust_transition import ControlledMutationTarget
from neural_engine.ports.playbook_run_repository import (
    PlaybookRunIdentityMismatchError,
    PlaybookRunPersistenceConflictError,
    PlaybookRunRepository,
    PlaybookRunStoredDataError,
)


class JsonPlaybookRunRepository(PlaybookRunRepository):
    """Stores playbook runs as JSON files."""

    def __init__(
        self,
        directory: Path | None = None,
        *,
        paths: NeuralPaths | None = None,
    ) -> None:
        self._path = RepositoryPath.build(directory, paths, lambda value: value.PLAYBOOK_RUNS)
        self._directory = self._path.directory

    def save(self, run: PlaybookRun) -> None:
        candidate, serialized = self._candidate_bytes(run)
        self._publish_candidate(self._directory / f"{run.id}.json", candidate, serialized)

    def controlled_create_target(self, run: PlaybookRun) -> ControlledMutationTarget:
        """Prepare one Run create for deferred Brain Trust publication."""

        if self._path.paths is None:
            raise ValueError("Controlled PlaybookRun targets require NeuralPaths-backed storage.")

        candidate, serialized = self._candidate_bytes(run)
        path = self._directory / f"{run.id}.json"
        relative_path = path.relative_to(self._path.paths.BRAIN).as_posix()
        return ControlledMutationTarget(
            relative_path=relative_path,
            action=TargetAction.CREATE,
            after_bytes=serialized,
            publish=lambda: self._publish_candidate(path, candidate, serialized),
        )

    def _publish_candidate(self, path: Path, candidate: PlaybookRun, serialized: bytes) -> None:
        self._path.prepare_for_write()
        try:
            create_once_bytes(path, serialized)
        except FileExistsError:
            existing = self._load_path(path, candidate.id)
            if existing != candidate:
                raise PlaybookRunPersistenceConflictError(candidate.id) from None

    @staticmethod
    def _candidate_bytes(run: PlaybookRun) -> tuple[PlaybookRun, bytes]:
        candidate = PlaybookRun.model_validate_json(run.model_dump_json(indent=2))
        return candidate, candidate.model_dump_json(indent=2).encode("utf-8")

    def load_all(self) -> list[PlaybookRun]:
        self._path.guard(operation="read")
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
        self._path.guard(operation="read")
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

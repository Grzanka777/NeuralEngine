from pathlib import Path
from uuid import UUID

from pydantic import ValidationError

from neural_engine.core.brain_trust import TargetAction
from neural_engine.core.paths import NeuralPaths
from neural_engine.domain import Knowledge
from neural_engine.infrastructure.durability import create_once_bytes
from neural_engine.infrastructure.repository_paths import RepositoryPath
from neural_engine.ports.brain_trust_transition import ControlledMutationTarget
from neural_engine.ports.knowledge_repository import (
    KnowledgeIdentityMismatchError,
    KnowledgePersistenceConflictError,
    KnowledgeRepository,
    KnowledgeStoredDataError,
)


class JsonKnowledgeRepository(KnowledgeRepository):
    """Stores knowledge as JSON files."""

    def __init__(
        self,
        directory: Path | None = None,
        *,
        paths: NeuralPaths | None = None,
    ) -> None:
        self._path = RepositoryPath.build(directory, paths, lambda value: value.KNOWLEDGE)
        self._directory = self._path.directory

    def save(self, knowledge: Knowledge) -> None:
        self._path.prepare_for_write()

        path = self._directory / f"{knowledge.id}.json"
        candidate, serialized = self._candidate_bytes(knowledge)
        self._publish_candidate(path, candidate, serialized)

    def controlled_create_target(self, knowledge: Knowledge) -> ControlledMutationTarget:
        """Prepare one Knowledge create for deferred coordinator publication."""

        if self._path.paths is None:
            raise ValueError("Controlled Knowledge targets require NeuralPaths-backed storage.")

        candidate, serialized = self._candidate_bytes(knowledge)
        path = self._directory / f"{knowledge.id}.json"
        relative_path = path.relative_to(self._path.paths.BRAIN).as_posix()
        try:
            path.relative_to(self._path.paths.BRAIN)
        except ValueError as error:
            raise ValueError("Controlled Knowledge target must be Brain-relative.") from error

        return ControlledMutationTarget(
            relative_path=relative_path,
            action=TargetAction.CREATE,
            after_bytes=serialized,
            publish=lambda: self._publish_candidate(path, candidate, serialized),
        )

    def _publish_candidate(self, path: Path, candidate: Knowledge, serialized: bytes) -> None:
        self._path.prepare_for_write()
        try:
            create_once_bytes(path, serialized)
        except FileExistsError:
            existing = self._load_path(path, candidate.id)
            if existing != candidate:
                raise KnowledgePersistenceConflictError(candidate.id) from None

    @staticmethod
    def _candidate_bytes(knowledge: Knowledge) -> tuple[Knowledge, bytes]:
        candidate = Knowledge.model_validate_json(knowledge.model_dump_json(indent=2))
        return candidate, candidate.model_dump_json(indent=2).encode("utf-8")

    def load_all(self) -> list[Knowledge]:
        self._path.guard(operation="read")
        if not self._directory.exists():
            return []

        knowledge_items: list[Knowledge] = []

        for path in sorted(self._directory.glob("*.json")):
            try:
                expected_id = UUID(path.stem)
            except ValueError as error:
                raise KnowledgeStoredDataError(path.stem) from error
            knowledge_items.append(self._load_path(path, expected_id))

        return knowledge_items

    def get_by_id(self, knowledge_id: UUID) -> Knowledge | None:
        self._path.guard(operation="read")
        path = self._directory / f"{knowledge_id}.json"

        if not path.exists():
            return None

        return self._load_path(path, knowledge_id)

    @staticmethod
    def _load_path(path: Path, expected_id: UUID) -> Knowledge:
        try:
            knowledge = Knowledge.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError) as error:
            raise KnowledgeStoredDataError(str(expected_id)) from error

        if knowledge.id != expected_id:
            raise KnowledgeIdentityMismatchError(expected_id, knowledge.id)

        return knowledge

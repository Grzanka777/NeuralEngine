import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import UUID

from pydantic import ValidationError

from neural_engine.core.paths import NeuralPaths
from neural_engine.domain import Knowledge
from neural_engine.ports.knowledge_repository import (
    KnowledgeIdentityMismatchError,
    KnowledgePersistenceConflictError,
    KnowledgeRepository,
    KnowledgeStoredDataError,
)


class JsonKnowledgeRepository(KnowledgeRepository):
    """Stores knowledge as JSON files."""

    def __init__(self, directory: Path = NeuralPaths.KNOWLEDGE) -> None:
        self._directory = directory

    def save(self, knowledge: Knowledge) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)

        path = self._directory / f"{knowledge.id}.json"
        serialized = knowledge.model_dump_json(indent=2)
        candidate = Knowledge.model_validate_json(serialized)
        temporary_path: Path | None = None

        try:
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self._directory,
                prefix=f".{knowledge.id}.",
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
                existing = self._load_path(path, knowledge.id)
                if existing != candidate:
                    raise KnowledgePersistenceConflictError(knowledge.id) from None
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def load_all(self) -> list[Knowledge]:
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

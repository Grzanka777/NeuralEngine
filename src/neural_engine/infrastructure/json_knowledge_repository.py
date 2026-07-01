from pathlib import Path
from uuid import UUID

from neural_engine.core.paths import NeuralPaths
from neural_engine.domain import Knowledge
from neural_engine.ports.knowledge_repository import KnowledgeRepository


class JsonKnowledgeRepository(KnowledgeRepository):
    """Stores knowledge as JSON files."""

    def __init__(self, directory: Path = NeuralPaths.KNOWLEDGE) -> None:
        self._directory = directory

    def save(self, knowledge: Knowledge) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)

        path = self._directory / f"{knowledge.id}.json"

        path.write_text(
            knowledge.model_dump_json(indent=2),
            encoding="utf-8",
        )

    def load_all(self) -> list[Knowledge]:
        if not self._directory.exists():
            return []

        knowledge_items: list[Knowledge] = []

        for path in sorted(self._directory.glob("*.json")):
            knowledge_items.append(Knowledge.model_validate_json(path.read_text(encoding="utf-8")))

        return knowledge_items

    def get_by_id(self, knowledge_id: UUID) -> Knowledge | None:
        path = self._directory / f"{knowledge_id}.json"

        if not path.exists():
            return None

        return Knowledge.model_validate_json(path.read_text(encoding="utf-8"))

from pathlib import Path
from uuid import UUID

from neural_engine.core.paths import NeuralPaths
from neural_engine.domain import Decision
from neural_engine.ports.decision_repository import DecisionRepository


class JsonDecisionRepository(DecisionRepository):
    """Stores decisions as JSON files."""

    def __init__(self, directory: Path = NeuralPaths.DECISIONS) -> None:
        self._directory = directory

    def save(self, decision: Decision) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)
        path = self._directory / f"{decision.id}.json"
        path.write_text(decision.model_dump_json(indent=2), encoding="utf-8")

    def load_all(self) -> list[Decision]:
        if not self._directory.exists():
            return []

        return [
            Decision.model_validate_json(path.read_text(encoding="utf-8"))
            for path in sorted(self._directory.glob("*.json"))
        ]

    def get_by_id(self, decision_id: UUID) -> Decision | None:
        path = self._directory / f"{decision_id}.json"
        if not path.exists():
            return None

        return Decision.model_validate_json(path.read_text(encoding="utf-8"))

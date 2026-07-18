import json
from pathlib import Path
from uuid import UUID

from neural_engine.core.paths import NeuralPaths
from neural_engine.domain import DecisionOutcome
from neural_engine.ports.decision_outcome_repository import DecisionOutcomeRepository


class JsonDecisionOutcomeRepository(DecisionOutcomeRepository):
    """Stores Decision outcome records as deterministic JSON files."""

    def __init__(self, directory: Path = NeuralPaths.DECISION_OUTCOMES) -> None:
        self._directory = directory

    def save(self, outcome: DecisionOutcome) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)
        path = self._directory / f"{outcome.id}.json"
        payload = outcome.model_dump(mode="json")
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def load_all(self) -> list[DecisionOutcome]:
        if not self._directory.exists():
            return []
        return [
            DecisionOutcome.model_validate_json(path.read_text(encoding="utf-8"))
            for path in sorted(self._directory.glob("*.json"))
        ]

    def get_by_id(self, outcome_id: UUID) -> DecisionOutcome | None:
        path = self._directory / f"{outcome_id}.json"
        if not path.exists():
            return None
        return DecisionOutcome.model_validate_json(path.read_text(encoding="utf-8"))

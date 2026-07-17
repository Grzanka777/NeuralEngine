from pathlib import Path
from uuid import UUID

from neural_engine.core.paths import NeuralPaths
from neural_engine.domain import DecisionAction
from neural_engine.ports.decision_action_repository import DecisionActionRepository


class JsonDecisionActionRepository(DecisionActionRepository):
    """Stores Decision action records as JSON files."""

    def __init__(self, directory: Path = NeuralPaths.DECISION_ACTIONS) -> None:
        self._directory = directory

    def save(self, action: DecisionAction) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)
        path = self._directory / f"{action.id}.json"
        path.write_text(action.model_dump_json(indent=2), encoding="utf-8")

    def load_all(self) -> list[DecisionAction]:
        if not self._directory.exists():
            return []

        return [
            DecisionAction.model_validate_json(path.read_text(encoding="utf-8"))
            for path in sorted(self._directory.glob("*.json"))
        ]

    def get_by_id(self, action_id: UUID) -> DecisionAction | None:
        path = self._directory / f"{action_id}.json"
        if not path.exists():
            return None

        return DecisionAction.model_validate_json(path.read_text(encoding="utf-8"))

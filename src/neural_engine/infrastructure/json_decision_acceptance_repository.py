from pathlib import Path
from uuid import UUID

from neural_engine.core.paths import NeuralPaths
from neural_engine.domain import DecisionAcceptance
from neural_engine.ports.decision_acceptance_repository import (
    DecisionAcceptanceRepository,
)


class JsonDecisionAcceptanceRepository(DecisionAcceptanceRepository):
    """Stores Decision acceptance records as JSON files."""

    def __init__(self, directory: Path = NeuralPaths.DECISION_ACCEPTANCES) -> None:
        self._directory = directory

    def save(self, acceptance: DecisionAcceptance) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)
        path = self._directory / f"{acceptance.id}.json"
        path.write_text(acceptance.model_dump_json(indent=2), encoding="utf-8")

    def load_all(self) -> list[DecisionAcceptance]:
        if not self._directory.exists():
            return []

        return [
            DecisionAcceptance.model_validate_json(path.read_text(encoding="utf-8"))
            for path in sorted(self._directory.glob("*.json"))
        ]

    def get_by_id(self, acceptance_id: UUID) -> DecisionAcceptance | None:
        path = self._directory / f"{acceptance_id}.json"
        if not path.exists():
            return None

        return DecisionAcceptance.model_validate_json(path.read_text(encoding="utf-8"))

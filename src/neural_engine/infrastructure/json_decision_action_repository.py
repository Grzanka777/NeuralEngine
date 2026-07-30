from pathlib import Path
from uuid import UUID

from neural_engine.core.paths import NeuralPaths
from neural_engine.domain import DecisionAction
from neural_engine.infrastructure.repository_paths import RepositoryPath
from neural_engine.ports.decision_action_repository import DecisionActionRepository


class JsonDecisionActionRepository(DecisionActionRepository):
    """Stores Decision action records as JSON files."""

    def __init__(
        self,
        directory: Path | None = None,
        *,
        paths: NeuralPaths | None = None,
    ) -> None:
        self._path = RepositoryPath.build(
            directory,
            paths,
            lambda value: value.DECISION_ACTIONS,
        )
        self._directory = self._path.directory

    def save(self, action: DecisionAction) -> None:
        self._path.prepare_for_write()
        path = self._directory / f"{action.id}.json"
        path.write_text(action.model_dump_json(indent=2), encoding="utf-8")

    def load_all(self) -> list[DecisionAction]:
        self._path.guard(operation="read")
        if not self._directory.exists():
            return []

        return [
            DecisionAction.model_validate_json(path.read_text(encoding="utf-8"))
            for path in sorted(self._directory.glob("*.json"))
        ]

    def get_by_id(self, action_id: UUID) -> DecisionAction | None:
        self._path.guard(operation="read")
        path = self._directory / f"{action_id}.json"
        if not path.exists():
            return None

        return DecisionAction.model_validate_json(path.read_text(encoding="utf-8"))

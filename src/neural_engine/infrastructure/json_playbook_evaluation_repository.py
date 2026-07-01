from pathlib import Path
from uuid import UUID

from neural_engine.core.paths import NeuralPaths
from neural_engine.domain import PlaybookEvaluation
from neural_engine.ports.playbook_evaluation_repository import (
    PlaybookEvaluationRepository,
)


class JsonPlaybookEvaluationRepository(PlaybookEvaluationRepository):
    """Stores playbook evaluations as JSON files."""

    def __init__(self, directory: Path = NeuralPaths.PLAYBOOK_EVALUATIONS) -> None:
        self._directory = directory

    def save(self, evaluation: PlaybookEvaluation) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)

        path = self._directory / f"{evaluation.id}.json"

        path.write_text(
            evaluation.model_dump_json(indent=2),
            encoding="utf-8",
        )

    def load_all(self) -> list[PlaybookEvaluation]:
        if not self._directory.exists():
            return []

        evaluations: list[PlaybookEvaluation] = []

        for path in sorted(self._directory.glob("*.json")):
            evaluations.append(
                PlaybookEvaluation.model_validate_json(path.read_text(encoding="utf-8"))
            )

        return evaluations

    def get_by_id(self, evaluation_id: UUID) -> PlaybookEvaluation | None:
        path = self._directory / f"{evaluation_id}.json"

        if not path.exists():
            return None

        return PlaybookEvaluation.model_validate_json(path.read_text(encoding="utf-8"))

import json
from pathlib import Path
from uuid import UUID

from neural_engine.core.paths import NeuralPaths
from neural_engine.domain import DecisionReview
from neural_engine.infrastructure.repository_paths import RepositoryPath
from neural_engine.ports.decision_review_repository import DecisionReviewRepository


class JsonDecisionReviewRepository(DecisionReviewRepository):
    """Stores Decision reviews as deterministic JSON files."""

    def __init__(
        self,
        directory: Path | None = None,
        *,
        paths: NeuralPaths | None = None,
    ) -> None:
        self._path = RepositoryPath.build(
            directory,
            paths,
            lambda value: value.DECISION_REVIEWS,
        )
        self._directory = self._path.directory

    def save(self, review: DecisionReview) -> None:
        self._path.prepare_for_write()
        path = self._directory / f"{review.id}.json"
        payload = review.model_dump(mode="json")
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def load_all(self) -> list[DecisionReview]:
        self._path.guard(operation="read")
        if not self._directory.exists():
            return []
        return [
            DecisionReview.model_validate_json(path.read_text(encoding="utf-8"))
            for path in sorted(self._directory.glob("*.json"))
        ]

    def get_by_id(self, review_id: UUID) -> DecisionReview | None:
        self._path.guard(operation="read")
        path = self._directory / f"{review_id}.json"
        if not path.exists():
            return None
        return DecisionReview.model_validate_json(path.read_text(encoding="utf-8"))

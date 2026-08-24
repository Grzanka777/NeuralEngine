import json
from pathlib import Path
from uuid import UUID

from neural_engine.core.paths import NeuralPaths
from neural_engine.domain import DecisionOutcome
from neural_engine.infrastructure.controlled_create import (
    build_controlled_create_target,
    publish_create_once,
)
from neural_engine.infrastructure.repository_paths import RepositoryPath
from neural_engine.ports.brain_trust_transition import ControlledMutationTarget
from neural_engine.ports.decision_outcome_repository import DecisionOutcomeRepository


class JsonDecisionOutcomeRepository(DecisionOutcomeRepository):
    """Stores Decision outcome records as deterministic JSON files."""

    def __init__(
        self,
        directory: Path | None = None,
        *,
        paths: NeuralPaths | None = None,
    ) -> None:
        self._path = RepositoryPath.build(
            directory,
            paths,
            lambda value: value.DECISION_OUTCOMES,
        )
        self._directory = self._path.directory

    def save(self, outcome: DecisionOutcome) -> None:
        self._path.prepare_for_write()
        path = self._directory / f"{outcome.id}.json"
        payload = outcome.model_dump(mode="json")
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def controlled_create_target(self, outcome: DecisionOutcome) -> ControlledMutationTarget:
        candidate, serialized = self._candidate_bytes(outcome)
        path = self._directory / f"{candidate.id}.json"
        return build_controlled_create_target(
            self._path.paths,
            path,
            serialized,
            lambda: publish_create_once(path, serialized, self._path.prepare_for_write),
        )

    @staticmethod
    def _candidate_bytes(outcome: DecisionOutcome) -> tuple[DecisionOutcome, bytes]:
        candidate = DecisionOutcome.model_validate_json(
            json.dumps(outcome.model_dump(mode="json"), sort_keys=True)
        )
        payload = candidate.model_dump(mode="json")
        return candidate, json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")

    def load_all(self) -> list[DecisionOutcome]:
        self._path.guard(operation="read")
        if not self._directory.exists():
            return []
        return [
            DecisionOutcome.model_validate_json(path.read_text(encoding="utf-8"))
            for path in sorted(self._directory.glob("*.json"))
        ]

    def get_by_id(self, outcome_id: UUID) -> DecisionOutcome | None:
        self._path.guard(operation="read")
        path = self._directory / f"{outcome_id}.json"
        if not path.exists():
            return None
        return DecisionOutcome.model_validate_json(path.read_text(encoding="utf-8"))

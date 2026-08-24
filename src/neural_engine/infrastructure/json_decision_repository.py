from pathlib import Path
from uuid import UUID

from neural_engine.core.paths import NeuralPaths
from neural_engine.domain import Decision
from neural_engine.infrastructure.controlled_create import (
    build_controlled_create_target,
    publish_create_once,
)
from neural_engine.infrastructure.repository_paths import RepositoryPath
from neural_engine.ports.brain_trust_transition import ControlledMutationTarget
from neural_engine.ports.decision_repository import DecisionRepository


class JsonDecisionRepository(DecisionRepository):
    """Stores decisions as JSON files."""

    def __init__(
        self,
        directory: Path | None = None,
        *,
        paths: NeuralPaths | None = None,
    ) -> None:
        self._path = RepositoryPath.build(directory, paths, lambda value: value.DECISIONS)
        self._directory = self._path.directory

    def save(self, decision: Decision) -> None:
        self._path.prepare_for_write()
        path = self._directory / f"{decision.id}.json"
        path.write_text(decision.model_dump_json(indent=2), encoding="utf-8")

    def controlled_create_target(self, decision: Decision) -> ControlledMutationTarget:
        candidate, serialized = self._candidate_bytes(decision)
        path = self._directory / f"{candidate.id}.json"
        return build_controlled_create_target(
            self._path.paths,
            path,
            serialized,
            lambda: publish_create_once(path, serialized, self._path.prepare_for_write),
        )

    @staticmethod
    def _candidate_bytes(decision: Decision) -> tuple[Decision, bytes]:
        candidate = Decision.model_validate_json(decision.model_dump_json(indent=2))
        return candidate, candidate.model_dump_json(indent=2).encode("utf-8")

    def load_all(self) -> list[Decision]:
        self._path.guard(operation="read")
        if not self._directory.exists():
            return []

        return [
            Decision.model_validate_json(path.read_text(encoding="utf-8"))
            for path in sorted(self._directory.glob("*.json"))
        ]

    def get_by_id(self, decision_id: UUID) -> Decision | None:
        self._path.guard(operation="read")
        path = self._directory / f"{decision_id}.json"
        if not path.exists():
            return None

        return Decision.model_validate_json(path.read_text(encoding="utf-8"))

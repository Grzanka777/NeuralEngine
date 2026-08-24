from pathlib import Path
from uuid import UUID

from neural_engine.core.paths import NeuralPaths
from neural_engine.domain import DecisionAcceptance
from neural_engine.infrastructure.controlled_create import (
    build_controlled_create_target,
    publish_create_once,
)
from neural_engine.infrastructure.repository_paths import RepositoryPath
from neural_engine.ports.brain_trust_transition import ControlledMutationTarget
from neural_engine.ports.decision_acceptance_repository import (
    DecisionAcceptanceRepository,
)


class JsonDecisionAcceptanceRepository(DecisionAcceptanceRepository):
    """Stores Decision acceptance records as JSON files."""

    def __init__(
        self,
        directory: Path | None = None,
        *,
        paths: NeuralPaths | None = None,
    ) -> None:
        self._path = RepositoryPath.build(
            directory,
            paths,
            lambda value: value.DECISION_ACCEPTANCES,
        )
        self._directory = self._path.directory

    def save(self, acceptance: DecisionAcceptance) -> None:
        self._path.prepare_for_write()
        path = self._directory / f"{acceptance.id}.json"
        path.write_text(acceptance.model_dump_json(indent=2), encoding="utf-8")

    def controlled_create_target(self, acceptance: DecisionAcceptance) -> ControlledMutationTarget:
        candidate, serialized = self._candidate_bytes(acceptance)
        path = self._directory / f"{candidate.id}.json"
        return build_controlled_create_target(
            self._path.paths,
            path,
            serialized,
            lambda: publish_create_once(path, serialized, self._path.prepare_for_write),
        )

    @staticmethod
    def _candidate_bytes(acceptance: DecisionAcceptance) -> tuple[DecisionAcceptance, bytes]:
        candidate = DecisionAcceptance.model_validate_json(acceptance.model_dump_json(indent=2))
        return candidate, candidate.model_dump_json(indent=2).encode("utf-8")

    def load_all(self) -> list[DecisionAcceptance]:
        self._path.guard(operation="read")
        if not self._directory.exists():
            return []

        return [
            DecisionAcceptance.model_validate_json(path.read_text(encoding="utf-8"))
            for path in sorted(self._directory.glob("*.json"))
        ]

    def get_by_id(self, acceptance_id: UUID) -> DecisionAcceptance | None:
        self._path.guard(operation="read")
        path = self._directory / f"{acceptance_id}.json"
        if not path.exists():
            return None

        return DecisionAcceptance.model_validate_json(path.read_text(encoding="utf-8"))

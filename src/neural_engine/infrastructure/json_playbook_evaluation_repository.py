from pathlib import Path
from uuid import UUID

from neural_engine.core.paths import NeuralPaths
from neural_engine.domain import PlaybookEvaluation
from neural_engine.infrastructure.controlled_create import (
    build_controlled_create_target,
    publish_create_once,
)
from neural_engine.infrastructure.repository_paths import RepositoryPath
from neural_engine.ports.brain_trust_transition import ControlledMutationTarget
from neural_engine.ports.playbook_evaluation_repository import (
    PlaybookEvaluationRepository,
)


class JsonPlaybookEvaluationRepository(PlaybookEvaluationRepository):
    """Stores playbook evaluations as JSON files."""

    def __init__(
        self,
        directory: Path | None = None,
        *,
        paths: NeuralPaths | None = None,
    ) -> None:
        self._path = RepositoryPath.build(
            directory,
            paths,
            lambda value: value.PLAYBOOK_EVALUATIONS,
        )
        self._directory = self._path.directory

    def save(self, evaluation: PlaybookEvaluation) -> None:
        self._path.prepare_for_write()

        path = self._directory / f"{evaluation.id}.json"

        path.write_text(
            evaluation.model_dump_json(indent=2),
            encoding="utf-8",
        )

    def controlled_create_target(self, evaluation: PlaybookEvaluation) -> ControlledMutationTarget:
        candidate, serialized = self._candidate_bytes(evaluation)
        path = self._directory / f"{candidate.id}.json"
        return build_controlled_create_target(
            self._path.paths,
            path,
            serialized,
            lambda: publish_create_once(path, serialized, self._path.prepare_for_write),
        )

    @staticmethod
    def _candidate_bytes(evaluation: PlaybookEvaluation) -> tuple[PlaybookEvaluation, bytes]:
        candidate = PlaybookEvaluation.model_validate_json(evaluation.model_dump_json(indent=2))
        return candidate, candidate.model_dump_json(indent=2).encode("utf-8")

    def load_all(self) -> list[PlaybookEvaluation]:
        self._path.guard(operation="read")
        if not self._directory.exists():
            return []

        evaluations: list[PlaybookEvaluation] = []

        for path in sorted(self._directory.glob("*.json")):
            evaluations.append(
                PlaybookEvaluation.model_validate_json(path.read_text(encoding="utf-8"))
            )

        return evaluations

    def get_by_id(self, evaluation_id: UUID) -> PlaybookEvaluation | None:
        self._path.guard(operation="read")
        path = self._directory / f"{evaluation_id}.json"

        if not path.exists():
            return None

        return PlaybookEvaluation.model_validate_json(path.read_text(encoding="utf-8"))

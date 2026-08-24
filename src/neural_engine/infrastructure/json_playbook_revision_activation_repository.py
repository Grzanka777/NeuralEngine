from pathlib import Path
from uuid import UUID

from neural_engine.core.paths import NeuralPaths
from neural_engine.domain import PlaybookRevisionActivation
from neural_engine.infrastructure.controlled_create import (
    build_controlled_create_target,
    publish_create_once,
)
from neural_engine.infrastructure.repository_paths import RepositoryPath
from neural_engine.ports.brain_trust_transition import ControlledMutationTarget
from neural_engine.ports.playbook_revision_activation_repository import (
    PlaybookRevisionActivationRepository,
)


class JsonPlaybookRevisionActivationRepository(PlaybookRevisionActivationRepository):
    """Stores playbook revision activations as JSON files."""

    def __init__(
        self,
        directory: Path | None = None,
        *,
        paths: NeuralPaths | None = None,
    ) -> None:
        self._path = RepositoryPath.build(
            directory,
            paths,
            lambda value: value.PLAYBOOK_REVISION_ACTIVATIONS,
        )
        self._directory = self._path.directory

    def save(self, activation: PlaybookRevisionActivation) -> None:
        self._path.prepare_for_write()

        path = self._directory / f"{activation.id}.json"

        path.write_text(
            activation.model_dump_json(indent=2),
            encoding="utf-8",
        )

    def controlled_create_target(
        self, activation: PlaybookRevisionActivation
    ) -> ControlledMutationTarget:
        candidate, serialized = self._candidate_bytes(activation)
        path = self._directory / f"{candidate.id}.json"
        return build_controlled_create_target(
            self._path.paths,
            path,
            serialized,
            lambda: publish_create_once(path, serialized, self._path.prepare_for_write),
        )

    @staticmethod
    def _candidate_bytes(
        activation: PlaybookRevisionActivation,
    ) -> tuple[PlaybookRevisionActivation, bytes]:
        candidate = PlaybookRevisionActivation.model_validate_json(
            activation.model_dump_json(indent=2)
        )
        return candidate, candidate.model_dump_json(indent=2).encode("utf-8")

    def load_all(self) -> list[PlaybookRevisionActivation]:
        self._path.guard(operation="read")
        if not self._directory.exists():
            return []

        activations: list[PlaybookRevisionActivation] = []

        for path in sorted(self._directory.glob("*.json")):
            activations.append(
                PlaybookRevisionActivation.model_validate_json(path.read_text(encoding="utf-8"))
            )

        return activations

    def get_by_id(self, activation_id: UUID) -> PlaybookRevisionActivation | None:
        self._path.guard(operation="read")
        path = self._directory / f"{activation_id}.json"

        if not path.exists():
            return None

        return PlaybookRevisionActivation.model_validate_json(path.read_text(encoding="utf-8"))

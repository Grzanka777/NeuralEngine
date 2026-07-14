from pathlib import Path
from uuid import UUID

from neural_engine.core.paths import NeuralPaths
from neural_engine.domain import PlaybookRevisionActivation
from neural_engine.ports.playbook_revision_activation_repository import (
    PlaybookRevisionActivationRepository,
)


class JsonPlaybookRevisionActivationRepository(PlaybookRevisionActivationRepository):
    """Stores playbook revision activations as JSON files."""

    def __init__(self, directory: Path = NeuralPaths.PLAYBOOK_REVISION_ACTIVATIONS) -> None:
        self._directory = directory

    def save(self, activation: PlaybookRevisionActivation) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)

        path = self._directory / f"{activation.id}.json"

        path.write_text(
            activation.model_dump_json(indent=2),
            encoding="utf-8",
        )

    def load_all(self) -> list[PlaybookRevisionActivation]:
        if not self._directory.exists():
            return []

        activations: list[PlaybookRevisionActivation] = []

        for path in sorted(self._directory.glob("*.json")):
            activations.append(
                PlaybookRevisionActivation.model_validate_json(path.read_text(encoding="utf-8"))
            )

        return activations

    def get_by_id(self, activation_id: UUID) -> PlaybookRevisionActivation | None:
        path = self._directory / f"{activation_id}.json"

        if not path.exists():
            return None

        return PlaybookRevisionActivation.model_validate_json(path.read_text(encoding="utf-8"))

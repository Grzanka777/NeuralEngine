from pathlib import Path
from uuid import UUID

from neural_engine.core.paths import NeuralPaths
from neural_engine.domain import PlaybookRevision
from neural_engine.ports.playbook_revision_repository import (
    PlaybookRevisionRepository,
)


class JsonPlaybookRevisionRepository(PlaybookRevisionRepository):
    """Stores playbook revisions as JSON files."""

    def __init__(self, directory: Path = NeuralPaths.PLAYBOOK_REVISIONS) -> None:
        self._directory = directory

    def save(self, revision: PlaybookRevision) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)

        path = self._directory / f"{revision.id}.json"

        path.write_text(
            revision.model_dump_json(indent=2),
            encoding="utf-8",
        )

    def load_all(self) -> list[PlaybookRevision]:
        if not self._directory.exists():
            return []

        revisions: list[PlaybookRevision] = []

        for path in sorted(self._directory.glob("*.json")):
            revisions.append(PlaybookRevision.model_validate_json(path.read_text(encoding="utf-8")))

        return revisions

    def get_by_id(self, revision_id: UUID) -> PlaybookRevision | None:
        path = self._directory / f"{revision_id}.json"

        if not path.exists():
            return None

        return PlaybookRevision.model_validate_json(path.read_text(encoding="utf-8"))

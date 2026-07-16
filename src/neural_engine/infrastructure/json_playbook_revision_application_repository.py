from pathlib import Path
from uuid import UUID

from neural_engine.core.paths import NeuralPaths
from neural_engine.domain import PlaybookRevisionApplication
from neural_engine.ports.playbook_revision_application_repository import (
    PlaybookRevisionApplicationRepository,
)


class JsonPlaybookRevisionApplicationRepository(PlaybookRevisionApplicationRepository):
    """Stores playbook revision application audit records as JSON files."""

    def __init__(self, directory: Path = NeuralPaths.PLAYBOOK_REVISION_APPLICATIONS) -> None:
        self._directory = directory

    def save(self, application: PlaybookRevisionApplication) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)

        path = self._directory / f"{application.id}.json"

        path.write_text(
            application.model_dump_json(indent=2),
            encoding="utf-8",
        )

    def load_all(self) -> list[PlaybookRevisionApplication]:
        if not self._directory.exists():
            return []

        applications: list[PlaybookRevisionApplication] = []

        for path in sorted(self._directory.glob("*.json")):
            applications.append(
                PlaybookRevisionApplication.model_validate_json(path.read_text(encoding="utf-8"))
            )

        return applications

    def get_by_id(self, application_id: UUID) -> PlaybookRevisionApplication | None:
        path = self._directory / f"{application_id}.json"

        if not path.exists():
            return None

        return PlaybookRevisionApplication.model_validate_json(path.read_text(encoding="utf-8"))

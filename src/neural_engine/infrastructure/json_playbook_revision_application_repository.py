from pathlib import Path
from uuid import UUID

from neural_engine.core.paths import NeuralPaths
from neural_engine.domain import PlaybookRevisionApplication
from neural_engine.infrastructure.controlled_create import (
    build_controlled_create_target,
    publish_create_once,
)
from neural_engine.infrastructure.repository_paths import RepositoryPath
from neural_engine.ports.brain_trust_transition import ControlledMutationTarget
from neural_engine.ports.playbook_revision_application_repository import (
    PlaybookRevisionApplicationRepository,
)


class JsonPlaybookRevisionApplicationRepository(PlaybookRevisionApplicationRepository):
    """Stores playbook revision application audit records as JSON files."""

    def __init__(
        self,
        directory: Path | None = None,
        *,
        paths: NeuralPaths | None = None,
    ) -> None:
        self._path = RepositoryPath.build(
            directory,
            paths,
            lambda value: value.PLAYBOOK_REVISION_APPLICATIONS,
        )
        self._directory = self._path.directory

    def save(self, application: PlaybookRevisionApplication) -> None:
        self._path.prepare_for_write()

        path = self._directory / f"{application.id}.json"

        path.write_text(
            application.model_dump_json(indent=2),
            encoding="utf-8",
        )

    def controlled_create_target(
        self, application: PlaybookRevisionApplication
    ) -> ControlledMutationTarget:
        candidate, serialized = self._candidate_bytes(application)
        path = self._directory / f"{candidate.id}.json"
        return build_controlled_create_target(
            self._path.paths,
            path,
            serialized,
            lambda: publish_create_once(path, serialized, self._path.prepare_for_write),
        )

    @staticmethod
    def _candidate_bytes(
        application: PlaybookRevisionApplication,
    ) -> tuple[PlaybookRevisionApplication, bytes]:
        candidate = PlaybookRevisionApplication.model_validate_json(
            application.model_dump_json(indent=2)
        )
        return candidate, candidate.model_dump_json(indent=2).encode("utf-8")

    def load_all(self) -> list[PlaybookRevisionApplication]:
        self._path.guard(operation="read")
        if not self._directory.exists():
            return []

        applications: list[PlaybookRevisionApplication] = []

        for path in sorted(self._directory.glob("*.json")):
            applications.append(
                PlaybookRevisionApplication.model_validate_json(path.read_text(encoding="utf-8"))
            )

        return applications

    def get_by_id(self, application_id: UUID) -> PlaybookRevisionApplication | None:
        self._path.guard(operation="read")
        path = self._directory / f"{application_id}.json"

        if not path.exists():
            return None

        return PlaybookRevisionApplication.model_validate_json(path.read_text(encoding="utf-8"))

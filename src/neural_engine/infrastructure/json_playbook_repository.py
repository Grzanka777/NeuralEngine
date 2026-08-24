from pathlib import Path
from uuid import UUID

from neural_engine.core.paths import NeuralPaths
from neural_engine.domain import Playbook
from neural_engine.infrastructure.controlled_create import (
    build_controlled_create_target,
    publish_create_once,
)
from neural_engine.infrastructure.repository_paths import RepositoryPath
from neural_engine.ports.brain_trust_transition import ControlledMutationTarget
from neural_engine.ports.playbook_repository import PlaybookRepository


class JsonPlaybookRepository(PlaybookRepository):
    """Stores playbooks as JSON files."""

    def __init__(
        self,
        directory: Path | None = None,
        *,
        paths: NeuralPaths | None = None,
    ) -> None:
        self._path = RepositoryPath.build(directory, paths, lambda value: value.PLAYBOOKS)
        self._directory = self._path.directory

    def save(self, playbook: Playbook) -> None:
        self._path.prepare_for_write()

        path = self._directory / f"{playbook.id}.json"

        path.write_text(
            playbook.model_dump_json(indent=2),
            encoding="utf-8",
        )

    def controlled_create_target(self, playbook: Playbook) -> ControlledMutationTarget:
        candidate, serialized = self._candidate_bytes(playbook)
        path = self._directory / f"{candidate.id}.json"
        return build_controlled_create_target(
            self._path.paths,
            path,
            serialized,
            lambda: publish_create_once(path, serialized, self._path.prepare_for_write),
        )

    @staticmethod
    def _candidate_bytes(playbook: Playbook) -> tuple[Playbook, bytes]:
        candidate = Playbook.model_validate_json(playbook.model_dump_json(indent=2))
        return candidate, candidate.model_dump_json(indent=2).encode("utf-8")

    def load_all(self) -> list[Playbook]:
        self._path.guard(operation="read")
        if not self._directory.exists():
            return []

        playbooks: list[Playbook] = []

        for path in sorted(self._directory.glob("*.json")):
            playbooks.append(Playbook.model_validate_json(path.read_text(encoding="utf-8")))

        return playbooks

    def get_by_id(self, playbook_id: UUID) -> Playbook | None:
        self._path.guard(operation="read")
        path = self._directory / f"{playbook_id}.json"

        if not path.exists():
            return None

        return Playbook.model_validate_json(path.read_text(encoding="utf-8"))

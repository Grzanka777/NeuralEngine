from pathlib import Path
from uuid import UUID

from neural_engine.core.paths import NeuralPaths
from neural_engine.domain import Playbook
from neural_engine.ports.playbook_repository import PlaybookRepository


class JsonPlaybookRepository(PlaybookRepository):
    """Stores playbooks as JSON files."""

    def __init__(self, directory: Path = NeuralPaths.PLAYBOOKS) -> None:
        self._directory = directory

    def save(self, playbook: Playbook) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)

        path = self._directory / f"{playbook.id}.json"

        path.write_text(
            playbook.model_dump_json(indent=2),
            encoding="utf-8",
        )

    def load_all(self) -> list[Playbook]:
        if not self._directory.exists():
            return []

        playbooks: list[Playbook] = []

        for path in sorted(self._directory.glob("*.json")):
            playbooks.append(Playbook.model_validate_json(path.read_text(encoding="utf-8")))

        return playbooks

    def get_by_id(self, playbook_id: UUID) -> Playbook | None:
        path = self._directory / f"{playbook_id}.json"

        if not path.exists():
            return None

        return Playbook.model_validate_json(path.read_text(encoding="utf-8"))

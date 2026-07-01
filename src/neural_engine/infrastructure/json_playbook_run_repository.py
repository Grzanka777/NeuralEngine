from pathlib import Path
from uuid import UUID

from neural_engine.core.paths import NeuralPaths
from neural_engine.domain import PlaybookRun
from neural_engine.ports.playbook_run_repository import PlaybookRunRepository


class JsonPlaybookRunRepository(PlaybookRunRepository):
    """Stores playbook runs as JSON files."""

    def __init__(self, directory: Path = NeuralPaths.PLAYBOOK_RUNS) -> None:
        self._directory = directory

    def save(self, run: PlaybookRun) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)

        path = self._directory / f"{run.id}.json"

        path.write_text(
            run.model_dump_json(indent=2),
            encoding="utf-8",
        )

    def load_all(self) -> list[PlaybookRun]:
        if not self._directory.exists():
            return []

        runs: list[PlaybookRun] = []

        for path in sorted(self._directory.glob("*.json")):
            runs.append(PlaybookRun.model_validate_json(path.read_text(encoding="utf-8")))

        return runs

    def get_by_id(self, run_id: UUID) -> PlaybookRun | None:
        path = self._directory / f"{run_id}.json"

        if not path.exists():
            return None

        return PlaybookRun.model_validate_json(path.read_text(encoding="utf-8"))

from pathlib import Path
from uuid import UUID

from neural_engine.core.paths import NeuralPaths
from neural_engine.domain import Observation
from neural_engine.infrastructure.repository_paths import RepositoryPath
from neural_engine.ports.observation_repository import ObservationRepository


class JsonObservationRepository(ObservationRepository):
    """Stores observations as JSON files."""

    def __init__(
        self,
        directory: Path | None = None,
        *,
        paths: NeuralPaths | None = None,
    ) -> None:
        self._path = RepositoryPath.build(directory, paths, lambda value: value.OBSERVATIONS)
        self._directory = self._path.directory

    def save(self, observation: Observation) -> None:
        self._path.prepare_for_write()

        path = self._directory / f"{observation.id}.json"

        path.write_text(
            observation.model_dump_json(indent=2),
            encoding="utf-8",
        )

    def load_all(self) -> list[Observation]:
        self._path.guard(operation="read")
        if not self._directory.exists():
            return []

        observations: list[Observation] = []

        for path in sorted(self._directory.glob("*.json")):
            observations.append(Observation.model_validate_json(path.read_text(encoding="utf-8")))

        return observations

    def get_by_id(self, observation_id: UUID) -> Observation | None:
        self._path.guard(operation="read")
        path = self._directory / f"{observation_id}.json"

        if not path.exists():
            return None

        return Observation.model_validate_json(path.read_text(encoding="utf-8"))

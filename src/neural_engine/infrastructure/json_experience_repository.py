from pathlib import Path
from uuid import UUID

from neural_engine.core.paths import NeuralPaths
from neural_engine.domain import Experience
from neural_engine.ports.experience_repository import ExperienceRepository


class JsonExperienceRepository(ExperienceRepository):
    """Stores experiences as JSON files."""

    def __init__(self, directory: Path = NeuralPaths.EXPERIENCES) -> None:
        self._directory = directory

    def save(self, experience: Experience) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)

        path = self._directory / f"{experience.id}.json"

        path.write_text(
            experience.model_dump_json(indent=2),
            encoding="utf-8",
        )

    def load_all(self) -> list[Experience]:
        if not self._directory.exists():
            return []

        experiences: list[Experience] = []

        for path in sorted(self._directory.glob("*.json")):
            experiences.append(Experience.model_validate_json(path.read_text(encoding="utf-8")))

        return experiences

    def get_by_id(self, experience_id: UUID) -> Experience | None:
        path = self._directory / f"{experience_id}.json"

        if not path.exists():
            return None

        return Experience.model_validate_json(path.read_text(encoding="utf-8"))

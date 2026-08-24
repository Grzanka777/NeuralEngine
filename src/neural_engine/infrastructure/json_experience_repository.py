from pathlib import Path
from uuid import UUID

from neural_engine.core.paths import NeuralPaths
from neural_engine.domain import Experience
from neural_engine.infrastructure.controlled_create import (
    build_controlled_create_target,
    publish_create_once,
)
from neural_engine.infrastructure.repository_paths import RepositoryPath
from neural_engine.ports.brain_trust_transition import ControlledMutationTarget
from neural_engine.ports.experience_repository import ExperienceRepository


class JsonExperienceRepository(ExperienceRepository):
    """Stores experiences as JSON files."""

    def __init__(
        self,
        directory: Path | None = None,
        *,
        paths: NeuralPaths | None = None,
    ) -> None:
        self._path = RepositoryPath.build(directory, paths, lambda value: value.EXPERIENCES)
        self._directory = self._path.directory

    def save(self, experience: Experience) -> None:
        self._path.prepare_for_write()

        path = self._directory / f"{experience.id}.json"

        path.write_text(
            experience.model_dump_json(indent=2),
            encoding="utf-8",
        )

    def controlled_create_target(self, experience: Experience) -> ControlledMutationTarget:
        candidate, serialized = self._candidate_bytes(experience)
        path = self._directory / f"{candidate.id}.json"
        return build_controlled_create_target(
            self._path.paths,
            path,
            serialized,
            lambda: publish_create_once(path, serialized, self._path.prepare_for_write),
        )

    @staticmethod
    def _candidate_bytes(experience: Experience) -> tuple[Experience, bytes]:
        candidate = Experience.model_validate_json(experience.model_dump_json(indent=2))
        return candidate, candidate.model_dump_json(indent=2).encode("utf-8")

    def load_all(self) -> list[Experience]:
        self._path.guard(operation="read")
        if not self._directory.exists():
            return []

        experiences: list[Experience] = []

        for path in sorted(self._directory.glob("*.json")):
            experiences.append(Experience.model_validate_json(path.read_text(encoding="utf-8")))

        return experiences

    def get_by_id(self, experience_id: UUID) -> Experience | None:
        self._path.guard(operation="read")
        path = self._directory / f"{experience_id}.json"

        if not path.exists():
            return None

        return Experience.model_validate_json(path.read_text(encoding="utf-8"))

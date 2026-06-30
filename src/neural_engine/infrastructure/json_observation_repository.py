from neural_engine.core.paths import NeuralPaths
from neural_engine.domain import Observation
from neural_engine.ports.observation_repository import ObservationRepository


class JsonObservationRepository(ObservationRepository):
    """Stores observations as JSON files."""

    def save(self, observation: Observation) -> None:
        NeuralPaths.OBSERVATIONS.mkdir(parents=True, exist_ok=True)

        path = NeuralPaths.OBSERVATIONS / f"{observation.id}.json"

        path.write_text(
            observation.model_dump_json(indent=2),
            encoding="utf-8",
        )

    def load_all(self) -> list[Observation]:
        if not NeuralPaths.OBSERVATIONS.exists():
            return []

        observations: list[Observation] = []

        for path in sorted(NeuralPaths.OBSERVATIONS.glob("*.json")):
            observations.append(Observation.model_validate_json(path.read_text(encoding="utf-8")))

        return observations

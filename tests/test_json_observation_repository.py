from pathlib import Path

from neural_engine.domain import Observation
from neural_engine.infrastructure.json_observation_repository import JsonObservationRepository


def test_get_by_id_returns_saved_observation(tmp_path: Path) -> None:
    repository = JsonObservationRepository(tmp_path)
    observation = Observation(content="Persisted observation")
    repository.save(observation)

    assert repository.get_by_id(observation.id) == observation


def test_get_by_id_returns_none_when_observation_file_is_missing(tmp_path: Path) -> None:
    repository = JsonObservationRepository(tmp_path)
    observation = Observation(content="Missing observation")

    assert repository.get_by_id(observation.id) is None

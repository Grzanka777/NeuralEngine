from uuid import UUID

from neural_engine.application.observation_service import ObservationService
from neural_engine.domain import Observation
from neural_engine.ports.observation_repository import ObservationRepository


class FakeObservationRepository(ObservationRepository):
    def __init__(self) -> None:
        self.saved: list[Observation] = []

    def save(self, observation: Observation) -> None:
        self.saved.append(observation)

    def load_all(self) -> list[Observation]:
        return self.saved

    def get_by_id(self, observation_id: UUID) -> Observation | None:
        for observation in self.saved:
            if observation.id == observation_id:
                return observation

        return None


def test_add_observation() -> None:
    repo = FakeObservationRepository()
    service = ObservationService(repo)

    result = service.add(
        content="Pytest is awesome",
        tags=["python"],
    )
    observation = result.observation

    assert len(repo.saved) == 1
    assert repo.saved[0] == observation
    assert observation.content == "Pytest is awesome"
    assert observation.tags == ["python"]
    assert result.duplicate_ids == []


def test_add_observation_reports_one_exact_duplicate() -> None:
    repo = FakeObservationRepository()
    service = ObservationService(repo)
    existing = service.add("Same content").observation

    result = service.add("Same content")

    assert result.duplicate_ids == [existing.id]
    assert repo.saved[-1] == result.observation
    assert result.observation.id not in result.duplicate_ids


def test_add_observation_reports_multiple_exact_duplicates() -> None:
    repo = FakeObservationRepository()
    service = ObservationService(repo)
    first = service.add("Same content").observation
    second = service.add("Same content").observation

    result = service.add("Same content")

    assert result.duplicate_ids == [first.id, second.id]
    assert repo.saved[-1] == result.observation
    assert result.observation.id not in result.duplicate_ids


def test_add_observation_treats_case_differences_as_distinct() -> None:
    repo = FakeObservationRepository()
    service = ObservationService(repo)
    service.add("Same content")

    result = service.add("same content")

    assert result.duplicate_ids == []


def test_add_observation_treats_whitespace_differences_as_distinct() -> None:
    repo = FakeObservationRepository()
    service = ObservationService(repo)
    service.add("Same content")

    result = service.add("Same  content")

    assert result.duplicate_ids == []


def test_list_observations_returns_repository_items() -> None:
    repo = FakeObservationRepository()
    service = ObservationService(repo)
    observation = service.add("Capture this", tags=["memory"]).observation

    assert service.list_observations() == [observation]


def test_search_observations_matches_content_case_insensitively() -> None:
    repo = FakeObservationRepository()
    service = ObservationService(repo)
    expected = service.add("Python testing notes").observation
    service.add("Architecture decision")

    assert service.search("PYTHON") == [expected]


def test_get_by_id_returns_matching_observation() -> None:
    repo = FakeObservationRepository()
    service = ObservationService(repo)
    expected = service.add("Find this", tags=["lookup"]).observation

    assert service.get_by_id(expected.id) == expected


def test_get_by_id_returns_none_when_missing() -> None:
    repo = FakeObservationRepository()
    service = ObservationService(repo)

    assert service.get_by_id(UUID("00000000-0000-0000-0000-000000000000")) is None

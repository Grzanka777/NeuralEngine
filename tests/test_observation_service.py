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


def test_add_observation() -> None:
    repo = FakeObservationRepository()
    service = ObservationService(repo)

    observation = service.add(
        content="Pytest is awesome",
        tags=["python"],
    )

    assert len(repo.saved) == 1
    assert repo.saved[0] == observation
    assert observation.content == "Pytest is awesome"
    assert observation.tags == ["python"]


def test_list_observations_returns_repository_items() -> None:
    repo = FakeObservationRepository()
    service = ObservationService(repo)
    observation = service.add("Capture this", tags=["memory"])

    assert service.list_observations() == [observation]


def test_search_observations_matches_content_case_insensitively() -> None:
    repo = FakeObservationRepository()
    service = ObservationService(repo)
    expected = service.add("Python testing notes")
    service.add("Architecture decision")

    assert service.search("PYTHON") == [expected]

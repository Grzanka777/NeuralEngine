import pytest
from typer.testing import CliRunner

from neural_engine import cli
from neural_engine.domain import Observation


class FakeObservationService:
    def __init__(self, observations: list[Observation]) -> None:
        self.observations = observations
        self.queries: list[str] = []

    def search(self, query: str) -> list[Observation]:
        self.queries.append(query)
        return self.observations


class FakeContainer:
    def __init__(self, service: FakeObservationService) -> None:
        self.service = service

    def observation_service(self) -> FakeObservationService:
        return self.service


def test_search_displays_matching_observations(monkeypatch: pytest.MonkeyPatch) -> None:
    observation = Observation(content="Python testing notes", tags=["python", "testing"])
    service = FakeObservationService([observation])
    monkeypatch.setattr(cli, "container", FakeContainer(service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["search", "python"])

    assert result.exit_code == 0
    assert service.queries == ["python"]
    assert "Python testing notes" in result.output
    assert "Tags: python, testing" in result.output


def test_search_handles_no_matching_observations(monkeypatch: pytest.MonkeyPatch) -> None:
    service = FakeObservationService([])
    monkeypatch.setattr(cli, "container", FakeContainer(service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["search", "missing"])

    assert result.exit_code == 0
    assert service.queries == ["missing"]
    assert "No matching observations found." in result.output

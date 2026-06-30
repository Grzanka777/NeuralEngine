from uuid import UUID

import pytest
from typer.testing import CliRunner

from neural_engine import cli
from neural_engine.domain import Experience, ExperienceResult, Observation


class FakeObservationService:
    def __init__(self, observations: list[Observation]) -> None:
        self.observations = observations
        self.queries: list[str] = []

    def search(self, query: str) -> list[Observation]:
        self.queries.append(query)
        return self.observations


class FakeExperienceService:
    def __init__(self, experiences: list[Experience]) -> None:
        self.experiences = experiences
        self.add_calls: list[
            tuple[str, str, str, str, ExperienceResult, list[UUID] | None, list[str] | None]
        ] = []
        self.requested_ids: list[UUID] = []

    def add(
        self,
        title: str,
        context: str,
        action: str,
        outcome: str,
        result: ExperienceResult,
        observation_ids: list[UUID] | None = None,
        tags: list[str] | None = None,
    ) -> Experience:
        self.add_calls.append((title, context, action, outcome, result, observation_ids, tags))

        experience = Experience(
            title=title,
            context=context,
            action=action,
            outcome=outcome,
            result=result,
            observation_ids=observation_ids or [],
            tags=tags or [],
        )
        self.experiences.append(experience)

        return experience

    def list_experiences(self) -> list[Experience]:
        return self.experiences

    def get_by_id(self, experience_id: UUID) -> Experience | None:
        self.requested_ids.append(experience_id)

        for experience in self.experiences:
            if experience.id == experience_id:
                return experience

        return None


class FakeContainer:
    def __init__(
        self,
        observation_service: FakeObservationService | None = None,
        experience_service: FakeExperienceService | None = None,
    ) -> None:
        self._observation_service = observation_service
        self._experience_service = experience_service

    def observation_service(self) -> FakeObservationService:
        if self._observation_service is None:
            raise AssertionError("Observation service was not expected")

        return self._observation_service

    def experience_service(self) -> FakeExperienceService:
        if self._experience_service is None:
            raise AssertionError("Experience service was not expected")

        return self._experience_service


def test_search_displays_matching_observations(monkeypatch: pytest.MonkeyPatch) -> None:
    observation = Observation(content="Python testing notes", tags=["python", "testing"])
    service = FakeObservationService([observation])
    monkeypatch.setattr(cli, "container", FakeContainer(observation_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["search", "python"])

    assert result.exit_code == 0
    assert service.queries == ["python"]
    assert "Python testing notes" in result.output
    assert "Tags: python, testing" in result.output


def test_search_handles_no_matching_observations(monkeypatch: pytest.MonkeyPatch) -> None:
    service = FakeObservationService([])
    monkeypatch.setattr(cli, "container", FakeContainer(observation_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["search", "missing"])

    assert result.exit_code == 0
    assert service.queries == ["missing"]
    assert "No matching observations found." in result.output


def test_experience_add_delegates_to_service_with_parsed_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observation_id = UUID("11111111-1111-1111-1111-111111111111")
    service = FakeExperienceService([])
    monkeypatch.setattr(cli, "container", FakeContainer(experience_service=service))
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "experience",
            "add",
            "--title",
            "Ship feature",
            "--context",
            "CLI surface",
            "--action",
            "Added commands",
            "--outcome",
            "Users can record experiences",
            "--result",
            "success",
            "--observation-id",
            str(observation_id),
            "--tag",
            "cli",
            "--tag",
            "experience",
        ],
    )

    assert result.exit_code == 0
    assert len(service.add_calls) == 1
    assert service.add_calls[0] == (
        "Ship feature",
        "CLI surface",
        "Added commands",
        "Users can record experiences",
        ExperienceResult.SUCCESS,
        [observation_id],
        ["cli", "experience"],
    )
    assert "Experience stored." in result.output
    assert str(service.experiences[0].id) in result.output


def test_experience_add_rejects_invalid_result(monkeypatch: pytest.MonkeyPatch) -> None:
    service = FakeExperienceService([])
    monkeypatch.setattr(cli, "container", FakeContainer(experience_service=service))
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "experience",
            "add",
            "--title",
            "Ship feature",
            "--context",
            "CLI surface",
            "--action",
            "Added commands",
            "--outcome",
            "Users can record experiences",
            "--result",
            "invalid",
        ],
    )

    assert result.exit_code != 0
    assert service.add_calls == []


def test_experience_list_displays_experiences(monkeypatch: pytest.MonkeyPatch) -> None:
    experience = Experience(
        title="Listed experience",
        context="CLI list",
        action="Fetch experiences",
        outcome="Experience is displayed",
        result=ExperienceResult.MIXED,
    )
    service = FakeExperienceService([experience])
    monkeypatch.setattr(cli, "container", FakeContainer(experience_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["experience", "list"])

    assert result.exit_code == 0
    assert str(experience.id) in result.output
    assert str(experience.timestamp) in result.output
    assert "Listed experience" in result.output
    assert "mixed" in result.output


def test_experience_list_handles_empty_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    service = FakeExperienceService([])
    monkeypatch.setattr(cli, "container", FakeContainer(experience_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["experience", "list"])

    assert result.exit_code == 0
    assert "No experiences found." in result.output


def test_experience_show_displays_existing_experience(monkeypatch: pytest.MonkeyPatch) -> None:
    observation_id = UUID("22222222-2222-2222-2222-222222222222")
    experience = Experience(
        title="Shown experience",
        context="CLI show",
        action="Fetch by id",
        outcome="All fields are displayed",
        result=ExperienceResult.FAILURE,
        observation_ids=[observation_id],
        tags=["debug"],
    )
    service = FakeExperienceService([experience])
    monkeypatch.setattr(cli, "container", FakeContainer(experience_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["experience", "show", str(experience.id)])

    assert result.exit_code == 0
    assert service.requested_ids == [experience.id]
    assert f"ID: {experience.id}" in result.output
    assert f"Timestamp: {experience.timestamp}" in result.output
    assert "Title: Shown experience" in result.output
    assert "Context: CLI show" in result.output
    assert "Action: Fetch by id" in result.output
    assert "Outcome: All fields are displayed" in result.output
    assert "Result: failure" in result.output
    assert f"Observation IDs: {observation_id}" in result.output
    assert "Tags: debug" in result.output


def test_experience_show_handles_missing_experience(monkeypatch: pytest.MonkeyPatch) -> None:
    missing_id = UUID("33333333-3333-3333-3333-333333333333")
    service = FakeExperienceService([])
    monkeypatch.setattr(cli, "container", FakeContainer(experience_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["experience", "show", str(missing_id)])

    assert result.exit_code == 1
    assert service.requested_ids == [missing_id]
    assert f"Experience not found: {missing_id}" in result.output

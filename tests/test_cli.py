from uuid import UUID

import pytest
from typer.testing import CliRunner

from neural_engine import cli
from neural_engine.application.experience_service import ObservationNotFoundError
from neural_engine.application.knowledge_service import (
    ExperienceNotFoundError,
    KnowledgeEvidenceRequiredError,
)
from neural_engine.application.observation_service import AddObservationResult
from neural_engine.application.playbook_service import (
    KnowledgeNotFoundError,
    PlaybookKnowledgeRequiredError,
    PlaybookStepsRequiredError,
)
from neural_engine.domain import (
    Experience,
    ExperienceResult,
    Knowledge,
    KnowledgeConfidence,
    Observation,
    Playbook,
)


class FakeObservationService:
    def __init__(self, observations: list[Observation]) -> None:
        self.observations = observations
        self.queries: list[str] = []
        self.requested_ids: list[UUID] = []
        self.add_calls: list[tuple[str, list[str] | None]] = []

    def list_observations(self) -> list[Observation]:
        return self.observations

    def add(
        self,
        content: str,
        tags: list[str] | None = None,
    ) -> AddObservationResult:
        self.add_calls.append((content, tags))
        duplicate_ids = [
            observation.id for observation in self.observations if observation.content == content
        ]
        observation = Observation(content=content, tags=tags or [])
        self.observations.append(observation)

        return AddObservationResult(
            observation=observation,
            duplicate_ids=duplicate_ids,
        )

    def search(self, query: str) -> list[Observation]:
        self.queries.append(query)
        return self.observations

    def get_by_id(self, observation_id: UUID) -> Observation | None:
        self.requested_ids.append(observation_id)

        for observation in self.observations:
            if observation.id == observation_id:
                return observation

        return None


class FakeExperienceService:
    def __init__(
        self,
        experiences: list[Experience],
        missing_observation_id: UUID | None = None,
    ) -> None:
        self.experiences = experiences
        self.missing_observation_id = missing_observation_id
        self.add_calls: list[
            tuple[str, str, str, str, ExperienceResult, list[UUID] | None, list[str] | None]
        ] = []
        self.add_from_observation_calls: list[
            tuple[UUID, str, str, str, ExperienceResult, list[str] | None]
        ] = []
        self.requested_ids: list[UUID] = []
        self.list_for_observation_calls: list[UUID] = []

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

        if self.missing_observation_id is not None:
            raise ObservationNotFoundError(self.missing_observation_id)

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

    def add_from_observation(
        self,
        observation_id: UUID,
        title: str,
        action: str,
        outcome: str,
        result: ExperienceResult,
        tags: list[str] | None = None,
    ) -> Experience:
        self.add_from_observation_calls.append(
            (observation_id, title, action, outcome, result, tags)
        )

        if self.missing_observation_id is not None:
            raise ObservationNotFoundError(self.missing_observation_id)

        experience = Experience(
            title=title,
            context="Observation content from service",
            action=action,
            outcome=outcome,
            result=result,
            observation_ids=[observation_id],
            tags=tags or [],
        )
        self.experiences.append(experience)

        return experience

    def list_experiences(self) -> list[Experience]:
        return self.experiences

    def list_for_observation(self, observation_id: UUID) -> list[Experience]:
        self.list_for_observation_calls.append(observation_id)

        if self.missing_observation_id is not None:
            raise ObservationNotFoundError(self.missing_observation_id)

        return [
            experience
            for experience in self.experiences
            if observation_id in experience.observation_ids
        ]

    def get_by_id(self, experience_id: UUID) -> Experience | None:
        self.requested_ids.append(experience_id)

        for experience in self.experiences:
            if experience.id == experience_id:
                return experience

        return None


class FakeKnowledgeService:
    def __init__(
        self,
        knowledge_items: list[Knowledge],
        missing_experience_id: UUID | None = None,
    ) -> None:
        self.knowledge_items = knowledge_items
        self.missing_experience_id = missing_experience_id
        self.add_calls: list[
            tuple[str, str, KnowledgeConfidence, list[UUID], list[str] | None]
        ] = []
        self.add_from_experience_calls: list[
            tuple[UUID, str, str, KnowledgeConfidence, list[str] | None]
        ] = []
        self.list_for_experience_calls: list[UUID] = []
        self.requested_ids: list[UUID] = []

    def add(
        self,
        statement: str,
        rationale: str,
        confidence: KnowledgeConfidence,
        experience_ids: list[UUID],
        tags: list[str] | None = None,
    ) -> Knowledge:
        self.add_calls.append((statement, rationale, confidence, experience_ids, tags))

        if not experience_ids:
            raise KnowledgeEvidenceRequiredError()

        if self.missing_experience_id is not None:
            raise ExperienceNotFoundError(self.missing_experience_id)

        knowledge = Knowledge(
            statement=statement,
            rationale=rationale,
            confidence=confidence,
            experience_ids=experience_ids,
            tags=tags or [],
        )
        self.knowledge_items.append(knowledge)

        return knowledge

    def add_from_experience(
        self,
        experience_id: UUID,
        statement: str,
        rationale: str,
        confidence: KnowledgeConfidence,
        tags: list[str] | None = None,
    ) -> Knowledge:
        self.add_from_experience_calls.append(
            (experience_id, statement, rationale, confidence, tags)
        )

        if self.missing_experience_id is not None:
            raise ExperienceNotFoundError(self.missing_experience_id)

        knowledge = Knowledge(
            statement=statement,
            rationale=rationale,
            confidence=confidence,
            experience_ids=[experience_id],
            tags=tags or [],
        )
        self.knowledge_items.append(knowledge)

        return knowledge

    def list_knowledge(self) -> list[Knowledge]:
        return self.knowledge_items

    def list_for_experience(self, experience_id: UUID) -> list[Knowledge]:
        self.list_for_experience_calls.append(experience_id)

        if self.missing_experience_id is not None:
            raise ExperienceNotFoundError(self.missing_experience_id)

        return [
            knowledge
            for knowledge in self.knowledge_items
            if experience_id in knowledge.experience_ids
        ]

    def get_by_id(self, knowledge_id: UUID) -> Knowledge | None:
        self.requested_ids.append(knowledge_id)

        for knowledge in self.knowledge_items:
            if knowledge.id == knowledge_id:
                return knowledge

        return None


class FakePlaybookService:
    def __init__(
        self,
        playbooks: list[Playbook],
        missing_knowledge_id: UUID | None = None,
    ) -> None:
        self.playbooks = playbooks
        self.missing_knowledge_id = missing_knowledge_id
        self.add_calls: list[
            tuple[
                str,
                str,
                str,
                list[str],
                list[str],
                list[UUID],
                list[str] | None,
                list[str] | None,
            ]
        ] = []
        self.list_for_knowledge_calls: list[UUID] = []
        self.requested_ids: list[UUID] = []

    def add(
        self,
        title: str,
        situation: str,
        objective: str,
        steps: list[str],
        success_criteria: list[str],
        knowledge_ids: list[UUID],
        constraints: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> Playbook:
        self.add_calls.append(
            (
                title,
                situation,
                objective,
                steps,
                success_criteria,
                knowledge_ids,
                constraints,
                tags,
            )
        )

        if not knowledge_ids:
            raise PlaybookKnowledgeRequiredError()

        if not steps:
            raise PlaybookStepsRequiredError()

        if self.missing_knowledge_id is not None:
            raise KnowledgeNotFoundError(self.missing_knowledge_id)

        playbook = Playbook(
            title=title,
            situation=situation,
            objective=objective,
            steps=steps,
            success_criteria=success_criteria,
            constraints=constraints or [],
            knowledge_ids=knowledge_ids,
            tags=tags or [],
        )
        self.playbooks.append(playbook)

        return playbook

    def list_playbooks(self) -> list[Playbook]:
        return self.playbooks

    def list_for_knowledge(self, knowledge_id: UUID) -> list[Playbook]:
        self.list_for_knowledge_calls.append(knowledge_id)

        if self.missing_knowledge_id is not None:
            raise KnowledgeNotFoundError(self.missing_knowledge_id)

        return [playbook for playbook in self.playbooks if knowledge_id in playbook.knowledge_ids]

    def get_by_id(self, playbook_id: UUID) -> Playbook | None:
        self.requested_ids.append(playbook_id)

        for playbook in self.playbooks:
            if playbook.id == playbook_id:
                return playbook

        return None


class FakeContainer:
    def __init__(
        self,
        observation_service: FakeObservationService | None = None,
        experience_service: FakeExperienceService | None = None,
        knowledge_service: FakeKnowledgeService | None = None,
        playbook_service: FakePlaybookService | None = None,
    ) -> None:
        self._observation_service = observation_service
        self._experience_service = experience_service
        self._knowledge_service = knowledge_service
        self._playbook_service = playbook_service

    def observation_service(self) -> FakeObservationService:
        if self._observation_service is None:
            raise AssertionError("Observation service was not expected")

        return self._observation_service

    def experience_service(self) -> FakeExperienceService:
        if self._experience_service is None:
            raise AssertionError("Experience service was not expected")

        return self._experience_service

    def knowledge_service(self) -> FakeKnowledgeService:
        if self._knowledge_service is None:
            raise AssertionError("Knowledge service was not expected")

        return self._knowledge_service

    def playbook_service(self) -> FakePlaybookService:
        if self._playbook_service is None:
            raise AssertionError("Playbook service was not expected")

        return self._playbook_service


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


def test_observe_stores_observation_without_duplicate_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakeObservationService([])
    monkeypatch.setattr(cli, "container", FakeContainer(observation_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["observe", "New content", "--tags", "new"])

    assert result.exit_code == 0
    assert service.add_calls == [("New content", ["new"])]
    assert len(service.observations) == 1
    assert "Observation stored." in result.output
    assert "Warning: exact duplicate observations already exist:" not in result.output


def test_observe_prints_duplicate_warning_and_existing_duplicate_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = Observation(content="Duplicate content")
    second = Observation(content="Duplicate content")
    service = FakeObservationService([first, second])
    monkeypatch.setattr(cli, "container", FakeContainer(observation_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["observe", "Duplicate content"])

    assert result.exit_code == 0
    assert service.add_calls == [("Duplicate content", None)]
    assert len(service.observations) == 3
    assert "Observation stored." in result.output
    assert "Warning: exact duplicate observations already exist:" in result.output
    assert f"- {first.id}" in result.output
    assert f"- {second.id}" in result.output
    assert f"- {service.observations[-1].id}" not in result.output


def test_list_displays_observation_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    observation = Observation(content="Observation content", tags=["one", "two"])
    service = FakeObservationService([observation])
    monkeypatch.setattr(cli, "container", FakeContainer(observation_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["list"])

    assert result.exit_code == 0
    assert f"ID: {observation.id}" in result.output
    assert f"Timestamp: {observation.timestamp}" in result.output
    assert "Content: Observation content" in result.output
    assert "Tags: one, two" in result.output


def test_list_handles_empty_observation_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    service = FakeObservationService([])
    monkeypatch.setattr(cli, "container", FakeContainer(observation_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["list"])

    assert result.exit_code == 0
    assert "No observations found." in result.output


def test_show_observation_delegates_and_displays_all_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observation = Observation(
        source="test",
        content="Detailed observation",
        tags=["detail"],
    )
    service = FakeObservationService([observation])
    monkeypatch.setattr(cli, "container", FakeContainer(observation_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["show", str(observation.id)])

    assert result.exit_code == 0
    assert service.requested_ids == [observation.id]
    assert f"ID: {observation.id}" in result.output
    assert f"Timestamp: {observation.timestamp}" in result.output
    assert "Source: test" in result.output
    assert "Content: Detailed observation" in result.output
    assert "Tags: detail" in result.output


def test_show_observation_handles_missing_observation(monkeypatch: pytest.MonkeyPatch) -> None:
    missing_id = UUID("77777777-7777-7777-7777-777777777777")
    service = FakeObservationService([])
    monkeypatch.setattr(cli, "container", FakeContainer(observation_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["show", str(missing_id)])

    assert result.exit_code == 1
    assert service.requested_ids == [missing_id]
    assert f"Observation not found: {missing_id}" in result.output


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


def test_experience_add_handles_missing_observation_without_storing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_id = UUID("44444444-4444-4444-4444-444444444444")
    service = FakeExperienceService([], missing_observation_id=missing_id)
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
            str(missing_id),
        ],
    )

    assert result.exit_code == 1
    assert len(service.add_calls) == 1
    assert service.experiences == []
    assert f"Observation not found: {missing_id}" in result.output


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


def test_experience_from_observation_delegates_with_parsed_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observation_id = UUID("55555555-5555-5555-5555-555555555555")
    service = FakeExperienceService([])
    monkeypatch.setattr(cli, "container", FakeContainer(experience_service=service))
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "experience",
            "from-observation",
            str(observation_id),
            "--title",
            "From observation",
            "--action",
            "Create linked experience",
            "--outcome",
            "Experience is created",
            "--result",
            "mixed",
            "--tag",
            "manual",
            "--tag",
            "linked",
        ],
    )

    assert result.exit_code == 0
    assert service.add_from_observation_calls == [
        (
            observation_id,
            "From observation",
            "Create linked experience",
            "Experience is created",
            ExperienceResult.MIXED,
            ["manual", "linked"],
        )
    ]
    assert "Experience stored from observation." in result.output
    assert str(service.experiences[0].id) in result.output


def test_experience_from_observation_handles_missing_observation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_id = UUID("66666666-6666-6666-6666-666666666666")
    service = FakeExperienceService([], missing_observation_id=missing_id)
    monkeypatch.setattr(cli, "container", FakeContainer(experience_service=service))
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "experience",
            "from-observation",
            str(missing_id),
            "--title",
            "From observation",
            "--action",
            "Create linked experience",
            "--outcome",
            "Experience is created",
            "--result",
            "success",
        ],
    )

    assert result.exit_code == 1
    assert len(service.add_from_observation_calls) == 1
    assert service.experiences == []
    assert f"Observation not found: {missing_id}" in result.output


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


def test_observation_experiences_delegates_and_displays_linked_experiences(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observation_id = UUID("88888888-8888-8888-8888-888888888888")
    experience = Experience(
        title="Linked experience",
        context="CLI relation",
        action="List linked experiences",
        outcome="Experience is displayed",
        result=ExperienceResult.SUCCESS,
        observation_ids=[observation_id],
    )
    service = FakeExperienceService([experience])
    monkeypatch.setattr(cli, "container", FakeContainer(experience_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["observation", "experiences", str(observation_id)])

    assert result.exit_code == 0
    assert service.list_for_observation_calls == [observation_id]
    assert f"ID: {experience.id}" in result.output
    assert f"Timestamp: {experience.timestamp}" in result.output
    assert "Title: Linked experience" in result.output
    assert "Result: success" in result.output


def test_observation_experiences_empty_state_returns_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observation_id = UUID("99999999-9999-9999-9999-999999999999")
    service = FakeExperienceService([])
    monkeypatch.setattr(cli, "container", FakeContainer(experience_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["observation", "experiences", str(observation_id)])

    assert result.exit_code == 0
    assert service.list_for_observation_calls == [observation_id]
    assert f"No experiences linked to observation: {observation_id}" in result.output


def test_observation_experiences_missing_observation_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    service = FakeExperienceService([], missing_observation_id=missing_id)
    monkeypatch.setattr(cli, "container", FakeContainer(experience_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["observation", "experiences", str(missing_id)])

    assert result.exit_code == 1
    assert service.list_for_observation_calls == [missing_id]
    assert f"Observation not found: {missing_id}" in result.output


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


def test_experience_knowledge_delegates_and_displays_linked_knowledge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    experience_id = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    knowledge = Knowledge(
        statement="Linked knowledge",
        rationale="CLI relation test",
        confidence=KnowledgeConfidence.HIGH,
        experience_ids=[experience_id],
    )
    service = FakeKnowledgeService([knowledge])
    monkeypatch.setattr(cli, "container", FakeContainer(knowledge_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["experience", "knowledge", str(experience_id)])

    assert result.exit_code == 0
    assert service.list_for_experience_calls == [experience_id]
    assert f"ID: {knowledge.id}" in result.output
    assert f"Timestamp: {knowledge.timestamp}" in result.output
    assert "Statement: Linked knowledge" in result.output
    assert "Confidence: high" in result.output


def test_experience_knowledge_empty_state_returns_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    experience_id = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
    service = FakeKnowledgeService([])
    monkeypatch.setattr(cli, "container", FakeContainer(knowledge_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["experience", "knowledge", str(experience_id)])

    assert result.exit_code == 0
    assert service.list_for_experience_calls == [experience_id]
    assert f"No knowledge linked to experience: {experience_id}" in result.output


def test_experience_knowledge_missing_experience_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_id = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
    service = FakeKnowledgeService([], missing_experience_id=missing_id)
    monkeypatch.setattr(cli, "container", FakeContainer(knowledge_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["experience", "knowledge", str(missing_id)])

    assert result.exit_code == 1
    assert service.list_for_experience_calls == [missing_id]
    assert f"Experience not found: {missing_id}" in result.output


def test_knowledge_add_delegates_with_parsed_values_and_prints_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_experience_id = UUID("11111111-1111-1111-1111-111111111111")
    second_experience_id = UUID("22222222-2222-2222-2222-222222222222")
    service = FakeKnowledgeService([])
    monkeypatch.setattr(cli, "container", FakeContainer(knowledge_service=service))
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "knowledge",
            "add",
            "--statement",
            "Focused tests reduce debugging time",
            "--rationale",
            "Two experiences showed faster isolation with narrow test runs.",
            "--confidence",
            "high",
            "--experience-id",
            str(first_experience_id),
            "--experience-id",
            str(second_experience_id),
            "--tag",
            "testing",
            "--tag",
            "quality",
        ],
    )

    assert result.exit_code == 0
    assert service.add_calls == [
        (
            "Focused tests reduce debugging time",
            "Two experiences showed faster isolation with narrow test runs.",
            KnowledgeConfidence.HIGH,
            [first_experience_id, second_experience_id],
            ["testing", "quality"],
        )
    ]
    assert "Knowledge stored." in result.output
    assert str(service.knowledge_items[0].id) in result.output


def test_knowledge_add_handles_empty_experience_ids_without_storing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakeKnowledgeService([])
    monkeypatch.setattr(cli, "container", FakeContainer(knowledge_service=service))
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "knowledge",
            "add",
            "--statement",
            "Needs evidence",
            "--rationale",
            "Knowledge must be linked to experience.",
            "--confidence",
            "low",
        ],
    )

    assert result.exit_code == 1
    assert service.add_calls == [
        (
            "Needs evidence",
            "Knowledge must be linked to experience.",
            KnowledgeConfidence.LOW,
            [],
            None,
        )
    ]
    assert service.knowledge_items == []
    assert "Knowledge requires at least one experience ID." in result.output


def test_knowledge_add_handles_missing_experience_without_storing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_id = UUID("33333333-3333-3333-3333-333333333333")
    service = FakeKnowledgeService([], missing_experience_id=missing_id)
    monkeypatch.setattr(cli, "container", FakeContainer(knowledge_service=service))
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "knowledge",
            "add",
            "--statement",
            "Invalid evidence",
            "--rationale",
            "The experience reference is missing.",
            "--confidence",
            "medium",
            "--experience-id",
            str(missing_id),
        ],
    )

    assert result.exit_code == 1
    assert len(service.add_calls) == 1
    assert service.knowledge_items == []
    assert f"Experience not found: {missing_id}" in result.output


def test_knowledge_from_experience_delegates_with_parsed_values_and_prints_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    experience_id = UUID("99999999-9999-9999-9999-999999999999")
    service = FakeKnowledgeService([])
    monkeypatch.setattr(cli, "container", FakeContainer(knowledge_service=service))
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "knowledge",
            "from-experience",
            str(experience_id),
            "--statement",
            "Use focused regression tests",
            "--rationale",
            "The source experience showed they isolate defects quickly.",
            "--confidence",
            "medium",
            "--tag",
            "testing",
            "--tag",
            "regression",
        ],
    )

    assert result.exit_code == 0
    assert service.add_from_experience_calls == [
        (
            experience_id,
            "Use focused regression tests",
            "The source experience showed they isolate defects quickly.",
            KnowledgeConfidence.MEDIUM,
            ["testing", "regression"],
        )
    ]
    assert service.knowledge_items[0].experience_ids == [experience_id]
    assert "Knowledge stored from experience." in result.output
    assert str(service.knowledge_items[0].id) in result.output


def test_knowledge_from_experience_handles_missing_experience_without_storing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    service = FakeKnowledgeService([], missing_experience_id=missing_id)
    monkeypatch.setattr(cli, "container", FakeContainer(knowledge_service=service))
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "knowledge",
            "from-experience",
            str(missing_id),
            "--statement",
            "Missing source",
            "--rationale",
            "The source experience is absent.",
            "--confidence",
            "low",
        ],
    )

    assert result.exit_code == 1
    assert len(service.add_from_experience_calls) == 1
    assert service.knowledge_items == []
    assert f"Experience not found: {missing_id}" in result.output


def test_knowledge_list_displays_knowledge(monkeypatch: pytest.MonkeyPatch) -> None:
    experience_id = UUID("44444444-4444-4444-4444-444444444444")
    knowledge = Knowledge(
        statement="Listed knowledge",
        rationale="CLI list test",
        confidence=KnowledgeConfidence.MEDIUM,
        experience_ids=[experience_id],
    )
    service = FakeKnowledgeService([knowledge])
    monkeypatch.setattr(cli, "container", FakeContainer(knowledge_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["knowledge", "list"])

    assert result.exit_code == 0
    assert f"ID: {knowledge.id}" in result.output
    assert f"Timestamp: {knowledge.timestamp}" in result.output
    assert "Statement: Listed knowledge" in result.output
    assert "Confidence: medium" in result.output


def test_knowledge_list_handles_empty_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    service = FakeKnowledgeService([])
    monkeypatch.setattr(cli, "container", FakeContainer(knowledge_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["knowledge", "list"])

    assert result.exit_code == 0
    assert "No knowledge found." in result.output


def test_knowledge_playbooks_delegates_and_displays_linked_playbooks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    knowledge_id = UUID("45454545-4545-4545-4545-454545454545")
    playbook = Playbook(
        title="Linked playbook",
        situation="CLI relation test",
        objective="Display linked playbooks",
        steps=["List playbooks"],
        success_criteria=["Playbook is displayed"],
        knowledge_ids=[knowledge_id],
    )
    service = FakePlaybookService([playbook])
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["knowledge", "playbooks", str(knowledge_id)])

    assert result.exit_code == 0
    assert service.list_for_knowledge_calls == [knowledge_id]
    assert f"ID: {playbook.id}" in result.output
    assert f"Timestamp: {playbook.timestamp}" in result.output
    assert "Title: Linked playbook" in result.output
    assert "Objective: Display linked playbooks" in result.output


def test_knowledge_playbooks_empty_state_returns_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    knowledge_id = UUID("67676767-6767-6767-6767-676767676767")
    service = FakePlaybookService([])
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["knowledge", "playbooks", str(knowledge_id)])

    assert result.exit_code == 0
    assert service.list_for_knowledge_calls == [knowledge_id]
    assert f"No playbooks linked to knowledge: {knowledge_id}" in result.output


def test_knowledge_playbooks_missing_knowledge_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_id = UUID("78787878-7878-7878-7878-787878787878")
    service = FakePlaybookService([], missing_knowledge_id=missing_id)
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["knowledge", "playbooks", str(missing_id)])

    assert result.exit_code == 1
    assert service.list_for_knowledge_calls == [missing_id]
    assert f"Knowledge not found: {missing_id}" in result.output


def test_knowledge_show_delegates_and_displays_all_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_experience_id = UUID("55555555-5555-5555-5555-555555555555")
    second_experience_id = UUID("66666666-6666-6666-6666-666666666666")
    knowledge = Knowledge(
        statement="Shown knowledge",
        rationale="CLI show should display every field.",
        confidence=KnowledgeConfidence.HIGH,
        experience_ids=[first_experience_id, second_experience_id],
        tags=["manual", "lesson"],
    )
    service = FakeKnowledgeService([knowledge])
    monkeypatch.setattr(cli, "container", FakeContainer(knowledge_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["knowledge", "show", str(knowledge.id)])

    assert result.exit_code == 0
    assert service.requested_ids == [knowledge.id]
    assert f"ID: {knowledge.id}" in result.output
    assert f"Timestamp: {knowledge.timestamp}" in result.output
    assert "Statement: Shown knowledge" in result.output
    assert "Rationale: CLI show should display every field." in result.output
    assert "Confidence: high" in result.output
    assert "Experience IDs:" in result.output
    assert str(first_experience_id) in result.output
    assert str(second_experience_id) in result.output
    assert "Tags: manual, lesson" in result.output


def test_knowledge_show_displays_dash_for_empty_tags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    experience_id = UUID("77777777-7777-7777-7777-777777777777")
    knowledge = Knowledge(
        statement="No tags",
        rationale="Empty tags should render consistently.",
        confidence=KnowledgeConfidence.LOW,
        experience_ids=[experience_id],
    )
    service = FakeKnowledgeService([knowledge])
    monkeypatch.setattr(cli, "container", FakeContainer(knowledge_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["knowledge", "show", str(knowledge.id)])

    assert result.exit_code == 0
    assert "Tags: -" in result.output


def test_knowledge_show_handles_missing_knowledge(monkeypatch: pytest.MonkeyPatch) -> None:
    missing_id = UUID("88888888-8888-8888-8888-888888888888")
    service = FakeKnowledgeService([])
    monkeypatch.setattr(cli, "container", FakeContainer(knowledge_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["knowledge", "show", str(missing_id)])

    assert result.exit_code == 1
    assert service.requested_ids == [missing_id]
    assert f"Knowledge not found: {missing_id}" in result.output


def test_playbook_add_delegates_with_parsed_repeatable_values_and_prints_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_knowledge_id = UUID("99999999-9999-9999-9999-999999999999")
    second_knowledge_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    service = FakePlaybookService([])
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_service=service))
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "playbook",
            "add",
            "--title",
            "Debug flaky tests",
            "--situation",
            "A test fails intermittently",
            "--objective",
            "Find the unstable dependency",
            "--step",
            "Run the failing test repeatedly",
            "--step",
            "Inspect shared state",
            "--success-criterion",
            "Failure source is isolated",
            "--success-criterion",
            "The fix is verified",
            "--knowledge-id",
            str(first_knowledge_id),
            "--knowledge-id",
            str(second_knowledge_id),
            "--constraint",
            "Do not skip the test",
            "--constraint",
            "Keep changes focused",
            "--tag",
            "testing",
            "--tag",
            "debugging",
        ],
    )

    assert result.exit_code == 0
    assert service.add_calls == [
        (
            "Debug flaky tests",
            "A test fails intermittently",
            "Find the unstable dependency",
            ["Run the failing test repeatedly", "Inspect shared state"],
            ["Failure source is isolated", "The fix is verified"],
            [first_knowledge_id, second_knowledge_id],
            ["Do not skip the test", "Keep changes focused"],
            ["testing", "debugging"],
        )
    ]
    assert "Playbook stored." in result.output
    assert str(service.playbooks[0].id) in result.output


def test_playbook_add_handles_empty_knowledge_ids_without_storing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakePlaybookService([])
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_service=service))
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "playbook",
            "add",
            "--title",
            "Needs knowledge",
            "--situation",
            "No knowledge was supplied",
            "--objective",
            "Reject the playbook",
            "--step",
            "Do one thing",
            "--success-criterion",
            "It is rejected",
        ],
    )

    assert result.exit_code == 1
    assert service.add_calls == [
        (
            "Needs knowledge",
            "No knowledge was supplied",
            "Reject the playbook",
            ["Do one thing"],
            ["It is rejected"],
            [],
            None,
            None,
        )
    ]
    assert service.playbooks == []
    assert "Playbook requires at least one knowledge ID." in result.output


def test_playbook_add_handles_empty_steps_without_storing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    knowledge_id = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    service = FakePlaybookService([])
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_service=service))
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "playbook",
            "add",
            "--title",
            "Needs steps",
            "--situation",
            "No steps were supplied",
            "--objective",
            "Reject the playbook",
            "--success-criterion",
            "It is rejected",
            "--knowledge-id",
            str(knowledge_id),
        ],
    )

    assert result.exit_code == 1
    assert len(service.add_calls) == 1
    assert service.add_calls[0][3] == []
    assert service.playbooks == []
    assert "Playbook requires at least one step." in result.output


def test_playbook_add_requires_success_criterion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    knowledge_id = UUID("56565656-5656-5656-5656-565656565656")
    service = FakePlaybookService([])
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_service=service))
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "playbook",
            "add",
            "--title",
            "Missing criterion",
            "--situation",
            "No success criterion was supplied",
            "--objective",
            "Reject incomplete CLI input",
            "--step",
            "Perform one action",
            "--knowledge-id",
            str(knowledge_id),
        ],
    )

    assert result.exit_code != 0
    assert service.add_calls == []


def test_playbook_add_handles_missing_knowledge_without_storing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_id = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
    service = FakePlaybookService([], missing_knowledge_id=missing_id)
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_service=service))
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "playbook",
            "add",
            "--title",
            "Missing knowledge",
            "--situation",
            "A linked knowledge item is absent",
            "--objective",
            "Reject the playbook",
            "--step",
            "Validate knowledge",
            "--success-criterion",
            "It is rejected",
            "--knowledge-id",
            str(missing_id),
        ],
    )

    assert result.exit_code == 1
    assert len(service.add_calls) == 1
    assert service.playbooks == []
    assert f"Knowledge not found: {missing_id}" in result.output


def test_playbook_list_displays_playbooks(monkeypatch: pytest.MonkeyPatch) -> None:
    knowledge_id = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
    playbook = Playbook(
        title="Listed playbook",
        situation="CLI list",
        objective="Display summary fields",
        steps=["List playbooks"],
        success_criteria=["Playbook is visible"],
        knowledge_ids=[knowledge_id],
    )
    service = FakePlaybookService([playbook])
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["playbook", "list"])

    assert result.exit_code == 0
    assert f"ID: {playbook.id}" in result.output
    assert f"Timestamp: {playbook.timestamp}" in result.output
    assert "Title: Listed playbook" in result.output
    assert "Objective: Display summary fields" in result.output


def test_playbook_list_handles_empty_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    service = FakePlaybookService([])
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["playbook", "list"])

    assert result.exit_code == 0
    assert "No playbooks found." in result.output


def test_playbook_show_delegates_and_displays_all_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_knowledge_id = UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
    second_knowledge_id = UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
    playbook = Playbook(
        title="Shown playbook",
        situation="A production issue repeats",
        objective="Resolve it consistently",
        steps=["Collect evidence", "Apply the fix"],
        success_criteria=["Root cause is known", "Regression is covered"],
        constraints=["No broad refactor", "Keep logs"],
        knowledge_ids=[first_knowledge_id, second_knowledge_id],
        tags=["ops", "debugging"],
    )
    service = FakePlaybookService([playbook])
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["playbook", "show", str(playbook.id)])

    assert result.exit_code == 0
    assert service.requested_ids == [playbook.id]
    assert f"ID: {playbook.id}" in result.output
    assert f"Timestamp: {playbook.timestamp}" in result.output
    assert "Title: Shown playbook" in result.output
    assert "Situation: A production issue repeats" in result.output
    assert "Objective: Resolve it consistently" in result.output
    assert "Steps:" in result.output
    assert "- Collect evidence" in result.output
    assert "- Apply the fix" in result.output
    assert "Success criteria:" in result.output
    assert "- Root cause is known" in result.output
    assert "- Regression is covered" in result.output
    assert "Constraints:" in result.output
    assert "- No broad refactor" in result.output
    assert "- Keep logs" in result.output
    assert "Knowledge IDs:" in result.output
    assert str(first_knowledge_id) in result.output
    assert str(second_knowledge_id) in result.output
    assert "Tags: ops, debugging" in result.output


def test_playbook_show_displays_dash_for_empty_constraints_and_tags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    knowledge_id = UUID("12121212-1212-1212-1212-121212121212")
    playbook = Playbook(
        title="No optional fields",
        situation="Optional fields are empty",
        objective="Render empty fields clearly",
        steps=["Show playbook"],
        success_criteria=["Output is clear"],
        knowledge_ids=[knowledge_id],
    )
    service = FakePlaybookService([playbook])
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["playbook", "show", str(playbook.id)])

    assert result.exit_code == 0
    assert "Constraints:\n-" in result.output
    assert "Tags: -" in result.output


def test_playbook_show_handles_missing_playbook(monkeypatch: pytest.MonkeyPatch) -> None:
    missing_id = UUID("34343434-3434-3434-3434-343434343434")
    service = FakePlaybookService([])
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["playbook", "show", str(missing_id)])

    assert result.exit_code == 1
    assert service.requested_ids == [missing_id]
    assert f"Playbook not found: {missing_id}" in result.output

from uuid import UUID

import pytest
from typer.testing import CliRunner

from neural_engine import cli
from neural_engine.application.evolution_proposal_service import (
    EvolutionProposalChangesRequiredError,
    EvolutionProposalEvaluationPlaybookMismatchError,
    EvolutionProposalEvaluationRunNotFoundError,
    EvolutionProposalEvaluationsRequiredError,
    PlaybookEvaluationNotFoundError,
)
from neural_engine.application.evolution_proposal_service import (
    PlaybookNotFoundError as ProposalPlaybookNotFoundError,
)
from neural_engine.application.experience_service import ObservationNotFoundError
from neural_engine.application.knowledge_service import (
    ExperienceNotFoundError,
    KnowledgeEvidenceRequiredError,
)
from neural_engine.application.observation_service import AddObservationResult
from neural_engine.application.playbook_evaluation_service import (
    PlaybookEvaluationFindingsRequiredError,
    PlaybookRunNotFoundError,
)
from neural_engine.application.playbook_run_service import (
    PlaybookNotFoundError,
    PlaybookRunActionsRequiredError,
)
from neural_engine.application.playbook_service import (
    KnowledgeNotFoundError,
    PlaybookKnowledgeRequiredError,
    PlaybookStepsRequiredError,
)
from neural_engine.domain import (
    EvolutionProposal,
    EvolutionProposalStatus,
    Experience,
    ExperienceResult,
    Knowledge,
    KnowledgeConfidence,
    Observation,
    Playbook,
    PlaybookEffectiveness,
    PlaybookEvaluation,
    PlaybookRun,
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


class FakePlaybookRunService:
    def __init__(
        self,
        runs: list[PlaybookRun],
        missing_playbook_id: UUID | None = None,
    ) -> None:
        self.runs = runs
        self.missing_playbook_id = missing_playbook_id
        self.add_calls: list[
            tuple[
                UUID,
                str,
                list[str],
                str,
                bool,
                list[str] | None,
                str | None,
                list[str] | None,
            ]
        ] = []
        self.list_for_playbook_calls: list[UUID] = []
        self.requested_ids: list[UUID] = []

    def add(
        self,
        playbook_id: UUID,
        situation: str,
        actions_taken: list[str],
        outcome: str,
        success: bool,
        evidence: list[str] | None = None,
        notes: str | None = None,
        tags: list[str] | None = None,
    ) -> PlaybookRun:
        self.add_calls.append(
            (
                playbook_id,
                situation,
                actions_taken,
                outcome,
                success,
                evidence,
                notes,
                tags,
            )
        )

        if not actions_taken:
            raise PlaybookRunActionsRequiredError()

        if self.missing_playbook_id is not None:
            raise PlaybookNotFoundError(self.missing_playbook_id)

        run = PlaybookRun(
            playbook_id=playbook_id,
            situation=situation,
            actions_taken=actions_taken,
            outcome=outcome,
            success=success,
            evidence=evidence or [],
            notes=notes,
            tags=tags or [],
        )
        self.runs.append(run)

        return run

    def list_runs(self) -> list[PlaybookRun]:
        return self.runs

    def list_for_playbook(self, playbook_id: UUID) -> list[PlaybookRun]:
        self.list_for_playbook_calls.append(playbook_id)

        if self.missing_playbook_id is not None:
            raise PlaybookNotFoundError(self.missing_playbook_id)

        return [run for run in self.runs if run.playbook_id == playbook_id]

    def get_by_id(self, run_id: UUID) -> PlaybookRun | None:
        self.requested_ids.append(run_id)

        for run in self.runs:
            if run.id == run_id:
                return run

        return None


class FakePlaybookEvaluationService:
    def __init__(
        self,
        evaluations: list[PlaybookEvaluation],
        missing_run_id: UUID | None = None,
    ) -> None:
        self.evaluations = evaluations
        self.missing_run_id = missing_run_id
        self.add_calls: list[
            tuple[
                UUID,
                PlaybookEffectiveness,
                list[str],
                list[str] | None,
                list[str] | None,
                str | None,
                list[str] | None,
            ]
        ] = []
        self.requested_ids: list[UUID] = []
        self.list_for_run_calls: list[UUID] = []

    def add(
        self,
        run_id: UUID,
        effectiveness: PlaybookEffectiveness,
        findings: list[str],
        improvements: list[str] | None = None,
        evidence: list[str] | None = None,
        notes: str | None = None,
        tags: list[str] | None = None,
    ) -> PlaybookEvaluation:
        self.add_calls.append(
            (
                run_id,
                effectiveness,
                findings,
                improvements,
                evidence,
                notes,
                tags,
            )
        )

        if not findings:
            raise PlaybookEvaluationFindingsRequiredError()

        if self.missing_run_id is not None:
            raise PlaybookRunNotFoundError(self.missing_run_id)

        evaluation = PlaybookEvaluation(
            run_id=run_id,
            effectiveness=effectiveness,
            findings=findings,
            improvements=improvements or [],
            evidence=evidence or [],
            notes=notes,
            tags=tags or [],
        )
        self.evaluations.append(evaluation)

        return evaluation

    def list_evaluations(self) -> list[PlaybookEvaluation]:
        return self.evaluations

    def list_for_run(self, run_id: UUID) -> list[PlaybookEvaluation]:
        self.list_for_run_calls.append(run_id)

        if self.missing_run_id is not None:
            raise PlaybookRunNotFoundError(self.missing_run_id)

        return [evaluation for evaluation in self.evaluations if evaluation.run_id == run_id]

    def get_by_id(self, evaluation_id: UUID) -> PlaybookEvaluation | None:
        self.requested_ids.append(evaluation_id)

        for evaluation in self.evaluations:
            if evaluation.id == evaluation_id:
                return evaluation

        return None


class FakeEvolutionProposalService:
    def __init__(
        self,
        proposals: list[EvolutionProposal],
        missing_playbook_id: UUID | None = None,
        missing_evaluation_id: UUID | None = None,
        missing_run: tuple[UUID, UUID] | None = None,
        playbook_mismatch: tuple[UUID, UUID, UUID] | None = None,
    ) -> None:
        self.proposals = proposals
        self.missing_playbook_id = missing_playbook_id
        self.missing_evaluation_id = missing_evaluation_id
        self.missing_run = missing_run
        self.playbook_mismatch = playbook_mismatch
        self.add_calls: list[
            tuple[
                UUID,
                list[UUID],
                str,
                str,
                list[str],
                list[str],
                list[str] | None,
                EvolutionProposalStatus,
                str | None,
                list[str] | None,
            ]
        ] = []
        self.requested_ids: list[UUID] = []

    def add(
        self,
        playbook_id: UUID,
        evaluation_ids: list[UUID],
        summary: str,
        rationale: str,
        proposed_changes: list[str],
        expected_benefits: list[str],
        risks: list[str] | None = None,
        status: EvolutionProposalStatus = EvolutionProposalStatus.DRAFT,
        notes: str | None = None,
        tags: list[str] | None = None,
    ) -> EvolutionProposal:
        self.add_calls.append(
            (
                playbook_id,
                evaluation_ids,
                summary,
                rationale,
                proposed_changes,
                expected_benefits,
                risks,
                status,
                notes,
                tags,
            )
        )

        if not evaluation_ids:
            raise EvolutionProposalEvaluationsRequiredError()

        if not proposed_changes:
            raise EvolutionProposalChangesRequiredError()

        if self.missing_playbook_id is not None:
            raise ProposalPlaybookNotFoundError(self.missing_playbook_id)

        if self.missing_evaluation_id is not None:
            raise PlaybookEvaluationNotFoundError(self.missing_evaluation_id)

        if self.missing_run is not None:
            evaluation_id, run_id = self.missing_run
            raise EvolutionProposalEvaluationRunNotFoundError(evaluation_id, run_id)

        if self.playbook_mismatch is not None:
            evaluation_id, expected_playbook_id, actual_playbook_id = self.playbook_mismatch
            raise EvolutionProposalEvaluationPlaybookMismatchError(
                evaluation_id,
                expected_playbook_id,
                actual_playbook_id,
            )

        proposal = EvolutionProposal(
            playbook_id=playbook_id,
            evaluation_ids=evaluation_ids,
            summary=summary,
            rationale=rationale,
            proposed_changes=proposed_changes,
            expected_benefits=expected_benefits,
            risks=risks or [],
            status=status,
            notes=notes,
            tags=tags or [],
        )
        self.proposals.append(proposal)

        return proposal

    def list_proposals(self) -> list[EvolutionProposal]:
        return self.proposals

    def get_by_id(self, proposal_id: UUID) -> EvolutionProposal | None:
        self.requested_ids.append(proposal_id)

        for proposal in self.proposals:
            if proposal.id == proposal_id:
                return proposal

        return None


class FakeContainer:
    def __init__(
        self,
        observation_service: FakeObservationService | None = None,
        experience_service: FakeExperienceService | None = None,
        knowledge_service: FakeKnowledgeService | None = None,
        playbook_service: FakePlaybookService | None = None,
        playbook_run_service: FakePlaybookRunService | None = None,
        playbook_evaluation_service: FakePlaybookEvaluationService | None = None,
        evolution_proposal_service: FakeEvolutionProposalService | None = None,
    ) -> None:
        self._observation_service = observation_service
        self._experience_service = experience_service
        self._knowledge_service = knowledge_service
        self._playbook_service = playbook_service
        self._playbook_run_service = playbook_run_service
        self._playbook_evaluation_service = playbook_evaluation_service
        self._evolution_proposal_service = evolution_proposal_service

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

    def playbook_run_service(self) -> FakePlaybookRunService:
        if self._playbook_run_service is None:
            raise AssertionError("Playbook run service was not expected")

        return self._playbook_run_service

    def playbook_evaluation_service(self) -> FakePlaybookEvaluationService:
        if self._playbook_evaluation_service is None:
            raise AssertionError("Playbook evaluation service was not expected")

        return self._playbook_evaluation_service

    def evolution_proposal_service(self) -> FakeEvolutionProposalService:
        if self._evolution_proposal_service is None:
            raise AssertionError("Evolution proposal service was not expected")

        return self._evolution_proposal_service


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


def test_playbook_runs_delegates_positional_uuid_and_displays_linked_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playbook_id = UUID("45454545-4545-4545-4545-454545454545")
    run = PlaybookRun(
        playbook_id=playbook_id,
        situation="Linked playbook run",
        actions_taken=["Applied playbook manually"],
        outcome="Run outcome recorded",
        success=True,
    )
    service = FakePlaybookRunService([run])
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_run_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["playbook", "runs", str(playbook_id)])

    assert result.exit_code == 0
    assert service.list_for_playbook_calls == [playbook_id]
    assert f"ID: {run.id}" in result.output
    assert f"Timestamp: {run.timestamp}" in result.output
    assert "Situation: Linked playbook run" in result.output
    assert "Success: true" in result.output


def test_playbook_runs_empty_state_returns_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playbook_id = UUID("56565656-5656-5656-5656-565656565656")
    service = FakePlaybookRunService([])
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_run_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["playbook", "runs", str(playbook_id)])

    assert result.exit_code == 0
    assert service.list_for_playbook_calls == [playbook_id]
    assert f"No playbook runs linked to playbook: {playbook_id}" in result.output


def test_playbook_runs_missing_playbook_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_id = UUID("67676767-6767-6767-6767-676767676767")
    service = FakePlaybookRunService([], missing_playbook_id=missing_id)
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_run_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["playbook", "runs", str(missing_id)])

    assert result.exit_code == 1
    assert service.list_for_playbook_calls == [missing_id]
    assert f"Playbook not found: {missing_id}" in result.output


def test_run_add_delegates_with_parsed_values_and_prints_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playbook_id = UUID("45454545-4545-4545-4545-454545454545")
    service = FakePlaybookRunService([])
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_run_service=service))
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "run",
            "add",
            "--playbook-id",
            str(playbook_id),
            "--situation",
            "Production incident repeated",
            "--action",
            "Applied the playbook manually",
            "--action",
            "Collected follow-up evidence",
            "--outcome",
            "Service recovered",
            "--success",
            "true",
            "--evidence",
            "Incident log",
            "--evidence",
            "Recovery metric",
            "--notes",
            "Manual run recorded after incident",
            "--tag",
            "ops",
            "--tag",
            "manual",
        ],
    )

    assert result.exit_code == 0
    assert service.add_calls == [
        (
            playbook_id,
            "Production incident repeated",
            ["Applied the playbook manually", "Collected follow-up evidence"],
            "Service recovered",
            True,
            ["Incident log", "Recovery metric"],
            "Manual run recorded after incident",
            ["ops", "manual"],
        )
    ]
    assert "Playbook run stored." in result.output
    assert str(service.runs[0].id) in result.output


def test_run_add_parses_success_false(monkeypatch: pytest.MonkeyPatch) -> None:
    playbook_id = UUID("56565656-5656-5656-5656-565656565656")
    service = FakePlaybookRunService([])
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_run_service=service))
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "run",
            "add",
            "--playbook-id",
            str(playbook_id),
            "--situation",
            "Manual application did not work",
            "--action",
            "Tried the documented procedure",
            "--outcome",
            "Issue remained unresolved",
            "--success",
            "false",
        ],
    )

    assert result.exit_code == 0
    assert service.add_calls[0][4] is False


def test_run_add_handles_empty_actions_without_storing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playbook_id = UUID("67676767-6767-6767-6767-676767676767")
    service = FakePlaybookRunService([])
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_run_service=service))
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "run",
            "add",
            "--playbook-id",
            str(playbook_id),
            "--situation",
            "No action was supplied",
            "--outcome",
            "Run rejected",
            "--success",
            "false",
        ],
    )

    assert result.exit_code == 1
    assert service.add_calls == [
        (
            playbook_id,
            "No action was supplied",
            [],
            "Run rejected",
            False,
            None,
            None,
            None,
        )
    ]
    assert service.runs == []
    assert "Playbook run requires at least one action taken." in result.output


def test_run_add_handles_missing_playbook_without_storing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_id = UUID("78787878-7878-7878-7878-787878787878")
    service = FakePlaybookRunService([], missing_playbook_id=missing_id)
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_run_service=service))
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "run",
            "add",
            "--playbook-id",
            str(missing_id),
            "--situation",
            "Missing playbook",
            "--action",
            "Tried to record the run",
            "--outcome",
            "Run rejected",
            "--success",
            "false",
        ],
    )

    assert result.exit_code == 1
    assert len(service.add_calls) == 1
    assert service.runs == []
    assert f"Playbook not found: {missing_id}" in result.output


def test_run_list_displays_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    playbook_id = UUID("89898989-8989-8989-8989-898989898989")
    run = PlaybookRun(
        playbook_id=playbook_id,
        situation="Listed run",
        actions_taken=["Applied playbook"],
        outcome="Outcome recorded",
        success=True,
    )
    service = FakePlaybookRunService([run])
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_run_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["run", "list"])

    assert result.exit_code == 0
    assert f"ID: {run.id}" in result.output
    assert f"Timestamp: {run.timestamp}" in result.output
    assert f"Playbook ID: {playbook_id}" in result.output
    assert "Situation: Listed run" in result.output
    assert "Success: true" in result.output


def test_run_list_handles_empty_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    service = FakePlaybookRunService([])
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_run_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["run", "list"])

    assert result.exit_code == 0
    assert "No playbook runs found." in result.output


def test_run_show_delegates_and_displays_all_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playbook_id = UUID("90909090-9090-9090-9090-909090909090")
    run = PlaybookRun(
        playbook_id=playbook_id,
        situation="Shown run",
        actions_taken=["Applied first step", "Recorded result"],
        outcome="The procedure worked",
        success=True,
        evidence=["Log entry", "Metric improved"],
        notes="No automation was involved",
        tags=["manual", "ops"],
    )
    service = FakePlaybookRunService([run])
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_run_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["run", "show", str(run.id)])

    assert result.exit_code == 0
    assert service.requested_ids == [run.id]
    assert f"ID: {run.id}" in result.output
    assert f"Timestamp: {run.timestamp}" in result.output
    assert f"Playbook ID: {playbook_id}" in result.output
    assert "Situation: Shown run" in result.output
    assert "Actions taken:" in result.output
    assert "- Applied first step" in result.output
    assert "- Recorded result" in result.output
    assert "Outcome: The procedure worked" in result.output
    assert "Success: true" in result.output
    assert "Evidence:" in result.output
    assert "- Log entry" in result.output
    assert "- Metric improved" in result.output
    assert "Notes: No automation was involved" in result.output
    assert "Tags: manual, ops" in result.output


def test_run_show_displays_false_and_empty_optional_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = PlaybookRun(
        playbook_id=UUID("abababab-abab-abab-abab-abababababab"),
        situation="Unsuccessful run",
        actions_taken=["Applied playbook manually"],
        outcome="The problem remained",
        success=False,
    )
    service = FakePlaybookRunService([run])
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_run_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["run", "show", str(run.id)])

    assert result.exit_code == 0
    assert "Success: false" in result.output
    assert "Evidence:\n-" in result.output
    assert "Notes: -" in result.output
    assert "Tags: -" in result.output


def test_run_show_handles_missing_run(monkeypatch: pytest.MonkeyPatch) -> None:
    missing_id = UUID("cdcdcdcd-cdcd-cdcd-cdcd-cdcdcdcdcdcd")
    service = FakePlaybookRunService([])
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_run_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["run", "show", str(missing_id)])

    assert result.exit_code == 1
    assert service.requested_ids == [missing_id]
    assert f"Playbook run not found: {missing_id}" in result.output


def test_run_evaluations_delegates_positional_uuid_and_displays_linked_evaluations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = UUID("11111111-2222-3333-4444-555555555555")
    evaluation = PlaybookEvaluation(
        run_id=run_id,
        effectiveness=PlaybookEffectiveness.EFFECTIVE,
        findings=["The run was effective"],
    )
    service = FakePlaybookEvaluationService([evaluation])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_evaluation_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(cli.app, ["run", "evaluations", str(run_id)])

    assert result.exit_code == 0
    assert service.list_for_run_calls == [run_id]
    assert f"ID: {evaluation.id}" in result.output
    assert f"Timestamp: {evaluation.timestamp}" in result.output
    assert "Effectiveness: effective" in result.output


def test_run_evaluations_empty_state_returns_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = UUID("22222222-3333-4444-5555-666666666666")
    service = FakePlaybookEvaluationService([])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_evaluation_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(cli.app, ["run", "evaluations", str(run_id)])

    assert result.exit_code == 0
    assert service.list_for_run_calls == [run_id]
    assert f"No playbook evaluations linked to run: {run_id}" in result.output


def test_run_evaluations_missing_run_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_id = UUID("33333333-4444-5555-6666-777777777777")
    service = FakePlaybookEvaluationService([], missing_run_id=missing_id)
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_evaluation_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(cli.app, ["run", "evaluations", str(missing_id)])

    assert result.exit_code == 1
    assert service.list_for_run_calls == [missing_id]
    assert f"Playbook run not found: {missing_id}" in result.output


@pytest.mark.parametrize(
    ("effectiveness_value", "effectiveness"),
    [
        ("ineffective", PlaybookEffectiveness.INEFFECTIVE),
        ("partial", PlaybookEffectiveness.PARTIAL),
        ("effective", PlaybookEffectiveness.EFFECTIVE),
    ],
)
def test_evaluation_add_delegates_with_parsed_values_and_prints_id(
    effectiveness_value: str,
    effectiveness: PlaybookEffectiveness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = UUID("11111111-2222-3333-4444-555555555555")
    service = FakePlaybookEvaluationService([])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_evaluation_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "evaluation",
            "add",
            "--run-id",
            str(run_id),
            "--effectiveness",
            effectiveness_value,
            "--finding",
            "The playbook isolated the issue",
            "--finding",
            "The rollback step was unclear",
            "--improvement",
            "Clarify rollback criteria",
            "--improvement",
            "Add verification evidence",
            "--evidence",
            "Incident log",
            "--evidence",
            "Reviewer note",
            "--notes",
            "Manual assessment",
            "--tag",
            "ops",
            "--tag",
            "review",
        ],
    )

    assert result.exit_code == 0
    assert service.add_calls == [
        (
            run_id,
            effectiveness,
            ["The playbook isolated the issue", "The rollback step was unclear"],
            ["Clarify rollback criteria", "Add verification evidence"],
            ["Incident log", "Reviewer note"],
            "Manual assessment",
            ["ops", "review"],
        )
    ]
    assert "Playbook evaluation stored." in result.output
    assert str(service.evaluations[0].id) in result.output


def test_evaluation_add_omitted_findings_returns_error_without_storing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = UUID("22222222-3333-4444-5555-666666666666")
    service = FakePlaybookEvaluationService([])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_evaluation_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "evaluation",
            "add",
            "--run-id",
            str(run_id),
            "--effectiveness",
            "ineffective",
        ],
    )

    assert result.exit_code == 1
    assert service.add_calls == [
        (
            run_id,
            PlaybookEffectiveness.INEFFECTIVE,
            [],
            None,
            None,
            None,
            None,
        )
    ]
    assert service.evaluations == []
    assert "Playbook evaluation requires at least one finding." in result.output


def test_evaluation_add_missing_run_returns_error_without_storing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_id = UUID("33333333-4444-5555-6666-777777777777")
    service = FakePlaybookEvaluationService([], missing_run_id=missing_id)
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_evaluation_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "evaluation",
            "add",
            "--run-id",
            str(missing_id),
            "--effectiveness",
            "partial",
            "--finding",
            "The run could not be assessed",
        ],
    )

    assert result.exit_code == 1
    assert len(service.add_calls) == 1
    assert service.evaluations == []
    assert f"Playbook run not found: {missing_id}" in result.output


def test_evaluation_list_displays_evaluation_summaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = UUID("44444444-5555-6666-7777-888888888888")
    evaluation = PlaybookEvaluation(
        run_id=run_id,
        effectiveness=PlaybookEffectiveness.EFFECTIVE,
        findings=["The playbook worked"],
    )
    service = FakePlaybookEvaluationService([evaluation])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_evaluation_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(cli.app, ["evaluation", "list"])

    assert result.exit_code == 0
    assert f"ID: {evaluation.id}" in result.output
    assert f"Timestamp: {evaluation.timestamp}" in result.output
    assert f"Run ID: {run_id}" in result.output
    assert "Effectiveness: effective" in result.output


def test_evaluation_list_handles_empty_repository(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakePlaybookEvaluationService([])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_evaluation_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(cli.app, ["evaluation", "list"])

    assert result.exit_code == 0
    assert "No playbook evaluations found." in result.output


def test_evaluation_show_delegates_and_displays_all_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = UUID("55555555-6666-7777-8888-999999999999")
    evaluation = PlaybookEvaluation(
        run_id=run_id,
        effectiveness=PlaybookEffectiveness.PARTIAL,
        findings=["The first step helped", "The second step was unclear"],
        improvements=["Clarify step two", "Add evidence guidance"],
        evidence=["Incident report", "Reviewer note"],
        notes="External assessment",
        tags=["ops", "manual"],
    )
    service = FakePlaybookEvaluationService([evaluation])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_evaluation_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(cli.app, ["evaluation", "show", str(evaluation.id)])

    assert result.exit_code == 0
    assert service.requested_ids == [evaluation.id]
    assert f"ID: {evaluation.id}" in result.output
    assert f"Timestamp: {evaluation.timestamp}" in result.output
    assert f"Run ID: {run_id}" in result.output
    assert "Effectiveness: partial" in result.output
    assert "Findings:" in result.output
    assert "- The first step helped" in result.output
    assert "- The second step was unclear" in result.output
    assert "Improvements:" in result.output
    assert "- Clarify step two" in result.output
    assert "- Add evidence guidance" in result.output
    assert "Evidence:" in result.output
    assert "- Incident report" in result.output
    assert "- Reviewer note" in result.output
    assert "Notes: External assessment" in result.output
    assert "Tags: ops, manual" in result.output


def test_evaluation_show_displays_empty_optional_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evaluation = PlaybookEvaluation(
        run_id=UUID("66666666-7777-8888-9999-aaaaaaaaaaaa"),
        effectiveness=PlaybookEffectiveness.INEFFECTIVE,
        findings=["The playbook did not help"],
    )
    service = FakePlaybookEvaluationService([evaluation])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_evaluation_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(cli.app, ["evaluation", "show", str(evaluation.id)])

    assert result.exit_code == 0
    assert "Effectiveness: ineffective" in result.output
    assert "Improvements:\n-" in result.output
    assert "Evidence:\n-" in result.output
    assert "Notes: -" in result.output
    assert "Tags: -" in result.output


def test_evaluation_show_handles_missing_evaluation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_id = UUID("77777777-8888-9999-aaaa-bbbbbbbbbbbb")
    service = FakePlaybookEvaluationService([])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_evaluation_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(cli.app, ["evaluation", "show", str(missing_id)])

    assert result.exit_code == 1
    assert service.requested_ids == [missing_id]
    assert f"Playbook evaluation not found: {missing_id}" in result.output


def test_proposal_add_delegates_with_parsed_values_and_prints_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playbook_id = UUID("88888888-9999-aaaa-bbbb-cccccccccccc")
    first_evaluation_id = UUID("99999999-aaaa-bbbb-cccc-dddddddddddd")
    second_evaluation_id = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    service = FakeEvolutionProposalService([])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(evolution_proposal_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "proposal",
            "add",
            "--playbook-id",
            str(playbook_id),
            "--evaluation-id",
            str(first_evaluation_id),
            "--evaluation-id",
            str(second_evaluation_id),
            "--summary",
            "Clarify rollback",
            "--rationale",
            "Evaluations found unclear recovery steps",
            "--change",
            "Add rollback criteria",
            "--change",
            "Add verification step",
            "--benefit",
            "Faster recovery",
            "--benefit",
            "Clearer evidence",
            "--risk",
            "Longer checklist",
            "--notes",
            "Manual proposal",
            "--tag",
            "ops",
            "--tag",
            "manual",
        ],
    )

    assert result.exit_code == 0
    assert service.add_calls == [
        (
            playbook_id,
            [first_evaluation_id, second_evaluation_id],
            "Clarify rollback",
            "Evaluations found unclear recovery steps",
            ["Add rollback criteria", "Add verification step"],
            ["Faster recovery", "Clearer evidence"],
            ["Longer checklist"],
            EvolutionProposalStatus.DRAFT,
            "Manual proposal",
            ["ops", "manual"],
        )
    ]
    assert "Evolution proposal stored." in result.output
    assert str(service.proposals[0].id) in result.output


@pytest.mark.parametrize(
    ("status_value", "status"),
    [
        ("draft", EvolutionProposalStatus.DRAFT),
        ("accepted", EvolutionProposalStatus.ACCEPTED),
        ("rejected", EvolutionProposalStatus.REJECTED),
    ],
)
def test_proposal_add_parses_status_values(
    status_value: str,
    status: EvolutionProposalStatus,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playbook_id = UUID("bbbbbbbb-cccc-dddd-eeee-ffffffffffff")
    evaluation_id = UUID("cccccccc-dddd-eeee-ffff-111111111111")
    service = FakeEvolutionProposalService([])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(evolution_proposal_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "proposal",
            "add",
            "--playbook-id",
            str(playbook_id),
            "--evaluation-id",
            str(evaluation_id),
            "--summary",
            "Status proposal",
            "--rationale",
            "Check status parsing",
            "--change",
            "Change",
            "--benefit",
            "Benefit",
            "--status",
            status_value,
        ],
    )

    assert result.exit_code == 0
    assert service.add_calls[0][7] == status


def test_proposal_add_omitted_evaluations_returns_error_without_storing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playbook_id = UUID("dddddddd-eeee-ffff-1111-222222222222")
    service = FakeEvolutionProposalService([])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(evolution_proposal_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "proposal",
            "add",
            "--playbook-id",
            str(playbook_id),
            "--summary",
            "No evaluations",
            "--rationale",
            "Reject missing evaluations",
            "--change",
            "Change",
            "--benefit",
            "Benefit",
        ],
    )

    assert result.exit_code == 1
    assert service.add_calls[0][1] == []
    assert service.proposals == []
    assert "Evolution proposal requires at least one evaluation ID." in result.output


def test_proposal_add_omitted_changes_returns_error_without_storing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playbook_id = UUID("eeeeeeee-ffff-1111-2222-333333333333")
    evaluation_id = UUID("ffffffff-1111-2222-3333-444444444444")
    service = FakeEvolutionProposalService([])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(evolution_proposal_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "proposal",
            "add",
            "--playbook-id",
            str(playbook_id),
            "--evaluation-id",
            str(evaluation_id),
            "--summary",
            "No changes",
            "--rationale",
            "Reject missing changes",
            "--benefit",
            "Benefit",
        ],
    )

    assert result.exit_code == 1
    assert service.add_calls[0][4] == []
    assert service.proposals == []
    assert "Evolution proposal requires at least one proposed change." in result.output


def test_proposal_add_missing_playbook_returns_error_without_storing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_id = UUID("11111111-2222-3333-4444-555555555555")
    evaluation_id = UUID("22222222-3333-4444-5555-666666666666")
    service = FakeEvolutionProposalService([], missing_playbook_id=missing_id)
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(evolution_proposal_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "proposal",
            "add",
            "--playbook-id",
            str(missing_id),
            "--evaluation-id",
            str(evaluation_id),
            "--summary",
            "Missing playbook",
            "--rationale",
            "Reject missing playbook",
            "--change",
            "Change",
            "--benefit",
            "Benefit",
        ],
    )

    assert result.exit_code == 1
    assert service.proposals == []
    assert f"Playbook not found: {missing_id}" in result.output


def test_proposal_add_missing_evaluation_returns_error_without_storing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playbook_id = UUID("33333333-4444-5555-6666-777777777777")
    missing_id = UUID("44444444-5555-6666-7777-888888888888")
    service = FakeEvolutionProposalService([], missing_evaluation_id=missing_id)
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(evolution_proposal_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "proposal",
            "add",
            "--playbook-id",
            str(playbook_id),
            "--evaluation-id",
            str(missing_id),
            "--summary",
            "Missing evaluation",
            "--rationale",
            "Reject missing evaluation",
            "--change",
            "Change",
            "--benefit",
            "Benefit",
        ],
    )

    assert result.exit_code == 1
    assert service.proposals == []
    assert f"Playbook evaluation not found: {missing_id}" in result.output


def test_proposal_add_missing_run_returns_error_without_storing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playbook_id = UUID("55555555-6666-7777-8888-999999999999")
    evaluation_id = UUID("66666666-7777-8888-9999-aaaaaaaaaaaa")
    run_id = UUID("77777777-8888-9999-aaaa-bbbbbbbbbbbb")
    service = FakeEvolutionProposalService([], missing_run=(evaluation_id, run_id))
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(evolution_proposal_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "proposal",
            "add",
            "--playbook-id",
            str(playbook_id),
            "--evaluation-id",
            str(evaluation_id),
            "--summary",
            "Missing run",
            "--rationale",
            "Reject missing run",
            "--change",
            "Change",
            "--benefit",
            "Benefit",
        ],
    )

    assert result.exit_code == 1
    assert service.proposals == []
    assert str(evaluation_id) in result.output
    assert str(run_id) in result.output


def test_proposal_add_playbook_mismatch_returns_error_without_storing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evaluation_id = UUID("88888888-9999-aaaa-bbbb-cccccccccccc")
    expected_id = UUID("99999999-aaaa-bbbb-cccc-dddddddddddd")
    actual_id = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    service = FakeEvolutionProposalService(
        [],
        playbook_mismatch=(evaluation_id, expected_id, actual_id),
    )
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(evolution_proposal_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "proposal",
            "add",
            "--playbook-id",
            str(expected_id),
            "--evaluation-id",
            str(evaluation_id),
            "--summary",
            "Mismatch",
            "--rationale",
            "Reject mismatch",
            "--change",
            "Change",
            "--benefit",
            "Benefit",
        ],
    )

    assert result.exit_code == 1
    assert service.proposals == []
    assert str(evaluation_id) in result.output
    assert str(expected_id) in result.output
    assert str(actual_id) in result.output


def test_proposal_list_displays_proposal_summaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playbook_id = UUID("bbbbbbbb-cccc-dddd-eeee-ffffffffffff")
    proposal = EvolutionProposal(
        playbook_id=playbook_id,
        evaluation_ids=[UUID("cccccccc-dddd-eeee-ffff-111111111111")],
        summary="Listed proposal",
        rationale="List all proposals",
        proposed_changes=["Change"],
        expected_benefits=["Benefit"],
        status=EvolutionProposalStatus.ACCEPTED,
    )
    service = FakeEvolutionProposalService([proposal])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(evolution_proposal_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(cli.app, ["proposal", "list"])

    assert result.exit_code == 0
    assert f"ID: {proposal.id}" in result.output
    assert f"Timestamp: {proposal.timestamp}" in result.output
    assert f"Playbook ID: {playbook_id}" in result.output
    assert "Summary: Listed proposal" in result.output
    assert "Status: accepted" in result.output


def test_proposal_list_handles_empty_repository(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakeEvolutionProposalService([])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(evolution_proposal_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(cli.app, ["proposal", "list"])

    assert result.exit_code == 0
    assert "No evolution proposals found." in result.output


def test_proposal_show_delegates_and_displays_all_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playbook_id = UUID("dddddddd-eeee-ffff-1111-222222222222")
    first_evaluation_id = UUID("eeeeeeee-ffff-1111-2222-333333333333")
    second_evaluation_id = UUID("ffffffff-1111-2222-3333-444444444444")
    proposal = EvolutionProposal(
        playbook_id=playbook_id,
        evaluation_ids=[first_evaluation_id, second_evaluation_id],
        summary="Shown proposal",
        rationale="Show all fields",
        proposed_changes=["Clarify step", "Add verification"],
        expected_benefits=["Faster recovery", "Better audit trail"],
        risks=["Longer checklist", "More manual work"],
        status=EvolutionProposalStatus.REJECTED,
        notes="Manual review rejected this",
        tags=["ops", "review"],
    )
    service = FakeEvolutionProposalService([proposal])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(evolution_proposal_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(cli.app, ["proposal", "show", str(proposal.id)])

    assert result.exit_code == 0
    assert service.requested_ids == [proposal.id]
    assert f"ID: {proposal.id}" in result.output
    assert f"Timestamp: {proposal.timestamp}" in result.output
    assert f"Playbook ID: {playbook_id}" in result.output
    assert "Evaluation IDs:" in result.output
    assert f"- {first_evaluation_id}" in result.output
    assert f"- {second_evaluation_id}" in result.output
    assert "Summary: Shown proposal" in result.output
    assert "Rationale: Show all fields" in result.output
    assert "Proposed changes:" in result.output
    assert "- Clarify step" in result.output
    assert "- Add verification" in result.output
    assert "Expected benefits:" in result.output
    assert "- Faster recovery" in result.output
    assert "- Better audit trail" in result.output
    assert "Risks:" in result.output
    assert "- Longer checklist" in result.output
    assert "- More manual work" in result.output
    assert "Status: rejected" in result.output
    assert "Notes: Manual review rejected this" in result.output
    assert "Tags: ops, review" in result.output


def test_proposal_show_displays_empty_optional_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal = EvolutionProposal(
        playbook_id=UUID("11111111-2222-3333-4444-555555555555"),
        evaluation_ids=[UUID("22222222-3333-4444-5555-666666666666")],
        summary="No optional fields",
        rationale="Render empty optional values",
        proposed_changes=["Change"],
        expected_benefits=["Benefit"],
    )
    service = FakeEvolutionProposalService([proposal])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(evolution_proposal_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(cli.app, ["proposal", "show", str(proposal.id)])

    assert result.exit_code == 0
    assert "Status: draft" in result.output
    assert "Risks:\n-" in result.output
    assert "Notes: -" in result.output
    assert "Tags: -" in result.output


def test_proposal_show_handles_missing_proposal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_id = UUID("33333333-4444-5555-6666-777777777777")
    service = FakeEvolutionProposalService([])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(evolution_proposal_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(cli.app, ["proposal", "show", str(missing_id)])

    assert result.exit_code == 1
    assert service.requested_ids == [missing_id]
    assert f"Evolution proposal not found: {missing_id}" in result.output


def test_proposal_add_omitted_benefit_returns_usage_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playbook_id = UUID("aaaaaaaa-1111-2222-3333-444444444444")
    evaluation_id = UUID("bbbbbbbb-1111-2222-3333-444444444444")
    service = FakeEvolutionProposalService([])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(evolution_proposal_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "proposal",
            "add",
            "--playbook-id",
            str(playbook_id),
            "--evaluation-id",
            str(evaluation_id),
            "--summary",
            "No benefit",
            "--rationale",
            "Reject omitted benefit",
            "--change",
            "Change",
        ],
    )

    assert result.exit_code == 2
    assert "Error" in result.output
    assert service.add_calls == []


def test_proposal_add_one_benefit_is_delegated_correctly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playbook_id = UUID("cccccccc-2222-3333-4444-555555555555")
    evaluation_id = UUID("dddddddd-2222-3333-4444-555555555555")
    service = FakeEvolutionProposalService([])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(evolution_proposal_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "proposal",
            "add",
            "--playbook-id",
            str(playbook_id),
            "--evaluation-id",
            str(evaluation_id),
            "--summary",
            "One benefit",
            "--rationale",
            "Check single benefit",
            "--change",
            "Change",
            "--benefit",
            "Reduce downtime",
        ],
    )

    assert result.exit_code == 0
    assert service.add_calls[0][5] == ["Reduce downtime"]


def test_proposal_add_multiple_benefits_in_supplied_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playbook_id = UUID("eeeeeeee-3333-4444-5555-666666666666")
    evaluation_id = UUID("ffffffff-3333-4444-5555-666666666666")
    service = FakeEvolutionProposalService([])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(evolution_proposal_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "proposal",
            "add",
            "--playbook-id",
            str(playbook_id),
            "--evaluation-id",
            str(evaluation_id),
            "--summary",
            "Multiple benefits",
            "--rationale",
            "Check benefit order",
            "--change",
            "Change",
            "--benefit",
            "Faster recovery",
            "--benefit",
            "Clearer audit trail",
            "--benefit",
            "Less manual work",
        ],
    )

    assert result.exit_code == 0
    assert service.add_calls[0][5] == [
        "Faster recovery",
        "Clearer audit trail",
        "Less manual work",
    ]

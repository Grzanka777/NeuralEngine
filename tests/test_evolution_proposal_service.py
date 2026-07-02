from uuid import UUID

import pytest

from neural_engine.application.evolution_proposal_service import (
    EvolutionProposalChangesRequiredError,
    EvolutionProposalEvaluationPlaybookMismatchError,
    EvolutionProposalEvaluationRunNotFoundError,
    EvolutionProposalEvaluationsRequiredError,
    EvolutionProposalService,
    PlaybookEvaluationNotFoundError,
    PlaybookNotFoundError,
)
from neural_engine.domain import (
    EvolutionProposal,
    EvolutionProposalStatus,
    Playbook,
    PlaybookEffectiveness,
    PlaybookEvaluation,
    PlaybookRun,
)
from neural_engine.ports.evolution_proposal_repository import (
    EvolutionProposalRepository,
)
from neural_engine.ports.playbook_evaluation_repository import (
    PlaybookEvaluationRepository,
)
from neural_engine.ports.playbook_repository import PlaybookRepository
from neural_engine.ports.playbook_run_repository import PlaybookRunRepository


class FakePlaybookRepository(PlaybookRepository):
    def __init__(self, playbooks: list[Playbook] | None = None) -> None:
        self.saved: list[Playbook] = playbooks or []
        self.requested_ids: list[UUID] = []

    def save(self, playbook: Playbook) -> None:
        self.saved.append(playbook)

    def load_all(self) -> list[Playbook]:
        return self.saved

    def get_by_id(self, playbook_id: UUID) -> Playbook | None:
        self.requested_ids.append(playbook_id)

        for playbook in self.saved:
            if playbook.id == playbook_id:
                return playbook

        return None


class FakePlaybookEvaluationRepository(PlaybookEvaluationRepository):
    def __init__(self, evaluations: list[PlaybookEvaluation] | None = None) -> None:
        self.saved: list[PlaybookEvaluation] = evaluations or []
        self.requested_ids: list[UUID] = []

    def save(self, evaluation: PlaybookEvaluation) -> None:
        self.saved.append(evaluation)

    def load_all(self) -> list[PlaybookEvaluation]:
        return self.saved

    def get_by_id(self, evaluation_id: UUID) -> PlaybookEvaluation | None:
        self.requested_ids.append(evaluation_id)

        for evaluation in self.saved:
            if evaluation.id == evaluation_id:
                return evaluation

        return None


class FakePlaybookRunRepository(PlaybookRunRepository):
    def __init__(self, runs: list[PlaybookRun] | None = None) -> None:
        self.saved: list[PlaybookRun] = runs or []
        self.requested_ids: list[UUID] = []

    def save(self, run: PlaybookRun) -> None:
        self.saved.append(run)

    def load_all(self) -> list[PlaybookRun]:
        return self.saved

    def get_by_id(self, run_id: UUID) -> PlaybookRun | None:
        self.requested_ids.append(run_id)

        for run in self.saved:
            if run.id == run_id:
                return run

        return None


class FakeEvolutionProposalRepository(EvolutionProposalRepository):
    def __init__(
        self,
        playbook_repository: FakePlaybookRepository,
        evaluation_repository: FakePlaybookEvaluationRepository,
        run_repository: FakePlaybookRunRepository,
    ) -> None:
        self.saved: list[EvolutionProposal] = []
        self.load_all_calls = 0
        self.playbook_lookups_at_save: list[UUID] = []
        self.evaluation_lookups_at_save: list[UUID] = []
        self.run_lookups_at_save: list[UUID] = []
        self._playbook_repository = playbook_repository
        self._evaluation_repository = evaluation_repository
        self._run_repository = run_repository

    def save(self, proposal: EvolutionProposal) -> None:
        self.playbook_lookups_at_save = list(self._playbook_repository.requested_ids)
        self.evaluation_lookups_at_save = list(self._evaluation_repository.requested_ids)
        self.run_lookups_at_save = list(self._run_repository.requested_ids)
        self.saved.append(proposal)

    def load_all(self) -> list[EvolutionProposal]:
        self.load_all_calls += 1
        return self.saved

    def get_by_id(self, proposal_id: UUID) -> EvolutionProposal | None:
        for proposal in self.saved:
            if proposal.id == proposal_id:
                return proposal

        return None


def make_playbook() -> Playbook:
    return Playbook(
        title="Debug flaky tests",
        situation="A test fails intermittently",
        objective="Find the unstable dependency",
        steps=["Run the test repeatedly"],
        success_criteria=["Failure source is isolated"],
        knowledge_ids=[UUID("11111111-1111-1111-1111-111111111111")],
    )


def make_run(playbook_id: UUID) -> PlaybookRun:
    return PlaybookRun(
        playbook_id=playbook_id,
        situation="A playbook was applied manually",
        actions_taken=["Applied playbook"],
        outcome="Outcome recorded",
        success=True,
    )


def make_evaluation(run_id: UUID, finding: str = "Evaluation finding") -> PlaybookEvaluation:
    return PlaybookEvaluation(
        run_id=run_id,
        effectiveness=PlaybookEffectiveness.PARTIAL,
        findings=[finding],
    )


def make_proposal(playbook_id: UUID, summary: str = "Proposal") -> EvolutionProposal:
    return EvolutionProposal(
        playbook_id=playbook_id,
        evaluation_ids=[UUID("22222222-2222-2222-2222-222222222222")],
        summary=summary,
        rationale="Manual or external proposal",
        proposed_changes=["Change"],
        expected_benefits=["Benefit"],
    )


def make_service(
    playbooks: list[Playbook] | None = None,
    evaluations: list[PlaybookEvaluation] | None = None,
    runs: list[PlaybookRun] | None = None,
) -> tuple[
    EvolutionProposalService,
    FakeEvolutionProposalRepository,
    FakePlaybookRepository,
    FakePlaybookEvaluationRepository,
    FakePlaybookRunRepository,
]:
    playbook_repo = FakePlaybookRepository(playbooks)
    evaluation_repo = FakePlaybookEvaluationRepository(evaluations)
    run_repo = FakePlaybookRunRepository(runs)
    proposal_repo = FakeEvolutionProposalRepository(playbook_repo, evaluation_repo, run_repo)
    service = EvolutionProposalService(
        proposal_repo,
        playbook_repo,
        evaluation_repo,
        run_repo,
    )

    return service, proposal_repo, playbook_repo, evaluation_repo, run_repo


def test_add_evolution_proposal_with_one_evaluation() -> None:
    playbook = make_playbook()
    run = make_run(playbook.id)
    evaluation = make_evaluation(run.id)
    service, proposal_repo, _, _, _ = make_service([playbook], [evaluation], [run])

    proposal = service.add(
        playbook_id=playbook.id,
        evaluation_ids=[evaluation.id],
        summary="Clarify verification",
        rationale="Evaluation found unclear verification",
        proposed_changes=["Add verification checklist"],
        expected_benefits=["More consistent manual application"],
    )

    assert proposal_repo.saved == [proposal]
    assert proposal.playbook_id == playbook.id
    assert proposal.evaluation_ids == [evaluation.id]


def test_add_evolution_proposal_with_multiple_evaluations() -> None:
    playbook = make_playbook()
    first_run = make_run(playbook.id)
    second_run = make_run(playbook.id)
    first = make_evaluation(first_run.id, "First evaluation")
    second = make_evaluation(second_run.id, "Second evaluation")
    service, proposal_repo, _, _, _ = make_service(
        [playbook],
        [first, second],
        [first_run, second_run],
    )

    proposal = service.add(
        playbook_id=playbook.id,
        evaluation_ids=[first.id, second.id],
        summary="Improve two steps",
        rationale="Both evaluations found issues",
        proposed_changes=["Clarify first step"],
        expected_benefits=["Less ambiguity"],
    )

    assert proposal_repo.saved == [proposal]
    assert proposal.evaluation_ids == [first.id, second.id]


def test_add_evolution_proposal_preserves_all_fields() -> None:
    playbook = make_playbook()
    run = make_run(playbook.id)
    evaluation = make_evaluation(run.id)
    service, _, _, _, _ = make_service([playbook], [evaluation], [run])

    proposal = service.add(
        playbook_id=playbook.id,
        evaluation_ids=[evaluation.id, evaluation.id],
        summary="Improve rollback",
        rationale="Manual evaluation identified a gap",
        proposed_changes=["Add rollback criteria", "Add verification step"],
        expected_benefits=["Faster recovery", "Clearer evidence"],
        risks=["Longer checklist"],
        status=EvolutionProposalStatus.ACCEPTED,
        notes="Supplied by external process",
        tags=["ops", "manual"],
    )

    assert proposal.playbook_id == playbook.id
    assert proposal.evaluation_ids == [evaluation.id, evaluation.id]
    assert proposal.summary == "Improve rollback"
    assert proposal.rationale == "Manual evaluation identified a gap"
    assert proposal.proposed_changes == ["Add rollback criteria", "Add verification step"]
    assert proposal.expected_benefits == ["Faster recovery", "Clearer evidence"]
    assert proposal.risks == ["Longer checklist"]
    assert proposal.status == EvolutionProposalStatus.ACCEPTED
    assert proposal.notes == "Supplied by external process"
    assert proposal.tags == ["ops", "manual"]


def test_add_evolution_proposal_raises_when_evaluations_are_empty() -> None:
    service, proposal_repo, playbook_repo, evaluation_repo, run_repo = make_service()

    with pytest.raises(EvolutionProposalEvaluationsRequiredError):
        service.add(
            playbook_id=UUID("22222222-2222-2222-2222-222222222222"),
            evaluation_ids=[],
            summary="No evaluations",
            rationale="Reject early",
            proposed_changes=["Change"],
            expected_benefits=["Benefit"],
        )

    assert playbook_repo.requested_ids == []
    assert evaluation_repo.requested_ids == []
    assert run_repo.requested_ids == []
    assert proposal_repo.saved == []


def test_add_evolution_proposal_raises_when_changes_are_empty() -> None:
    service, proposal_repo, playbook_repo, evaluation_repo, run_repo = make_service()

    with pytest.raises(EvolutionProposalChangesRequiredError):
        service.add(
            playbook_id=UUID("33333333-3333-3333-3333-333333333333"),
            evaluation_ids=[UUID("44444444-4444-4444-4444-444444444444")],
            summary="No changes",
            rationale="Reject early",
            proposed_changes=[],
            expected_benefits=["Benefit"],
        )

    assert playbook_repo.requested_ids == []
    assert evaluation_repo.requested_ids == []
    assert run_repo.requested_ids == []
    assert proposal_repo.saved == []


def test_add_evolution_proposal_raises_when_playbook_is_missing() -> None:
    evaluation_id = UUID("55555555-5555-5555-5555-555555555555")
    missing_id = UUID("66666666-6666-6666-6666-666666666666")
    service, proposal_repo, playbook_repo, evaluation_repo, run_repo = make_service()

    with pytest.raises(PlaybookNotFoundError) as error:
        service.add(
            playbook_id=missing_id,
            evaluation_ids=[evaluation_id],
            summary="Missing playbook",
            rationale="Reject missing playbook",
            proposed_changes=["Change"],
            expected_benefits=["Benefit"],
        )

    assert error.value.playbook_id == missing_id
    assert playbook_repo.requested_ids == [missing_id]
    assert evaluation_repo.requested_ids == []
    assert run_repo.requested_ids == []
    assert proposal_repo.saved == []


def test_add_evolution_proposal_raises_when_evaluation_is_missing() -> None:
    playbook = make_playbook()
    missing_id = UUID("77777777-7777-7777-7777-777777777777")
    service, proposal_repo, _, evaluation_repo, run_repo = make_service([playbook])

    with pytest.raises(PlaybookEvaluationNotFoundError) as error:
        service.add(
            playbook_id=playbook.id,
            evaluation_ids=[missing_id],
            summary="Missing evaluation",
            rationale="Reject missing evaluation",
            proposed_changes=["Change"],
            expected_benefits=["Benefit"],
        )

    assert error.value.evaluation_id == missing_id
    assert evaluation_repo.requested_ids == [missing_id]
    assert run_repo.requested_ids == []
    assert proposal_repo.saved == []


def test_add_evolution_proposal_stops_on_first_missing_evaluation() -> None:
    playbook = make_playbook()
    missing_id = UUID("88888888-8888-8888-8888-888888888888")
    later_id = UUID("99999999-9999-9999-9999-999999999999")
    service, proposal_repo, _, evaluation_repo, run_repo = make_service([playbook])

    with pytest.raises(PlaybookEvaluationNotFoundError):
        service.add(
            playbook_id=playbook.id,
            evaluation_ids=[missing_id, later_id],
            summary="Stop on missing",
            rationale="Reject first missing evaluation",
            proposed_changes=["Change"],
            expected_benefits=["Benefit"],
        )

    assert evaluation_repo.requested_ids == [missing_id]
    assert run_repo.requested_ids == []
    assert proposal_repo.saved == []


def test_add_evolution_proposal_raises_when_evaluation_belongs_to_other_playbook() -> None:
    playbook = make_playbook()
    other_playbook = make_playbook()
    run = make_run(other_playbook.id)
    evaluation = make_evaluation(run.id)
    service, proposal_repo, _, _, _ = make_service([playbook], [evaluation], [run])

    with pytest.raises(EvolutionProposalEvaluationPlaybookMismatchError) as error:
        service.add(
            playbook_id=playbook.id,
            evaluation_ids=[evaluation.id],
            summary="Mismatch",
            rationale="Evaluation belongs elsewhere",
            proposed_changes=["Change"],
            expected_benefits=["Benefit"],
        )

    assert error.value.evaluation_id == evaluation.id
    assert error.value.expected_playbook_id == playbook.id
    assert error.value.actual_playbook_id == other_playbook.id
    assert proposal_repo.saved == []


def test_add_evolution_proposal_stops_on_first_mismatch() -> None:
    playbook = make_playbook()
    other_playbook = make_playbook()
    mismatch_run = make_run(other_playbook.id)
    later_run = make_run(playbook.id)
    mismatch = make_evaluation(mismatch_run.id, "Mismatch")
    later = make_evaluation(later_run.id, "Later")
    service, proposal_repo, _, evaluation_repo, run_repo = make_service(
        [playbook],
        [mismatch, later],
        [mismatch_run, later_run],
    )

    with pytest.raises(EvolutionProposalEvaluationPlaybookMismatchError):
        service.add(
            playbook_id=playbook.id,
            evaluation_ids=[mismatch.id, later.id],
            summary="Stop on mismatch",
            rationale="Reject first mismatch",
            proposed_changes=["Change"],
            expected_benefits=["Benefit"],
        )

    assert evaluation_repo.requested_ids == [mismatch.id]
    assert run_repo.requested_ids == [mismatch_run.id]
    assert proposal_repo.saved == []


def test_add_evolution_proposal_raises_when_run_is_missing() -> None:
    playbook = make_playbook()
    missing_run_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    evaluation = make_evaluation(missing_run_id)
    service, proposal_repo, _, evaluation_repo, run_repo = make_service([playbook], [evaluation])

    with pytest.raises(EvolutionProposalEvaluationRunNotFoundError):
        service.add(
            playbook_id=playbook.id,
            evaluation_ids=[evaluation.id],
            summary="Missing run",
            rationale="Reject missing run",
            proposed_changes=["Change"],
            expected_benefits=["Benefit"],
        )

    assert evaluation_repo.requested_ids == [evaluation.id]
    assert run_repo.requested_ids == [missing_run_id]
    assert proposal_repo.saved == []


def test_add_evolution_proposal_missing_run_exposes_ids() -> None:
    playbook = make_playbook()
    missing_run_id = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    evaluation = make_evaluation(missing_run_id)
    service, _, _, _, _ = make_service([playbook], [evaluation])

    with pytest.raises(EvolutionProposalEvaluationRunNotFoundError) as error:
        service.add(
            playbook_id=playbook.id,
            evaluation_ids=[evaluation.id],
            summary="Missing run",
            rationale="Reject missing run",
            proposed_changes=["Change"],
            expected_benefits=["Benefit"],
        )

    assert error.value.evaluation_id == evaluation.id
    assert error.value.run_id == missing_run_id


def test_add_evolution_proposal_does_not_save_when_run_is_missing() -> None:
    playbook = make_playbook()
    missing_run_id = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
    evaluation = make_evaluation(missing_run_id)
    service, proposal_repo, _, _, _ = make_service([playbook], [evaluation])

    with pytest.raises(EvolutionProposalEvaluationRunNotFoundError):
        service.add(
            playbook_id=playbook.id,
            evaluation_ids=[evaluation.id],
            summary="Missing run",
            rationale="Reject missing run",
            proposed_changes=["Change"],
            expected_benefits=["Benefit"],
        )

    assert proposal_repo.saved == []


def test_add_evolution_proposal_stops_on_first_missing_run() -> None:
    playbook = make_playbook()
    first_run_id = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
    second_run = make_run(playbook.id)
    first = make_evaluation(first_run_id, "First")
    second = make_evaluation(second_run.id, "Second")
    service, proposal_repo, _, evaluation_repo, run_repo = make_service(
        [playbook], [first, second], [second_run]
    )

    with pytest.raises(EvolutionProposalEvaluationRunNotFoundError):
        service.add(
            playbook_id=playbook.id,
            evaluation_ids=[first.id, second.id],
            summary="Stop on missing run",
            rationale="Reject first missing run",
            proposed_changes=["Change"],
            expected_benefits=["Benefit"],
        )

    assert evaluation_repo.requested_ids == [first.id]
    assert run_repo.requested_ids == [first_run_id]
    assert proposal_repo.saved == []


def test_add_evolution_proposal_missing_run_does_not_query_later() -> None:
    playbook = make_playbook()
    first_run_id = UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
    second_run = make_run(playbook.id)
    first = make_evaluation(first_run_id, "First")
    second = make_evaluation(second_run.id, "Second")
    service, proposal_repo, _, evaluation_repo, run_repo = make_service(
        [playbook], [first, second], [second_run]
    )

    with pytest.raises(EvolutionProposalEvaluationRunNotFoundError):
        service.add(
            playbook_id=playbook.id,
            evaluation_ids=[first.id, second.id],
            summary="Stop on missing run",
            rationale="Reject first missing run",
            proposed_changes=["Change"],
            expected_benefits=["Benefit"],
        )

    assert evaluation_repo.requested_ids == [first.id]
    assert run_repo.requested_ids == [first_run_id]
    assert second_run.id not in run_repo.requested_ids


def test_add_evolution_proposal_performs_all_lookups_before_saving() -> None:
    playbook = make_playbook()
    run = make_run(playbook.id)
    evaluation = make_evaluation(run.id)
    service, proposal_repo, _, _, _ = make_service([playbook], [evaluation], [run])

    service.add(
        playbook_id=playbook.id,
        evaluation_ids=[evaluation.id],
        summary="Lookup order",
        rationale="Lookups must happen before save",
        proposed_changes=["Change"],
        expected_benefits=["Benefit"],
    )

    assert proposal_repo.playbook_lookups_at_save == [playbook.id]
    assert proposal_repo.evaluation_lookups_at_save == [evaluation.id]
    assert proposal_repo.run_lookups_at_save == [run.id]


def test_list_proposals_returns_repository_items() -> None:
    playbook = make_playbook()
    run = make_run(playbook.id)
    evaluation = make_evaluation(run.id)
    service, proposal_repo, _, _, _ = make_service([playbook], [evaluation], [run])
    proposal = service.add(
        playbook_id=playbook.id,
        evaluation_ids=[evaluation.id],
        summary="List proposals",
        rationale="Repository delegation",
        proposed_changes=["Change"],
        expected_benefits=["Benefit"],
    )

    assert service.list_proposals() == [proposal]
    assert proposal_repo.load_all_calls == 1


def test_list_for_playbook_returns_one_linked_proposal() -> None:
    playbook = make_playbook()
    linked = make_proposal(playbook.id, "Linked")
    service, proposal_repo, playbook_repo, _, _ = make_service([playbook])
    proposal_repo.saved = [linked]

    assert service.list_for_playbook(playbook.id) == [linked]
    assert playbook_repo.requested_ids == [playbook.id]
    assert proposal_repo.load_all_calls == 1


def test_list_for_playbook_returns_multiple_linked_proposals() -> None:
    playbook = make_playbook()
    first = make_proposal(playbook.id, "First")
    second = make_proposal(playbook.id, "Second")
    service, proposal_repo, _, _, _ = make_service([playbook])
    proposal_repo.saved = [first, second]

    assert service.list_for_playbook(playbook.id) == [first, second]


def test_list_for_playbook_excludes_unrelated_proposals() -> None:
    playbook = make_playbook()
    other_playbook = make_playbook()
    linked = make_proposal(playbook.id, "Linked")
    unrelated = make_proposal(other_playbook.id, "Unrelated")
    service, proposal_repo, _, _, _ = make_service([playbook])
    proposal_repo.saved = [unrelated, linked]

    assert service.list_for_playbook(playbook.id) == [linked]


def test_list_for_playbook_returns_empty_list_when_no_proposals_linked() -> None:
    playbook = make_playbook()
    service, proposal_repo, _, _, _ = make_service([playbook])

    assert service.list_for_playbook(playbook.id) == []
    assert proposal_repo.load_all_calls == 1


def test_list_for_playbook_raises_when_playbook_is_missing() -> None:
    missing_id = UUID("12345678-1234-1234-1234-123456789abc")
    service, proposal_repo, playbook_repo, _, _ = make_service()

    with pytest.raises(PlaybookNotFoundError) as error:
        service.list_for_playbook(missing_id)

    assert error.value.playbook_id == missing_id
    assert playbook_repo.requested_ids == [missing_id]
    assert proposal_repo.load_all_calls == 0


def test_list_for_playbook_looks_up_playbook_exactly_once() -> None:
    playbook = make_playbook()
    service, proposal_repo, playbook_repo, _, _ = make_service([playbook])
    proposal_repo.saved = [make_proposal(playbook.id)]

    service.list_for_playbook(playbook.id)

    assert playbook_repo.requested_ids == [playbook.id]


def test_get_by_id_returns_matching_proposal() -> None:
    playbook = make_playbook()
    run = make_run(playbook.id)
    evaluation = make_evaluation(run.id)
    service, _, _, _, _ = make_service([playbook], [evaluation], [run])
    expected = service.add(
        playbook_id=playbook.id,
        evaluation_ids=[evaluation.id],
        summary="Find proposal",
        rationale="Repository lookup",
        proposed_changes=["Change"],
        expected_benefits=["Benefit"],
    )

    assert service.get_by_id(expected.id) == expected


def test_get_by_id_returns_none_when_missing() -> None:
    service, _, _, _, _ = make_service()

    assert service.get_by_id(UUID("00000000-0000-0000-0000-000000000000")) is None

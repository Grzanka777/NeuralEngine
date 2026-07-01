from uuid import UUID

import pytest

from neural_engine.application.playbook_evaluation_service import (
    PlaybookEvaluationFindingsRequiredError,
    PlaybookEvaluationService,
    PlaybookRunNotFoundError,
)
from neural_engine.domain import PlaybookEffectiveness, PlaybookEvaluation, PlaybookRun
from neural_engine.ports.playbook_evaluation_repository import (
    PlaybookEvaluationRepository,
)
from neural_engine.ports.playbook_run_repository import PlaybookRunRepository


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


class FakePlaybookEvaluationRepository(PlaybookEvaluationRepository):
    def __init__(self, run_repository: FakePlaybookRunRepository) -> None:
        self.saved: list[PlaybookEvaluation] = []
        self.load_all_calls = 0
        self.lookup_order_at_save: list[UUID] = []
        self._run_repository = run_repository

    def save(self, evaluation: PlaybookEvaluation) -> None:
        self.lookup_order_at_save = list(self._run_repository.requested_ids)
        self.saved.append(evaluation)

    def load_all(self) -> list[PlaybookEvaluation]:
        self.load_all_calls += 1
        return self.saved

    def get_by_id(self, evaluation_id: UUID) -> PlaybookEvaluation | None:
        for evaluation in self.saved:
            if evaluation.id == evaluation_id:
                return evaluation

        return None


def make_run() -> PlaybookRun:
    return PlaybookRun(
        playbook_id=UUID("11111111-1111-1111-1111-111111111111"),
        situation="A playbook was applied manually",
        actions_taken=["Applied playbook"],
        outcome="Outcome recorded",
        success=True,
    )


def test_add_playbook_evaluation_for_existing_run() -> None:
    run = make_run()
    run_repo = FakePlaybookRunRepository([run])
    evaluation_repo = FakePlaybookEvaluationRepository(run_repo)
    service = PlaybookEvaluationService(evaluation_repo, run_repo)

    evaluation = service.add(
        run_id=run.id,
        effectiveness=PlaybookEffectiveness.EFFECTIVE,
        findings=["The playbook worked"],
    )

    assert evaluation_repo.saved == [evaluation]
    assert evaluation.run_id == run.id


def test_add_playbook_evaluation_preserves_all_fields() -> None:
    run = make_run()
    run_repo = FakePlaybookRunRepository([run])
    evaluation_repo = FakePlaybookEvaluationRepository(run_repo)
    service = PlaybookEvaluationService(evaluation_repo, run_repo)

    evaluation = service.add(
        run_id=run.id,
        effectiveness=PlaybookEffectiveness.PARTIAL,
        findings=["Step one worked", "Step two was unclear"],
        improvements=["Clarify step two", "Add rollback evidence"],
        evidence=["Incident report", "Reviewer note"],
        notes="Supplied by an external review system",
        tags=["manual", "review"],
    )

    assert evaluation.run_id == run.id
    assert evaluation.effectiveness == PlaybookEffectiveness.PARTIAL
    assert evaluation.findings == ["Step one worked", "Step two was unclear"]
    assert evaluation.improvements == ["Clarify step two", "Add rollback evidence"]
    assert evaluation.evidence == ["Incident report", "Reviewer note"]
    assert evaluation.notes == "Supplied by an external review system"
    assert evaluation.tags == ["manual", "review"]


def test_add_playbook_evaluation_raises_when_findings_are_empty() -> None:
    run = make_run()
    run_repo = FakePlaybookRunRepository([run])
    evaluation_repo = FakePlaybookEvaluationRepository(run_repo)
    service = PlaybookEvaluationService(evaluation_repo, run_repo)

    with pytest.raises(PlaybookEvaluationFindingsRequiredError):
        service.add(
            run_id=run.id,
            effectiveness=PlaybookEffectiveness.INEFFECTIVE,
            findings=[],
        )

    assert run_repo.requested_ids == []
    assert evaluation_repo.saved == []


def test_add_playbook_evaluation_raises_when_run_is_missing() -> None:
    missing_id = UUID("22222222-2222-2222-2222-222222222222")
    run_repo = FakePlaybookRunRepository()
    evaluation_repo = FakePlaybookEvaluationRepository(run_repo)
    service = PlaybookEvaluationService(evaluation_repo, run_repo)

    with pytest.raises(PlaybookRunNotFoundError) as error:
        service.add(
            run_id=missing_id,
            effectiveness=PlaybookEffectiveness.INEFFECTIVE,
            findings=["The run could not be assessed"],
        )

    assert error.value.run_id == missing_id
    assert run_repo.requested_ids == [missing_id]
    assert evaluation_repo.saved == []


def test_add_playbook_evaluation_looks_up_run_once_before_saving() -> None:
    run = make_run()
    run_repo = FakePlaybookRunRepository([run])
    evaluation_repo = FakePlaybookEvaluationRepository(run_repo)
    service = PlaybookEvaluationService(evaluation_repo, run_repo)

    service.add(
        run_id=run.id,
        effectiveness=PlaybookEffectiveness.EFFECTIVE,
        findings=["Run was effective"],
    )

    assert run_repo.requested_ids == [run.id]
    assert evaluation_repo.lookup_order_at_save == [run.id]


def test_list_evaluations_returns_repository_items() -> None:
    run = make_run()
    run_repo = FakePlaybookRunRepository([run])
    evaluation_repo = FakePlaybookEvaluationRepository(run_repo)
    service = PlaybookEvaluationService(evaluation_repo, run_repo)
    evaluation = service.add(
        run_id=run.id,
        effectiveness=PlaybookEffectiveness.EFFECTIVE,
        findings=["List evaluation"],
    )

    assert service.list_evaluations() == [evaluation]
    assert evaluation_repo.load_all_calls == 1


def test_get_by_id_returns_matching_evaluation() -> None:
    run = make_run()
    run_repo = FakePlaybookRunRepository([run])
    evaluation_repo = FakePlaybookEvaluationRepository(run_repo)
    service = PlaybookEvaluationService(evaluation_repo, run_repo)
    expected = service.add(
        run_id=run.id,
        effectiveness=PlaybookEffectiveness.PARTIAL,
        findings=["Find evaluation"],
    )

    assert service.get_by_id(expected.id) == expected


def test_get_by_id_returns_none_when_missing() -> None:
    run_repo = FakePlaybookRunRepository()
    evaluation_repo = FakePlaybookEvaluationRepository(run_repo)
    service = PlaybookEvaluationService(evaluation_repo, run_repo)

    assert service.get_by_id(UUID("00000000-0000-0000-0000-000000000000")) is None

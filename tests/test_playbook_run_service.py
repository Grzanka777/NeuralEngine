from uuid import UUID

import pytest

from neural_engine.application.playbook_run_service import (
    PlaybookNotFoundError,
    PlaybookRunActionsRequiredError,
    PlaybookRunService,
)
from neural_engine.domain import Playbook, PlaybookRun
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


class FakePlaybookRunRepository(PlaybookRunRepository):
    def __init__(self, playbook_repository: FakePlaybookRepository) -> None:
        self.saved: list[PlaybookRun] = []
        self.load_all_calls = 0
        self.lookup_order_at_save: list[UUID] = []
        self._playbook_repository = playbook_repository

    def save(self, run: PlaybookRun) -> None:
        self.lookup_order_at_save = list(self._playbook_repository.requested_ids)
        self.saved.append(run)

    def load_all(self) -> list[PlaybookRun]:
        self.load_all_calls += 1
        return self.saved

    def get_by_id(self, run_id: UUID) -> PlaybookRun | None:
        for run in self.saved:
            if run.id == run_id:
                return run

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


def test_add_playbook_run_for_existing_playbook() -> None:
    playbook = make_playbook()
    playbook_repo = FakePlaybookRepository([playbook])
    run_repo = FakePlaybookRunRepository(playbook_repo)
    service = PlaybookRunService(run_repo, playbook_repo)

    run = service.add(
        playbook_id=playbook.id,
        situation="CI showed a flaky test",
        actions_taken=["Applied the playbook manually"],
        outcome="The unstable dependency was isolated",
        success=True,
    )

    assert run_repo.saved == [run]
    assert run.playbook_id == playbook.id


def test_add_playbook_run_preserves_all_fields() -> None:
    playbook = make_playbook()
    playbook_repo = FakePlaybookRepository([playbook])
    run_repo = FakePlaybookRunRepository(playbook_repo)
    service = PlaybookRunService(run_repo, playbook_repo)

    run = service.add(
        playbook_id=playbook.id,
        situation="A deployment failed",
        actions_taken=["Checked logs", "Rolled back release"],
        outcome="Service recovered",
        success=True,
        evidence=["Log line 42", "Rollback completed"],
        notes="Follow-up issue created",
        tags=["deployment", "manual"],
    )

    assert run.playbook_id == playbook.id
    assert run.situation == "A deployment failed"
    assert run.actions_taken == ["Checked logs", "Rolled back release"]
    assert run.outcome == "Service recovered"
    assert run.success is True
    assert run.evidence == ["Log line 42", "Rollback completed"]
    assert run.notes == "Follow-up issue created"
    assert run.tags == ["deployment", "manual"]


def test_add_playbook_run_raises_when_actions_are_empty() -> None:
    playbook = make_playbook()
    playbook_repo = FakePlaybookRepository([playbook])
    run_repo = FakePlaybookRunRepository(playbook_repo)
    service = PlaybookRunService(run_repo, playbook_repo)

    with pytest.raises(PlaybookRunActionsRequiredError):
        service.add(
            playbook_id=playbook.id,
            situation="No action was recorded",
            actions_taken=[],
            outcome="No outcome",
            success=False,
        )

    assert playbook_repo.requested_ids == []
    assert run_repo.saved == []


def test_add_playbook_run_raises_when_playbook_is_missing() -> None:
    missing_id = UUID("22222222-2222-2222-2222-222222222222")
    playbook_repo = FakePlaybookRepository()
    run_repo = FakePlaybookRunRepository(playbook_repo)
    service = PlaybookRunService(run_repo, playbook_repo)

    with pytest.raises(PlaybookNotFoundError) as error:
        service.add(
            playbook_id=missing_id,
            situation="Unknown playbook",
            actions_taken=["Tried to apply it"],
            outcome="Run rejected",
            success=False,
        )

    assert error.value.playbook_id == missing_id
    assert playbook_repo.requested_ids == [missing_id]
    assert run_repo.saved == []


def test_add_playbook_run_looks_up_playbook_before_saving() -> None:
    playbook = make_playbook()
    playbook_repo = FakePlaybookRepository([playbook])
    run_repo = FakePlaybookRunRepository(playbook_repo)
    service = PlaybookRunService(run_repo, playbook_repo)

    service.add(
        playbook_id=playbook.id,
        situation="Lookup order matters",
        actions_taken=["Applied playbook"],
        outcome="Run saved",
        success=True,
    )

    assert run_repo.lookup_order_at_save == [playbook.id]


def test_list_runs_returns_repository_items() -> None:
    playbook = make_playbook()
    playbook_repo = FakePlaybookRepository([playbook])
    run_repo = FakePlaybookRunRepository(playbook_repo)
    service = PlaybookRunService(run_repo, playbook_repo)
    run = service.add(
        playbook_id=playbook.id,
        situation="List runs",
        actions_taken=["Applied playbook"],
        outcome="Run listed",
        success=True,
    )

    assert service.list_runs() == [run]
    assert run_repo.load_all_calls == 1


def test_get_by_id_returns_matching_run() -> None:
    playbook = make_playbook()
    playbook_repo = FakePlaybookRepository([playbook])
    run_repo = FakePlaybookRunRepository(playbook_repo)
    service = PlaybookRunService(run_repo, playbook_repo)
    expected = service.add(
        playbook_id=playbook.id,
        situation="Find run",
        actions_taken=["Applied playbook"],
        outcome="Run found",
        success=True,
    )

    assert service.get_by_id(expected.id) == expected


def test_get_by_id_returns_none_when_missing() -> None:
    playbook_repo = FakePlaybookRepository()
    run_repo = FakePlaybookRunRepository(playbook_repo)
    service = PlaybookRunService(run_repo, playbook_repo)

    assert service.get_by_id(UUID("00000000-0000-0000-0000-000000000000")) is None

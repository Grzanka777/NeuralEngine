from uuid import UUID

import pytest

from neural_engine.application.playbook_run_service import (
    PlaybookNotFoundError,
    PlaybookRevisionNotFoundError,
    PlaybookRunActionsRequiredError,
    PlaybookRunRevisionPlaybookMismatchError,
    PlaybookRunService,
)
from neural_engine.domain import Playbook, PlaybookRevision, PlaybookRun
from neural_engine.ports.playbook_repository import PlaybookRepository
from neural_engine.ports.playbook_revision_repository import PlaybookRevisionRepository
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


class FakePlaybookRevisionRepository(PlaybookRevisionRepository):
    def __init__(self, revisions: list[PlaybookRevision] | None = None) -> None:
        self.saved = revisions or []
        self.requested_ids: list[UUID] = []

    def save(self, revision: PlaybookRevision) -> None:
        self.saved.append(revision)

    def load_all(self) -> list[PlaybookRevision]:
        return self.saved

    def get_by_id(self, revision_id: UUID) -> PlaybookRevision | None:
        self.requested_ids.append(revision_id)
        return next((revision for revision in self.saved if revision.id == revision_id), None)


def make_playbook() -> Playbook:
    return Playbook(
        title="Debug flaky tests",
        situation="A test fails intermittently",
        objective="Find the unstable dependency",
        steps=["Run the test repeatedly"],
        success_criteria=["Failure source is isolated"],
        knowledge_ids=[UUID("11111111-1111-1111-1111-111111111111")],
    )


def make_revision(playbook_id: UUID) -> PlaybookRevision:
    return PlaybookRevision(
        playbook_id=playbook_id,
        proposal_id=UUID("22222222-2222-2222-2222-222222222222"),
        title="Revised playbook",
        situation="A revised situation",
        objective="Use exact revised content",
        steps=["Apply revised step"],
        success_criteria=["Revision outcome recorded"],
        knowledge_ids=[],
    )


def make_service(
    playbook_repo: FakePlaybookRepository,
    run_repo: FakePlaybookRunRepository,
    revisions: list[PlaybookRevision] | None = None,
) -> tuple[PlaybookRunService, FakePlaybookRevisionRepository]:
    revision_repo = FakePlaybookRevisionRepository(revisions)
    return PlaybookRunService(run_repo, playbook_repo, revision_repo), revision_repo


def test_add_playbook_run_for_existing_playbook() -> None:
    playbook = make_playbook()
    playbook_repo = FakePlaybookRepository([playbook])
    run_repo = FakePlaybookRunRepository(playbook_repo)
    service, _ = make_service(playbook_repo, run_repo)

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
    service, _ = make_service(playbook_repo, run_repo)

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
    service, _ = make_service(playbook_repo, run_repo)

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
    service, _ = make_service(playbook_repo, run_repo)

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
    service, _ = make_service(playbook_repo, run_repo)

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
    service, _ = make_service(playbook_repo, run_repo)
    run = service.add(
        playbook_id=playbook.id,
        situation="List runs",
        actions_taken=["Applied playbook"],
        outcome="Run listed",
        success=True,
    )

    assert service.list_runs() == [run]
    assert run_repo.load_all_calls == 1


def test_list_runs_for_playbook_returns_one_linked_run() -> None:
    playbook = make_playbook()
    playbook_repo = FakePlaybookRepository([playbook])
    run_repo = FakePlaybookRunRepository(playbook_repo)
    service, _ = make_service(playbook_repo, run_repo)
    run = service.add(
        playbook_id=playbook.id,
        situation="Linked run",
        actions_taken=["Applied playbook"],
        outcome="Run linked",
        success=True,
    )

    assert service.list_for_playbook(playbook.id) == [run]
    assert playbook_repo.requested_ids == [playbook.id, playbook.id]
    assert run_repo.load_all_calls == 1


def test_list_runs_for_playbook_returns_multiple_linked_runs() -> None:
    playbook = make_playbook()
    playbook_repo = FakePlaybookRepository([playbook])
    run_repo = FakePlaybookRunRepository(playbook_repo)
    service, _ = make_service(playbook_repo, run_repo)
    first = service.add(
        playbook_id=playbook.id,
        situation="First linked run",
        actions_taken=["Applied first"],
        outcome="First listed",
        success=True,
    )
    second = service.add(
        playbook_id=playbook.id,
        situation="Second linked run",
        actions_taken=["Applied second"],
        outcome="Second listed",
        success=False,
    )

    assert service.list_for_playbook(playbook.id) == [first, second]


def test_list_runs_for_playbook_excludes_unrelated_runs() -> None:
    playbook = make_playbook()
    other_playbook = make_playbook()
    playbook_repo = FakePlaybookRepository([playbook, other_playbook])
    run_repo = FakePlaybookRunRepository(playbook_repo)
    service, _ = make_service(playbook_repo, run_repo)
    linked = service.add(
        playbook_id=playbook.id,
        situation="Linked run",
        actions_taken=["Applied linked playbook"],
        outcome="Linked run listed",
        success=True,
    )
    service.add(
        playbook_id=other_playbook.id,
        situation="Unrelated run",
        actions_taken=["Applied other playbook"],
        outcome="Unrelated run excluded",
        success=True,
    )

    assert service.list_for_playbook(playbook.id) == [linked]


def test_list_runs_for_playbook_returns_empty_list_when_none_are_linked() -> None:
    playbook = make_playbook()
    other_playbook = make_playbook()
    playbook_repo = FakePlaybookRepository([playbook, other_playbook])
    run_repo = FakePlaybookRunRepository(playbook_repo)
    service, _ = make_service(playbook_repo, run_repo)
    service.add(
        playbook_id=other_playbook.id,
        situation="Unrelated run",
        actions_taken=["Applied other playbook"],
        outcome="No linked runs",
        success=True,
    )

    assert service.list_for_playbook(playbook.id) == []
    assert run_repo.load_all_calls == 1


def test_list_runs_for_playbook_raises_when_missing_without_loading_runs() -> None:
    missing_id = UUID("33333333-3333-3333-3333-333333333333")
    playbook_repo = FakePlaybookRepository()
    run_repo = FakePlaybookRunRepository(playbook_repo)
    service, _ = make_service(playbook_repo, run_repo)

    with pytest.raises(PlaybookNotFoundError) as error:
        service.list_for_playbook(missing_id)

    assert error.value.playbook_id == missing_id
    assert playbook_repo.requested_ids == [missing_id]
    assert run_repo.load_all_calls == 0


def test_list_runs_for_playbook_looks_up_playbook_once() -> None:
    playbook = make_playbook()
    playbook_repo = FakePlaybookRepository([playbook])
    run_repo = FakePlaybookRunRepository(playbook_repo)
    service, _ = make_service(playbook_repo, run_repo)

    service.list_for_playbook(playbook.id)

    assert playbook_repo.requested_ids == [playbook.id]


def test_get_by_id_returns_matching_run() -> None:
    playbook = make_playbook()
    playbook_repo = FakePlaybookRepository([playbook])
    run_repo = FakePlaybookRunRepository(playbook_repo)
    service, _ = make_service(playbook_repo, run_repo)
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
    service, _ = make_service(playbook_repo, run_repo)

    assert service.get_by_id(UUID("00000000-0000-0000-0000-000000000000")) is None


def test_add_preserves_explicit_same_playbook_revision() -> None:
    playbook = make_playbook()
    revision = make_revision(playbook.id)
    playbook_repo = FakePlaybookRepository([playbook])
    run_repo = FakePlaybookRunRepository(playbook_repo)
    service, revision_repo = make_service(playbook_repo, run_repo, [revision])

    run = service.add(
        playbook_id=playbook.id,
        revision_id=revision.id,
        situation="Exact revision was used",
        actions_taken=["Applied revised step"],
        outcome="Revision outcome",
        success=True,
    )

    assert run.revision_id == revision.id
    assert revision_repo.requested_ids == [revision.id]
    assert run_repo.saved == [run]


def test_add_without_revision_does_not_query_revisions() -> None:
    playbook = make_playbook()
    playbook_repo = FakePlaybookRepository([playbook])
    run_repo = FakePlaybookRunRepository(playbook_repo)
    service, revision_repo = make_service(playbook_repo, run_repo)

    run = service.add(
        playbook_id=playbook.id,
        situation="Base playbook was used",
        actions_taken=["Applied base step"],
        outcome="Base outcome",
        success=True,
    )

    assert run.revision_id is None
    assert revision_repo.requested_ids == []


def test_add_rejects_missing_revision_without_write() -> None:
    playbook = make_playbook()
    missing_id = UUID("99999999-9999-9999-9999-999999999999")
    playbook_repo = FakePlaybookRepository([playbook])
    run_repo = FakePlaybookRunRepository(playbook_repo)
    service, _ = make_service(playbook_repo, run_repo)

    with pytest.raises(PlaybookRevisionNotFoundError):
        service.add(
            playbook_id=playbook.id,
            revision_id=missing_id,
            situation="Missing revision",
            actions_taken=["Attempted record"],
            outcome="Rejected",
            success=False,
        )

    assert run_repo.saved == []


def test_add_rejects_cross_playbook_revision_without_write() -> None:
    playbook = make_playbook()
    other = make_playbook()
    revision = make_revision(other.id)
    playbook_repo = FakePlaybookRepository([playbook, other])
    run_repo = FakePlaybookRunRepository(playbook_repo)
    service, _ = make_service(playbook_repo, run_repo, [revision])

    with pytest.raises(PlaybookRunRevisionPlaybookMismatchError):
        service.add(
            playbook_id=playbook.id,
            revision_id=revision.id,
            situation="Wrong revision",
            actions_taken=["Attempted record"],
            outcome="Rejected",
            success=False,
        )

    assert run_repo.saved == []


def test_add_checks_playbook_before_supplied_revision() -> None:
    missing_playbook_id = UUID("88888888-8888-8888-8888-888888888888")
    revision = make_revision(missing_playbook_id)
    playbook_repo = FakePlaybookRepository()
    run_repo = FakePlaybookRunRepository(playbook_repo)
    service, revision_repo = make_service(playbook_repo, run_repo, [revision])

    with pytest.raises(PlaybookNotFoundError):
        service.add(
            playbook_id=missing_playbook_id,
            revision_id=revision.id,
            situation="Missing playbook",
            actions_taken=["Attempted record"],
            outcome="Rejected",
            success=False,
        )

    assert revision_repo.requested_ids == []
    assert run_repo.saved == []


def test_get_by_id_fails_closed_for_missing_persisted_revision() -> None:
    playbook = make_playbook()
    run = PlaybookRun(
        playbook_id=playbook.id,
        revision_id=UUID("99999999-9999-9999-9999-999999999999"),
        situation="Corrupt relation",
        actions_taken=["Recorded action"],
        outcome="Recorded outcome",
        success=False,
    )
    playbook_repo = FakePlaybookRepository([playbook])
    run_repo = FakePlaybookRunRepository(playbook_repo)
    run_repo.saved = [run]
    service, _ = make_service(playbook_repo, run_repo)

    with pytest.raises(PlaybookRevisionNotFoundError):
        service.get_by_id(run.id)


def test_get_by_id_fails_closed_for_cross_playbook_persisted_revision() -> None:
    playbook = make_playbook()
    other = make_playbook()
    revision = make_revision(other.id)
    run = PlaybookRun(
        playbook_id=playbook.id,
        revision_id=revision.id,
        situation="Corrupt ownership",
        actions_taken=["Recorded action"],
        outcome="Recorded outcome",
        success=False,
    )
    playbook_repo = FakePlaybookRepository([playbook, other])
    run_repo = FakePlaybookRunRepository(playbook_repo)
    run_repo.saved = [run]
    service, _ = make_service(playbook_repo, run_repo, [revision])

    with pytest.raises(PlaybookRunRevisionPlaybookMismatchError):
        service.get_by_id(run.id)


def test_complete_and_playbook_lists_validate_revision_linked_runs() -> None:
    playbook = make_playbook()
    revision = make_revision(playbook.id)
    linked = PlaybookRun(
        playbook_id=playbook.id,
        revision_id=revision.id,
        situation="Valid provenance",
        actions_taken=["Recorded action"],
        outcome="Recorded outcome",
        success=True,
    )
    legacy = linked.model_copy(
        update={
            "id": UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
            "revision_id": None,
        }
    )
    playbook_repo = FakePlaybookRepository([playbook])
    run_repo = FakePlaybookRunRepository(playbook_repo)
    run_repo.saved = [linked, legacy]
    service, revision_repo = make_service(playbook_repo, run_repo, [revision])

    assert service.list_runs() == [linked, legacy]
    assert service.list_for_playbook(playbook.id) == [linked, legacy]
    assert revision_repo.requested_ids == [revision.id, revision.id]


@pytest.mark.parametrize("method_name", ["list_runs", "list_for_playbook"])
def test_run_lists_fail_closed_for_corrupt_revision_provenance(method_name: str) -> None:
    playbook = make_playbook()
    run = PlaybookRun(
        playbook_id=playbook.id,
        revision_id=UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
        situation="Missing provenance target",
        actions_taken=["Recorded action"],
        outcome="Recorded outcome",
        success=False,
    )
    playbook_repo = FakePlaybookRepository([playbook])
    run_repo = FakePlaybookRunRepository(playbook_repo)
    run_repo.saved = [run]
    service, _ = make_service(playbook_repo, run_repo)

    with pytest.raises(PlaybookRevisionNotFoundError):
        if method_name == "list_runs":
            service.list_runs()
        else:
            service.list_for_playbook(playbook.id)


@pytest.mark.parametrize("match_count", [0, 1])
def test_list_for_revision_returns_zero_or_one_explicit_match(match_count: int) -> None:
    playbook = make_playbook()
    revision = make_revision(playbook.id)
    playbook_repo = FakePlaybookRepository([playbook])
    run_repo = FakePlaybookRunRepository(playbook_repo)
    linked = PlaybookRun(
        playbook_id=playbook.id,
        revision_id=revision.id,
        situation="Optional match",
        actions_taken=["Recorded action"],
        outcome="Recorded outcome",
        success=True,
    )
    if match_count:
        run_repo.saved = [linked]
    service, _ = make_service(playbook_repo, run_repo, [revision])

    assert service.list_for_revision(revision.id) == ([linked] if match_count else [])


def test_list_for_revision_filters_validated_runs_in_repository_order() -> None:
    playbook = make_playbook()
    revision = make_revision(playbook.id)
    playbook_repo = FakePlaybookRepository([playbook])
    run_repo = FakePlaybookRunRepository(playbook_repo)
    first = PlaybookRun(
        playbook_id=playbook.id,
        revision_id=revision.id,
        situation="First",
        actions_taken=["First action"],
        outcome="First outcome",
        success=True,
    )
    legacy = PlaybookRun(
        playbook_id=playbook.id,
        situation="Legacy",
        actions_taken=["Legacy action"],
        outcome="Legacy outcome",
        success=True,
    )
    second = first.model_copy(update={"id": UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")})
    run_repo.saved = [first, legacy, second]
    service, _ = make_service(playbook_repo, run_repo, [revision])

    assert service.list_for_revision(revision.id) == [first, second]


def test_list_for_revision_fails_closed_for_corrupt_matching_provenance() -> None:
    playbook = make_playbook()
    other_playbook = make_playbook()
    revision = make_revision(other_playbook.id)
    run = PlaybookRun(
        playbook_id=playbook.id,
        revision_id=revision.id,
        situation="Corrupt matching provenance",
        actions_taken=["Recorded action"],
        outcome="Recorded outcome",
        success=False,
    )
    playbook_repo = FakePlaybookRepository([playbook, other_playbook])
    run_repo = FakePlaybookRunRepository(playbook_repo)
    run_repo.saved = [run]
    service, _ = make_service(playbook_repo, run_repo, [revision])

    with pytest.raises(PlaybookRunRevisionPlaybookMismatchError):
        service.list_for_revision(revision.id)


def test_list_for_revision_rejects_missing_requested_revision_without_loading_runs() -> None:
    playbook_repo = FakePlaybookRepository()
    run_repo = FakePlaybookRunRepository(playbook_repo)
    service, _ = make_service(playbook_repo, run_repo)

    with pytest.raises(PlaybookRevisionNotFoundError):
        service.list_for_revision(UUID("99999999-9999-9999-9999-999999999999"))

    assert run_repo.load_all_calls == 0

from __future__ import annotations

from uuid import UUID

import pytest

from neural_engine.application.evolution_proposal_service import (
    EvolutionProposalNotFoundError,
)
from neural_engine.application.playbook_revision_service import (
    KnowledgeNotFoundError,
    PlaybookNotFoundError,
    PlaybookRevisionProposalMismatchError,
    PlaybookRevisionProposalNotAcceptedError,
    PlaybookRevisionService,
    PlaybookRevisionStepsRequiredError,
    PlaybookRevisionSuccessCriteriaRequiredError,
)
from neural_engine.domain import (
    EvolutionProposal,
    EvolutionProposalStatus,
    Knowledge,
    KnowledgeConfidence,
    Playbook,
    PlaybookRevision,
)
from neural_engine.ports.evolution_proposal_repository import (
    EvolutionProposalRepository,
)
from neural_engine.ports.knowledge_repository import KnowledgeRepository
from neural_engine.ports.playbook_repository import PlaybookRepository
from neural_engine.ports.playbook_revision_repository import (
    PlaybookRevisionRepository,
)


class FakePlaybookRevisionRepository(PlaybookRevisionRepository):
    def __init__(
        self,
        playbook_repository: FakePlaybookRepository,
        proposal_repository: FakeEvolutionProposalRepository,
        knowledge_repository: FakeKnowledgeRepository,
    ) -> None:
        self.saved: list[PlaybookRevision] = []
        self.save_calls: list[PlaybookRevision] = []
        self.load_all_calls = 0
        self.requested_ids: list[UUID] = []
        self.playbook_lookups_at_load: list[UUID] = []
        self.proposal_lookups_at_load: list[UUID] = []
        self.knowledge_lookups_at_load: list[UUID] = []
        self.playbook_lookups_at_save: list[UUID] = []
        self.proposal_lookups_at_save: list[UUID] = []
        self.knowledge_lookups_at_save: list[UUID] = []
        self._playbook_repository = playbook_repository
        self._proposal_repository = proposal_repository
        self._knowledge_repository = knowledge_repository

    def save(self, revision: PlaybookRevision) -> None:
        self.save_calls.append(revision)
        self.playbook_lookups_at_save = list(self._playbook_repository.requested_ids)
        self.proposal_lookups_at_save = list(self._proposal_repository.requested_ids)
        self.knowledge_lookups_at_save = list(self._knowledge_repository.requested_ids)
        self.saved.append(revision)

    def load_all(self) -> list[PlaybookRevision]:
        self.load_all_calls += 1
        self.playbook_lookups_at_load = list(self._playbook_repository.requested_ids)
        self.proposal_lookups_at_load = list(self._proposal_repository.requested_ids)
        self.knowledge_lookups_at_load = list(self._knowledge_repository.requested_ids)
        return self.saved

    def get_by_id(self, revision_id: UUID) -> PlaybookRevision | None:
        self.requested_ids.append(revision_id)

        for revision in self.saved:
            if revision.id == revision_id:
                return revision

        return None


class FakePlaybookRepository(PlaybookRepository):
    def __init__(self, playbooks: list[Playbook] | None = None) -> None:
        self.saved = playbooks or []
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


class FakeEvolutionProposalRepository(EvolutionProposalRepository):
    def __init__(self, proposals: list[EvolutionProposal] | None = None) -> None:
        self.saved = proposals or []
        self.requested_ids: list[UUID] = []

    def save(self, proposal: EvolutionProposal) -> None:
        self.saved.append(proposal)

    def load_all(self) -> list[EvolutionProposal]:
        return self.saved

    def get_by_id(self, proposal_id: UUID) -> EvolutionProposal | None:
        self.requested_ids.append(proposal_id)

        for proposal in self.saved:
            if proposal.id == proposal_id:
                return proposal

        return None


class FakeKnowledgeRepository(KnowledgeRepository):
    def __init__(self, knowledge_items: list[Knowledge] | None = None) -> None:
        self.saved = knowledge_items or []
        self.requested_ids: list[UUID] = []

    def save(self, knowledge: Knowledge) -> None:
        self.saved.append(knowledge)

    def load_all(self) -> list[Knowledge]:
        return self.saved

    def get_by_id(self, knowledge_id: UUID) -> Knowledge | None:
        self.requested_ids.append(knowledge_id)

        for knowledge in self.saved:
            if knowledge.id == knowledge_id:
                return knowledge

        return None


def make_playbook() -> Playbook:
    return Playbook(
        title="Debug flaky tests",
        situation="A test fails intermittently",
        objective="Find the unstable dependency",
        steps=["Run the failing test repeatedly"],
        success_criteria=["Failure source is isolated"],
        knowledge_ids=[UUID("11111111-1111-1111-1111-111111111111")],
    )


def make_proposal(
    playbook_id: UUID,
    status: EvolutionProposalStatus = EvolutionProposalStatus.ACCEPTED,
) -> EvolutionProposal:
    return EvolutionProposal(
        playbook_id=playbook_id,
        evaluation_ids=[UUID("22222222-2222-2222-2222-222222222222")],
        summary="Accepted manual proposal",
        rationale="Manual review identified an improvement",
        proposed_changes=["Clarify verification"],
        expected_benefits=["More consistent use"],
        status=status,
    )


def make_knowledge() -> Knowledge:
    return Knowledge(
        statement="Focused tests reduce debugging time",
        rationale="Manual evidence supports focused runs",
        confidence=KnowledgeConfidence.HIGH,
        experience_ids=[UUID("33333333-3333-3333-3333-333333333333")],
    )


def make_revision(playbook_id: UUID, title: str = "Candidate revision") -> PlaybookRevision:
    return PlaybookRevision(
        playbook_id=playbook_id,
        proposal_id=UUID("44444444-4444-4444-4444-444444444444"),
        title=title,
        situation="Revision relation test",
        objective="Return linked revisions",
        steps=["Inspect linked revisions"],
        success_criteria=["Only linked revisions are returned"],
        knowledge_ids=[UUID("55555555-5555-5555-5555-555555555555")],
    )


def make_revision_for_proposal(
    playbook_id: UUID,
    proposal_id: UUID,
    title: str = "Candidate revision",
) -> PlaybookRevision:
    return PlaybookRevision(
        playbook_id=playbook_id,
        proposal_id=proposal_id,
        title=title,
        situation="Revision relation test",
        objective="Return linked revisions",
        steps=["Inspect linked revisions"],
        success_criteria=["Only linked revisions are returned"],
        knowledge_ids=[UUID("55555555-5555-5555-5555-555555555555")],
    )


def make_revision_for_knowledge(
    playbook_id: UUID,
    knowledge_ids: list[UUID],
    title: str = "Candidate revision",
) -> PlaybookRevision:
    return PlaybookRevision(
        playbook_id=playbook_id,
        proposal_id=UUID("44444444-4444-4444-4444-444444444444"),
        title=title,
        situation="Revision relation test",
        objective="Return linked revisions",
        steps=["Inspect linked revisions"],
        success_criteria=["Only linked revisions are returned"],
        knowledge_ids=knowledge_ids,
    )


def make_service(
    playbooks: list[Playbook] | None = None,
    proposals: list[EvolutionProposal] | None = None,
    knowledge_items: list[Knowledge] | None = None,
) -> tuple[
    PlaybookRevisionService,
    FakePlaybookRevisionRepository,
    FakePlaybookRepository,
    FakeEvolutionProposalRepository,
    FakeKnowledgeRepository,
]:
    playbook_repo = FakePlaybookRepository(playbooks)
    proposal_repo = FakeEvolutionProposalRepository(proposals)
    knowledge_repo = FakeKnowledgeRepository(knowledge_items)
    revision_repo = FakePlaybookRevisionRepository(playbook_repo, proposal_repo, knowledge_repo)
    service = PlaybookRevisionService(
        revision_repo,
        playbook_repo,
        proposal_repo,
        knowledge_repo,
    )

    return service, revision_repo, playbook_repo, proposal_repo, knowledge_repo


def add_revision(
    service: PlaybookRevisionService,
    playbook_id: UUID,
    proposal_id: UUID,
    knowledge_ids: list[UUID],
    steps: list[str] | None = None,
    success_criteria: list[str] | None = None,
) -> PlaybookRevision:
    return service.add(
        playbook_id=playbook_id,
        proposal_id=proposal_id,
        title="Revised playbook",
        situation="Revised situation",
        objective="Revised objective",
        steps=steps if steps is not None else ["Apply revised step"],
        success_criteria=(
            success_criteria if success_criteria is not None else ["Revision succeeds"]
        ),
        knowledge_ids=knowledge_ids,
        notes="Manual candidate",
        tags=["manual", "candidate"],
    )


def test_add_revision_from_accepted_proposal() -> None:
    playbook = make_playbook()
    proposal = make_proposal(playbook.id)
    knowledge = make_knowledge()
    service, revision_repo, _, _, _ = make_service([playbook], [proposal], [knowledge])

    revision = add_revision(service, playbook.id, proposal.id, [knowledge.id])

    assert revision_repo.saved == [revision]
    assert revision.playbook_id == playbook.id
    assert revision.proposal_id == proposal.id


def test_normal_revision_creation_remains_fresh_id_and_non_idempotent() -> None:
    playbook = make_playbook()
    proposal = make_proposal(playbook.id)
    knowledge = make_knowledge()
    service, revision_repo, _, _, _ = make_service([playbook], [proposal], [knowledge])

    first = add_revision(service, playbook.id, proposal.id, [knowledge.id])
    second = add_revision(service, playbook.id, proposal.id, [knowledge.id])

    assert first.id != second.id
    assert revision_repo.saved == [first, second]


def test_add_revision_preserves_all_supplied_fields() -> None:
    playbook = make_playbook()
    proposal = make_proposal(playbook.id)
    first_knowledge = make_knowledge()
    second_knowledge = make_knowledge()
    service, _, _, _, _ = make_service(
        [playbook],
        [proposal],
        [first_knowledge, second_knowledge],
    )

    revision = service.add(
        playbook_id=playbook.id,
        proposal_id=proposal.id,
        title="Explicit title",
        situation="Explicit situation",
        objective="Explicit objective",
        steps=["First step", "Second step"],
        success_criteria=["First criterion", "Second criterion"],
        knowledge_ids=[first_knowledge.id, second_knowledge.id, first_knowledge.id],
        notes="Explicit notes",
        tags=["explicit", "manual"],
    )

    assert revision.title == "Explicit title"
    assert revision.situation == "Explicit situation"
    assert revision.objective == "Explicit objective"
    assert revision.steps == ["First step", "Second step"]
    assert revision.success_criteria == ["First criterion", "Second criterion"]
    assert revision.knowledge_ids == [first_knowledge.id, second_knowledge.id, first_knowledge.id]
    assert revision.notes == "Explicit notes"
    assert revision.tags == ["explicit", "manual"]


def test_add_revision_raises_when_steps_are_empty() -> None:
    service, revision_repo, playbook_repo, proposal_repo, knowledge_repo = make_service()

    with pytest.raises(PlaybookRevisionStepsRequiredError):
        add_revision(
            service,
            UUID("44444444-4444-4444-4444-444444444444"),
            UUID("55555555-5555-5555-5555-555555555555"),
            [],
            steps=[],
        )

    assert playbook_repo.requested_ids == []
    assert proposal_repo.requested_ids == []
    assert knowledge_repo.requested_ids == []
    assert revision_repo.saved == []


def test_add_revision_raises_when_success_criteria_are_empty() -> None:
    service, revision_repo, playbook_repo, proposal_repo, knowledge_repo = make_service()

    with pytest.raises(PlaybookRevisionSuccessCriteriaRequiredError):
        add_revision(
            service,
            UUID("66666666-6666-6666-6666-666666666666"),
            UUID("77777777-7777-7777-7777-777777777777"),
            [],
            success_criteria=[],
        )

    assert playbook_repo.requested_ids == []
    assert proposal_repo.requested_ids == []
    assert knowledge_repo.requested_ids == []
    assert revision_repo.saved == []


def test_add_revision_raises_when_playbook_is_missing() -> None:
    playbook_id = UUID("88888888-8888-8888-8888-888888888888")
    proposal = make_proposal(playbook_id)
    service, revision_repo, playbook_repo, _, knowledge_repo = make_service(
        proposals=[proposal],
    )

    with pytest.raises(PlaybookNotFoundError) as error:
        add_revision(
            service,
            playbook_id,
            proposal.id,
            [],
        )

    assert error.value.playbook_id == playbook_id
    assert playbook_repo.requested_ids == [playbook_id]
    assert knowledge_repo.requested_ids == []
    assert revision_repo.saved == []


def test_add_revision_raises_when_proposal_is_missing() -> None:
    playbook = make_playbook()
    missing_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    service, revision_repo, playbook_repo, proposal_repo, knowledge_repo = make_service(
        [playbook],
    )

    with pytest.raises(EvolutionProposalNotFoundError) as error:
        add_revision(service, playbook.id, missing_id, [])

    assert error.value.proposal_id == missing_id
    assert playbook_repo.requested_ids == []
    assert proposal_repo.requested_ids == [missing_id]
    assert knowledge_repo.requested_ids == []
    assert revision_repo.saved == []


def test_add_revision_raises_when_proposal_belongs_to_other_playbook() -> None:
    playbook = make_playbook()
    other_playbook = make_playbook()
    proposal = make_proposal(other_playbook.id)
    service, revision_repo, _, _, knowledge_repo = make_service([playbook], [proposal])

    with pytest.raises(PlaybookRevisionProposalMismatchError) as error:
        add_revision(service, playbook.id, proposal.id, [])

    assert error.value.proposal_id == proposal.id
    assert error.value.expected_playbook_id == playbook.id
    assert error.value.actual_playbook_id == other_playbook.id
    assert knowledge_repo.requested_ids == []
    assert revision_repo.saved == []


@pytest.mark.parametrize(
    "status",
    [EvolutionProposalStatus.DRAFT, EvolutionProposalStatus.REJECTED],
)
def test_add_revision_raises_when_proposal_is_not_accepted(
    status: EvolutionProposalStatus,
) -> None:
    playbook = make_playbook()
    proposal = make_proposal(playbook.id, status)
    service, revision_repo, _, _, knowledge_repo = make_service([playbook], [proposal])

    with pytest.raises(PlaybookRevisionProposalNotAcceptedError) as error:
        add_revision(service, playbook.id, proposal.id, [])

    assert error.value.proposal_id == proposal.id
    assert error.value.actual_status == status
    assert knowledge_repo.requested_ids == []
    assert revision_repo.saved == []


def test_add_revision_raises_when_knowledge_is_missing() -> None:
    playbook = make_playbook()
    proposal = make_proposal(playbook.id)
    missing_id = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    service, revision_repo, _, _, knowledge_repo = make_service([playbook], [proposal])

    with pytest.raises(KnowledgeNotFoundError) as error:
        add_revision(service, playbook.id, proposal.id, [missing_id])

    assert error.value.knowledge_id == missing_id
    assert knowledge_repo.requested_ids == [missing_id]
    assert revision_repo.saved == []


def test_add_revision_stops_on_first_missing_knowledge() -> None:
    playbook = make_playbook()
    proposal = make_proposal(playbook.id)
    first_missing_id = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
    second_missing_id = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
    service, revision_repo, _, _, knowledge_repo = make_service([playbook], [proposal])

    with pytest.raises(KnowledgeNotFoundError):
        add_revision(service, playbook.id, proposal.id, [first_missing_id, second_missing_id])

    assert knowledge_repo.requested_ids == [first_missing_id]
    assert revision_repo.saved == []


def test_add_revision_missing_proposal_does_not_read_playbook() -> None:
    playbook = make_playbook()
    missing_id = UUID("deadbeef-dead-beef-dead-beefdeadbeef")
    service, revision_repo, playbook_repo, _, _ = make_service([playbook])

    with pytest.raises(EvolutionProposalNotFoundError):
        add_revision(service, playbook.id, missing_id, [])

    assert playbook_repo.requested_ids == []


@pytest.mark.parametrize(
    "status",
    [EvolutionProposalStatus.DRAFT, EvolutionProposalStatus.REJECTED],
)
def test_add_revision_non_accepted_proposal_does_not_read_playbook(
    status: EvolutionProposalStatus,
) -> None:
    playbook = make_playbook()
    proposal = make_proposal(playbook.id, status)
    service, revision_repo, playbook_repo, _, _ = make_service([playbook], [proposal])

    with pytest.raises(PlaybookRevisionProposalNotAcceptedError):
        add_revision(service, playbook.id, proposal.id, [])

    assert playbook_repo.requested_ids == []


def test_add_revision_mismatched_proposal_does_not_read_playbook() -> None:
    playbook = make_playbook()
    other_playbook = make_playbook()
    proposal = make_proposal(other_playbook.id)
    service, revision_repo, playbook_repo, _, _ = make_service([playbook], [proposal])

    with pytest.raises(PlaybookRevisionProposalMismatchError):
        add_revision(service, playbook.id, proposal.id, [])

    assert playbook_repo.requested_ids == []


def test_add_revision_accepted_proposal_does_read_playbook() -> None:
    playbook = make_playbook()
    proposal = make_proposal(playbook.id)
    service, revision_repo, playbook_repo, _, _ = make_service([playbook], [proposal])

    add_revision(service, playbook.id, proposal.id, [])

    assert playbook_repo.requested_ids == [playbook.id]


def test_add_revision_missing_playbook_does_not_read_knowledge() -> None:
    playbook_id = UUID("deadc0de-dead-c0de-dead-c0dedeadc0de")
    proposal = make_proposal(playbook_id)
    knowledge = make_knowledge()
    service, revision_repo, playbook_repo, _, knowledge_repo = make_service(
        proposals=[proposal],
        knowledge_items=[knowledge],
    )

    with pytest.raises(PlaybookNotFoundError):
        add_revision(service, playbook_id, proposal.id, [knowledge.id])

    assert knowledge_repo.requested_ids == []


def test_add_revision_does_not_save_on_any_validation_failure() -> None:
    playbook = make_playbook()
    proposal = make_proposal(playbook.id)
    service, revision_repo, _, _, _ = make_service([playbook], [proposal])

    with pytest.raises(PlaybookRevisionStepsRequiredError):
        add_revision(service, playbook.id, proposal.id, [], steps=[])

    assert revision_repo.saved == []

    with pytest.raises(PlaybookRevisionSuccessCriteriaRequiredError):
        add_revision(service, playbook.id, proposal.id, [], success_criteria=[])

    assert revision_repo.saved == []

    missing_proposal_id = UUID("baadbaad-baad-baad-baad-baadbaadbaad")
    with pytest.raises(EvolutionProposalNotFoundError):
        add_revision(service, playbook.id, missing_proposal_id, [])

    assert revision_repo.saved == []

    draft_proposal = make_proposal(playbook.id, EvolutionProposalStatus.DRAFT)
    service2, revision_repo2, _, _, _ = make_service([playbook], [draft_proposal])
    with pytest.raises(PlaybookRevisionProposalNotAcceptedError):
        add_revision(service2, playbook.id, draft_proposal.id, [])

    assert revision_repo2.saved == []

    other_proposal = make_proposal(UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"))
    service3, revision_repo3, _, _, _ = make_service([playbook], [other_proposal])
    with pytest.raises(PlaybookRevisionProposalMismatchError):
        add_revision(service3, playbook.id, other_proposal.id, [])

    assert revision_repo3.saved == []

    missing_playbook_id = UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
    missing_proposal = make_proposal(missing_playbook_id)
    service4, revision_repo4, _, _, _ = make_service(
        proposals=[missing_proposal],
    )
    with pytest.raises(PlaybookNotFoundError):
        add_revision(service4, missing_playbook_id, missing_proposal.id, [])

    assert revision_repo4.saved == []

    missing_knowledge_id = UUID("babababa-baba-baba-baba-babababababa")
    service5, revision_repo5, _, _, _ = make_service([playbook], [proposal])
    with pytest.raises(KnowledgeNotFoundError):
        add_revision(service5, playbook.id, proposal.id, [missing_knowledge_id])

    assert revision_repo5.saved == []


def test_add_revision_performs_all_lookups_before_saving() -> None:
    playbook = make_playbook()
    proposal = make_proposal(playbook.id)
    knowledge = make_knowledge()
    service, revision_repo, _, _, _ = make_service([playbook], [proposal], [knowledge])

    add_revision(service, playbook.id, proposal.id, [knowledge.id])

    assert revision_repo.playbook_lookups_at_save == [playbook.id]
    assert revision_repo.proposal_lookups_at_save == [proposal.id]
    assert revision_repo.knowledge_lookups_at_save == [knowledge.id]


def test_list_revisions_delegates_to_repository() -> None:
    service, revision_repo, _, _, _ = make_service()
    revision = PlaybookRevision(
        playbook_id=UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"),
        proposal_id=UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"),
        title="Listed revision",
        situation="Listed situation",
        objective="Listed objective",
        steps=["Step"],
        success_criteria=["Criterion"],
        knowledge_ids=[UUID("12121212-1212-1212-1212-121212121212")],
    )
    revision_repo.saved = [revision]

    assert service.list_revisions() == [revision]
    assert revision_repo.load_all_calls == 1


def test_list_for_playbook_returns_only_linked_revisions() -> None:
    playbook = make_playbook()
    linked = make_revision(playbook.id, "Linked revision")
    unrelated = make_revision(UUID("67676767-6767-6767-6767-676767676767"), "Other revision")
    service, revision_repo, _, _, _ = make_service([playbook])
    revision_repo.saved = [linked, unrelated]

    assert service.list_for_playbook(playbook.id) == [linked]


def test_list_for_playbook_returns_empty_list_when_none_are_linked() -> None:
    playbook = make_playbook()
    service, revision_repo, _, _, _ = make_service([playbook])
    revision_repo.saved = [
        make_revision(UUID("78787878-7878-7878-7878-787878787878"), "Unrelated revision")
    ]

    assert service.list_for_playbook(playbook.id) == []


def test_list_for_playbook_preserves_repository_order() -> None:
    playbook = make_playbook()
    first = make_revision(playbook.id, "First revision")
    second = make_revision(playbook.id, "Second revision")
    service, revision_repo, _, _, _ = make_service([playbook])
    revision_repo.saved = [first, second]

    assert service.list_for_playbook(playbook.id) == [first, second]


def test_list_for_playbook_missing_playbook_raises_controlled_error() -> None:
    missing_id = UUID("89898989-8989-8989-8989-898989898989")
    service, _, _, _, _ = make_service()

    with pytest.raises(PlaybookNotFoundError) as error:
        service.list_for_playbook(missing_id)

    assert error.value.playbook_id == missing_id


def test_list_for_playbook_does_not_load_revisions_when_playbook_is_missing() -> None:
    missing_id = UUID("90909090-9090-9090-9090-909090909090")
    service, revision_repo, _, _, _ = make_service()

    with pytest.raises(PlaybookNotFoundError):
        service.list_for_playbook(missing_id)

    assert revision_repo.load_all_calls == 0


def test_list_for_playbook_looks_up_playbook_before_loading_revisions() -> None:
    playbook = make_playbook()
    service, revision_repo, _, _, _ = make_service([playbook])

    service.list_for_playbook(playbook.id)

    assert revision_repo.playbook_lookups_at_load == [playbook.id]


def test_list_for_playbook_does_not_save_or_mutate_data() -> None:
    playbook = make_playbook()
    original_playbook = playbook.model_dump()
    revision = make_revision(playbook.id, "Stable revision")
    original_revision = revision.model_copy(deep=True)
    service, revision_repo, _, _, _ = make_service([playbook])
    revision_repo.saved = [revision]

    result = service.list_for_playbook(playbook.id)

    assert result == [revision]
    assert revision_repo.saved == [revision]
    assert revision_repo.save_calls == []
    assert revision == original_revision
    assert playbook.model_dump() == original_playbook


def test_list_for_proposal_returns_only_linked_revisions() -> None:
    playbook = make_playbook()
    proposal = make_proposal(playbook.id)
    linked = make_revision_for_proposal(playbook.id, proposal.id, "Linked revision")
    unrelated = make_revision_for_proposal(
        playbook.id,
        UUID("abababab-abab-abab-abab-abababababab"),
        "Other revision",
    )
    service, revision_repo, _, _, _ = make_service([playbook], [proposal])
    revision_repo.saved = [linked, unrelated]

    assert service.list_for_proposal(proposal.id) == [linked]


def test_list_for_proposal_returns_empty_list_when_none_are_linked() -> None:
    playbook = make_playbook()
    proposal = make_proposal(playbook.id)
    service, revision_repo, _, _, _ = make_service([playbook], [proposal])
    revision_repo.saved = [
        make_revision_for_proposal(
            playbook.id,
            UUID("bcbcbcbc-bcbc-bcbc-bcbc-bcbcbcbcbcbc"),
            "Unrelated revision",
        )
    ]

    assert service.list_for_proposal(proposal.id) == []


def test_list_for_proposal_preserves_repository_order() -> None:
    playbook = make_playbook()
    proposal = make_proposal(playbook.id)
    first = make_revision_for_proposal(playbook.id, proposal.id, "First revision")
    second = make_revision_for_proposal(playbook.id, proposal.id, "Second revision")
    service, revision_repo, _, _, _ = make_service([playbook], [proposal])
    revision_repo.saved = [first, second]

    assert service.list_for_proposal(proposal.id) == [first, second]


def test_list_for_proposal_missing_proposal_raises_controlled_error() -> None:
    missing_id = UUID("cdcdcdcd-cdcd-cdcd-cdcd-cdcdcdcdcdcd")
    service, _, _, _, _ = make_service()

    with pytest.raises(EvolutionProposalNotFoundError) as error:
        service.list_for_proposal(missing_id)

    assert error.value.proposal_id == missing_id


def test_list_for_proposal_does_not_load_revisions_when_proposal_is_missing() -> None:
    missing_id = UUID("dededede-dede-dede-dede-dededededede")
    service, revision_repo, _, _, _ = make_service()

    with pytest.raises(EvolutionProposalNotFoundError):
        service.list_for_proposal(missing_id)

    assert revision_repo.load_all_calls == 0


def test_list_for_proposal_looks_up_proposal_before_loading_revisions() -> None:
    playbook = make_playbook()
    proposal = make_proposal(playbook.id)
    service, revision_repo, _, _, _ = make_service([playbook], [proposal])

    service.list_for_proposal(proposal.id)

    assert revision_repo.proposal_lookups_at_load == [proposal.id]


def test_list_for_proposal_does_not_save_or_mutate_data() -> None:
    playbook = make_playbook()
    proposal = make_proposal(playbook.id)
    original_playbook = playbook.model_dump()
    original_proposal = proposal.model_dump()
    revision = make_revision_for_proposal(playbook.id, proposal.id, "Stable revision")
    original_revision = revision.model_copy(deep=True)
    service, revision_repo, _, _, _ = make_service([playbook], [proposal])
    revision_repo.saved = [revision]

    result = service.list_for_proposal(proposal.id)

    assert result == [revision]
    assert revision_repo.saved == [revision]
    assert revision_repo.save_calls == []
    assert revision == original_revision
    assert proposal.model_dump() == original_proposal
    assert playbook.model_dump() == original_playbook


def test_list_for_knowledge_returns_only_revisions_that_reference_knowledge() -> None:
    playbook = make_playbook()
    knowledge = make_knowledge()
    linked = make_revision_for_knowledge(
        playbook.id,
        [UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"), knowledge.id],
        "Linked revision",
    )
    unrelated = make_revision_for_knowledge(
        playbook.id,
        [UUID("abababab-abab-abab-abab-abababababab")],
        "Other revision",
    )
    service, revision_repo, _, _, _ = make_service([playbook], knowledge_items=[knowledge])
    revision_repo.saved = [linked, unrelated]

    assert service.list_for_knowledge(knowledge.id) == [linked]


def test_list_for_knowledge_returns_empty_list_when_none_reference_knowledge() -> None:
    playbook = make_playbook()
    knowledge = make_knowledge()
    service, revision_repo, _, _, _ = make_service([playbook], knowledge_items=[knowledge])
    revision_repo.saved = [
        make_revision_for_knowledge(
            playbook.id,
            [UUID("bcbcbcbc-bcbc-bcbc-bcbc-bcbcbcbcbcbc")],
            "Unrelated revision",
        )
    ]

    assert service.list_for_knowledge(knowledge.id) == []


def test_list_for_knowledge_preserves_repository_order() -> None:
    playbook = make_playbook()
    knowledge = make_knowledge()
    first = make_revision_for_knowledge(playbook.id, [knowledge.id], "First revision")
    second = make_revision_for_knowledge(playbook.id, [knowledge.id], "Second revision")
    service, revision_repo, _, _, _ = make_service([playbook], knowledge_items=[knowledge])
    revision_repo.saved = [first, second]

    assert service.list_for_knowledge(knowledge.id) == [first, second]


def test_list_for_knowledge_missing_knowledge_raises_controlled_error() -> None:
    missing_id = UUID("cdcdcdcd-cdcd-cdcd-cdcd-cdcdcdcdcdcd")
    service, _, _, _, _ = make_service()

    with pytest.raises(KnowledgeNotFoundError) as error:
        service.list_for_knowledge(missing_id)

    assert error.value.knowledge_id == missing_id


def test_list_for_knowledge_does_not_load_revisions_when_knowledge_is_missing() -> None:
    missing_id = UUID("dededede-dede-dede-dede-dededededede")
    service, revision_repo, _, _, _ = make_service()

    with pytest.raises(KnowledgeNotFoundError):
        service.list_for_knowledge(missing_id)

    assert revision_repo.load_all_calls == 0


def test_list_for_knowledge_looks_up_knowledge_before_loading_revisions() -> None:
    playbook = make_playbook()
    knowledge = make_knowledge()
    service, revision_repo, _, _, _ = make_service([playbook], knowledge_items=[knowledge])

    service.list_for_knowledge(knowledge.id)

    assert revision_repo.knowledge_lookups_at_load == [knowledge.id]


def test_list_for_knowledge_does_not_save_or_mutate_data() -> None:
    playbook = make_playbook()
    proposal = make_proposal(playbook.id)
    knowledge = make_knowledge()
    original_playbook = playbook.model_dump()
    original_proposal = proposal.model_dump()
    original_knowledge = knowledge.model_dump()
    revision = make_revision_for_knowledge(playbook.id, [knowledge.id], "Stable revision")
    original_revision = revision.model_copy(deep=True)
    service, revision_repo, _, _, _ = make_service([playbook], [proposal], [knowledge])
    revision_repo.saved = [revision]

    result = service.list_for_knowledge(knowledge.id)

    assert result == [revision]
    assert revision_repo.saved == [revision]
    assert revision_repo.save_calls == []
    assert revision == original_revision
    assert knowledge.model_dump() == original_knowledge
    assert proposal.model_dump() == original_proposal
    assert playbook.model_dump() == original_playbook


def test_get_by_id_returns_existing_revision() -> None:
    service, revision_repo, _, _, _ = make_service()
    revision = PlaybookRevision(
        playbook_id=UUID("23232323-2323-2323-2323-232323232323"),
        proposal_id=UUID("34343434-3434-3434-3434-343434343434"),
        title="Existing revision",
        situation="Existing situation",
        objective="Existing objective",
        steps=["Step"],
        success_criteria=["Criterion"],
        knowledge_ids=[UUID("45454545-4545-4545-4545-454545454545")],
    )
    revision_repo.saved = [revision]

    assert service.get_by_id(revision.id) == revision
    assert revision_repo.requested_ids == [revision.id]


def test_get_by_id_returns_none_when_missing() -> None:
    service, revision_repo, _, _, _ = make_service()
    missing_id = UUID("56565656-5656-5656-5656-565656565656")

    assert service.get_by_id(missing_id) is None
    assert revision_repo.requested_ids == [missing_id]


def test_add_does_not_mutate_source_playbook() -> None:
    playbook = make_playbook()
    original = playbook.model_dump()
    proposal = make_proposal(playbook.id)
    knowledge = make_knowledge()
    service, _, _, _, _ = make_service([playbook], [proposal], [knowledge])

    add_revision(service, playbook.id, proposal.id, [knowledge.id])

    assert playbook.model_dump() == original


def test_add_does_not_mutate_source_proposal() -> None:
    playbook = make_playbook()
    proposal = make_proposal(playbook.id)
    original = proposal.model_dump()
    knowledge = make_knowledge()
    service, _, _, _, _ = make_service([playbook], [proposal], [knowledge])

    add_revision(service, playbook.id, proposal.id, [knowledge.id])

    assert proposal.model_dump() == original


def test_add_does_not_auto_copy_proposed_changes_to_steps() -> None:
    playbook = make_playbook()
    proposal = make_proposal(playbook.id)
    knowledge = make_knowledge()
    service, revision_repo, _, _, _ = make_service([playbook], [proposal], [knowledge])

    revision = add_revision(
        service,
        playbook.id,
        proposal.id,
        [knowledge.id],
        steps=["Explicitly supplied step"],
    )

    assert revision.steps == ["Explicitly supplied step"]
    assert revision.steps != proposal.proposed_changes


def test_add_preserves_exactly_supplied_content() -> None:
    playbook = make_playbook()
    proposal = make_proposal(playbook.id)
    knowledge = make_knowledge()
    service, revision_repo, _, _, _ = make_service([playbook], [proposal], [knowledge])

    revision = service.add(
        playbook_id=playbook.id,
        proposal_id=proposal.id,
        title="Exact title",
        situation="Exact situation",
        objective="Exact objective",
        steps=["Exact step A", "Exact step B"],
        success_criteria=["Exact criterion"],
        knowledge_ids=[knowledge.id],
        notes="Exact notes",
        tags=["exact"],
    )

    assert revision.title == "Exact title"
    assert revision.situation == "Exact situation"
    assert revision.objective == "Exact objective"
    assert revision.steps == ["Exact step A", "Exact step B"]
    assert revision.success_criteria == ["Exact criterion"]
    assert revision.knowledge_ids == [knowledge.id]
    assert revision.notes == "Exact notes"
    assert revision.tags == ["exact"]

from uuid import UUID

import pytest

from neural_engine.application.playbook_revision_activation_service import (
    PlaybookRevisionActivationService,
)
from neural_engine.application.playbook_revision_application_service import (
    PlaybookRevisionApplicationActivationMismatchError,
    PlaybookRevisionApplicationActivationNotFoundError,
    PlaybookRevisionApplicationInactiveRevisionError,
    PlaybookRevisionApplicationNoActiveRevisionError,
    PlaybookRevisionApplicationPlaybookNotFoundError,
    PlaybookRevisionApplicationProposalNotAcceptedError,
    PlaybookRevisionApplicationProposalNotFoundError,
    PlaybookRevisionApplicationRevisionNotFoundError,
    PlaybookRevisionApplicationRevisionPlaybookMismatchError,
    PlaybookRevisionApplicationRevisionProposalMismatchError,
    PlaybookRevisionApplicationService,
)
from neural_engine.domain import (
    EvolutionProposal,
    EvolutionProposalStatus,
    Playbook,
    PlaybookRevision,
    PlaybookRevisionActivation,
    PlaybookRevisionActivationDecision,
    PlaybookRevisionApplication,
)
from neural_engine.ports.evolution_proposal_repository import (
    EvolutionProposalRepository,
)
from neural_engine.ports.playbook_repository import PlaybookRepository
from neural_engine.ports.playbook_revision_activation_repository import (
    PlaybookRevisionActivationRepository,
)
from neural_engine.ports.playbook_revision_application_repository import (
    PlaybookRevisionApplicationRepository,
)
from neural_engine.ports.playbook_revision_repository import (
    PlaybookRevisionRepository,
)


class FakePlaybookRevisionApplicationRepository(PlaybookRevisionApplicationRepository):
    def __init__(self, applications: list[PlaybookRevisionApplication] | None = None) -> None:
        self.saved = applications or []
        self.save_calls: list[PlaybookRevisionApplication] = []
        self.load_all_calls = 0
        self.requested_ids: list[UUID] = []

    def save(self, application: PlaybookRevisionApplication) -> None:
        self.save_calls.append(application)
        self.saved.append(application)

    def load_all(self) -> list[PlaybookRevisionApplication]:
        self.load_all_calls += 1
        return self.saved

    def get_by_id(self, application_id: UUID) -> PlaybookRevisionApplication | None:
        self.requested_ids.append(application_id)

        for application in self.saved:
            if application.id == application_id:
                return application

        return None


class FakePlaybookRevisionActivationRepository(PlaybookRevisionActivationRepository):
    def __init__(self, activations: list[PlaybookRevisionActivation] | None = None) -> None:
        self.saved = activations or []
        self.save_calls: list[PlaybookRevisionActivation] = []
        self.load_all_calls = 0
        self.requested_ids: list[UUID] = []

    def save(self, activation: PlaybookRevisionActivation) -> None:
        self.save_calls.append(activation)
        self.saved.append(activation)

    def load_all(self) -> list[PlaybookRevisionActivation]:
        self.load_all_calls += 1
        return self.saved

    def get_by_id(self, activation_id: UUID) -> PlaybookRevisionActivation | None:
        self.requested_ids.append(activation_id)

        for activation in self.saved:
            if activation.id == activation_id:
                return activation

        return None


class FakePlaybookRevisionActivationService(PlaybookRevisionActivationService):
    def __init__(self, active_revision: PlaybookRevision | None = None) -> None:
        self.active_revision = active_revision
        self.requested_playbook_ids: list[UUID] = []

    def get_active_revision_for_playbook(self, playbook_id: UUID) -> PlaybookRevision | None:
        self.requested_playbook_ids.append(playbook_id)
        return self.active_revision


class FakePlaybookRevisionRepository(PlaybookRevisionRepository):
    def __init__(self, revisions: list[PlaybookRevision] | None = None) -> None:
        self.saved = revisions or []
        self.save_calls: list[PlaybookRevision] = []
        self.requested_ids: list[UUID] = []

    def save(self, revision: PlaybookRevision) -> None:
        self.save_calls.append(revision)
        self.saved.append(revision)

    def load_all(self) -> list[PlaybookRevision]:
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
        self.save_calls: list[Playbook] = []
        self.requested_ids: list[UUID] = []

    def save(self, playbook: Playbook) -> None:
        self.save_calls.append(playbook)
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
        self.save_calls: list[EvolutionProposal] = []
        self.requested_ids: list[UUID] = []

    def save(self, proposal: EvolutionProposal) -> None:
        self.save_calls.append(proposal)
        self.saved.append(proposal)

    def load_all(self) -> list[EvolutionProposal]:
        return self.saved

    def get_by_id(self, proposal_id: UUID) -> EvolutionProposal | None:
        self.requested_ids.append(proposal_id)

        for proposal in self.saved:
            if proposal.id == proposal_id:
                return proposal

        return None


def make_playbook(title: str = "Application playbook") -> Playbook:
    return Playbook(
        title=title,
        situation="A selected revision is ready",
        objective="Record explicit application intent",
        steps=["Review selected revision"],
        success_criteria=["Application boundary is auditable"],
        knowledge_ids=[UUID("11111111-1111-1111-1111-111111111111")],
    )


def make_proposal(
    playbook_id: UUID,
    status: EvolutionProposalStatus = EvolutionProposalStatus.ACCEPTED,
) -> EvolutionProposal:
    return EvolutionProposal(
        playbook_id=playbook_id,
        evaluation_ids=[UUID("22222222-2222-2222-2222-222222222222")],
        summary="Manual proposal",
        rationale="Manual review identified a useful change",
        proposed_changes=["Clarify the application step"],
        expected_benefits=["The boundary is easier to audit"],
        status=status,
    )


def make_revision(
    playbook_id: UUID,
    proposal_id: UUID,
    title: str = "Application candidate",
) -> PlaybookRevision:
    return PlaybookRevision(
        playbook_id=playbook_id,
        proposal_id=proposal_id,
        title=title,
        situation="Application service test",
        objective="Persist an explicit audit record",
        steps=["Validate linked aggregates"],
        success_criteria=["Application is saved only after validation"],
        knowledge_ids=[UUID("33333333-3333-3333-3333-333333333333")],
    )


def make_activation(
    playbook_id: UUID,
    revision_id: UUID,
    proposal_id: UUID,
    decision: PlaybookRevisionActivationDecision = PlaybookRevisionActivationDecision.ACTIVE,
    previous_revision_id: UUID | None = None,
) -> PlaybookRevisionActivation:
    return PlaybookRevisionActivation(
        playbook_id=playbook_id,
        revision_id=revision_id,
        proposal_id=proposal_id,
        decision=decision,
        reason="Selected revision",
        previous_revision_id=previous_revision_id,
    )


def make_application(
    playbook_id: UUID,
    revision_id: UUID,
    proposal_id: UUID,
    reason: str = "Recorded application",
) -> PlaybookRevisionApplication:
    return PlaybookRevisionApplication(
        playbook_id=playbook_id,
        revision_id=revision_id,
        proposal_id=proposal_id,
        reason=reason,
    )


def make_service(
    playbooks: list[Playbook] | None = None,
    revisions: list[PlaybookRevision] | None = None,
    proposals: list[EvolutionProposal] | None = None,
    activations: list[PlaybookRevisionActivation] | None = None,
    applications: list[PlaybookRevisionApplication] | None = None,
    active_revision: PlaybookRevision | None = None,
) -> tuple[
    PlaybookRevisionApplicationService,
    FakePlaybookRevisionApplicationRepository,
    FakePlaybookRevisionRepository,
    FakePlaybookRepository,
    FakeEvolutionProposalRepository,
    FakePlaybookRevisionActivationRepository,
]:
    application_repo = FakePlaybookRevisionApplicationRepository(applications)
    revision_repo = FakePlaybookRevisionRepository(revisions)
    playbook_repo = FakePlaybookRepository(playbooks)
    proposal_repo = FakeEvolutionProposalRepository(proposals)
    activation_repo = FakePlaybookRevisionActivationRepository(activations)
    activation_service = FakePlaybookRevisionActivationService(active_revision)
    service = PlaybookRevisionApplicationService(
        application_repo,
        revision_repo,
        playbook_repo,
        proposal_repo,
        activation_repo,
        activation_service,
    )

    return service, application_repo, revision_repo, playbook_repo, proposal_repo, activation_repo


def add_application(
    service: PlaybookRevisionApplicationService,
    playbook_id: UUID,
    revision_id: UUID,
    proposal_id: UUID,
    source_activation_id: UUID | None = None,
) -> PlaybookRevisionApplication:
    return service.add(
        playbook_id=playbook_id,
        revision_id=revision_id,
        proposal_id=proposal_id,
        reason="Record explicit application audit",
        applied_by="reviewer",
        notes="Foundation audit record",
        tags=("manual", "application"),
        source_activation_id=source_activation_id,
        idempotency_key="apply-1",
    )


def test_add_application_persists_application_record() -> None:
    playbook = make_playbook()
    proposal = make_proposal(playbook.id)
    revision = make_revision(playbook.id, proposal.id)
    activation = make_activation(playbook.id, revision.id, proposal.id)
    service, application_repo, _, _, _, activation_repo = make_service(
        [playbook],
        [revision],
        [proposal],
        [activation],
        active_revision=revision,
    )

    application = add_application(
        service,
        playbook.id,
        revision.id,
        proposal.id,
        activation.id,
    )

    assert application_repo.saved == [application]
    assert application.playbook_id == playbook.id
    assert application.revision_id == revision.id
    assert application.proposal_id == proposal.id
    assert application.source_activation_id == activation.id
    assert application.content_changed is False
    assert application.tags == ("manual", "application")
    assert isinstance(service._activation_service, FakePlaybookRevisionActivationService)
    assert service._activation_service.requested_playbook_ids == [playbook.id]
    assert activation_repo.load_all_calls == 0


def test_add_application_delegates_active_revision_resolution_without_loading_history() -> None:
    playbook = make_playbook()
    proposal = make_proposal(playbook.id)
    revision = make_revision(playbook.id, proposal.id)
    service, _, _, _, _, activation_repo = make_service(
        [playbook],
        [revision],
        [proposal],
        active_revision=revision,
    )

    add_application(service, playbook.id, revision.id, proposal.id)

    assert isinstance(service._activation_service, FakePlaybookRevisionActivationService)
    assert service._activation_service.requested_playbook_ids == [playbook.id]
    assert activation_repo.load_all_calls == 0
    assert activation_repo.requested_ids == []


def test_add_application_raises_when_playbook_is_missing() -> None:
    playbook_id = UUID("44444444-4444-4444-4444-444444444444")
    revision_id = UUID("55555555-5555-5555-5555-555555555555")
    proposal_id = UUID("66666666-6666-6666-6666-666666666666")
    service, application_repo, revision_repo, playbook_repo, proposal_repo, _ = make_service()

    with pytest.raises(PlaybookRevisionApplicationPlaybookNotFoundError) as error:
        add_application(service, playbook_id, revision_id, proposal_id)

    assert error.value.playbook_id == playbook_id
    assert playbook_repo.requested_ids == [playbook_id]
    assert revision_repo.requested_ids == []
    assert proposal_repo.requested_ids == []
    assert application_repo.saved == []


def test_add_application_raises_when_revision_is_missing() -> None:
    playbook = make_playbook()
    proposal_id = UUID("77777777-7777-7777-7777-777777777777")
    missing_revision_id = UUID("88888888-8888-8888-8888-888888888888")
    service, application_repo, revision_repo, _, proposal_repo, _ = make_service([playbook])

    with pytest.raises(PlaybookRevisionApplicationRevisionNotFoundError) as error:
        add_application(service, playbook.id, missing_revision_id, proposal_id)

    assert error.value.revision_id == missing_revision_id
    assert revision_repo.requested_ids == [missing_revision_id]
    assert proposal_repo.requested_ids == []
    assert application_repo.saved == []


def test_add_application_raises_when_proposal_is_missing() -> None:
    playbook = make_playbook()
    missing_proposal_id = UUID("99999999-9999-9999-9999-999999999999")
    revision = make_revision(playbook.id, missing_proposal_id)
    service, application_repo, _, _, proposal_repo, _ = make_service(
        [playbook],
        [revision],
    )

    with pytest.raises(PlaybookRevisionApplicationProposalNotFoundError) as error:
        add_application(service, playbook.id, revision.id, missing_proposal_id)

    assert error.value.proposal_id == missing_proposal_id
    assert proposal_repo.requested_ids == [missing_proposal_id]
    assert application_repo.saved == []


def test_add_application_raises_when_revision_belongs_to_other_playbook() -> None:
    playbook = make_playbook()
    other_playbook = make_playbook("Other playbook")
    proposal = make_proposal(playbook.id)
    revision = make_revision(other_playbook.id, proposal.id)
    service, application_repo, _, _, _, _ = make_service(
        [playbook],
        [revision],
        [proposal],
    )

    with pytest.raises(PlaybookRevisionApplicationRevisionPlaybookMismatchError) as error:
        add_application(service, playbook.id, revision.id, proposal.id)

    assert error.value.revision_id == revision.id
    assert error.value.expected_playbook_id == playbook.id
    assert error.value.actual_playbook_id == other_playbook.id
    assert application_repo.saved == []


def test_add_application_raises_when_revision_belongs_to_other_proposal() -> None:
    playbook = make_playbook()
    proposal = make_proposal(playbook.id)
    other_proposal = make_proposal(playbook.id)
    revision = make_revision(playbook.id, other_proposal.id)
    service, application_repo, _, _, _, _ = make_service(
        [playbook],
        [revision],
        [proposal, other_proposal],
    )

    with pytest.raises(PlaybookRevisionApplicationRevisionProposalMismatchError) as error:
        add_application(service, playbook.id, revision.id, proposal.id)

    assert error.value.revision_id == revision.id
    assert error.value.expected_proposal_id == proposal.id
    assert error.value.actual_proposal_id == other_proposal.id
    assert application_repo.saved == []


def test_add_application_raises_when_source_activation_is_missing() -> None:
    playbook = make_playbook()
    proposal = make_proposal(playbook.id)
    revision = make_revision(playbook.id, proposal.id)
    active_activation = make_activation(playbook.id, revision.id, proposal.id)
    missing_activation_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    service, application_repo, _, _, _, activation_repo = make_service(
        [playbook],
        [revision],
        [proposal],
        [active_activation],
    )

    with pytest.raises(PlaybookRevisionApplicationActivationNotFoundError) as error:
        add_application(service, playbook.id, revision.id, proposal.id, missing_activation_id)

    assert error.value.activation_id == missing_activation_id
    assert activation_repo.requested_ids == [missing_activation_id]
    assert application_repo.saved == []


def test_add_application_raises_when_source_activation_mismatches_relation() -> None:
    playbook = make_playbook()
    proposal = make_proposal(playbook.id)
    revision = make_revision(playbook.id, proposal.id)
    other_revision = make_revision(playbook.id, proposal.id, "Other candidate")
    active_activation = make_activation(playbook.id, revision.id, proposal.id)
    mismatched_activation = make_activation(playbook.id, other_revision.id, proposal.id)
    service, application_repo, _, _, _, _ = make_service(
        [playbook],
        [revision, other_revision],
        [proposal],
        [active_activation, mismatched_activation],
    )

    with pytest.raises(PlaybookRevisionApplicationActivationMismatchError) as error:
        add_application(service, playbook.id, revision.id, proposal.id, mismatched_activation.id)

    assert error.value.activation_id == mismatched_activation.id
    assert error.value.expected_revision_id == revision.id
    assert error.value.actual_revision_id == other_revision.id
    assert application_repo.saved == []


def test_add_application_requires_currently_active_revision() -> None:
    playbook = make_playbook()
    proposal = make_proposal(playbook.id)
    revision = make_revision(playbook.id, proposal.id)
    service, application_repo, _, _, _, _ = make_service(
        [playbook],
        [revision],
        [proposal],
    )

    with pytest.raises(PlaybookRevisionApplicationNoActiveRevisionError) as error:
        add_application(service, playbook.id, revision.id, proposal.id)

    assert error.value.playbook_id == playbook.id
    assert application_repo.saved == []


def test_add_application_rejects_inactive_revision_when_other_revision_is_active() -> None:
    playbook = make_playbook()
    proposal = make_proposal(playbook.id)
    revision = make_revision(playbook.id, proposal.id)
    other_revision = make_revision(playbook.id, proposal.id, "Active candidate")
    active_activation = make_activation(playbook.id, other_revision.id, proposal.id)
    service, application_repo, _, _, _, _ = make_service(
        [playbook],
        [revision, other_revision],
        [proposal],
        [active_activation],
        active_revision=other_revision,
    )

    with pytest.raises(PlaybookRevisionApplicationInactiveRevisionError) as error:
        add_application(service, playbook.id, revision.id, proposal.id)

    assert error.value.revision_id == revision.id
    assert error.value.active_revision_id == other_revision.id
    assert application_repo.saved == []


def test_add_application_requires_accepted_proposal_status() -> None:
    playbook = make_playbook()
    proposal = make_proposal(playbook.id, status=EvolutionProposalStatus.DRAFT)
    revision = make_revision(playbook.id, proposal.id)
    service, application_repo, _, _, _, _ = make_service(
        [playbook],
        [revision],
        [proposal],
    )

    with pytest.raises(PlaybookRevisionApplicationProposalNotAcceptedError) as error:
        add_application(service, playbook.id, revision.id, proposal.id)

    assert error.value.proposal_id == proposal.id
    assert error.value.actual_status == EvolutionProposalStatus.DRAFT
    assert application_repo.saved == []


def test_add_application_does_not_mutate_source_records_or_call_unrelated_saves() -> None:
    playbook = make_playbook()
    proposal = make_proposal(playbook.id)
    revision = make_revision(playbook.id, proposal.id)
    activation = make_activation(playbook.id, revision.id, proposal.id)
    original_playbook = playbook.model_copy(deep=True)
    original_revision = revision.model_copy(deep=True)
    original_proposal = proposal.model_copy(deep=True)
    original_activation = activation.model_copy(deep=True)
    (
        service,
        _,
        revision_repo,
        playbook_repo,
        proposal_repo,
        activation_repo,
    ) = make_service(
        [playbook],
        [revision],
        [proposal],
        [activation],
        active_revision=revision,
    )

    add_application(service, playbook.id, revision.id, proposal.id, activation.id)

    assert playbook == original_playbook
    assert revision == original_revision
    assert proposal == original_proposal
    assert activation == original_activation
    assert playbook_repo.save_calls == []
    assert revision_repo.save_calls == []
    assert proposal_repo.save_calls == []
    assert activation_repo.save_calls == []
    assert activation_repo.load_all_calls == 0


def test_list_for_playbook_verifies_playbook_filters_and_preserves_order() -> None:
    playbook = make_playbook()
    other_playbook = make_playbook("Other playbook")
    proposal = make_proposal(playbook.id)
    first = make_application(playbook.id, UUID("11111111-2222-3333-4444-555555555555"), proposal.id)
    unrelated = make_application(
        other_playbook.id,
        UUID("22222222-3333-4444-5555-666666666666"),
        proposal.id,
    )
    second = make_application(
        playbook.id, UUID("33333333-4444-5555-6666-777777777777"), proposal.id
    )
    service, application_repo, _, _, _, _ = make_service(
        [playbook, other_playbook],
        applications=[second, unrelated, first],
    )

    assert service.list_for_playbook(playbook.id) == [second, first]
    assert application_repo.load_all_calls == 1
    assert application_repo.save_calls == []


def test_list_for_playbook_raises_when_playbook_missing_and_does_not_load() -> None:
    missing_id = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    service, application_repo, _, playbook_repo, _, _ = make_service()

    with pytest.raises(PlaybookRevisionApplicationPlaybookNotFoundError) as error:
        service.list_for_playbook(missing_id)

    assert error.value.playbook_id == missing_id
    assert playbook_repo.requested_ids == [missing_id]
    assert application_repo.load_all_calls == 0


def test_list_for_playbook_returns_empty_list_when_no_records_match() -> None:
    playbook = make_playbook()
    service, _, _, _, _, _ = make_service([playbook], applications=[])

    assert service.list_for_playbook(playbook.id) == []


def test_list_for_revision_verifies_revision_filters_and_preserves_order() -> None:
    playbook = make_playbook()
    proposal = make_proposal(playbook.id)
    revision = make_revision(playbook.id, proposal.id)
    other_revision = make_revision(playbook.id, proposal.id, "Other")
    first = make_application(playbook.id, revision.id, proposal.id, "First")
    unrelated = make_application(playbook.id, other_revision.id, proposal.id, "Other")
    second = make_application(playbook.id, revision.id, proposal.id, "Second")
    service, application_repo, _, _, _, _ = make_service(
        [playbook],
        [revision, other_revision],
        [proposal],
        applications=[second, unrelated, first],
    )

    assert service.list_for_revision(revision.id) == [second, first]
    assert application_repo.save_calls == []


def test_list_for_revision_raises_when_revision_missing_and_does_not_load() -> None:
    missing_id = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
    service, application_repo, revision_repo, _, _, _ = make_service()

    with pytest.raises(PlaybookRevisionApplicationRevisionNotFoundError) as error:
        service.list_for_revision(missing_id)

    assert error.value.revision_id == missing_id
    assert revision_repo.requested_ids == [missing_id]
    assert application_repo.load_all_calls == 0


def test_list_for_revision_returns_empty_list_when_no_records_match() -> None:
    playbook = make_playbook()
    proposal = make_proposal(playbook.id)
    revision = make_revision(playbook.id, proposal.id)
    service, _, _, _, _, _ = make_service([playbook], [revision], [proposal], applications=[])

    assert service.list_for_revision(revision.id) == []


def test_list_for_proposal_verifies_proposal_filters_and_preserves_order() -> None:
    playbook = make_playbook()
    proposal = make_proposal(playbook.id)
    other_proposal = make_proposal(playbook.id)
    first = make_application(playbook.id, UUID("dddddddd-dddd-dddd-dddd-dddddddddddd"), proposal.id)
    unrelated = make_application(
        playbook.id,
        UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"),
        other_proposal.id,
    )
    second = make_application(
        playbook.id, UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"), proposal.id
    )
    service, application_repo, _, _, _, _ = make_service(
        [playbook],
        proposals=[proposal, other_proposal],
        applications=[second, unrelated, first],
    )

    assert service.list_for_proposal(proposal.id) == [second, first]
    assert application_repo.save_calls == []


def test_list_for_proposal_raises_when_proposal_missing_and_does_not_load() -> None:
    missing_id = UUID("12121212-1212-1212-1212-121212121212")
    service, application_repo, _, _, proposal_repo, _ = make_service()

    with pytest.raises(PlaybookRevisionApplicationProposalNotFoundError) as error:
        service.list_for_proposal(missing_id)

    assert error.value.proposal_id == missing_id
    assert proposal_repo.requested_ids == [missing_id]
    assert application_repo.load_all_calls == 0


def test_list_for_proposal_returns_empty_list_when_no_records_match() -> None:
    playbook = make_playbook()
    proposal = make_proposal(playbook.id)
    service, _, _, _, _, _ = make_service([playbook], proposals=[proposal], applications=[])

    assert service.list_for_proposal(proposal.id) == []

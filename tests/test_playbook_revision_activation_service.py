from uuid import UUID

import pytest

from neural_engine.application.playbook_revision_activation_service import (
    PlaybookRevisionActivationPlaybookNotFoundError,
    PlaybookRevisionActivationPreviousRevisionForbiddenError,
    PlaybookRevisionActivationPreviousRevisionNotFoundError,
    PlaybookRevisionActivationPreviousRevisionPlaybookMismatchError,
    PlaybookRevisionActivationPreviousRevisionRequiredError,
    PlaybookRevisionActivationProposalNotFoundError,
    PlaybookRevisionActivationRevisionNotFoundError,
    PlaybookRevisionActivationRevisionPlaybookMismatchError,
    PlaybookRevisionActivationRevisionProposalMismatchError,
    PlaybookRevisionActivationService,
)
from neural_engine.domain import (
    EvolutionProposal,
    EvolutionProposalStatus,
    Playbook,
    PlaybookRevision,
    PlaybookRevisionActivation,
    PlaybookRevisionActivationDecision,
)
from neural_engine.ports.evolution_proposal_repository import (
    EvolutionProposalRepository,
)
from neural_engine.ports.playbook_repository import PlaybookRepository
from neural_engine.ports.playbook_revision_activation_repository import (
    PlaybookRevisionActivationRepository,
)
from neural_engine.ports.playbook_revision_repository import (
    PlaybookRevisionRepository,
)


class FakePlaybookRevisionActivationRepository(PlaybookRevisionActivationRepository):
    def __init__(
        self,
        revision_repository: FakePlaybookRevisionRepository,
        playbook_repository: FakePlaybookRepository,
        proposal_repository: FakeEvolutionProposalRepository,
    ) -> None:
        self.saved: list[PlaybookRevisionActivation] = []
        self.save_calls: list[PlaybookRevisionActivation] = []
        self.load_all_calls = 0
        self.requested_ids: list[UUID] = []
        self.revision_lookups_at_load: list[UUID] = []
        self.playbook_lookups_at_load: list[UUID] = []
        self.proposal_lookups_at_load: list[UUID] = []
        self.revision_lookups_at_save: list[UUID] = []
        self.playbook_lookups_at_save: list[UUID] = []
        self.proposal_lookups_at_save: list[UUID] = []
        self._revision_repository = revision_repository
        self._playbook_repository = playbook_repository
        self._proposal_repository = proposal_repository

    def save(self, activation: PlaybookRevisionActivation) -> None:
        self.save_calls.append(activation)
        self.revision_lookups_at_save = list(self._revision_repository.requested_ids)
        self.playbook_lookups_at_save = list(self._playbook_repository.requested_ids)
        self.proposal_lookups_at_save = list(self._proposal_repository.requested_ids)
        self.saved.append(activation)

    def load_all(self) -> list[PlaybookRevisionActivation]:
        self.load_all_calls += 1
        self.revision_lookups_at_load = list(self._revision_repository.requested_ids)
        self.playbook_lookups_at_load = list(self._playbook_repository.requested_ids)
        self.proposal_lookups_at_load = list(self._proposal_repository.requested_ids)
        return self.saved

    def get_by_id(self, activation_id: UUID) -> PlaybookRevisionActivation | None:
        self.requested_ids.append(activation_id)

        for activation in self.saved:
            if activation.id == activation_id:
                return activation

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


def make_playbook(title: str = "Activation playbook") -> Playbook:
    return Playbook(
        title=title,
        situation="A candidate revision is ready",
        objective="Record the lifecycle decision",
        steps=["Review candidate revision"],
        success_criteria=["Decision is auditable"],
        knowledge_ids=[UUID("11111111-1111-1111-1111-111111111111")],
    )


def make_proposal(playbook_id: UUID) -> EvolutionProposal:
    return EvolutionProposal(
        playbook_id=playbook_id,
        evaluation_ids=[UUID("22222222-2222-2222-2222-222222222222")],
        summary="Manual proposal",
        rationale="Manual review identified a useful change",
        proposed_changes=["Clarify the activation step"],
        expected_benefits=["The lifecycle is easier to audit"],
    )


def make_revision(
    playbook_id: UUID,
    proposal_id: UUID,
    title: str = "Activation candidate",
) -> PlaybookRevision:
    return PlaybookRevision(
        playbook_id=playbook_id,
        proposal_id=proposal_id,
        title=title,
        situation="Activation service test",
        objective="Persist an explicit decision",
        steps=["Validate linked aggregates"],
        success_criteria=["Activation is saved only after validation"],
        knowledge_ids=[UUID("33333333-3333-3333-3333-333333333333")],
    )


def make_service(
    playbooks: list[Playbook] | None = None,
    revisions: list[PlaybookRevision] | None = None,
    proposals: list[EvolutionProposal] | None = None,
) -> tuple[
    PlaybookRevisionActivationService,
    FakePlaybookRevisionActivationRepository,
    FakePlaybookRevisionRepository,
    FakePlaybookRepository,
    FakeEvolutionProposalRepository,
]:
    revision_repo = FakePlaybookRevisionRepository(revisions)
    playbook_repo = FakePlaybookRepository(playbooks)
    proposal_repo = FakeEvolutionProposalRepository(proposals)
    activation_repo = FakePlaybookRevisionActivationRepository(
        revision_repo,
        playbook_repo,
        proposal_repo,
    )
    service = PlaybookRevisionActivationService(
        activation_repo,
        revision_repo,
        playbook_repo,
        proposal_repo,
    )

    return service, activation_repo, revision_repo, playbook_repo, proposal_repo


def add_activation(
    service: PlaybookRevisionActivationService,
    playbook_id: UUID,
    revision_id: UUID,
    proposal_id: UUID,
    decision: PlaybookRevisionActivationDecision = PlaybookRevisionActivationDecision.ACTIVE,
    previous_revision_id: UUID | None = None,
) -> PlaybookRevisionActivation:
    return service.add(
        playbook_id=playbook_id,
        revision_id=revision_id,
        proposal_id=proposal_id,
        decision=decision,
        reason="Manual lifecycle decision",
        previous_revision_id=previous_revision_id,
        decided_by="reviewer",
        notes="Explicit application-service record",
        tags=["manual", "activation"],
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
        reason="Recorded lifecycle decision",
        previous_revision_id=previous_revision_id,
    )


def test_add_activation_persists_explicit_decision() -> None:
    playbook = make_playbook()
    proposal = make_proposal(playbook.id)
    revision = make_revision(playbook.id, proposal.id)
    service, activation_repo, _, _, _ = make_service([playbook], [revision], [proposal])

    activation = add_activation(service, playbook.id, revision.id, proposal.id)

    assert activation_repo.saved == [activation]
    assert activation.playbook_id == playbook.id
    assert activation.revision_id == revision.id
    assert activation.proposal_id == proposal.id
    assert activation.decision == PlaybookRevisionActivationDecision.ACTIVE
    assert activation.reason == "Manual lifecycle decision"
    assert activation.previous_revision_id is None
    assert activation.decided_by == "reviewer"
    assert activation.notes == "Explicit application-service record"
    assert activation.tags == ["manual", "activation"]


def test_add_activation_does_not_require_accepted_proposal_status() -> None:
    playbook = make_playbook()
    proposal = make_proposal(playbook.id)
    revision = make_revision(playbook.id, proposal.id)
    service, activation_repo, _, _, _ = make_service([playbook], [revision], [proposal])

    activation = add_activation(service, playbook.id, revision.id, proposal.id)

    assert activation_repo.saved == [activation]


def test_add_superseded_activation_requires_existing_previous_revision() -> None:
    playbook = make_playbook()
    proposal = make_proposal(playbook.id)
    revision = make_revision(playbook.id, proposal.id, "New candidate")
    previous_revision = make_revision(playbook.id, proposal.id, "Previous candidate")
    service, activation_repo, _, _, _ = make_service(
        [playbook],
        [revision, previous_revision],
        [proposal],
    )

    activation = add_activation(
        service,
        playbook.id,
        revision.id,
        proposal.id,
        PlaybookRevisionActivationDecision.SUPERSEDED,
        previous_revision.id,
    )

    assert activation_repo.saved == [activation]
    assert activation.previous_revision_id == previous_revision.id


def test_add_rejected_activation_forbids_previous_revision() -> None:
    playbook = make_playbook()
    proposal = make_proposal(playbook.id)
    revision = make_revision(playbook.id, proposal.id)
    previous_revision_id = UUID("44444444-4444-4444-4444-444444444444")
    service, activation_repo, revision_repo, _, _ = make_service(
        [playbook],
        [revision],
        [proposal],
    )

    with pytest.raises(PlaybookRevisionActivationPreviousRevisionForbiddenError) as error:
        add_activation(
            service,
            playbook.id,
            revision.id,
            proposal.id,
            PlaybookRevisionActivationDecision.REJECTED,
            previous_revision_id,
        )

    assert error.value.previous_revision_id == previous_revision_id
    assert revision_repo.requested_ids == [revision.id]
    assert activation_repo.saved == []


def test_add_activation_raises_when_playbook_is_missing() -> None:
    playbook_id = UUID("55555555-5555-5555-5555-555555555555")
    revision_id = UUID("66666666-6666-6666-6666-666666666666")
    proposal_id = UUID("77777777-7777-7777-7777-777777777777")
    service, activation_repo, revision_repo, playbook_repo, proposal_repo = make_service()

    with pytest.raises(PlaybookRevisionActivationPlaybookNotFoundError) as error:
        add_activation(service, playbook_id, revision_id, proposal_id)

    assert error.value.playbook_id == playbook_id
    assert playbook_repo.requested_ids == [playbook_id]
    assert revision_repo.requested_ids == []
    assert proposal_repo.requested_ids == []
    assert activation_repo.saved == []


def test_add_activation_raises_when_revision_is_missing() -> None:
    playbook = make_playbook()
    proposal_id = UUID("88888888-8888-8888-8888-888888888888")
    missing_revision_id = UUID("99999999-9999-9999-9999-999999999999")
    service, activation_repo, revision_repo, _, proposal_repo = make_service([playbook])

    with pytest.raises(PlaybookRevisionActivationRevisionNotFoundError) as error:
        add_activation(service, playbook.id, missing_revision_id, proposal_id)

    assert error.value.revision_id == missing_revision_id
    assert revision_repo.requested_ids == [missing_revision_id]
    assert proposal_repo.requested_ids == []
    assert activation_repo.saved == []


def test_add_activation_raises_when_proposal_is_missing() -> None:
    playbook = make_playbook()
    missing_proposal_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    revision = make_revision(playbook.id, missing_proposal_id)
    service, activation_repo, _, _, proposal_repo = make_service([playbook], [revision])

    with pytest.raises(PlaybookRevisionActivationProposalNotFoundError) as error:
        add_activation(service, playbook.id, revision.id, missing_proposal_id)

    assert error.value.proposal_id == missing_proposal_id
    assert proposal_repo.requested_ids == [missing_proposal_id]
    assert activation_repo.saved == []


def test_add_activation_raises_when_revision_belongs_to_other_playbook() -> None:
    playbook = make_playbook()
    other_playbook = make_playbook("Other playbook")
    proposal = make_proposal(playbook.id)
    revision = make_revision(other_playbook.id, proposal.id)
    service, activation_repo, _, _, _ = make_service([playbook], [revision], [proposal])

    with pytest.raises(PlaybookRevisionActivationRevisionPlaybookMismatchError) as error:
        add_activation(service, playbook.id, revision.id, proposal.id)

    assert error.value.revision_id == revision.id
    assert error.value.expected_playbook_id == playbook.id
    assert error.value.actual_playbook_id == other_playbook.id
    assert activation_repo.saved == []


def test_add_activation_raises_when_revision_belongs_to_other_proposal() -> None:
    playbook = make_playbook()
    proposal = make_proposal(playbook.id)
    other_proposal = make_proposal(playbook.id)
    revision = make_revision(playbook.id, other_proposal.id)
    service, activation_repo, _, _, _ = make_service(
        [playbook],
        [revision],
        [proposal, other_proposal],
    )

    with pytest.raises(PlaybookRevisionActivationRevisionProposalMismatchError) as error:
        add_activation(service, playbook.id, revision.id, proposal.id)

    assert error.value.revision_id == revision.id
    assert error.value.expected_proposal_id == proposal.id
    assert error.value.actual_proposal_id == other_proposal.id
    assert activation_repo.saved == []


def test_add_superseded_activation_requires_previous_revision_id() -> None:
    playbook = make_playbook()
    proposal = make_proposal(playbook.id)
    revision = make_revision(playbook.id, proposal.id)
    service, activation_repo, revision_repo, _, _ = make_service([playbook], [revision], [proposal])

    with pytest.raises(PlaybookRevisionActivationPreviousRevisionRequiredError):
        add_activation(
            service,
            playbook.id,
            revision.id,
            proposal.id,
            PlaybookRevisionActivationDecision.SUPERSEDED,
        )

    assert revision_repo.requested_ids == [revision.id]
    assert activation_repo.saved == []


def test_add_superseded_activation_raises_when_previous_revision_is_missing() -> None:
    playbook = make_playbook()
    proposal = make_proposal(playbook.id)
    revision = make_revision(playbook.id, proposal.id)
    missing_previous_id = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    service, activation_repo, revision_repo, _, _ = make_service([playbook], [revision], [proposal])

    with pytest.raises(PlaybookRevisionActivationPreviousRevisionNotFoundError) as error:
        add_activation(
            service,
            playbook.id,
            revision.id,
            proposal.id,
            PlaybookRevisionActivationDecision.SUPERSEDED,
            missing_previous_id,
        )

    assert error.value.previous_revision_id == missing_previous_id
    assert revision_repo.requested_ids == [revision.id, missing_previous_id]
    assert activation_repo.saved == []


def test_add_superseded_activation_raises_when_previous_revision_belongs_to_other_playbook() -> (
    None
):
    playbook = make_playbook()
    other_playbook = make_playbook("Other playbook")
    proposal = make_proposal(playbook.id)
    revision = make_revision(playbook.id, proposal.id)
    previous_revision = make_revision(other_playbook.id, proposal.id, "Other previous")
    service, activation_repo, _, _, _ = make_service(
        [playbook],
        [revision, previous_revision],
        [proposal],
    )

    with pytest.raises(PlaybookRevisionActivationPreviousRevisionPlaybookMismatchError) as error:
        add_activation(
            service,
            playbook.id,
            revision.id,
            proposal.id,
            PlaybookRevisionActivationDecision.SUPERSEDED,
            previous_revision.id,
        )

    assert error.value.previous_revision_id == previous_revision.id
    assert error.value.expected_playbook_id == playbook.id
    assert error.value.actual_playbook_id == other_playbook.id
    assert activation_repo.saved == []


def test_add_activation_performs_all_lookups_before_saving() -> None:
    playbook = make_playbook()
    proposal = make_proposal(playbook.id)
    revision = make_revision(playbook.id, proposal.id)
    service, activation_repo, _, _, _ = make_service([playbook], [revision], [proposal])

    add_activation(service, playbook.id, revision.id, proposal.id)

    assert activation_repo.playbook_lookups_at_save == [playbook.id]
    assert activation_repo.revision_lookups_at_save == [revision.id]
    assert activation_repo.proposal_lookups_at_save == [proposal.id]


def test_add_superseded_activation_performs_previous_revision_lookup_before_saving() -> None:
    playbook = make_playbook()
    proposal = make_proposal(playbook.id)
    revision = make_revision(playbook.id, proposal.id, "New candidate")
    previous_revision = make_revision(playbook.id, proposal.id, "Previous candidate")
    service, activation_repo, _, _, _ = make_service(
        [playbook],
        [revision, previous_revision],
        [proposal],
    )

    add_activation(
        service,
        playbook.id,
        revision.id,
        proposal.id,
        PlaybookRevisionActivationDecision.SUPERSEDED,
        previous_revision.id,
    )

    assert activation_repo.revision_lookups_at_save == [revision.id, previous_revision.id]


def test_list_for_playbook_returns_only_linked_activation_records() -> None:
    playbook = make_playbook()
    other_playbook = make_playbook("Other playbook")
    proposal = make_proposal(playbook.id)
    other_proposal = make_proposal(other_playbook.id)
    first = make_activation(
        playbook.id,
        UUID("11111111-2222-3333-4444-555555555555"),
        proposal.id,
    )
    unrelated = make_activation(
        other_playbook.id,
        UUID("22222222-3333-4444-5555-666666666666"),
        other_proposal.id,
    )
    second = make_activation(
        playbook.id,
        UUID("33333333-4444-5555-6666-777777777777"),
        proposal.id,
    )
    service, activation_repo, _, _, _ = make_service([playbook, other_playbook])
    activation_repo.saved = [first, unrelated, second]

    assert service.list_for_playbook(playbook.id) == [first, second]


def test_list_for_playbook_preserves_repository_order() -> None:
    playbook = make_playbook()
    proposal = make_proposal(playbook.id)
    first = make_activation(
        playbook.id,
        UUID("44444444-5555-6666-7777-888888888888"),
        proposal.id,
    )
    second = make_activation(
        playbook.id,
        UUID("55555555-6666-7777-8888-999999999999"),
        proposal.id,
    )
    service, activation_repo, _, _, _ = make_service([playbook])
    activation_repo.saved = [second, first]

    assert service.list_for_playbook(playbook.id) == [second, first]


def test_list_for_playbook_raises_when_playbook_is_missing() -> None:
    missing_id = UUID("66666666-7777-8888-9999-aaaaaaaaaaaa")
    service, activation_repo, revision_repo, playbook_repo, _ = make_service()

    with pytest.raises(PlaybookRevisionActivationPlaybookNotFoundError) as error:
        service.list_for_playbook(missing_id)

    assert error.value.playbook_id == missing_id
    assert playbook_repo.requested_ids == [missing_id]
    assert activation_repo.load_all_calls == 0
    assert revision_repo.requested_ids == []


def test_list_for_playbook_does_not_call_revision_repository() -> None:
    playbook = make_playbook()
    proposal = make_proposal(playbook.id)
    activation = make_activation(
        playbook.id,
        UUID("77777777-8888-9999-aaaa-bbbbbbbbbbbb"),
        proposal.id,
    )
    service, activation_repo, revision_repo, _, _ = make_service([playbook])
    activation_repo.saved = [activation]

    assert service.list_for_playbook(playbook.id) == [activation]
    assert revision_repo.requested_ids == []
    assert activation_repo.revision_lookups_at_load == []


def test_list_for_playbook_does_not_mutate_records() -> None:
    playbook = make_playbook()
    proposal = make_proposal(playbook.id)
    revision = make_revision(playbook.id, proposal.id)
    activation = make_activation(playbook.id, revision.id, proposal.id)
    original_playbook = playbook.model_copy(deep=True)
    original_revision = revision.model_copy(deep=True)
    original_proposal = proposal.model_copy(deep=True)
    original_activation = activation.model_copy(deep=True)
    service, activation_repo, _, _, _ = make_service([playbook], [revision], [proposal])
    activation_repo.saved = [activation]

    result = service.list_for_playbook(playbook.id)

    assert result == [activation]
    assert playbook == original_playbook
    assert revision == original_revision
    assert proposal == original_proposal
    assert activation == original_activation
    assert activation_repo.save_calls == []


def test_get_active_revision_for_playbook_returns_none_without_activation_records() -> None:
    playbook = make_playbook()
    service, activation_repo, revision_repo, _, _ = make_service([playbook])

    assert service.get_active_revision_for_playbook(playbook.id) is None
    assert activation_repo.load_all_calls == 1
    assert revision_repo.requested_ids == []


def test_get_active_revision_for_playbook_returns_revision_after_active_record() -> None:
    playbook = make_playbook()
    proposal = make_proposal(playbook.id)
    revision = make_revision(playbook.id, proposal.id)
    activation = make_activation(playbook.id, revision.id, proposal.id)
    service, activation_repo, _, _, _ = make_service([playbook], [revision], [proposal])
    activation_repo.saved = [activation]

    assert service.get_active_revision_for_playbook(playbook.id) == revision


def test_get_active_revision_for_playbook_later_active_overrides_earlier_active() -> None:
    playbook = make_playbook()
    proposal = make_proposal(playbook.id)
    first_revision = make_revision(playbook.id, proposal.id, "First candidate")
    second_revision = make_revision(playbook.id, proposal.id, "Second candidate")
    service, activation_repo, _, _, _ = make_service(
        [playbook],
        [first_revision, second_revision],
        [proposal],
    )
    activation_repo.saved = [
        make_activation(playbook.id, first_revision.id, proposal.id),
        make_activation(playbook.id, second_revision.id, proposal.id),
    ]

    assert service.get_active_revision_for_playbook(playbook.id) == second_revision


def test_get_active_revision_for_playbook_superseded_moves_from_previous_to_new() -> None:
    playbook = make_playbook()
    proposal = make_proposal(playbook.id)
    previous_revision = make_revision(playbook.id, proposal.id, "Previous candidate")
    new_revision = make_revision(playbook.id, proposal.id, "New candidate")
    service, activation_repo, _, _, _ = make_service(
        [playbook],
        [previous_revision, new_revision],
        [proposal],
    )
    activation_repo.saved = [
        make_activation(playbook.id, previous_revision.id, proposal.id),
        make_activation(
            playbook.id,
            new_revision.id,
            proposal.id,
            PlaybookRevisionActivationDecision.SUPERSEDED,
            previous_revision.id,
        ),
    ]

    assert service.get_active_revision_for_playbook(playbook.id) == new_revision


def test_get_active_revision_for_playbook_superseded_sets_active_when_none_exists() -> None:
    playbook = make_playbook()
    proposal = make_proposal(playbook.id)
    previous_revision_id = UUID("88888888-9999-aaaa-bbbb-cccccccccccc")
    revision = make_revision(playbook.id, proposal.id)
    service, activation_repo, _, _, _ = make_service([playbook], [revision], [proposal])
    activation_repo.saved = [
        make_activation(
            playbook.id,
            revision.id,
            proposal.id,
            PlaybookRevisionActivationDecision.SUPERSEDED,
            previous_revision_id,
        )
    ]

    assert service.get_active_revision_for_playbook(playbook.id) == revision


def test_get_active_revision_for_playbook_rejected_clears_current_active_revision() -> None:
    playbook = make_playbook()
    proposal = make_proposal(playbook.id)
    revision = make_revision(playbook.id, proposal.id)
    service, activation_repo, revision_repo, _, _ = make_service([playbook], [revision], [proposal])
    activation_repo.saved = [
        make_activation(playbook.id, revision.id, proposal.id),
        make_activation(
            playbook.id,
            revision.id,
            proposal.id,
            PlaybookRevisionActivationDecision.REJECTED,
        ),
    ]

    assert service.get_active_revision_for_playbook(playbook.id) is None
    assert revision_repo.requested_ids == []


def test_get_active_revision_for_playbook_rejected_non_active_revision_does_not_clear() -> None:
    playbook = make_playbook()
    proposal = make_proposal(playbook.id)
    active_revision = make_revision(playbook.id, proposal.id, "Active candidate")
    rejected_revision = make_revision(playbook.id, proposal.id, "Rejected candidate")
    service, activation_repo, _, _, _ = make_service(
        [playbook],
        [active_revision, rejected_revision],
        [proposal],
    )
    activation_repo.saved = [
        make_activation(playbook.id, active_revision.id, proposal.id),
        make_activation(
            playbook.id,
            rejected_revision.id,
            proposal.id,
            PlaybookRevisionActivationDecision.REJECTED,
        ),
    ]

    assert service.get_active_revision_for_playbook(playbook.id) == active_revision


def test_get_active_revision_for_playbook_ignores_other_playbook_records() -> None:
    playbook = make_playbook()
    other_playbook = make_playbook("Other playbook")
    proposal = make_proposal(playbook.id)
    other_proposal = make_proposal(other_playbook.id)
    revision = make_revision(playbook.id, proposal.id)
    other_revision = make_revision(other_playbook.id, other_proposal.id)
    service, activation_repo, _, _, _ = make_service(
        [playbook, other_playbook],
        [revision, other_revision],
        [proposal, other_proposal],
    )
    activation_repo.saved = [
        make_activation(other_playbook.id, other_revision.id, other_proposal.id),
        make_activation(playbook.id, revision.id, proposal.id),
    ]

    assert service.get_active_revision_for_playbook(playbook.id) == revision


def test_get_active_revision_for_playbook_raises_when_derived_revision_is_missing() -> None:
    playbook = make_playbook()
    proposal = make_proposal(playbook.id)
    missing_revision_id = UUID("99999999-aaaa-bbbb-cccc-dddddddddddd")
    service, activation_repo, revision_repo, _, _ = make_service([playbook], proposals=[proposal])
    activation_repo.saved = [make_activation(playbook.id, missing_revision_id, proposal.id)]

    with pytest.raises(PlaybookRevisionActivationRevisionNotFoundError) as error:
        service.get_active_revision_for_playbook(playbook.id)

    assert error.value.revision_id == missing_revision_id
    assert revision_repo.requested_ids == [missing_revision_id]


def test_get_active_revision_for_playbook_raises_when_derived_revision_belongs_elsewhere() -> None:
    playbook = make_playbook()
    other_playbook = make_playbook("Other playbook")
    proposal = make_proposal(playbook.id)
    revision = make_revision(other_playbook.id, proposal.id)
    service, activation_repo, _, _, _ = make_service(
        [playbook, other_playbook],
        [revision],
        [proposal],
    )
    activation_repo.saved = [make_activation(playbook.id, revision.id, proposal.id)]

    with pytest.raises(PlaybookRevisionActivationRevisionPlaybookMismatchError) as error:
        service.get_active_revision_for_playbook(playbook.id)

    assert error.value.revision_id == revision.id
    assert error.value.expected_playbook_id == playbook.id
    assert error.value.actual_playbook_id == other_playbook.id


def test_get_active_revision_for_playbook_does_not_validate_knowledge_existence() -> None:
    playbook = make_playbook()
    proposal = make_proposal(playbook.id)
    revision = PlaybookRevision(
        playbook_id=playbook.id,
        proposal_id=proposal.id,
        title="Candidate with external knowledge reference",
        situation="Knowledge is not loaded during inspection",
        objective="Return active revision",
        steps=["Inspect lifecycle records"],
        success_criteria=["No knowledge lookup is needed"],
        knowledge_ids=[UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")],
    )
    service, activation_repo, _, _, _ = make_service([playbook], [revision], [proposal])
    activation_repo.saved = [make_activation(playbook.id, revision.id, proposal.id)]

    assert service.get_active_revision_for_playbook(playbook.id) == revision


def test_get_active_revision_for_playbook_does_not_validate_or_mutate_proposal_status() -> None:
    playbook = make_playbook()
    proposal = EvolutionProposal(
        playbook_id=playbook.id,
        evaluation_ids=[UUID("bbbbbbbb-cccc-dddd-eeee-ffffffffffff")],
        summary="Rejected proposal with historical activation",
        rationale="Imported lifecycle records may reference old decisions",
        proposed_changes=["Keep inspection read-only"],
        expected_benefits=["No proposal mutation"],
        status=EvolutionProposalStatus.REJECTED,
    )
    revision = make_revision(playbook.id, proposal.id)
    original_proposal = proposal.model_copy(deep=True)
    service, activation_repo, _, _, proposal_repo = make_service([playbook], [revision], [proposal])
    activation_repo.saved = [make_activation(playbook.id, revision.id, proposal.id)]

    assert service.get_active_revision_for_playbook(playbook.id) == revision
    assert proposal == original_proposal
    assert proposal_repo.requested_ids == []


def test_get_active_revision_for_playbook_does_not_save_activation_records() -> None:
    playbook = make_playbook()
    proposal = make_proposal(playbook.id)
    revision = make_revision(playbook.id, proposal.id)
    activation = make_activation(playbook.id, revision.id, proposal.id)
    service, activation_repo, _, _, _ = make_service([playbook], [revision], [proposal])
    activation_repo.saved = [activation]

    assert service.get_active_revision_for_playbook(playbook.id) == revision
    assert activation_repo.saved == [activation]
    assert activation_repo.save_calls == []


def test_get_active_revision_for_playbook_uses_repository_ports() -> None:
    playbook = make_playbook()
    proposal = make_proposal(playbook.id)
    revision = make_revision(playbook.id, proposal.id)
    service, activation_repo, revision_repo, playbook_repo, proposal_repo = make_service(
        [playbook],
        [revision],
        [proposal],
    )
    activation_repo.saved = [make_activation(playbook.id, revision.id, proposal.id)]

    assert service.get_active_revision_for_playbook(playbook.id) == revision
    assert playbook_repo.requested_ids == [playbook.id]
    assert activation_repo.load_all_calls == 1
    assert revision_repo.requested_ids == [revision.id]
    assert proposal_repo.requested_ids == []

from datetime import UTC
from uuid import UUID

from neural_engine.domain import EvolutionProposal, EvolutionProposalStatus


def test_evolution_proposal_has_domain_defaults_and_preserves_required_fields() -> None:
    playbook_id = UUID("11111111-1111-1111-1111-111111111111")
    evaluation_id = UUID("22222222-2222-2222-2222-222222222222")

    proposal = EvolutionProposal(
        playbook_id=playbook_id,
        evaluation_ids=[evaluation_id],
        summary="Clarify recovery steps",
        rationale="Evaluations showed unclear verification",
        proposed_changes=["Add verification step"],
        expected_benefits=["Faster manual recovery"],
    )

    assert isinstance(proposal.id, UUID)
    assert proposal.timestamp.tzinfo == UTC
    assert proposal.playbook_id == playbook_id
    assert proposal.evaluation_ids == [evaluation_id]
    assert proposal.summary == "Clarify recovery steps"
    assert proposal.rationale == "Evaluations showed unclear verification"
    assert proposal.proposed_changes == ["Add verification step"]
    assert proposal.expected_benefits == ["Faster manual recovery"]
    assert proposal.risks == []
    assert proposal.status == EvolutionProposalStatus.DRAFT
    assert proposal.notes is None
    assert proposal.tags == []


def test_evolution_proposal_preserves_optional_fields() -> None:
    proposal = EvolutionProposal(
        playbook_id=UUID("33333333-3333-3333-3333-333333333333"),
        evaluation_ids=[UUID("44444444-4444-4444-4444-444444444444")],
        summary="Improve rollback",
        rationale="Manual review found a risk",
        proposed_changes=["Add rollback decision point"],
        expected_benefits=["Lower incident duration"],
        risks=["Longer checklist"],
        status=EvolutionProposalStatus.ACCEPTED,
        notes="Accepted by external process",
        tags=["ops", "manual"],
    )

    assert proposal.risks == ["Longer checklist"]
    assert proposal.status == EvolutionProposalStatus.ACCEPTED
    assert proposal.notes == "Accepted by external process"
    assert proposal.tags == ["ops", "manual"]


def test_evolution_proposal_accepts_all_status_values() -> None:
    for status in EvolutionProposalStatus:
        proposal = EvolutionProposal(
            playbook_id=UUID("55555555-5555-5555-5555-555555555555"),
            evaluation_ids=[UUID("66666666-6666-6666-6666-666666666666")],
            summary="Status test",
            rationale="All statuses should parse",
            proposed_changes=["Record status"],
            expected_benefits=["Status is preserved"],
            status=status,
        )

        assert proposal.status == status

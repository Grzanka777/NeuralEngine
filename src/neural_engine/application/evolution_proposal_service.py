from uuid import UUID

from neural_engine.domain import EvolutionProposal, EvolutionProposalStatus
from neural_engine.ports.evolution_proposal_repository import (
    EvolutionProposalRepository,
)
from neural_engine.ports.playbook_evaluation_repository import (
    PlaybookEvaluationRepository,
)
from neural_engine.ports.playbook_repository import PlaybookRepository
from neural_engine.ports.playbook_run_repository import PlaybookRunRepository


class EvolutionProposalEvaluationsRequiredError(Exception):
    """Raised when an evolution proposal is created without evaluations."""

    def __init__(self) -> None:
        super().__init__("Evolution proposal requires at least one evaluation ID.")


class EvolutionProposalChangesRequiredError(Exception):
    """Raised when an evolution proposal is created without proposed changes."""

    def __init__(self) -> None:
        super().__init__("Evolution proposal requires at least one proposed change.")


class PlaybookNotFoundError(Exception):
    """Raised when an evolution proposal references an unknown playbook."""

    def __init__(self, playbook_id: UUID) -> None:
        self.playbook_id = playbook_id
        super().__init__(f"Playbook not found: {playbook_id}")


class PlaybookEvaluationNotFoundError(Exception):
    """Raised when an evolution proposal references an unknown evaluation."""

    def __init__(self, evaluation_id: UUID) -> None:
        self.evaluation_id = evaluation_id
        super().__init__(f"Playbook evaluation not found: {evaluation_id}")


class EvolutionProposalEvaluationPlaybookMismatchError(Exception):
    """Raised when an evaluation belongs to a run for a different playbook."""

    def __init__(
        self,
        evaluation_id: UUID,
        expected_playbook_id: UUID,
        actual_playbook_id: UUID,
    ) -> None:
        self.evaluation_id = evaluation_id
        self.expected_playbook_id = expected_playbook_id
        self.actual_playbook_id = actual_playbook_id
        super().__init__(
            "Playbook evaluation "
            f"{evaluation_id} belongs to playbook {actual_playbook_id}, "
            f"expected {expected_playbook_id}."
        )


class EvolutionProposalEvaluationRunNotFoundError(Exception):
    """Raised when an evaluation references a run that does not exist."""

    def __init__(self, evaluation_id: UUID, run_id: UUID) -> None:
        self.evaluation_id = evaluation_id
        self.run_id = run_id
        super().__init__(
            f"Playbook run not found: {run_id} (referenced by evaluation {evaluation_id})."
        )


class EvolutionProposalService:
    """Application service for evolution proposals."""

    def __init__(
        self,
        proposal_repository: EvolutionProposalRepository,
        playbook_repository: PlaybookRepository,
        evaluation_repository: PlaybookEvaluationRepository,
        run_repository: PlaybookRunRepository,
    ) -> None:
        self._proposal_repository = proposal_repository
        self._playbook_repository = playbook_repository
        self._evaluation_repository = evaluation_repository
        self._run_repository = run_repository

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
        self._validate(playbook_id, evaluation_ids, proposed_changes)

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

        self._proposal_repository.save(proposal)

        return proposal

    def list_proposals(self) -> list[EvolutionProposal]:
        return self._proposal_repository.load_all()

    def list_for_playbook(self, playbook_id: UUID) -> list[EvolutionProposal]:
        if self._playbook_repository.get_by_id(playbook_id) is None:
            raise PlaybookNotFoundError(playbook_id)

        proposals = self._proposal_repository.load_all()

        return [proposal for proposal in proposals if proposal.playbook_id == playbook_id]

    def list_for_evaluation(self, evaluation_id: UUID) -> list[EvolutionProposal]:
        if self._evaluation_repository.get_by_id(evaluation_id) is None:
            raise PlaybookEvaluationNotFoundError(evaluation_id)

        proposals = self._proposal_repository.load_all()

        return [proposal for proposal in proposals if evaluation_id in proposal.evaluation_ids]

    def get_by_id(self, proposal_id: UUID) -> EvolutionProposal | None:
        return self._proposal_repository.get_by_id(proposal_id)

    def _validate(
        self,
        playbook_id: UUID,
        evaluation_ids: list[UUID],
        proposed_changes: list[str],
    ) -> None:
        if not evaluation_ids:
            raise EvolutionProposalEvaluationsRequiredError()

        if not proposed_changes:
            raise EvolutionProposalChangesRequiredError()

        if self._playbook_repository.get_by_id(playbook_id) is None:
            raise PlaybookNotFoundError(playbook_id)

        for evaluation_id in evaluation_ids:
            evaluation = self._evaluation_repository.get_by_id(evaluation_id)

            if evaluation is None:
                raise PlaybookEvaluationNotFoundError(evaluation_id)

            run = self._run_repository.get_by_id(evaluation.run_id)
            if run is None:
                raise EvolutionProposalEvaluationRunNotFoundError(
                    evaluation_id=evaluation_id,
                    run_id=evaluation.run_id,
                )

            if run.playbook_id != playbook_id:
                raise EvolutionProposalEvaluationPlaybookMismatchError(
                    evaluation_id=evaluation_id,
                    expected_playbook_id=playbook_id,
                    actual_playbook_id=run.playbook_id,
                )

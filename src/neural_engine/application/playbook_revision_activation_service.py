from uuid import UUID

from neural_engine.domain import (
    PlaybookRevision,
    PlaybookRevisionActivation,
    PlaybookRevisionActivationDecision,
)
from neural_engine.ports.brain_trust_transition import (
    BrainTrustMutationCoordinator,
    ControlledCreateWriter,
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


class PlaybookRevisionActivationError(Exception):
    """Base error for playbook revision activation service failures."""


class PlaybookRevisionActivationPlaybookNotFoundError(PlaybookRevisionActivationError):
    """Raised when an activation references an unknown playbook."""

    def __init__(self, playbook_id: UUID) -> None:
        self.playbook_id = playbook_id
        super().__init__(f"Playbook not found: {playbook_id}")


class PlaybookRevisionActivationRevisionNotFoundError(PlaybookRevisionActivationError):
    """Raised when an activation references an unknown revision."""

    def __init__(self, revision_id: UUID) -> None:
        self.revision_id = revision_id
        super().__init__(f"Playbook revision not found: {revision_id}")


class PlaybookRevisionActivationProposalNotFoundError(PlaybookRevisionActivationError):
    """Raised when an activation references an unknown proposal."""

    def __init__(self, proposal_id: UUID) -> None:
        self.proposal_id = proposal_id
        super().__init__(f"Evolution proposal not found: {proposal_id}")


class PlaybookRevisionActivationRevisionPlaybookMismatchError(PlaybookRevisionActivationError):
    """Raised when an activation revision belongs to another playbook."""

    def __init__(
        self,
        revision_id: UUID,
        expected_playbook_id: UUID,
        actual_playbook_id: UUID,
    ) -> None:
        self.revision_id = revision_id
        self.expected_playbook_id = expected_playbook_id
        self.actual_playbook_id = actual_playbook_id
        super().__init__(
            f"Playbook revision {revision_id} belongs to playbook {actual_playbook_id}, "
            f"expected {expected_playbook_id}."
        )


class PlaybookRevisionActivationRevisionProposalMismatchError(PlaybookRevisionActivationError):
    """Raised when an activation revision belongs to another proposal."""

    def __init__(
        self,
        revision_id: UUID,
        expected_proposal_id: UUID,
        actual_proposal_id: UUID,
    ) -> None:
        self.revision_id = revision_id
        self.expected_proposal_id = expected_proposal_id
        self.actual_proposal_id = actual_proposal_id
        super().__init__(
            f"Playbook revision {revision_id} belongs to proposal {actual_proposal_id}, "
            f"expected {expected_proposal_id}."
        )


class PlaybookRevisionActivationPreviousRevisionRequiredError(PlaybookRevisionActivationError):
    """Raised when a superseded activation omits the previous revision."""

    def __init__(self) -> None:
        super().__init__("Superseded revision activation requires a previous revision ID.")


class PlaybookRevisionActivationPreviousRevisionNotFoundError(PlaybookRevisionActivationError):
    """Raised when a superseded activation references an unknown previous revision."""

    def __init__(self, previous_revision_id: UUID) -> None:
        self.previous_revision_id = previous_revision_id
        super().__init__(f"Previous playbook revision not found: {previous_revision_id}")


class PlaybookRevisionActivationPreviousRevisionPlaybookMismatchError(
    PlaybookRevisionActivationError
):
    """Raised when a previous revision belongs to another playbook."""

    def __init__(
        self,
        previous_revision_id: UUID,
        expected_playbook_id: UUID,
        actual_playbook_id: UUID,
    ) -> None:
        self.previous_revision_id = previous_revision_id
        self.expected_playbook_id = expected_playbook_id
        self.actual_playbook_id = actual_playbook_id
        super().__init__(
            f"Previous playbook revision {previous_revision_id} belongs to playbook "
            f"{actual_playbook_id}, expected {expected_playbook_id}."
        )


class PlaybookRevisionActivationPreviousRevisionForbiddenError(PlaybookRevisionActivationError):
    """Raised when a rejected activation references a previous revision."""

    def __init__(self, previous_revision_id: UUID) -> None:
        self.previous_revision_id = previous_revision_id
        super().__init__(
            f"Rejected revision activation must not reference previous revision "
            f"{previous_revision_id}."
        )


class PlaybookRevisionActivationService:
    """Application service for playbook revision activation decisions."""

    def __init__(
        self,
        activation_repository: PlaybookRevisionActivationRepository,
        revision_repository: PlaybookRevisionRepository,
        playbook_repository: PlaybookRepository,
        proposal_repository: EvolutionProposalRepository,
        controlled_writer: ControlledCreateWriter[PlaybookRevisionActivation] | None = None,
        mutation_coordinator: BrainTrustMutationCoordinator | None = None,
    ) -> None:
        if (controlled_writer is None) != (mutation_coordinator is None):
            raise ValueError(
                "Controlled PlaybookRevisionActivation writer and coordinator must be "
                "configured together."
            )
        self._activation_repository = activation_repository
        self._revision_repository = revision_repository
        self._playbook_repository = playbook_repository
        self._proposal_repository = proposal_repository
        self._controlled_writer = controlled_writer
        self._mutation_coordinator = mutation_coordinator

    def add(
        self,
        playbook_id: UUID,
        revision_id: UUID,
        proposal_id: UUID,
        decision: PlaybookRevisionActivationDecision,
        reason: str,
        previous_revision_id: UUID | None = None,
        decided_by: str | None = None,
        notes: str | None = None,
        tags: list[str] | None = None,
    ) -> PlaybookRevisionActivation:
        self._validate(
            playbook_id=playbook_id,
            revision_id=revision_id,
            proposal_id=proposal_id,
            decision=decision,
            previous_revision_id=previous_revision_id,
        )

        activation = PlaybookRevisionActivation(
            playbook_id=playbook_id,
            revision_id=revision_id,
            proposal_id=proposal_id,
            decision=decision,
            reason=reason,
            previous_revision_id=previous_revision_id,
            decided_by=decided_by,
            notes=notes,
            tags=tags or [],
        )

        if self._controlled_writer is not None and self._mutation_coordinator is not None:
            self._mutation_coordinator.execute(
                self._controlled_writer.controlled_create_target(activation)
            )
        else:
            self._activation_repository.save(activation)

        return activation

    def list_for_playbook(self, playbook_id: UUID) -> list[PlaybookRevisionActivation]:
        if self._playbook_repository.get_by_id(playbook_id) is None:
            raise PlaybookRevisionActivationPlaybookNotFoundError(playbook_id)

        activations = self._activation_repository.load_all()

        return [activation for activation in activations if activation.playbook_id == playbook_id]

    def list_for_revision(self, revision_id: UUID) -> list[PlaybookRevisionActivation]:
        if self._revision_repository.get_by_id(revision_id) is None:
            raise PlaybookRevisionActivationRevisionNotFoundError(revision_id)

        activations = self._activation_repository.load_all()

        return [activation for activation in activations if activation.revision_id == revision_id]

    def list_for_proposal(self, proposal_id: UUID) -> list[PlaybookRevisionActivation]:
        if self._proposal_repository.get_by_id(proposal_id) is None:
            raise PlaybookRevisionActivationProposalNotFoundError(proposal_id)

        activations = self._activation_repository.load_all()

        return [activation for activation in activations if activation.proposal_id == proposal_id]

    def get_active_revision_for_playbook(self, playbook_id: UUID) -> PlaybookRevision | None:
        active_revision_id: UUID | None = None

        for activation in self.list_for_playbook(playbook_id):
            if activation.decision == PlaybookRevisionActivationDecision.ACTIVE:
                active_revision_id = activation.revision_id

            if activation.decision == PlaybookRevisionActivationDecision.SUPERSEDED and (
                active_revision_id is None or activation.previous_revision_id == active_revision_id
            ):
                active_revision_id = activation.revision_id

            if (
                activation.decision == PlaybookRevisionActivationDecision.REJECTED
                and activation.revision_id == active_revision_id
            ):
                active_revision_id = None

        if active_revision_id is None:
            return None

        revision = self._revision_repository.get_by_id(active_revision_id)
        if revision is None:
            raise PlaybookRevisionActivationRevisionNotFoundError(active_revision_id)

        if revision.playbook_id != playbook_id:
            raise PlaybookRevisionActivationRevisionPlaybookMismatchError(
                revision_id=active_revision_id,
                expected_playbook_id=playbook_id,
                actual_playbook_id=revision.playbook_id,
            )

        return revision

    def _validate(
        self,
        playbook_id: UUID,
        revision_id: UUID,
        proposal_id: UUID,
        decision: PlaybookRevisionActivationDecision,
        previous_revision_id: UUID | None,
    ) -> None:
        if self._playbook_repository.get_by_id(playbook_id) is None:
            raise PlaybookRevisionActivationPlaybookNotFoundError(playbook_id)

        revision = self._revision_repository.get_by_id(revision_id)
        if revision is None:
            raise PlaybookRevisionActivationRevisionNotFoundError(revision_id)

        if self._proposal_repository.get_by_id(proposal_id) is None:
            raise PlaybookRevisionActivationProposalNotFoundError(proposal_id)

        if revision.playbook_id != playbook_id:
            raise PlaybookRevisionActivationRevisionPlaybookMismatchError(
                revision_id=revision_id,
                expected_playbook_id=playbook_id,
                actual_playbook_id=revision.playbook_id,
            )

        if revision.proposal_id != proposal_id:
            raise PlaybookRevisionActivationRevisionProposalMismatchError(
                revision_id=revision_id,
                expected_proposal_id=proposal_id,
                actual_proposal_id=revision.proposal_id,
            )

        if decision == PlaybookRevisionActivationDecision.SUPERSEDED:
            if previous_revision_id is None:
                raise PlaybookRevisionActivationPreviousRevisionRequiredError()

            previous_revision = self._revision_repository.get_by_id(previous_revision_id)
            if previous_revision is None:
                raise PlaybookRevisionActivationPreviousRevisionNotFoundError(previous_revision_id)

            if previous_revision.playbook_id != playbook_id:
                raise PlaybookRevisionActivationPreviousRevisionPlaybookMismatchError(
                    previous_revision_id=previous_revision_id,
                    expected_playbook_id=playbook_id,
                    actual_playbook_id=previous_revision.playbook_id,
                )

        if (
            decision == PlaybookRevisionActivationDecision.REJECTED
            and previous_revision_id is not None
        ):
            raise PlaybookRevisionActivationPreviousRevisionForbiddenError(previous_revision_id)

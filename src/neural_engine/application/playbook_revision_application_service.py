from uuid import UUID

from neural_engine.application.playbook_revision_activation_service import (
    PlaybookRevisionActivationService,
)
from neural_engine.domain import (
    EvolutionProposalStatus,
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


class PlaybookRevisionApplicationError(Exception):
    """Base error for playbook revision application service failures."""


class PlaybookRevisionApplicationPlaybookNotFoundError(PlaybookRevisionApplicationError):
    """Raised when an application references an unknown playbook."""

    def __init__(self, playbook_id: UUID) -> None:
        self.playbook_id = playbook_id
        super().__init__(f"Playbook not found: {playbook_id}")


class PlaybookRevisionApplicationRevisionNotFoundError(PlaybookRevisionApplicationError):
    """Raised when an application references an unknown revision."""

    def __init__(self, revision_id: UUID) -> None:
        self.revision_id = revision_id
        super().__init__(f"Playbook revision not found: {revision_id}")


class PlaybookRevisionApplicationProposalNotFoundError(PlaybookRevisionApplicationError):
    """Raised when an application references an unknown proposal."""

    def __init__(self, proposal_id: UUID) -> None:
        self.proposal_id = proposal_id
        super().__init__(f"Evolution proposal not found: {proposal_id}")


class PlaybookRevisionApplicationRevisionPlaybookMismatchError(PlaybookRevisionApplicationError):
    """Raised when an application revision belongs to another playbook."""

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


class PlaybookRevisionApplicationRevisionProposalMismatchError(PlaybookRevisionApplicationError):
    """Raised when an application revision belongs to another proposal."""

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


class PlaybookRevisionApplicationActivationNotFoundError(PlaybookRevisionApplicationError):
    """Raised when an application references an unknown source activation."""

    def __init__(self, activation_id: UUID) -> None:
        self.activation_id = activation_id
        super().__init__(f"Playbook revision activation not found: {activation_id}")


class PlaybookRevisionApplicationActivationMismatchError(PlaybookRevisionApplicationError):
    """Raised when a source activation points at a different relation."""

    def __init__(
        self,
        activation_id: UUID,
        expected_playbook_id: UUID,
        expected_revision_id: UUID,
        expected_proposal_id: UUID,
        actual_playbook_id: UUID,
        actual_revision_id: UUID,
        actual_proposal_id: UUID,
    ) -> None:
        self.activation_id = activation_id
        self.expected_playbook_id = expected_playbook_id
        self.expected_revision_id = expected_revision_id
        self.expected_proposal_id = expected_proposal_id
        self.actual_playbook_id = actual_playbook_id
        self.actual_revision_id = actual_revision_id
        self.actual_proposal_id = actual_proposal_id
        super().__init__(
            f"Playbook revision activation {activation_id} points to "
            f"{actual_playbook_id}/{actual_revision_id}/{actual_proposal_id}, "
            f"expected {expected_playbook_id}/{expected_revision_id}/{expected_proposal_id}."
        )


class PlaybookRevisionApplicationNoActiveRevisionError(PlaybookRevisionApplicationError):
    """Raised when application is requested without an active revision."""

    def __init__(self, playbook_id: UUID) -> None:
        self.playbook_id = playbook_id
        super().__init__(f"Playbook has no active revision: {playbook_id}")


class PlaybookRevisionApplicationInactiveRevisionError(PlaybookRevisionApplicationError):
    """Raised when application is requested for a revision that is not active."""

    def __init__(
        self,
        revision_id: UUID,
        active_revision_id: UUID,
    ) -> None:
        self.revision_id = revision_id
        self.active_revision_id = active_revision_id
        super().__init__(
            f"Playbook revision {revision_id} is not active; active revision is "
            f"{active_revision_id}."
        )


class PlaybookRevisionApplicationProposalNotAcceptedError(PlaybookRevisionApplicationError):
    """Raised when an application references a proposal that is not accepted."""

    def __init__(
        self,
        proposal_id: UUID,
        actual_status: EvolutionProposalStatus,
    ) -> None:
        self.proposal_id = proposal_id
        self.actual_status = actual_status
        super().__init__(
            f"Evolution proposal {proposal_id} must be accepted, got {actual_status.value}."
        )


class PlaybookRevisionApplicationService:
    """Application service for playbook revision application audit records."""

    def __init__(
        self,
        application_repository: PlaybookRevisionApplicationRepository,
        revision_repository: PlaybookRevisionRepository,
        playbook_repository: PlaybookRepository,
        proposal_repository: EvolutionProposalRepository,
        activation_repository: PlaybookRevisionActivationRepository,
        activation_service: PlaybookRevisionActivationService,
    ) -> None:
        self._application_repository = application_repository
        self._revision_repository = revision_repository
        self._playbook_repository = playbook_repository
        self._proposal_repository = proposal_repository
        self._activation_repository = activation_repository
        self._activation_service = activation_service

    def add(
        self,
        playbook_id: UUID,
        revision_id: UUID,
        proposal_id: UUID,
        reason: str,
        applied_by: str | None = None,
        notes: str | None = None,
        tags: tuple[str, ...] = (),
        source_activation_id: UUID | None = None,
        idempotency_key: str | None = None,
    ) -> PlaybookRevisionApplication:
        self._validate(
            playbook_id=playbook_id,
            revision_id=revision_id,
            proposal_id=proposal_id,
            source_activation_id=source_activation_id,
        )

        application = PlaybookRevisionApplication(
            playbook_id=playbook_id,
            revision_id=revision_id,
            proposal_id=proposal_id,
            reason=reason,
            applied_by=applied_by,
            notes=notes,
            tags=tags,
            source_activation_id=source_activation_id,
            idempotency_key=idempotency_key,
            content_changed=False,
        )

        self._application_repository.save(application)

        return application

    def list_for_playbook(self, playbook_id: UUID) -> list[PlaybookRevisionApplication]:
        if self._playbook_repository.get_by_id(playbook_id) is None:
            raise PlaybookRevisionApplicationPlaybookNotFoundError(playbook_id)

        applications = self._application_repository.load_all()

        return [
            application for application in applications if application.playbook_id == playbook_id
        ]

    def list_for_revision(self, revision_id: UUID) -> list[PlaybookRevisionApplication]:
        if self._revision_repository.get_by_id(revision_id) is None:
            raise PlaybookRevisionApplicationRevisionNotFoundError(revision_id)

        applications = self._application_repository.load_all()

        return [
            application for application in applications if application.revision_id == revision_id
        ]

    def list_for_proposal(self, proposal_id: UUID) -> list[PlaybookRevisionApplication]:
        if self._proposal_repository.get_by_id(proposal_id) is None:
            raise PlaybookRevisionApplicationProposalNotFoundError(proposal_id)

        applications = self._application_repository.load_all()

        return [
            application for application in applications if application.proposal_id == proposal_id
        ]

    def _validate(
        self,
        playbook_id: UUID,
        revision_id: UUID,
        proposal_id: UUID,
        source_activation_id: UUID | None,
    ) -> None:
        if self._playbook_repository.get_by_id(playbook_id) is None:
            raise PlaybookRevisionApplicationPlaybookNotFoundError(playbook_id)

        revision = self._revision_repository.get_by_id(revision_id)
        if revision is None:
            raise PlaybookRevisionApplicationRevisionNotFoundError(revision_id)

        proposal = self._proposal_repository.get_by_id(proposal_id)
        if proposal is None:
            raise PlaybookRevisionApplicationProposalNotFoundError(proposal_id)

        if proposal.status != EvolutionProposalStatus.ACCEPTED:
            raise PlaybookRevisionApplicationProposalNotAcceptedError(
                proposal_id=proposal_id,
                actual_status=proposal.status,
            )

        if revision.playbook_id != playbook_id:
            raise PlaybookRevisionApplicationRevisionPlaybookMismatchError(
                revision_id=revision_id,
                expected_playbook_id=playbook_id,
                actual_playbook_id=revision.playbook_id,
            )

        if revision.proposal_id != proposal_id:
            raise PlaybookRevisionApplicationRevisionProposalMismatchError(
                revision_id=revision_id,
                expected_proposal_id=proposal_id,
                actual_proposal_id=revision.proposal_id,
            )

        if source_activation_id is not None:
            self._validate_source_activation(
                source_activation_id=source_activation_id,
                playbook_id=playbook_id,
                revision_id=revision_id,
                proposal_id=proposal_id,
            )

        active_revision = self._activation_service.get_active_revision_for_playbook(playbook_id)
        if active_revision is None:
            raise PlaybookRevisionApplicationNoActiveRevisionError(playbook_id)

        if active_revision.id != revision_id:
            raise PlaybookRevisionApplicationInactiveRevisionError(
                revision_id=revision_id,
                active_revision_id=active_revision.id,
            )

    def _validate_source_activation(
        self,
        source_activation_id: UUID,
        playbook_id: UUID,
        revision_id: UUID,
        proposal_id: UUID,
    ) -> None:
        activation = self._activation_repository.get_by_id(source_activation_id)
        if activation is None:
            raise PlaybookRevisionApplicationActivationNotFoundError(source_activation_id)

        if (
            activation.playbook_id != playbook_id
            or activation.revision_id != revision_id
            or activation.proposal_id != proposal_id
        ):
            raise PlaybookRevisionApplicationActivationMismatchError(
                activation_id=source_activation_id,
                expected_playbook_id=playbook_id,
                expected_revision_id=revision_id,
                expected_proposal_id=proposal_id,
                actual_playbook_id=activation.playbook_id,
                actual_revision_id=activation.revision_id,
                actual_proposal_id=activation.proposal_id,
            )

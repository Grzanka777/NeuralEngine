from uuid import UUID

from neural_engine.application.evolution_proposal_service import (
    EvolutionProposalNotFoundError,
)
from neural_engine.domain import EvolutionProposalStatus, PlaybookRevision
from neural_engine.ports.evolution_proposal_repository import (
    EvolutionProposalRepository,
)
from neural_engine.ports.knowledge_repository import KnowledgeRepository
from neural_engine.ports.playbook_repository import PlaybookRepository
from neural_engine.ports.playbook_revision_repository import (
    PlaybookRevisionRepository,
)


class PlaybookRevisionStepsRequiredError(Exception):
    """Raised when a playbook revision is created without steps."""

    def __init__(self) -> None:
        super().__init__("Playbook revision requires at least one step.")


class PlaybookRevisionSuccessCriteriaRequiredError(Exception):
    """Raised when a playbook revision is created without success criteria."""

    def __init__(self) -> None:
        super().__init__("Playbook revision requires at least one success criterion.")


class PlaybookNotFoundError(Exception):
    """Raised when a playbook revision references an unknown playbook."""

    def __init__(self, playbook_id: UUID) -> None:
        self.playbook_id = playbook_id
        super().__init__(f"Playbook not found: {playbook_id}")


class PlaybookRevisionProposalMismatchError(Exception):
    """Raised when a revision proposal belongs to another playbook."""

    def __init__(
        self,
        proposal_id: UUID,
        expected_playbook_id: UUID,
        actual_playbook_id: UUID,
    ) -> None:
        self.proposal_id = proposal_id
        self.expected_playbook_id = expected_playbook_id
        self.actual_playbook_id = actual_playbook_id
        super().__init__(
            f"Evolution proposal {proposal_id} belongs to playbook {actual_playbook_id}, "
            f"expected {expected_playbook_id}."
        )


class PlaybookRevisionProposalNotAcceptedError(Exception):
    """Raised when a revision references a proposal that is not accepted."""

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


class KnowledgeNotFoundError(Exception):
    """Raised when a playbook revision references an unknown knowledge item."""

    def __init__(self, knowledge_id: UUID) -> None:
        self.knowledge_id = knowledge_id
        super().__init__(f"Knowledge not found: {knowledge_id}")


class PlaybookRevisionService:
    """Application service for playbook revisions."""

    def __init__(
        self,
        revision_repository: PlaybookRevisionRepository,
        playbook_repository: PlaybookRepository,
        proposal_repository: EvolutionProposalRepository,
        knowledge_repository: KnowledgeRepository,
    ) -> None:
        self._revision_repository = revision_repository
        self._playbook_repository = playbook_repository
        self._proposal_repository = proposal_repository
        self._knowledge_repository = knowledge_repository

    def add(
        self,
        playbook_id: UUID,
        proposal_id: UUID,
        title: str,
        situation: str,
        objective: str,
        steps: list[str],
        success_criteria: list[str],
        knowledge_ids: list[UUID],
        notes: str | None = None,
        tags: list[str] | None = None,
    ) -> PlaybookRevision:
        self._validate(playbook_id, proposal_id, steps, success_criteria, knowledge_ids)

        revision = PlaybookRevision(
            playbook_id=playbook_id,
            proposal_id=proposal_id,
            title=title,
            situation=situation,
            objective=objective,
            steps=steps,
            success_criteria=success_criteria,
            knowledge_ids=knowledge_ids,
            notes=notes,
            tags=tags or [],
        )

        self._revision_repository.save(revision)

        return revision

    def list_revisions(self) -> list[PlaybookRevision]:
        return self._revision_repository.load_all()

    def list_for_playbook(self, playbook_id: UUID) -> list[PlaybookRevision]:
        if self._playbook_repository.get_by_id(playbook_id) is None:
            raise PlaybookNotFoundError(playbook_id)

        revisions = self._revision_repository.load_all()

        return [revision for revision in revisions if revision.playbook_id == playbook_id]

    def get_by_id(self, revision_id: UUID) -> PlaybookRevision | None:
        return self._revision_repository.get_by_id(revision_id)

    def _validate(
        self,
        playbook_id: UUID,
        proposal_id: UUID,
        steps: list[str],
        success_criteria: list[str],
        knowledge_ids: list[UUID],
    ) -> None:
        if not steps:
            raise PlaybookRevisionStepsRequiredError()

        if not success_criteria:
            raise PlaybookRevisionSuccessCriteriaRequiredError()

        proposal = self._proposal_repository.get_by_id(proposal_id)
        if proposal is None:
            raise EvolutionProposalNotFoundError(proposal_id)

        if proposal.status != EvolutionProposalStatus.ACCEPTED:
            raise PlaybookRevisionProposalNotAcceptedError(
                proposal_id=proposal_id,
                actual_status=proposal.status,
            )

        if proposal.playbook_id != playbook_id:
            raise PlaybookRevisionProposalMismatchError(
                proposal_id=proposal_id,
                expected_playbook_id=playbook_id,
                actual_playbook_id=proposal.playbook_id,
            )

        if self._playbook_repository.get_by_id(playbook_id) is None:
            raise PlaybookNotFoundError(playbook_id)

        for knowledge_id in knowledge_ids:
            if self._knowledge_repository.get_by_id(knowledge_id) is None:
                raise KnowledgeNotFoundError(knowledge_id)

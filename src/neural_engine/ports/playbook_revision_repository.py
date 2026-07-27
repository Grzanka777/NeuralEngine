from abc import ABC, abstractmethod
from uuid import UUID

from neural_engine.domain import PlaybookRevision


class PlaybookRevisionRepositoryError(Exception):
    """Base error for PlaybookRevision persistence failures."""


class PlaybookRevisionPersistenceConflictError(PlaybookRevisionRepositoryError):
    """Raised when one PlaybookRevision id is reused for a different payload."""

    def __init__(self, revision_id: UUID) -> None:
        self.revision_id = revision_id
        super().__init__(
            f"PlaybookRevision persistence conflict for {revision_id}: "
            "the stored payload is different."
        )


class PlaybookRevisionStoredDataError(PlaybookRevisionRepositoryError):
    """Raised when persisted PlaybookRevision data cannot be validated."""

    def __init__(self, identity: str) -> None:
        self.identity = identity
        super().__init__(f"Stored PlaybookRevision data is invalid for identity: {identity}")


class PlaybookRevisionIdentityMismatchError(PlaybookRevisionRepositoryError):
    """Raised when a PlaybookRevision payload id differs from its persisted identity."""

    def __init__(self, expected_id: UUID, actual_id: UUID) -> None:
        self.expected_id = expected_id
        self.actual_id = actual_id
        super().__init__(
            "Stored PlaybookRevision identity mismatch: "
            f"expected {expected_id}, payload contains {actual_id}."
        )


class PlaybookRevisionRepository(ABC):
    """Port for storing playbook revisions."""

    @abstractmethod
    def save(self, revision: PlaybookRevision) -> None:
        """Create a PlaybookRevision once or accept an identical replay."""

    @abstractmethod
    def load_all(self) -> list[PlaybookRevision]:
        """Load all playbook revisions."""

    @abstractmethod
    def get_by_id(self, revision_id: UUID) -> PlaybookRevision | None:
        """Load one playbook revision by id."""

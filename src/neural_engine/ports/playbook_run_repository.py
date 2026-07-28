from abc import ABC, abstractmethod
from uuid import UUID

from neural_engine.domain import PlaybookRun


class PlaybookRunRepositoryError(Exception):
    """Base error for PlaybookRun persistence failures."""


class PlaybookRunPersistenceConflictError(PlaybookRunRepositoryError):
    """Raised when one PlaybookRun id is reused for a different payload."""

    def __init__(self, run_id: UUID) -> None:
        self.run_id = run_id
        super().__init__(
            f"PlaybookRun persistence conflict for {run_id}: the stored payload is different."
        )


class PlaybookRunStoredDataError(PlaybookRunRepositoryError):
    """Raised when persisted PlaybookRun data cannot be validated."""

    def __init__(self, identity: str) -> None:
        self.identity = identity
        super().__init__(f"Stored PlaybookRun data is invalid for identity: {identity}")


class PlaybookRunIdentityMismatchError(PlaybookRunRepositoryError):
    """Raised when a PlaybookRun payload id differs from its persisted identity."""

    def __init__(self, expected_id: UUID, actual_id: UUID) -> None:
        self.expected_id = expected_id
        self.actual_id = actual_id
        super().__init__(
            "Stored PlaybookRun identity mismatch: "
            f"expected {expected_id}, payload contains {actual_id}."
        )


class PlaybookRunRepository(ABC):
    """Port for storing playbook runs."""

    @abstractmethod
    def save(self, run: PlaybookRun) -> None:
        """Create a PlaybookRun once or accept an identical replay."""

    @abstractmethod
    def load_all(self) -> list[PlaybookRun]:
        """Load all playbook runs."""

    @abstractmethod
    def get_by_id(self, run_id: UUID) -> PlaybookRun | None:
        """Load one playbook run by id."""

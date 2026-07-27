from abc import ABC, abstractmethod
from uuid import UUID

from neural_engine.domain import Knowledge


class KnowledgeRepositoryError(Exception):
    """Base error for Knowledge persistence failures."""


class KnowledgePersistenceConflictError(KnowledgeRepositoryError):
    """Raised when one Knowledge id is reused for a different payload."""

    def __init__(self, knowledge_id: UUID) -> None:
        self.knowledge_id = knowledge_id
        super().__init__(
            f"Knowledge persistence conflict for {knowledge_id}: the stored payload is different."
        )


class KnowledgeStoredDataError(KnowledgeRepositoryError):
    """Raised when persisted Knowledge data cannot be validated."""

    def __init__(self, identity: str) -> None:
        self.identity = identity
        super().__init__(f"Stored Knowledge data is invalid for identity: {identity}")


class KnowledgeIdentityMismatchError(KnowledgeRepositoryError):
    """Raised when a Knowledge payload id differs from its persisted identity."""

    def __init__(self, expected_id: UUID, actual_id: UUID) -> None:
        self.expected_id = expected_id
        self.actual_id = actual_id
        super().__init__(
            "Stored Knowledge identity mismatch: "
            f"expected {expected_id}, payload contains {actual_id}."
        )


class KnowledgeRepository(ABC):
    """Port for storing knowledge."""

    @abstractmethod
    def save(self, knowledge: Knowledge) -> None:
        """Create Knowledge once or accept an identical replay."""

    @abstractmethod
    def load_all(self) -> list[Knowledge]:
        """Load all knowledge."""

    @abstractmethod
    def get_by_id(self, knowledge_id: UUID) -> Knowledge | None:
        """Load one knowledge item by id."""

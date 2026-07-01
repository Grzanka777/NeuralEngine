from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class KnowledgeConfidence(StrEnum):
    """Confidence level assigned to a knowledge statement."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Knowledge(BaseModel):
    """A durable rule, lesson, or conclusion derived from experiences."""

    id: UUID = Field(default_factory=uuid4)

    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    statement: str

    rationale: str

    confidence: KnowledgeConfidence

    experience_ids: list[UUID]

    tags: list[str] = Field(default_factory=list)

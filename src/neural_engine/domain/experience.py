from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ExperienceResult(StrEnum):
    """Known outcome classification for an experience."""

    SUCCESS = "success"
    FAILURE = "failure"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class Experience(BaseModel):
    """An event or action whose outcome is known or recorded."""

    id: UUID = Field(default_factory=uuid4)

    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    title: str

    context: str

    action: str

    outcome: str

    result: ExperienceResult

    observation_ids: list[UUID] = Field(default_factory=list)

    tags: list[str] = Field(default_factory=list)

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class Observation(BaseModel):
    """A single observation recorded by Neural Engine."""

    id: UUID = Field(default_factory=uuid4)

    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    source: str = "user"

    content: str

    tags: list[str] = Field(default_factory=list)

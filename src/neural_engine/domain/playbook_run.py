from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class PlaybookRun(BaseModel):
    """A record of manually applying one playbook to a concrete situation."""

    id: UUID = Field(default_factory=uuid4)

    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    playbook_id: UUID

    revision_id: UUID | None = None

    situation: str

    actions_taken: list[str]

    outcome: str

    success: bool

    evidence: list[str] = Field(default_factory=list)

    notes: str | None = None

    tags: list[str] = Field(default_factory=list)

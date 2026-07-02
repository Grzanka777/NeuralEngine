from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class PlaybookRevision(BaseModel):
    """An immutable candidate revision for one playbook."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)

    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    playbook_id: UUID

    proposal_id: UUID

    title: str

    situation: str

    objective: str

    steps: list[str]

    success_criteria: list[str]

    knowledge_ids: list[UUID]

    notes: str | None = None

    tags: list[str] = Field(default_factory=list)

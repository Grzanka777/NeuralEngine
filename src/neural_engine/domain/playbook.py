from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class Playbook(BaseModel):
    """An explicit operational procedure that applies knowledge to situations."""

    id: UUID = Field(default_factory=uuid4)

    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    title: str

    situation: str

    objective: str

    steps: list[str]

    success_criteria: list[str]

    constraints: list[str] = Field(default_factory=list)

    knowledge_ids: list[UUID]

    tags: list[str] = Field(default_factory=list)

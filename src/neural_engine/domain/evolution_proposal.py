from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class EvolutionProposalStatus(StrEnum):
    """Lifecycle status assigned to an evolution proposal."""

    DRAFT = "draft"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class EvolutionProposal(BaseModel):
    """A proposed improvement for one playbook based on evaluations."""

    id: UUID = Field(default_factory=uuid4)

    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    playbook_id: UUID

    evaluation_ids: list[UUID]

    summary: str

    rationale: str

    proposed_changes: list[str]

    expected_benefits: list[str]

    risks: list[str] = Field(default_factory=list)

    status: EvolutionProposalStatus = EvolutionProposalStatus.DRAFT

    notes: str | None = None

    tags: list[str] = Field(default_factory=list)

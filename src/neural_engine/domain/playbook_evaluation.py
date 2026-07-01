from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class PlaybookEffectiveness(StrEnum):
    """Effectiveness judgment assigned to a playbook run."""

    INEFFECTIVE = "ineffective"
    PARTIAL = "partial"
    EFFECTIVE = "effective"


class PlaybookEvaluation(BaseModel):
    """A human or external assessment of one playbook run."""

    id: UUID = Field(default_factory=uuid4)

    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    run_id: UUID

    effectiveness: PlaybookEffectiveness

    findings: list[str]

    improvements: list[str] = Field(default_factory=list)

    evidence: list[str] = Field(default_factory=list)

    notes: str | None = None

    tags: list[str] = Field(default_factory=list)

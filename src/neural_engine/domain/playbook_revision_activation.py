from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class PlaybookRevisionActivationDecision(StrEnum):
    """Decision recorded for a playbook revision lifecycle event."""

    ACTIVE = "active"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"


class PlaybookRevisionActivation(BaseModel):
    """An immutable explicit lifecycle decision for one playbook revision."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)

    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    playbook_id: UUID

    revision_id: UUID

    proposal_id: UUID

    decision: PlaybookRevisionActivationDecision

    reason: str

    previous_revision_id: UUID | None = None

    decided_by: str | None = None

    notes: str | None = None

    tags: list[str] = Field(default_factory=list)

    @field_validator("reason")
    @classmethod
    def _reason_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Playbook revision activation requires a reason.")

        return value

    @field_validator("decided_by", "notes")
    @classmethod
    def _optional_text_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Optional text fields must not be blank when supplied.")

        return value

    @field_validator("tags")
    @classmethod
    def _tags_must_not_contain_blank_values(cls, value: list[str]) -> list[str]:
        if any(not tag.strip() for tag in value):
            raise ValueError("Tags must not contain blank values.")

        return value

    @model_validator(mode="after")
    def _decision_must_match_previous_revision(self) -> PlaybookRevisionActivation:
        if (
            self.decision == PlaybookRevisionActivationDecision.SUPERSEDED
            and self.previous_revision_id is None
        ):
            raise ValueError("Superseded revision activation requires a previous revision ID.")

        if (
            self.decision == PlaybookRevisionActivationDecision.REJECTED
            and self.previous_revision_id is not None
        ):
            raise ValueError("Rejected revision activation must not reference a previous revision.")

        return self

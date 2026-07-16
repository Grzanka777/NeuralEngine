from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PlaybookRevisionApplication(BaseModel):
    """An immutable audit record for explicit playbook revision application."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)

    applied_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    playbook_id: UUID

    revision_id: UUID

    proposal_id: UUID

    reason: str

    applied_by: str | None = None

    notes: str | None = None

    tags: tuple[str, ...] = ()

    source_activation_id: UUID | None = None

    idempotency_key: str | None = None

    content_changed: bool = False

    @field_validator("reason")
    @classmethod
    def _reason_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Playbook revision application requires a reason.")

        return value

    @field_validator("applied_by", "notes", "idempotency_key")
    @classmethod
    def _optional_text_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Optional text fields must not be blank when supplied.")

        return value

    @field_validator("tags")
    @classmethod
    def _tags_must_not_contain_blank_values(
        cls,
        value: tuple[str, ...],
    ) -> tuple[str, ...]:
        if any(not tag.strip() for tag in value):
            raise ValueError("Tags must not contain blank values.")

        return value

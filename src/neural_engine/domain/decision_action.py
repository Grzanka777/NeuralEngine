from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

from neural_engine.domain.decision import EvidenceReference


class DecisionAction(BaseModel):
    """An immutable record of work performed under an accepted Decision."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    decision_id: UUID
    acceptance_id: UUID
    action_type: str
    summary: str
    performed_by: str
    started_at: datetime
    completed_at: datetime | None = None
    evidence_references: tuple[EvidenceReference, ...] = ()
    playbook_run_id: UUID | None = None
    idempotency_key: str
    tags: tuple[str, ...] = ()

    @field_validator("recorded_at", "started_at", "completed_at")
    @classmethod
    def _timestamps_must_be_utc_aware(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Decision action timestamps must be timezone-aware.")

        return value.astimezone(UTC)

    @field_validator(
        "action_type",
        "summary",
        "performed_by",
        "idempotency_key",
        mode="before",
    )
    @classmethod
    def _required_text_must_not_be_blank(
        cls,
        value: object,
        info: ValidationInfo,
    ) -> object:
        if not isinstance(value, str):
            return value

        normalized = value.strip()
        if not normalized:
            raise ValueError(f"Decision action {info.field_name} must not be blank.")
        if info.field_name == "action_type" and len(normalized) > 64:
            raise ValueError("Decision action action_type is too long.")

        return normalized

    @field_validator("tags", mode="before")
    @classmethod
    def _normalize_tags(cls, value: object) -> object:
        if not isinstance(value, (list, tuple)):
            return value

        normalized: list[str] = []
        seen: set[str] = set()
        for tag in value:
            if not isinstance(tag, str):
                return value

            item = tag.strip()
            if not item:
                raise ValueError("Decision action tags must not contain blank values.")

            duplicate_key = item.casefold()
            if duplicate_key not in seen:
                seen.add(duplicate_key)
                normalized.append(item)

        return tuple(normalized)

    @model_validator(mode="after")
    def _completed_at_must_not_precede_started_at(self) -> DecisionAction:
        if self.completed_at is not None and self.completed_at < self.started_at:
            raise ValueError("Decision action completed_at must not precede started_at.")

        return self

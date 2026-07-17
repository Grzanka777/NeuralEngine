from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from neural_engine.domain.decision import EvidenceReference


class DecisionAcceptance(BaseModel):
    """An immutable explicit authorization of one proposed Decision."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    accepted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    decision_id: UUID
    accepted_by: str
    reason: str
    evidence_references: tuple[EvidenceReference, ...] = ()
    idempotency_key: str
    tags: tuple[str, ...] = ()

    @field_validator("accepted_at")
    @classmethod
    def _accepted_at_must_be_utc_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Decision acceptance accepted_at must be timezone-aware.")

        return value.astimezone(UTC)

    @field_validator("accepted_by", "reason", "idempotency_key", mode="before")
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
            raise ValueError(f"Decision acceptance {info.field_name} must not be blank.")

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
                raise ValueError("Decision acceptance tags must not contain blank values.")

            duplicate_key = item.casefold()
            if duplicate_key not in seen:
                seen.add(duplicate_key)
                normalized.append(item)

        return tuple(normalized)

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator


class EvidenceReference(BaseModel):
    """A bounded immutable reference to evidence outside NeuralEngine."""

    model_config = ConfigDict(frozen=True)

    kind: str
    locator: str
    repository_or_project: str | None = None
    content_hash: str | None = None
    captured_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source: str | None = None
    summary: str | None = None

    @field_validator("captured_at")
    @classmethod
    def _captured_at_must_be_utc_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Evidence reference captured_at must be timezone-aware.")

        return value.astimezone(UTC)

    @field_validator("kind", "locator", mode="before")
    @classmethod
    def _required_text_must_be_bounded(cls, value: object, info: ValidationInfo) -> object:
        if not isinstance(value, str):
            return value

        normalized = value.strip()
        limits = {"kind": 64, "locator": 2048}
        field_name = info.field_name
        assert field_name is not None
        if not normalized:
            raise ValueError(f"Evidence reference {field_name} must not be blank.")
        if len(normalized) > limits[field_name]:
            raise ValueError(f"Evidence reference {field_name} is too long.")

        return normalized

    @field_validator(
        "repository_or_project",
        "content_hash",
        "source",
        "summary",
        mode="before",
    )
    @classmethod
    def _optional_text_must_be_bounded(cls, value: object, info: ValidationInfo) -> object:
        if value is None or not isinstance(value, str):
            return value

        normalized = value.strip()
        limits = {
            "repository_or_project": 255,
            "content_hash": 256,
            "source": 255,
            "summary": 1000,
        }
        field_name = info.field_name
        assert field_name is not None
        if not normalized:
            raise ValueError(f"Evidence reference {field_name} must not be blank when supplied.")
        if len(normalized) > limits[field_name]:
            raise ValueError(f"Evidence reference {field_name} is too long.")

        return normalized


class Decision(BaseModel):
    """An immutable proposed decision with explicit context and provenance."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    project_key: str
    title: str
    objective: str
    context_summary: str
    alternatives: tuple[str, ...]
    proposed_option: str
    rationale: str
    observation_ids: tuple[UUID, ...] = ()
    evidence_references: tuple[EvidenceReference, ...] = ()
    proposed_by: str
    supersedes_decision_id: UUID | None = None
    idempotency_key: str
    tags: tuple[str, ...] = ()

    @field_validator("created_at")
    @classmethod
    def _created_at_must_be_utc_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Decision created_at must be timezone-aware.")

        return value.astimezone(UTC)

    @field_validator(
        "project_key",
        "title",
        "objective",
        "context_summary",
        "proposed_option",
        "rationale",
        "proposed_by",
        "idempotency_key",
        mode="before",
    )
    @classmethod
    def _required_text_must_not_be_blank(cls, value: object, info: ValidationInfo) -> object:
        if not isinstance(value, str):
            return value

        normalized = value.strip()
        if not normalized:
            raise ValueError(f"Decision {info.field_name} must not be blank.")

        return normalized

    @field_validator("alternatives", mode="before")
    @classmethod
    def _alternatives_must_be_meaningful_and_unique(cls, value: object) -> object:
        if not isinstance(value, (list, tuple)):
            return value

        normalized: list[str] = []
        seen: set[str] = set()
        for alternative in value:
            if not isinstance(alternative, str):
                return value

            item = alternative.strip()
            if not item:
                raise ValueError("Decision alternatives must not contain blank values.")

            duplicate_key = item.casefold()
            if duplicate_key in seen:
                raise ValueError("Decision alternatives must be unique.")

            seen.add(duplicate_key)
            normalized.append(item)

        if len(normalized) < 2:
            raise ValueError("Decision requires at least two alternatives.")

        return tuple(normalized)

    @field_validator("observation_ids")
    @classmethod
    def _observation_ids_must_be_unique(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        if len(value) != len(set(value)):
            raise ValueError("Decision observation IDs must be unique.")

        return value

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
                raise ValueError("Decision tags must not contain blank values.")

            duplicate_key = item.casefold()
            if duplicate_key not in seen:
                seen.add(duplicate_key)
                normalized.append(item)

        return tuple(normalized)

    @model_validator(mode="after")
    def _relations_must_be_valid(self) -> Decision:
        if self.proposed_option not in self.alternatives:
            raise ValueError("Decision proposed option must exactly match one alternative.")

        if self.supersedes_decision_id == self.id:
            raise ValueError("Decision must not supersede itself.")

        return self

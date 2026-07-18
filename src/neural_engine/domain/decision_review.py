from datetime import UTC, datetime
from enum import StrEnum
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

MAX_DECISION_REVIEW_REVIEWER_LENGTH = 255
MAX_DECISION_REVIEW_SUMMARY_LENGTH = 1000
MAX_DECISION_REVIEW_FINDINGS = 100
MAX_DECISION_REVIEW_FINDING_LENGTH = 1000
MAX_DECISION_REVIEW_CANDIDATE_LESSONS = 100
MAX_DECISION_REVIEW_CANDIDATE_LESSON_LENGTH = 1000


class DecisionReviewAssessment(StrEnum):
    SOUND = "sound"
    FLAWED = "flawed"
    MIXED = "mixed"
    INCONCLUSIVE = "inconclusive"


class DecisionReviewConfidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class DecisionReview(BaseModel):
    """An immutable authorized interpretation of explicit Decision outcomes."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    decision_id: UUID
    acceptance_id: UUID
    outcome_ids: tuple[UUID, ...]
    reviewed_by: str
    reviewed_at: datetime
    assessment: DecisionReviewAssessment
    summary: str
    findings: tuple[str, ...]
    candidate_lessons: tuple[str, ...] = ()
    evidence_references: tuple[EvidenceReference, ...] = ()
    confidence: DecisionReviewConfidence
    idempotency_key: str
    tags: tuple[str, ...] = ()

    @field_validator("recorded_at", "reviewed_at")
    @classmethod
    def _timestamps_must_be_utc_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Decision review timestamps must be timezone-aware.")
        return value.astimezone(UTC)

    @field_validator("reviewed_by", "summary", "idempotency_key", mode="before")
    @classmethod
    def _required_text_must_be_bounded(cls, value: object, info: ValidationInfo) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"Decision review {info.field_name} must not be blank.")
        limits = {
            "reviewed_by": MAX_DECISION_REVIEW_REVIEWER_LENGTH,
            "summary": MAX_DECISION_REVIEW_SUMMARY_LENGTH,
        }
        field_name = info.field_name
        assert field_name is not None
        limit = limits.get(field_name)
        if limit is not None and len(normalized) > limit:
            raise ValueError(f"Decision review {info.field_name} is too long.")
        return normalized

    @field_validator("outcome_ids", mode="before")
    @classmethod
    def _outcome_ids_must_be_present_and_unique(cls, value: object) -> object:
        if not isinstance(value, (list, tuple)):
            return value
        normalized = tuple(value)
        if not normalized:
            raise ValueError("Decision review requires at least one outcome ID.")
        if len(normalized) != len(set(normalized)):
            raise ValueError("Decision review outcome IDs must be unique.")
        return normalized

    @field_validator("findings", mode="before")
    @classmethod
    def _findings_must_be_bounded_and_unique(cls, value: object) -> object:
        return cls._normalize_ordered_text(
            value,
            field_name="findings",
            required=True,
            max_items=MAX_DECISION_REVIEW_FINDINGS,
            max_length=MAX_DECISION_REVIEW_FINDING_LENGTH,
        )

    @field_validator("candidate_lessons", mode="before")
    @classmethod
    def _candidate_lessons_must_be_bounded_and_unique(cls, value: object) -> object:
        return cls._normalize_ordered_text(
            value,
            field_name="candidate lessons",
            required=False,
            max_items=MAX_DECISION_REVIEW_CANDIDATE_LESSONS,
            max_length=MAX_DECISION_REVIEW_CANDIDATE_LESSON_LENGTH,
        )

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
                raise ValueError("Decision review tags must not contain blank values.")
            semantic_key = item.casefold()
            if semantic_key not in seen:
                seen.add(semantic_key)
                normalized.append(item)
        return tuple(normalized)

    @model_validator(mode="after")
    def _reviewed_at_must_not_be_later_than_recorded_at(self) -> DecisionReview:
        if self.reviewed_at > self.recorded_at:
            raise ValueError("Decision review reviewed_at must not be later than recorded_at.")
        return self

    @staticmethod
    def _normalize_ordered_text(
        value: object,
        *,
        field_name: str,
        required: bool,
        max_items: int,
        max_length: int,
    ) -> object:
        if not isinstance(value, (list, tuple)):
            return value
        if required and not value:
            raise ValueError("Decision review requires at least one finding.")
        if len(value) > max_items:
            raise ValueError(
                f"Decision review {field_name} must contain at most {max_items} items."
            )
        normalized: list[str] = []
        seen: set[str] = set()
        for raw_item in value:
            if not isinstance(raw_item, str):
                return value
            item = raw_item.strip()
            if not item:
                raise ValueError(f"Decision review {field_name} must not contain blank values.")
            if len(item) > max_length:
                raise ValueError(f"Decision review {field_name} item is too long.")
            semantic_key = item.casefold()
            if semantic_key in seen:
                raise ValueError(f"Decision review {field_name} must be unique.")
            seen.add(semantic_key)
            normalized.append(item)
        return tuple(normalized)

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

MAX_DECISION_REVIEW_PROMOTED_BY_LENGTH = 255
MAX_DECISION_REVIEW_PROMOTION_REASON_LENGTH = 1000
MAX_DECISION_REVIEW_PROMOTION_IDEMPOTENCY_KEY_LENGTH = 255
MAX_DECISION_REVIEW_PROMOTION_SOURCE_TEXT_LENGTH = 1000


class ExperienceResult(StrEnum):
    """Known outcome classification for an experience."""

    SUCCESS = "success"
    FAILURE = "failure"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class DecisionReviewPromotionSourceKind(StrEnum):
    """The exact DecisionReview collection from which a statement was selected."""

    FINDING = "finding"
    CANDIDATE_LESSON = "candidate_lesson"


class DecisionReviewPromotionSourceStatement(BaseModel):
    """One immutable statement copied from a DecisionReview at promotion time."""

    model_config = ConfigDict(frozen=True)

    kind: DecisionReviewPromotionSourceKind
    index: int = Field(ge=0)
    text: str

    @field_validator("text", mode="before")
    @classmethod
    def _text_must_be_bounded(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError("Decision review promotion source text must not be blank.")
        if len(normalized) > MAX_DECISION_REVIEW_PROMOTION_SOURCE_TEXT_LENGTH:
            raise ValueError("Decision review promotion source text is too long.")
        return normalized


class DecisionReviewPromotion(BaseModel):
    """Immutable provenance for explicit promotion of Review statements."""

    model_config = ConfigDict(frozen=True)

    decision_review_id: UUID
    source_statements: tuple[DecisionReviewPromotionSourceStatement, ...]
    promoted_by: str
    promotion_reason: str
    idempotency_key: str

    @field_validator("promoted_by", "promotion_reason", "idempotency_key", mode="before")
    @classmethod
    def _required_text_must_be_bounded(cls, value: object, info: ValidationInfo) -> object:
        if not isinstance(value, str):
            return value
        field_name = info.field_name
        assert field_name is not None
        return cls._normalize_required_text(field_name, value)

    @classmethod
    def normalize_metadata(
        cls, promoted_by: str, promotion_reason: str, idempotency_key: str
    ) -> tuple[str, str, str]:
        """Validate and normalize caller-owned promotion metadata before relation reads."""

        return (
            cls._normalize_required_text("promoted_by", promoted_by),
            cls._normalize_required_text("promotion_reason", promotion_reason),
            cls._normalize_required_text("idempotency_key", idempotency_key),
        )

    @staticmethod
    def _normalize_required_text(field_name: str, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"Decision review promotion {field_name} must not be blank.")
        limits = {
            "promoted_by": MAX_DECISION_REVIEW_PROMOTED_BY_LENGTH,
            "promotion_reason": MAX_DECISION_REVIEW_PROMOTION_REASON_LENGTH,
            "idempotency_key": MAX_DECISION_REVIEW_PROMOTION_IDEMPOTENCY_KEY_LENGTH,
        }
        if len(normalized) > limits[field_name]:
            raise ValueError(f"Decision review promotion {field_name} is too long.")
        return normalized

    @field_validator("source_statements")
    @classmethod
    def _sources_must_be_present_and_unique(
        cls,
        value: tuple[DecisionReviewPromotionSourceStatement, ...],
    ) -> tuple[DecisionReviewPromotionSourceStatement, ...]:
        if not value:
            raise ValueError("Decision review promotion requires at least one source statement.")
        pairs = [(statement.kind, statement.index) for statement in value]
        if len(pairs) != len(set(pairs)):
            raise ValueError("Decision review promotion source selectors must be unique.")
        return value


class Experience(BaseModel):
    """An event or action whose outcome is known or recorded."""

    id: UUID = Field(default_factory=uuid4)

    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    title: str

    context: str

    action: str

    outcome: str

    result: ExperienceResult

    observation_ids: list[UUID] = Field(default_factory=list)

    tags: list[str] = Field(default_factory=list)

    decision_review_promotion: DecisionReviewPromotion | None = Field(default=None, frozen=True)

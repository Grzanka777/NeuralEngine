from collections.abc import Mapping
from datetime import UTC, datetime
from enum import StrEnum
from math import isfinite
from types import MappingProxyType
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_serializer,
    field_validator,
)

from neural_engine.domain.decision import EvidenceReference

type DecisionOutcomeMetricValue = int | float | str | bool


class DecisionOutcomeResult(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


class DecisionOutcome(BaseModel):
    """A factual result and validation evidence for recorded Decision actions."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    decision_id: UUID
    acceptance_id: UUID
    action_ids: tuple[UUID, ...]
    result: DecisionOutcomeResult
    summary: str
    validated_by: str
    validated_at: datetime
    evidence_references: tuple[EvidenceReference, ...] = ()
    metrics: Mapping[str, DecisionOutcomeMetricValue] = Field(default_factory=dict)
    idempotency_key: str
    tags: tuple[str, ...] = ()

    @field_validator("recorded_at", "validated_at")
    @classmethod
    def _timestamps_must_be_utc_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Decision outcome timestamps must be timezone-aware.")
        return value.astimezone(UTC)

    @field_validator("summary", "validated_by", "idempotency_key", mode="before")
    @classmethod
    def _required_text_must_not_be_blank(cls, value: object, info: ValidationInfo) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"Decision outcome {info.field_name} must not be blank.")
        return normalized

    @field_validator("action_ids", mode="before")
    @classmethod
    def _action_ids_must_be_present_and_unique(cls, value: object) -> object:
        if not isinstance(value, (list, tuple)):
            return value
        normalized = tuple(value)
        if not normalized:
            raise ValueError("Decision outcome requires at least one action ID.")
        if len(normalized) != len(set(normalized)):
            raise ValueError("Decision outcome action IDs must be unique.")
        return normalized

    @field_validator("metrics", mode="before")
    @classmethod
    def _validate_metrics(cls, value: object) -> object:
        if not isinstance(value, Mapping):
            return value
        if len(value) > 100:
            raise ValueError("Decision outcome metrics must contain at most 100 entries.")

        normalized: dict[str, DecisionOutcomeMetricValue] = {}
        semantic_keys: set[str] = set()
        for key, metric_value in value.items():
            if not isinstance(key, str):
                raise ValueError("Decision outcome metric keys must be strings.")
            normalized_key = key.strip()
            if not normalized_key:
                raise ValueError("Decision outcome metric keys must not be blank.")
            if len(normalized_key) > 64:
                raise ValueError("Decision outcome metric key is too long.")
            semantic_key = normalized_key.casefold()
            if semantic_key in semantic_keys:
                raise ValueError("Decision outcome metric keys must be unique.")
            semantic_keys.add(semantic_key)

            if not isinstance(metric_value, (bool, int, float, str)):
                raise ValueError(
                    "Decision outcome metric values must be bool, int, float, or string."
                )
            if isinstance(metric_value, float) and not isfinite(metric_value):
                raise ValueError("Decision outcome float metrics must be finite.")
            if isinstance(metric_value, str) and len(metric_value) > 1000:
                raise ValueError("Decision outcome string metric value is too long.")
            normalized[normalized_key] = metric_value

        return normalized

    @field_validator("metrics")
    @classmethod
    def _freeze_metrics(
        cls, value: Mapping[str, DecisionOutcomeMetricValue]
    ) -> Mapping[str, DecisionOutcomeMetricValue]:
        return MappingProxyType(dict(value))

    @field_serializer("metrics")
    def _serialize_metrics(
        self, value: Mapping[str, DecisionOutcomeMetricValue]
    ) -> dict[str, DecisionOutcomeMetricValue]:
        return {key: value[key] for key in sorted(value)}

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
                raise ValueError("Decision outcome tags must not contain blank values.")
            semantic_key = item.casefold()
            if semantic_key not in seen:
                seen.add(semantic_key)
                normalized.append(item)
        return tuple(normalized)

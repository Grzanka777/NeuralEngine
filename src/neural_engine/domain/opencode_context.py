"""Value objects for bounded, read-only OpenCode context observation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ContextSourceQuality(StrEnum):
    """How faithfully an observation represents current OpenCode context."""

    EXACT = "EXACT"
    ESTIMATED = "ESTIMATED"
    UNKNOWN = "UNKNOWN"


class ContextPressureLevel(StrEnum):
    """Explicit pressure categories for the frozen production context limit."""

    HEALTHY = "HEALTHY"
    NOTICE = "NOTICE"
    HANDOFF = "HANDOFF"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class OpencodeContextObservation:
    """One read-only session selection and token observation."""

    session_id: str | None
    current_tokens: int | None
    context_limit: int
    source_quality: ContextSourceQuality
    source_description: str
    uncertainty: str | None = None


@dataclass(frozen=True, slots=True)
class ContextPressure:
    """A source-aware assessment, independent from OpenCode access."""

    level: ContextPressureLevel
    remaining_tokens: int | None
    ratio: float | None
    recommendation: str


class SessionAssociationMethod(StrEnum):
    """Technique used to associate a watcher with a specific OpenCode session."""

    DIRECT_ARGUMENT = "direct_argument"
    PROCESS_CORRELATED = "process_correlated"
    NEW_SESSION_DELTA = "new_session_delta"
    TIMESTAMP_CORRELATION = "timestamp_correlation"


@dataclass(frozen=True, slots=True)
class SessionResolutionResult:
    """Outcome of resolving an exact OpenCode session."""

    session_id: str | None
    method: SessionAssociationMethod | None
    candidates: tuple[str, ...]
    error: str | None = None

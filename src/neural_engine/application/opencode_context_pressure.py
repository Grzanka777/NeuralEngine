"""Pure, source-aware assessment of OpenCode context pressure."""

from __future__ import annotations

from neural_engine.domain.opencode_context import (
    ContextPressure,
    ContextPressureLevel,
    ContextSourceQuality,
)

PRODUCTION_CONTEXT_LIMIT = 32_768
NOTICE_THRESHOLD = 22_000
HANDOFF_THRESHOLD = 25_000
CRITICAL_THRESHOLD = 29_000


def assess_context_pressure(
    current_tokens: int | None,
    context_limit: int = PRODUCTION_CONTEXT_LIMIT,
    source_quality: ContextSourceQuality = ContextSourceQuality.UNKNOWN,
) -> ContextPressure:
    """Classify tokens without assuming an estimated value is exact live state."""

    if current_tokens is None or source_quality is ContextSourceQuality.UNKNOWN:
        return ContextPressure(
            level=ContextPressureLevel.UNKNOWN,
            remaining_tokens=None,
            ratio=None,
            recommendation="verify the OpenCode session and context source before continuing",
        )
    if current_tokens < 0:
        raise ValueError("Current context tokens must not be negative.")
    if context_limit <= 0:
        raise ValueError("Context limit must be positive.")

    remaining = max(context_limit - current_tokens, 0)
    ratio = current_tokens / context_limit
    if current_tokens < NOTICE_THRESHOLD:
        return ContextPressure(
            level=ContextPressureLevel.HEALTHY,
            remaining_tokens=remaining,
            ratio=ratio,
            recommendation="continue current session",
        )
    if current_tokens < HANDOFF_THRESHOLD:
        return ContextPressure(
            level=ContextPressureLevel.NOTICE,
            remaining_tokens=remaining,
            ratio=ratio,
            recommendation="continue, but avoid unnecessary full-file/log expansion",
        )
    if current_tokens < CRITICAL_THRESHOLD:
        return ContextPressure(
            level=ContextPressureLevel.HANDOFF,
            remaining_tokens=remaining,
            ratio=ratio,
            recommendation="prepare verified fresh-session handoff",
        )
    if source_quality is ContextSourceQuality.EXACT:
        return ContextPressure(
            level=ContextPressureLevel.CRITICAL,
            remaining_tokens=remaining,
            ratio=ratio,
            recommendation="create handoff before additional large tool/file output",
        )
    return ContextPressure(
        level=ContextPressureLevel.HANDOFF,
        remaining_tokens=remaining,
        ratio=ratio,
        recommendation=(
            "prepare verified fresh-session handoff; estimate cannot confirm critical pressure"
        ),
    )

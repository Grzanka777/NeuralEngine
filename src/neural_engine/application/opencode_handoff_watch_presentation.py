"""Presentation-only rendering for OpenCode handoff-watch reports."""

from __future__ import annotations

from neural_engine.application.opencode_handoff_watch_service import OpencodeHandoffWatchReport
from neural_engine.domain.opencode_context import ContextSourceQuality


def render_opencode_handoff_watch(report: OpencodeHandoffWatchReport) -> str:
    """Render concise status without querying, changing, or summarizing OpenCode."""

    observation = report.observation
    pressure = report.pressure
    if observation.current_tokens is None:
        context = f"unavailable / {observation.context_limit}"
    elif observation.source_quality is ContextSourceQuality.ESTIMATED:
        context = f"~{observation.current_tokens} / {observation.context_limit}"
    else:
        context = f"{observation.current_tokens} / {observation.context_limit}"

    lines = [
        "OPENCODE CONTEXT WATCH",
        f"session: {observation.session_id or 'unavailable'}",
        f"context: {context}",
        f"source: {observation.source_quality.value} ({observation.source_description})",
    ]
    if pressure.remaining_tokens is not None:
        lines.append(f"remaining: {pressure.remaining_tokens}")
    lines.extend(
        [
            f"pressure: {pressure.level.value}",
            f"recommendation: {pressure.recommendation}",
        ]
    )
    if observation.uncertainty is not None:
        lines.append(f"uncertainty: {observation.uncertainty}")
    return "\n".join(lines)

"""Read-only OpenCode observation and pressure-assessment use case."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from neural_engine.application.opencode_context_pressure import assess_context_pressure
from neural_engine.domain.opencode_context import ContextPressure, OpencodeContextObservation
from neural_engine.ports.opencode_session_observer import OpencodeSessionObserver


@dataclass(frozen=True, slots=True)
class OpencodeHandoffWatchReport:
    """One separated observation and pure pressure result."""

    observation: OpencodeContextObservation
    pressure: ContextPressure


class OpencodeHandoffWatchService:
    """Coordinate a read-only observer with the independent pressure model."""

    def __init__(self, observer: OpencodeSessionObserver) -> None:
        self._observer = observer

    def inspect(self, *, session_id: str | None, directory: Path) -> OpencodeHandoffWatchReport:
        observation = self._observer.observe(session_id=session_id, directory=directory)
        return OpencodeHandoffWatchReport(
            observation=observation,
            pressure=assess_context_pressure(
                observation.current_tokens,
                observation.context_limit,
                observation.source_quality,
            ),
        )

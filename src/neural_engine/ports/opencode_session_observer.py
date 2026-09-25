"""Read-only boundary for selecting and observing an OpenCode session."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from neural_engine.domain.opencode_context import OpencodeContextObservation


class OpencodeSessionObserver(Protocol):
    """Observe one explicitly selected or unambiguous local OpenCode session."""

    def observe(self, *, session_id: str | None, directory: Path) -> OpencodeContextObservation: ...

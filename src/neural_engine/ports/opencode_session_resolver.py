"""Port protocol for resolving exact OpenCode sessions safely without guessing."""

from pathlib import Path
from typing import Protocol

from neural_engine.domain.opencode_context import SessionResolutionResult


class OpencodeSessionResolver(Protocol):
    """Resolve an exact OpenCode session ID safely without guessing."""

    def snapshot_sessions(self, *, directory: Path) -> set[str]:
        """Capture existing session IDs for the directory before launching OpenCode."""
        ...

    def resolve(
        self,
        *,
        directory: Path,
        explicit_session_id: str | None = None,
        snapshot_ids: set[str] | None = None,
        start_timestamp_ms: int | None = None,
    ) -> SessionResolutionResult:
        """Resolve the session using preferred association methods, failing closed on ambiguity."""
        ...

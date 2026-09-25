"""Read-only repository facts needed for an OpenCode handoff."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class HandoffRepositoryCheckpoint:
    """One bounded live repository checkpoint without raw status output."""

    root: Path
    branch: str
    head: str
    worktree_entries: int


class OpencodeHandoffRepository(Protocol):
    """Inspect one Git repository and validate named working-set files."""

    def inspect(self, requested_root: Path) -> HandoffRepositoryCheckpoint: ...

    def resolve_file(self, checkpoint: HandoffRepositoryCheckpoint, value: str) -> str: ...

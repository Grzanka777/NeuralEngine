"""Local, read-only Git and path adapter for manual OpenCode handoffs."""

from __future__ import annotations

import subprocess
from pathlib import Path

from neural_engine.ports.opencode_handoff_repository import HandoffRepositoryCheckpoint


class OpencodeHandoffRepositoryError(Exception):
    """Base failure while collecting local handoff repository facts."""


class LocalOpencodeHandoffRepository:
    """Read only bounded Git metadata and caller-selected repository files."""

    def inspect(self, requested_root: Path) -> HandoffRepositoryCheckpoint:
        root = requested_root.resolve()
        if not root.is_dir():
            raise OpencodeHandoffRepositoryError(f"Repository root does not exist: {root}")

        try:
            git_root = Path(self._git(root, "rev-parse", "--show-toplevel")).resolve()
            branch = self._git(root, "branch", "--show-current") or "DETACHED"
            head = self._git(root, "rev-parse", "HEAD")
            worktree_entries = len(
                self._git(root, "status", "--short", "--untracked-files=normal").splitlines()
            )
        except RuntimeError as error:
            raise OpencodeHandoffRepositoryError(
                "Could not establish a live Git repository checkpoint."
            ) from error

        return HandoffRepositoryCheckpoint(
            root=git_root,
            branch=branch,
            head=head,
            worktree_entries=worktree_entries,
        )

    def resolve_file(self, checkpoint: HandoffRepositoryCheckpoint, value: str) -> str:
        supplied = Path(value)
        if supplied.is_absolute():
            raise OpencodeHandoffRepositoryError(
                "Working-set file paths must be repository-relative."
            )
        resolved = (checkpoint.root / supplied).resolve()
        try:
            relative = resolved.relative_to(checkpoint.root)
        except ValueError as error:
            raise OpencodeHandoffRepositoryError(
                "Working-set file path escapes the repository."
            ) from error
        if not resolved.is_file():
            raise OpencodeHandoffRepositoryError(
                f"Working-set file does not exist: {relative.as_posix()}"
            )
        return relative.as_posix()

    @staticmethod
    def _git(root: Path, *arguments: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(root), *arguments],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if result.returncode != 0:
            raise RuntimeError("Git command failed")
        return result.stdout.strip()

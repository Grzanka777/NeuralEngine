import os
from dataclasses import dataclass
from pathlib import Path

from neural_engine.core.paths import NeuralPaths, resolve_neural_paths

BRAIN_FORMAT_VERSION = "1.0.0"


@dataclass(frozen=True, slots=True)
class BrainStatus:
    """Read-only status of one selected Neural home and Brain."""

    home_exists: bool
    home_is_directory: bool
    home_accessible: bool
    brain_exists: bool
    brain_accessible: bool

    @property
    def initialized(self) -> bool:
        return self.brain_exists and self.brain_accessible


class Brain:
    """Represents one selected local Neural Engine brain."""

    def __init__(self, paths: NeuralPaths | None = None) -> None:
        self.paths = paths if paths is not None else resolve_neural_paths()

    def initialize(self) -> None:
        if self.paths.is_override:
            self.paths.require_available(operation="initialization", writable=True)
        else:
            self.paths.HOME.mkdir(parents=True, exist_ok=True)

        directories: list[Path] = [
            self.paths.BRAIN,
            *(path for _, path in self.paths.record_stores),
            self.paths.PROJECTS,
            self.paths.LOGS,
        ]

        for directory in directories:
            directory.mkdir(exist_ok=True)

        self.paths.VERSION.write_text(f"{BRAIN_FORMAT_VERSION}\n")

        if not self.paths.CONFIG.exists():
            self.paths.CONFIG.write_text("# Neural Engine configuration\n")

    def status(self) -> BrainStatus:
        home_exists = self.paths.HOME.exists()
        home_is_directory = home_exists and self.paths.HOME.is_dir()
        home_accessible = home_is_directory and os.access(
            self.paths.HOME,
            os.R_OK | os.X_OK,
        )
        brain_exists = home_accessible and (
            self.paths.BRAIN.exists() or self.paths.BRAIN.is_symlink()
        )
        brain_accessible = (
            brain_exists
            and self.paths.BRAIN.is_dir()
            and os.access(self.paths.BRAIN, os.R_OK | os.X_OK)
        )
        return BrainStatus(
            home_exists=home_exists,
            home_is_directory=home_is_directory,
            home_accessible=home_accessible,
            brain_exists=brain_exists,
            brain_accessible=brain_accessible,
        )

    def exists(self) -> bool:
        return self.status().initialized

    def require_initialized(self, *, operation: str, writable: bool = False) -> None:
        self.paths.require_available(
            operation=operation,
            writable=writable,
            require_brain=True,
        )

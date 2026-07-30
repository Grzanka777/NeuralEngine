from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from neural_engine.core.paths import NeuralPaths, resolve_neural_paths

StoreSelector = Callable[[NeuralPaths], Path]


@dataclass(frozen=True, slots=True)
class RepositoryPath:
    """A repository directory with an optional resolved-root guard."""

    directory: Path
    paths: NeuralPaths | None

    @classmethod
    def build(
        cls,
        directory: Path | None,
        paths: NeuralPaths | None,
        selector: StoreSelector,
    ) -> RepositoryPath:
        if directory is not None:
            if paths is not None:
                raise ValueError("directory and paths are mutually exclusive")
            return cls(directory=directory, paths=None)

        resolved_paths = paths if paths is not None else resolve_neural_paths()
        return cls(directory=selector(resolved_paths), paths=resolved_paths)

    def guard(self, *, operation: str, writable: bool = False) -> None:
        if self.paths is None:
            return
        self.paths.require_available(
            operation=operation,
            writable=writable,
            require_brain=True,
        )

    def prepare_for_write(self) -> None:
        self.guard(operation="write", writable=True)
        if self.paths is None or not self.paths.is_override:
            self.directory.mkdir(parents=True, exist_ok=True)
        else:
            self.directory.mkdir(exist_ok=True)

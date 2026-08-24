from collections.abc import Callable
from pathlib import Path

from neural_engine.core.brain_trust import TargetAction
from neural_engine.core.paths import NeuralPaths
from neural_engine.infrastructure.durability import create_once_bytes
from neural_engine.ports.brain_trust_transition import ControlledMutationTarget


def build_controlled_create_target(
    paths: NeuralPaths | None,
    path: Path,
    after_bytes: bytes,
    publish: Callable[[], None],
) -> ControlledMutationTarget:
    """Build one Brain-relative CREATE target for a paths-backed adapter."""

    if paths is None:
        raise ValueError("Controlled CREATE targets require NeuralPaths-backed storage.")

    try:
        relative_path = path.relative_to(paths.BRAIN).as_posix()
    except ValueError as error:
        raise ValueError("Controlled CREATE target must be Brain-relative.") from error

    return ControlledMutationTarget(
        relative_path=relative_path,
        action=TargetAction.CREATE,
        after_bytes=after_bytes,
        publish=publish,
    )


def publish_create_once(
    path: Path,
    data: bytes,
    prepare_for_write: Callable[[], None],
) -> None:
    """Publish exact bytes without replacing an existing target."""

    prepare_for_write()
    create_once_bytes(path, data)

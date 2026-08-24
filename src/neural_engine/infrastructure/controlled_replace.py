import hashlib
import stat
from collections.abc import Callable
from pathlib import Path

from neural_engine.application.brain_trust_transition import BrainTrustStalePreimageError
from neural_engine.core.brain_trust import TargetAction
from neural_engine.core.paths import NeuralPaths
from neural_engine.infrastructure.durability import atomic_replace_bytes
from neural_engine.ports.brain_trust_transition import ControlledMutationTarget


def build_controlled_replace_target(
    paths: NeuralPaths | None,
    path: Path,
    before_sha256: str,
    after_bytes: bytes,
    publish: Callable[[], None],
) -> ControlledMutationTarget:
    """Build one Brain-relative single-record REPLACE target."""

    if paths is None:
        raise ValueError("Controlled REPLACE targets require NeuralPaths-backed storage.")

    try:
        relative_path = path.relative_to(paths.BRAIN).as_posix()
    except ValueError as error:
        raise ValueError("Controlled REPLACE target must be Brain-relative.") from error

    return ControlledMutationTarget(
        relative_path=relative_path,
        action=TargetAction.REPLACE,
        after_bytes=after_bytes,
        publish=publish,
        before_sha256=before_sha256,
    )


def publish_replace_if_unchanged(
    path: Path,
    relative_path: str,
    before_sha256: str,
    data: bytes,
    prepare_for_write: Callable[[], None],
) -> None:
    """Publish exact replacement bytes only when the literal preimage remains current."""

    try:
        target_stat = path.lstat()
    except FileNotFoundError:
        actual_sha256 = None
    else:
        if not stat.S_ISREG(target_stat.st_mode):
            raise BrainTrustStalePreimageError(relative_path, before_sha256, None)
        actual_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()

    if actual_sha256 != before_sha256:
        raise BrainTrustStalePreimageError(relative_path, before_sha256, actual_sha256)

    prepare_for_write()
    atomic_replace_bytes(path, data)

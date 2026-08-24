from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from neural_engine.core.brain_trust import TargetAction


@dataclass(frozen=True, slots=True)
class ControlledMutationTarget:
    """One exact durable target prepared for a controlled Brain mutation."""

    relative_path: str
    action: TargetAction
    after_bytes: bytes | None
    publish: Callable[[], None]


class BrainTrustMutationCoordinator(Protocol):
    """Application-facing port for one controlled Brain mutation."""

    def execute(self, target: ControlledMutationTarget) -> None:
        """Execute one ordinary mutation using the frozen trust ordering."""


WriteBytes = Callable[[Path, bytes], None]

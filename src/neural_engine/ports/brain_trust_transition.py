from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import UUID

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


class BrainTrustRecoveryCoordinator(Protocol):
    """Application-facing port for the explicit bounded recovery command."""

    def recover_pending_knowledge_create(self) -> UUID:
        """Complete only a valid pending Knowledge CREATE suffix."""


WriteBytes = Callable[[Path, bytes], None]

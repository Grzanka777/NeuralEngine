from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, TypeVar
from uuid import UUID

from neural_engine.core.brain_trust import TargetAction

RecordT = TypeVar("RecordT", contravariant=True)


@dataclass(frozen=True, slots=True)
class ControlledMutationTarget:
    """One exact durable target prepared for a controlled Brain mutation."""

    relative_path: str
    action: TargetAction
    after_bytes: bytes | None
    publish: Callable[[], None]


class ControlledCreateWriter(Protocol[RecordT]):
    """Prepare one validated single-record CREATE without publishing it."""

    def controlled_create_target(self, record: RecordT) -> ControlledMutationTarget: ...


class BrainTrustMutationCoordinator(Protocol):
    """Application-facing port for one controlled Brain mutation."""

    def execute(self, target: ControlledMutationTarget) -> None:
        """Execute one ordinary mutation using the frozen trust ordering."""


class BrainTrustRecoveryCoordinator(Protocol):
    """Application-facing port for the explicit bounded recovery command."""

    def recover_pending_knowledge_create(self) -> UUID:
        """Complete only a valid pending supported single-record CREATE suffix."""


WriteBytes = Callable[[Path, bytes], None]

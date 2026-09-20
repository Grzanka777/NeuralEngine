from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class OpencodeCapabilityObservation:
    """Raw capability evidence collected without applying policy."""

    name: str
    available: bool | None
    detail: str
    critical: bool


@dataclass(frozen=True, slots=True)
class OpencodeCompatibilityEvidence:
    """Read-only local evidence used by the compatibility service."""

    version: str | None
    capabilities: tuple[OpencodeCapabilityObservation, ...]
    wrapper_path: Path | None
    llm_path: Path | None
    model_ids: tuple[tuple[str, str], ...]


class OpencodeCompatibilityProbe(Protocol):
    """Read the local OpenCode integration surface without mutating it."""

    def inspect(self) -> OpencodeCompatibilityEvidence: ...


class OpencodeLiveSmokeRunner(Protocol):
    """Run the explicitly requested bounded OpenCode smoke."""

    def run(
        self,
        evidence: OpencodeCompatibilityEvidence,
        *,
        lane: str,
    ) -> tuple[bool, str]: ...

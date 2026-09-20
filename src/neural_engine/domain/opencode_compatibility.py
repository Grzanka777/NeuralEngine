from dataclasses import dataclass
from enum import StrEnum


class OpencodeCompatibilityState(StrEnum):
    """Outcome of the rolling OpenCode capability check."""

    PASS = "PASS"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"


class OpencodeCommandProtocolState(StrEnum):
    """Read-only status of the repository-owned Command Protocol adapter."""

    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass(frozen=True, slots=True)
class OpencodeCommandProtocolCheck:
    """One observable Command Protocol adapter result."""

    name: str
    state: OpencodeCommandProtocolState
    detail: str


@dataclass(frozen=True, slots=True)
class OpencodeCommandProtocolReport:
    """Read-only Command Protocol adapter report."""

    checks: tuple[OpencodeCommandProtocolCheck, ...]
    protocol_version: str | None
    workflow_version: str | None


@dataclass(frozen=True, slots=True)
class OpencodeCompatibilityCheck:
    """One observable OpenCode capability result."""

    name: str
    state: OpencodeCompatibilityState
    detail: str


@dataclass(frozen=True, slots=True)
class OpencodeLiveSmokeResult:
    """Result of an explicitly requested bounded runtime smoke."""

    lane: str
    state: OpencodeCompatibilityState
    detail: str


@dataclass(frozen=True, slots=True)
class OpencodeCompatibilityReport:
    """Complete fast-preflight and optional live-smoke report."""

    version: str | None
    checks: tuple[OpencodeCompatibilityCheck, ...]
    compatibility: OpencodeCompatibilityState
    live_smoke: OpencodeLiveSmokeResult | None = None
    command_protocol: OpencodeCommandProtocolReport | None = None

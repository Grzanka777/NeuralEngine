from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from uuid import UUID


class AdoptionState(StrEnum):
    """Adoption-specific states kept separate from the generic trust enum."""

    UNADOPTED_FRESH = "UNADOPTED_FRESH"
    ADOPTION_PENDING_BINDING = "ADOPTION_PENDING_BINDING"
    ADOPTION_PENDING_FINALIZATION = "ADOPTION_PENDING_FINALIZATION"
    TRUSTED_CURRENT = "TRUSTED_CURRENT"
    MANUAL_INTERVENTION_REQUIRED = "MANUAL_INTERVENTION_REQUIRED"


class AdoptionErrorCode(StrEnum):
    """Stable categories for controlled adoption failures."""

    NOT_ELIGIBLE = "not eligible"
    BACKUP_MISSING = "backup missing"
    HOME_NOT_WRITABLE = "home not writable"
    BINDING_PARENT_NOT_READY = "binding parent not ready"
    PREEXISTING_TRUST_ARTIFACT = "preexisting trust artifact"
    UNSAFE_PATH = "unsafe path"
    RECORD_VALIDATION_FAILURE = "record validation failure"
    METADATA_PUBLICATION_FAILURE = "metadata publication failure"
    METADATA_VERIFICATION_FAILURE = "metadata verification failure"
    BINDING_CREATION_FAILURE = "binding creation failure"
    BINDING_VERIFICATION_FAILURE = "binding verification failure"
    FINALIZATION_FAILURE = "finalization failure"
    MANUAL_INTERVENTION_REQUIRED = "manual intervention required"
    AUTHORIZATION_REJECTED = "authorization rejected"


class BrainTrustAdoptionError(Exception):
    """Base error for controlled Brain Trust adoption operations."""

    def __init__(self, code: AdoptionErrorCode, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"Brain Trust adoption {code.value}: {detail}.")


class AdoptionNotEligibleError(BrainTrustAdoptionError):
    """Raised when final adoption preflight has blockers."""

    def __init__(self, blockers: tuple[str, ...]) -> None:
        self.blockers = blockers
        super().__init__(AdoptionErrorCode.NOT_ELIGIBLE, "; ".join(blockers))


class AdoptionAuthorizationError(BrainTrustAdoptionError):
    """Raised when an identity-bound adoption confirmation is absent or wrong."""

    def __init__(self, detail: str = "exact identity-bound confirmation was not provided") -> None:
        super().__init__(AdoptionErrorCode.AUTHORIZATION_REJECTED, detail)


class AdoptionManualInterventionError(BrainTrustAdoptionError):
    """Raised when durable evidence is ambiguous or outside the bounded slice."""

    def __init__(self, detail: str) -> None:
        super().__init__(AdoptionErrorCode.MANUAL_INTERVENTION_REQUIRED, detail)


@dataclass(frozen=True, slots=True)
class AdoptionPlan:
    """Read-only adoption evidence and blockers."""

    neural_home: Path
    brain_path: Path
    binding_path: Path
    binding_parent: Path
    state: AdoptionState
    eligible: bool
    blockers: tuple[str, ...]
    store_counts: tuple[tuple[str, int], ...]
    record_snapshot: tuple[tuple[str, bytes], ...]
    metadata_present: bool
    binding_present: bool
    home_writable: bool
    binding_parent_ready: bool
    backup_evidence: Path | None


@dataclass(frozen=True, slots=True)
class PreparedAdoption:
    """In-memory, non-persisted execution plan bound to one generated identity."""

    plan: AdoptionPlan
    brain_id: UUID
    transition_id: UUID

    @property
    def confirmation_token(self) -> str:
        return f"ADOPT {self.brain_id}"


@dataclass(frozen=True, slots=True)
class AdoptionResult:
    """Evidence returned only after final TRUSTED_CURRENT verification."""

    state: AdoptionState
    brain_id: UUID
    transition_id: UUID
    generation: int
    record_count: int
    neural_home: Path
    brain_path: Path
    binding_path: Path

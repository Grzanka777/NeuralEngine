from __future__ import annotations

from pathlib import Path
from typing import Protocol

from neural_engine.application.brain_trust_adoption import (
    AdoptionPlan,
    AdoptionResult,
    PreparedAdoption,
)


class BrainTrustAdoptionCoordinator(Protocol):
    """Application-facing port for bounded local Brain adoption."""

    def plan(self, backup_evidence: Path | None = None) -> AdoptionPlan:
        """Return read-only eligibility evidence and blockers."""

    def prepare(self, backup_evidence: Path | None = None) -> PreparedAdoption:
        """Run final preflight and generate an in-memory identity-bound plan."""

    def execute(self, prepared: PreparedAdoption, confirmation: str) -> AdoptionResult:
        """Revalidate and execute A1-A6 after exact authorization."""

    def recover(self, authorization: str) -> AdoptionResult:
        """Continue only a valid persisted S1/S2 adoption suffix."""

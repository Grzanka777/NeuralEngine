from __future__ import annotations

from uuid import UUID

from neural_engine.application.brain_trust_inspector import BrainTrustState


class BrainTrustMutationError(Exception):
    """Base error for a controlled Brain mutation."""


class BrainTrustMutationNotPermittedError(BrainTrustMutationError):
    """Raised when the current Brain is not eligible for ordinary mutation."""

    def __init__(self, state: BrainTrustState, reasons: tuple[str, ...]) -> None:
        self.state = state
        self.reasons = reasons
        detail = "; ".join(reasons) if reasons else "no classification details"
        super().__init__(f"Controlled Brain mutation is not permitted in state {state}: {detail}.")


class BrainTrustTransitionExecutionError(BrainTrustMutationError):
    """Raised when a controlled transition fails and its state must be inspected."""

    def __init__(self, transition_id: UUID, cause: Exception) -> None:
        self.transition_id = transition_id
        self.cause = cause
        super().__init__(
            f"Controlled Brain transition {transition_id} failed; durable state may be advanced."
        )

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from neural_engine.core.brain_trust import (
    BrainMetadata,
    BrainTrustCompatibility,
    ExternalTrustBinding,
)
from neural_engine.core.paths import NeuralPaths
from neural_engine.ports.brain_trust_probe import (
    BrainTrustProbe,
    BrainTrustProbeEvidence,
    TrustArtifactEvidence,
)


class BrainTrustState(StrEnum):
    """Frozen top-level read-only Brain trust classifications."""

    UNADOPTED = "UNADOPTED"
    TRUSTED_CURRENT = "TRUSTED_CURRENT"
    TRANSITION_PENDING = "TRANSITION_PENDING"
    UNTRUSTED_AHEAD = "UNTRUSTED_AHEAD"
    STALE_OR_ROLLBACK = "STALE_OR_ROLLBACK"
    FOREIGN = "FOREIGN"
    BINDING_MISSING = "BINDING_MISSING"
    METADATA_INVALID = "METADATA_INVALID"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"


@dataclass(frozen=True, slots=True)
class BrainTrustInspection:
    """Immutable evidence and classification for one trust inspection."""

    state: BrainTrustState
    brain_present: bool
    brain_structurally_present: bool
    brain_readable: bool
    brain_metadata_present: bool
    binding_present: bool
    metadata_format_status: BrainTrustCompatibility | None
    binding_format_status: BrainTrustCompatibility | None
    metadata_valid: bool
    binding_valid: bool
    brain_id: UUID | None
    expected_brain_id: UUID | None
    generation: int | None
    accepted_generation: int | None
    pending_transition_present: bool
    metadata_issue: str | None
    binding_issue: str | None
    reasons: tuple[str, ...]


class BrainTrustInspector:
    """Classify Brain trust state without repair, adoption, or other writes."""

    def __init__(self, path_resolver: Callable[[], NeuralPaths], probe: BrainTrustProbe) -> None:
        self._path_resolver = path_resolver
        self._probe = probe

    def inspect(self) -> BrainTrustInspection:
        paths = self._path_resolver()
        return self.inspect_paths(paths)

    def inspect_paths(self, paths: NeuralPaths) -> BrainTrustInspection:
        """Inspect one already-resolved Neural home without resolving it again."""

        return self.classify(self._probe.inspect(paths))

    @classmethod
    def classify(cls, evidence: BrainTrustProbeEvidence) -> BrainTrustInspection:
        metadata = evidence.metadata
        binding = evidence.binding
        metadata_model = metadata.model if isinstance(metadata.model, BrainMetadata) else None
        binding_model = binding.model if isinstance(binding.model, ExternalTrustBinding) else None
        metadata_issue = _artifact_issue(metadata)
        binding_issue = _artifact_issue(binding)
        base_reasons = _brain_reasons(evidence)

        if not evidence.brain_structurally_present or not evidence.brain_readable:
            if not metadata.present and not binding.present:
                return cls._result(
                    evidence,
                    BrainTrustState.UNADOPTED,
                    metadata_model,
                    binding_model,
                    (*base_reasons, "trust metadata and binding absent"),
                    metadata_issue,
                    binding_issue,
                )
            return cls._result(
                evidence,
                BrainTrustState.RECOVERY_REQUIRED,
                metadata_model,
                binding_model,
                (*base_reasons, "Brain is not inspectable"),
                metadata_issue,
                binding_issue,
            )

        if not metadata.present:
            if not binding.present:
                return cls._result(
                    evidence,
                    BrainTrustState.UNADOPTED,
                    metadata_model,
                    binding_model,
                    (*base_reasons, "trust metadata and binding absent"),
                    metadata_issue,
                    binding_issue,
                )
            return cls._result(
                evidence,
                BrainTrustState.RECOVERY_REQUIRED,
                metadata_model,
                binding_model,
                (*base_reasons, "metadata missing while binding is present"),
                metadata_issue,
                binding_issue,
            )

        if metadata_issue is not None or metadata_model is None:
            return cls._result(
                evidence,
                BrainTrustState.METADATA_INVALID,
                metadata_model,
                binding_model,
                (*base_reasons, _metadata_reason(metadata)),
                metadata_issue,
                binding_issue,
            )

        if not binding.present:
            return cls._result(
                evidence,
                BrainTrustState.BINDING_MISSING,
                metadata_model,
                binding_model,
                (*base_reasons, "binding missing"),
                metadata_issue,
                binding_issue,
            )

        if binding_issue is not None or binding_model is None:
            return cls._result(
                evidence,
                BrainTrustState.RECOVERY_REQUIRED,
                metadata_model,
                binding_model,
                (*base_reasons, _binding_reason(binding)),
                metadata_issue,
                binding_issue,
            )

        pending = metadata_model.pending_transition
        if pending is not None and pending.brain_id != metadata_model.brain_id:
            return cls._result(
                evidence,
                BrainTrustState.METADATA_INVALID,
                metadata_model,
                binding_model,
                (*base_reasons, "pending transition brain identity mismatch"),
                metadata_issue,
                binding_issue,
            )

        if metadata_model.brain_id != binding_model.expected_brain_id:
            return cls._result(
                evidence,
                BrainTrustState.FOREIGN,
                metadata_model,
                binding_model,
                (*base_reasons, "brain identity mismatch"),
                metadata_issue,
                binding_issue,
            )

        generation_reason: str | None = None
        generation_state: BrainTrustState | None = None
        if metadata_model.generation < binding_model.accepted_generation:
            generation_state = BrainTrustState.STALE_OR_ROLLBACK
            generation_reason = "brain generation behind accepted generation"
        elif metadata_model.generation > binding_model.accepted_generation:
            generation_state = BrainTrustState.UNTRUSTED_AHEAD
            generation_reason = "brain generation ahead of accepted generation"

        if pending is not None:
            reasons = (*base_reasons, "pending transition present")
            if generation_reason is not None:
                reasons = (*reasons, generation_reason)
            return cls._result(
                evidence,
                BrainTrustState.TRANSITION_PENDING,
                metadata_model,
                binding_model,
                reasons,
                metadata_issue,
                binding_issue,
            )

        if generation_state is not None and generation_reason is not None:
            return cls._result(
                evidence,
                generation_state,
                metadata_model,
                binding_model,
                (*base_reasons, generation_reason),
                metadata_issue,
                binding_issue,
            )

        return cls._result(
            evidence,
            BrainTrustState.TRUSTED_CURRENT,
            metadata_model,
            binding_model,
            (*base_reasons, "identity and generation match"),
            metadata_issue,
            binding_issue,
        )

    @staticmethod
    def _result(
        evidence: BrainTrustProbeEvidence,
        state: BrainTrustState,
        metadata: BrainMetadata | None,
        binding: ExternalTrustBinding | None,
        reasons: tuple[str, ...],
        metadata_issue: str | None,
        binding_issue: str | None,
    ) -> BrainTrustInspection:
        return BrainTrustInspection(
            state=state,
            brain_present=evidence.brain_present,
            brain_structurally_present=evidence.brain_structurally_present,
            brain_readable=evidence.brain_readable,
            brain_metadata_present=evidence.metadata.present,
            binding_present=evidence.binding.present,
            metadata_format_status=evidence.metadata.format_status,
            binding_format_status=evidence.binding.format_status,
            metadata_valid=metadata is not None,
            binding_valid=binding is not None,
            brain_id=metadata.brain_id if metadata is not None else None,
            expected_brain_id=binding.expected_brain_id if binding is not None else None,
            generation=metadata.generation if metadata is not None else None,
            accepted_generation=binding.accepted_generation if binding is not None else None,
            pending_transition_present=(
                metadata is not None and metadata.pending_transition is not None
            ),
            metadata_issue=metadata_issue,
            binding_issue=binding_issue,
            reasons=_unique(reasons),
        )


def _artifact_issue(artifact: TrustArtifactEvidence) -> str | None:
    return artifact.issue


def _metadata_reason(artifact: TrustArtifactEvidence) -> str:
    if artifact.issue == "unsupported_format":
        return "unsupported metadata format"
    return "metadata malformed"


def _binding_reason(artifact: TrustArtifactEvidence) -> str:
    if artifact.issue == "unsupported_format":
        return "unsupported binding format"
    return "binding malformed"


def _brain_reasons(evidence: BrainTrustProbeEvidence) -> tuple[str, ...]:
    reasons: list[str] = []
    if not evidence.brain_present:
        reasons.append("Brain directory missing")
    elif not evidence.brain_structurally_present:
        reasons.append("Brain path is not a directory")
    elif not evidence.brain_readable:
        reasons.append("Brain directory unreadable")
    if evidence.brain_inspection_failed:
        reasons.append("Brain directory inspection failed")
    return tuple(reasons)


def _unique(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))

from dataclasses import dataclass
from typing import Literal, Protocol

from neural_engine.core.brain_trust import (
    BrainMetadata,
    BrainTrustCompatibility,
    ExternalTrustBinding,
)
from neural_engine.core.paths import NeuralPaths

TrustArtifactIssue = Literal[
    "not_regular",
    "unreadable",
    "read_error",
    "invalid_utf8",
    "malformed_json",
    "missing_format",
    "unsupported_format",
    "schema_invalid",
]
TrustArtifactModel = BrainMetadata | ExternalTrustBinding


@dataclass(frozen=True, slots=True)
class TrustArtifactEvidence:
    """Read-only evidence for one persisted trust artifact."""

    present: bool
    is_file: bool
    readable: bool
    format_status: BrainTrustCompatibility | None
    model: TrustArtifactModel | None
    issue: TrustArtifactIssue | None


@dataclass(frozen=True, slots=True)
class BrainTrustProbeEvidence:
    """Filesystem and parsed-artifact evidence used by the trust classifier."""

    brain_present: bool
    brain_structurally_present: bool
    brain_readable: bool
    brain_inspection_failed: bool
    metadata: TrustArtifactEvidence
    binding: TrustArtifactEvidence


class BrainTrustProbe(Protocol):
    """Read Brain trust artifacts without creating or changing them."""

    def inspect(self, paths: NeuralPaths) -> BrainTrustProbeEvidence: ...

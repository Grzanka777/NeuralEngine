import json
import os
from collections.abc import Callable
from pathlib import Path

from pydantic import ValidationError

from neural_engine.core.brain_trust import (
    BrainMetadata,
    BrainTrustCompatibility,
    ExternalTrustBinding,
    classify_binding_format,
    classify_metadata_format,
)
from neural_engine.core.paths import NeuralPaths
from neural_engine.ports.brain_trust_probe import (
    BrainTrustProbeEvidence,
    TrustArtifactEvidence,
    TrustArtifactModel,
)

AccessChecker = Callable[[Path, int], bool]
BytesReader = Callable[[Path], bytes]


class LocalBrainTrustProbe:
    """Inspect local trust artifacts using read-only filesystem operations."""

    def __init__(
        self,
        *,
        access_checker: AccessChecker = os.access,
        bytes_reader: BytesReader | None = None,
        binding_path: Path | None = None,
    ) -> None:
        self._access_checker = access_checker
        self._bytes_reader = bytes_reader or Path.read_bytes
        self._binding_path = binding_path

    def inspect(self, paths: NeuralPaths) -> BrainTrustProbeEvidence:
        brain_present, brain_is_directory, brain_readable, brain_failed = self._brain_evidence(
            paths.BRAIN
        )
        return BrainTrustProbeEvidence(
            brain_present=brain_present,
            brain_structurally_present=brain_is_directory,
            brain_readable=brain_readable,
            brain_inspection_failed=brain_failed,
            metadata=self._read_artifact(
                paths.BRAIN_METADATA,
                metadata=True,
            ),
            binding=self._read_artifact(
                self._binding_path or paths.TRUST_BINDING,
                metadata=False,
            ),
        )

    def _brain_evidence(self, path: Path) -> tuple[bool, bool, bool, bool]:
        try:
            present = path.exists() or path.is_symlink()
            is_directory = present and path.is_dir()
            readable = is_directory and self._access_checker(path, os.R_OK | os.X_OK)
        except OSError:
            return False, False, False, True
        return present, is_directory, readable, False

    def _read_artifact(self, path: Path, *, metadata: bool) -> TrustArtifactEvidence:
        format_status_for_missing = (
            classify_metadata_format(None) if metadata else classify_binding_format(None)
        )
        try:
            present = path.exists() or path.is_symlink()
        except OSError:
            return TrustArtifactEvidence(True, False, False, None, None, "read_error")
        if not present:
            return TrustArtifactEvidence(
                False,
                False,
                False,
                format_status_for_missing,
                None,
                None,
            )

        try:
            is_file = path.is_file()
        except OSError:
            return TrustArtifactEvidence(True, False, False, None, None, "read_error")
        if not is_file:
            return TrustArtifactEvidence(True, False, False, None, None, "not_regular")

        try:
            readable = self._access_checker(path, os.R_OK)
        except OSError:
            return TrustArtifactEvidence(True, True, False, None, None, "read_error")
        if not readable:
            return TrustArtifactEvidence(True, True, False, None, None, "unreadable")

        try:
            raw = json.loads(self._bytes_reader(path).decode("utf-8"))
        except UnicodeDecodeError:
            return TrustArtifactEvidence(True, True, True, None, None, "invalid_utf8")
        except json.JSONDecodeError:
            return TrustArtifactEvidence(True, True, True, None, None, "malformed_json")
        except OSError:
            return TrustArtifactEvidence(True, True, True, None, None, "read_error")

        if not isinstance(raw, dict):
            return TrustArtifactEvidence(True, True, True, None, None, "schema_invalid")

        format_key = "metadata_format" if metadata else "binding_format"
        format_value = raw.get(format_key)
        if not isinstance(format_value, str):
            return TrustArtifactEvidence(True, True, True, None, None, "missing_format")

        format_status = (
            classify_metadata_format(format_value)
            if metadata
            else classify_binding_format(format_value)
        )
        supported = (
            BrainTrustCompatibility.TRUST_METADATA_SUPPORTED
            if metadata
            else BrainTrustCompatibility.BINDING_SUPPORTED
        )
        if format_status is not supported:
            return TrustArtifactEvidence(
                True,
                True,
                True,
                format_status,
                None,
                "unsupported_format",
            )

        model_type: type[TrustArtifactModel] = BrainMetadata if metadata else ExternalTrustBinding
        try:
            model = model_type.model_validate(raw)
        except ValidationError:
            return TrustArtifactEvidence(
                True,
                True,
                True,
                format_status,
                None,
                "schema_invalid",
            )
        return TrustArtifactEvidence(True, True, True, format_status, model, None)

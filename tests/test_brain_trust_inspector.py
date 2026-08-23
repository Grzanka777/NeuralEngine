from pathlib import Path
from uuid import UUID

import pytest

from neural_engine.application.brain_trust_inspector import (
    BrainTrustInspector,
    BrainTrustState,
)
from neural_engine.core.brain_trust import (
    BRAIN_TRUST_BINDING_FORMAT,
    BRAIN_TRUST_METADATA_FORMAT,
    BrainMetadata,
    ExternalTrustBinding,
    PendingTransition,
    TargetAction,
    TargetDescriptor,
    TransitionOperationKind,
)
from neural_engine.core.paths import NeuralPaths, resolve_neural_paths
from neural_engine.infrastructure.local_brain_trust_probe import LocalBrainTrustProbe

BRAIN_ID = UUID("11111111-1111-4111-8111-111111111111")
FOREIGN_BRAIN_ID = UUID("33333333-3333-4333-8333-333333333333")
TRANSITION_ID = UUID("22222222-2222-4222-8222-222222222222")
BEFORE = "a" * 64
AFTER = "b" * 64


def _paths(tmp_path: Path) -> tuple[NeuralPaths, Path]:
    root = tmp_path / "portable"
    root.mkdir()
    paths = resolve_neural_paths(environ={"NEURAL_HOME": str(root)})
    paths.BRAIN.mkdir()
    return paths, root / "binding.json"


def _inspector(paths: NeuralPaths, binding_path: Path) -> BrainTrustInspector:
    return BrainTrustInspector(
        lambda: paths,
        LocalBrainTrustProbe(binding_path=binding_path),
    )


def _metadata(paths: NeuralPaths, *, brain_id: UUID = BRAIN_ID, generation: int = 1) -> None:
    paths.BRAIN_METADATA.write_text(
        BrainMetadata(
            metadata_format=BRAIN_TRUST_METADATA_FORMAT,
            brain_id=brain_id,
            generation=generation,
        ).model_dump_json(),
        encoding="utf-8",
    )


def _binding(binding_path: Path, *, brain_id: UUID = BRAIN_ID, generation: int = 1) -> None:
    binding_path.write_text(
        ExternalTrustBinding(
            binding_format=BRAIN_TRUST_BINDING_FORMAT,
            expected_brain_id=brain_id,
            accepted_generation=generation,
        ).model_dump_json(),
        encoding="utf-8",
    )


def _snapshot(root: Path) -> dict[str, bytes | None]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes() if path.is_file() else None
        for path in root.rglob("*")
    }


def test_pretrust_brain_is_unadopted(tmp_path: Path) -> None:
    paths, binding_path = _paths(tmp_path)

    result = _inspector(paths, binding_path).inspect()

    assert result.state is BrainTrustState.UNADOPTED
    assert not result.brain_metadata_present
    assert not result.binding_present
    assert "trust metadata and binding absent" in result.reasons


def test_valid_matching_binding_and_equal_generation_is_trusted(tmp_path: Path) -> None:
    paths, binding_path = _paths(tmp_path)
    _metadata(paths)
    _binding(binding_path)

    result = _inspector(paths, binding_path).inspect()

    assert result.state is BrainTrustState.TRUSTED_CURRENT
    assert result.metadata_valid and result.binding_valid
    assert result.brain_id == BRAIN_ID
    assert result.expected_brain_id == BRAIN_ID
    assert result.generation == result.accepted_generation == 1


def test_valid_metadata_without_binding_is_not_trusted(tmp_path: Path) -> None:
    paths, binding_path = _paths(tmp_path)
    _metadata(paths)

    result = _inspector(paths, binding_path).inspect()

    assert result.state is BrainTrustState.BINDING_MISSING
    assert "binding missing" in result.reasons


def test_foreign_identity_is_classified_before_generation(tmp_path: Path) -> None:
    paths, binding_path = _paths(tmp_path)
    _metadata(paths, brain_id=BRAIN_ID)
    _binding(binding_path, brain_id=FOREIGN_BRAIN_ID, generation=5)

    result = _inspector(paths, binding_path).inspect()

    assert result.state is BrainTrustState.FOREIGN
    assert "brain identity mismatch" in result.reasons


@pytest.mark.parametrize(
    ("brain_generation", "accepted_generation", "expected_state", "expected_reason"),
    [
        (1, 2, BrainTrustState.STALE_OR_ROLLBACK, "brain generation behind accepted generation"),
        (2, 1, BrainTrustState.UNTRUSTED_AHEAD, "brain generation ahead of accepted generation"),
    ],
)
def test_generation_relationship_is_classified(
    tmp_path: Path,
    brain_generation: int,
    accepted_generation: int,
    expected_state: BrainTrustState,
    expected_reason: str,
) -> None:
    paths, binding_path = _paths(tmp_path)
    _metadata(paths, generation=brain_generation)
    _binding(binding_path, generation=accepted_generation)

    result = _inspector(paths, binding_path).inspect()

    assert result.state is expected_state
    assert expected_reason in result.reasons


def test_pending_transition_fails_closed_as_transition_pending(tmp_path: Path) -> None:
    paths, binding_path = _paths(tmp_path)
    marker = PendingTransition(
        transition_id=TRANSITION_ID,
        brain_id=BRAIN_ID,
        from_generation=1,
        to_generation=2,
        operation_kind=TransitionOperationKind.ORDINARY_MUTATION,
        targets=(
            TargetDescriptor(
                relative_path="observations/record.json",
                action=TargetAction.REPLACE,
                before_sha256=BEFORE,
                after_sha256=AFTER,
            ),
        ),
    )
    paths.BRAIN_METADATA.write_text(
        BrainMetadata(
            metadata_format=BRAIN_TRUST_METADATA_FORMAT,
            brain_id=BRAIN_ID,
            generation=1,
            pending_transition=marker,
        ).model_dump_json(),
        encoding="utf-8",
    )
    _binding(binding_path)

    result = _inspector(paths, binding_path).inspect()

    assert result.state is BrainTrustState.TRANSITION_PENDING
    assert result.pending_transition_present
    assert "pending transition present" in result.reasons


def test_malformed_metadata_is_invalid(tmp_path: Path) -> None:
    paths, binding_path = _paths(tmp_path)
    paths.BRAIN_METADATA.write_text("{", encoding="utf-8")
    _binding(binding_path)

    result = _inspector(paths, binding_path).inspect()

    assert result.state is BrainTrustState.METADATA_INVALID
    assert result.metadata_issue == "malformed_json"
    assert "metadata malformed" in result.reasons


def test_malformed_binding_requires_recovery(tmp_path: Path) -> None:
    paths, binding_path = _paths(tmp_path)
    _metadata(paths)
    binding_path.write_text("{", encoding="utf-8")

    result = _inspector(paths, binding_path).inspect()

    assert result.state is BrainTrustState.RECOVERY_REQUIRED
    assert result.binding_issue == "malformed_json"
    assert "binding malformed" in result.reasons


def test_unsupported_formats_fail_closed_and_remain_distinguishable(tmp_path: Path) -> None:
    paths, binding_path = _paths(tmp_path)
    paths.BRAIN_METADATA.write_text(
        f'{{"metadata_format":"2.0.0","brain_id":"{BRAIN_ID}","generation":1}}',
        encoding="utf-8",
    )
    binding_path.write_text(
        f'{{"binding_format":"2.0.0","expected_brain_id":"{BRAIN_ID}","accepted_generation":1}}',
        encoding="utf-8",
    )

    result = _inspector(paths, binding_path).inspect()

    assert result.state is BrainTrustState.METADATA_INVALID
    assert result.metadata_issue == "unsupported_format"
    assert result.binding_issue == "unsupported_format"
    assert result.metadata_format_status is not None
    assert result.binding_format_status is not None
    assert "unsupported metadata format" in result.reasons


def test_metadata_present_and_binding_present_are_required_for_trusted_current(
    tmp_path: Path,
) -> None:
    paths, binding_path = _paths(tmp_path)
    _metadata(paths)
    _binding(binding_path)
    paths.BRAIN_METADATA.unlink()

    result = _inspector(paths, binding_path).inspect()

    assert result.state is BrainTrustState.RECOVERY_REQUIRED
    assert "metadata missing while binding is present" in result.reasons


def test_pending_transition_identity_mismatch_is_invalid_metadata(tmp_path: Path) -> None:
    paths, binding_path = _paths(tmp_path)
    marker = PendingTransition(
        transition_id=TRANSITION_ID,
        brain_id=FOREIGN_BRAIN_ID,
        from_generation=1,
        to_generation=2,
        operation_kind=TransitionOperationKind.ORDINARY_MUTATION,
        targets=(
            TargetDescriptor(
                relative_path="observations/record.json",
                action=TargetAction.REPLACE,
                before_sha256=BEFORE,
                after_sha256=AFTER,
            ),
        ),
    )
    paths.BRAIN_METADATA.write_text(
        BrainMetadata(
            metadata_format=BRAIN_TRUST_METADATA_FORMAT,
            brain_id=BRAIN_ID,
            generation=1,
            pending_transition=marker,
        ).model_dump_json(),
        encoding="utf-8",
    )
    _binding(binding_path)

    result = _inspector(paths, binding_path).inspect()

    assert result.state is BrainTrustState.METADATA_INVALID
    assert "pending transition brain identity mismatch" in result.reasons


def test_inspection_does_not_mutate_brain_or_binding_files(tmp_path: Path) -> None:
    paths, binding_path = _paths(tmp_path)
    _metadata(paths)
    _binding(binding_path)
    before = _snapshot(tmp_path / "portable")

    _inspector(paths, binding_path).inspect()

    assert _snapshot(tmp_path / "portable") == before

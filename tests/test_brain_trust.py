from uuid import UUID

import pytest
from pydantic import ValidationError

from neural_engine.core.brain_trust import (
    BRAIN_TRUST_BINDING_FORMAT,
    BRAIN_TRUST_METADATA_FORMAT,
    BrainMetadata,
    BrainTrustCompatibility,
    ExternalTrustBinding,
    PendingTransition,
    TargetAction,
    TargetDescriptor,
    TransitionOperationKind,
    classify_binding_format,
    classify_metadata_format,
)

BRAIN_ID = UUID("11111111-1111-4111-8111-111111111111")
TRANSITION_ID = UUID("22222222-2222-4222-8222-222222222222")
BEFORE = "a" * 64
AFTER = "b" * 64


def _target(action: TargetAction = TargetAction.REPLACE) -> TargetDescriptor:
    if action is TargetAction.CREATE:
        return TargetDescriptor(
            relative_path="observations/record.json",
            action=action,
            after_sha256=AFTER,
        )
    if action is TargetAction.REMOVE:
        return TargetDescriptor(
            relative_path="observations/record.json",
            action=action,
            before_sha256=BEFORE,
        )
    return TargetDescriptor(
        relative_path="observations/record.json",
        action=action,
        before_sha256=BEFORE,
        after_sha256=AFTER,
    )


def _ordinary_marker(**updates: object) -> PendingTransition:
    values: dict[str, object] = {
        "transition_id": TRANSITION_ID,
        "brain_id": BRAIN_ID,
        "from_generation": 1,
        "to_generation": 2,
        "operation_kind": TransitionOperationKind.ORDINARY_MUTATION,
        "targets": (_target(),),
    }
    values.update(updates)
    return PendingTransition.model_validate(values)


def test_valid_metadata_round_trips_uuid_canonically() -> None:
    metadata = BrainMetadata(
        metadata_format=BRAIN_TRUST_METADATA_FORMAT,
        brain_id=UUID("AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA"),
        generation=1,
    )

    dumped = metadata.model_dump(mode="json")

    assert dumped["brain_id"] == "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    assert metadata.pending_transition is None


@pytest.mark.parametrize("value", ["0.0.0", "", "1.0"])
def test_unsupported_metadata_format_is_rejected(value: str) -> None:
    with pytest.raises(ValidationError):
        BrainMetadata(metadata_format=value, brain_id=BRAIN_ID, generation=1)


@pytest.mark.parametrize("value", [0, -1, True])
def test_invalid_metadata_generation_is_rejected(value: object) -> None:
    with pytest.raises(ValidationError):
        BrainMetadata.model_validate(
            {
                "metadata_format": BRAIN_TRUST_METADATA_FORMAT,
                "brain_id": BRAIN_ID,
                "generation": value,
            }
        )


def test_metadata_accepts_valid_marker_and_rejects_persisted_phase() -> None:
    metadata = BrainMetadata(
        metadata_format=BRAIN_TRUST_METADATA_FORMAT,
        brain_id=BRAIN_ID,
        generation=1,
        pending_transition=_ordinary_marker(),
    )

    assert metadata.pending_transition is not None
    with pytest.raises(ValidationError):
        BrainMetadata.model_validate(
            {
                **metadata.model_dump(),
                "phase": "prepared",
            }
        )


def test_malformed_marker_is_rejected() -> None:
    with pytest.raises(ValidationError):
        BrainMetadata.model_validate(
            {
                "metadata_format": BRAIN_TRUST_METADATA_FORMAT,
                "brain_id": BRAIN_ID,
                "generation": 1,
                "pending_transition": {
                    "transition_id": str(TRANSITION_ID),
                    "brain_id": str(BRAIN_ID),
                    "from_generation": 1,
                    "to_generation": 3,
                    "operation_kind": "ordinary_mutation",
                    "targets": [_target().model_dump()],
                },
            }
        )


def test_valid_binding_and_rejected_fields() -> None:
    binding = ExternalTrustBinding(
        binding_format=BRAIN_TRUST_BINDING_FORMAT,
        expected_brain_id=BRAIN_ID,
        accepted_generation=2,
    )

    assert binding.model_dump(mode="json")["expected_brain_id"] == str(BRAIN_ID)
    with pytest.raises(ValidationError):
        ExternalTrustBinding.model_validate(
            {
                "binding_format": BRAIN_TRUST_BINDING_FORMAT,
                "expected_brain_id": "not-a-uuid",
                "accepted_generation": 1,
            }
        )
    with pytest.raises(ValidationError):
        ExternalTrustBinding.model_validate(
            {
                **binding.model_dump(),
                "path": "/tmp/brain",
            }
        )


@pytest.mark.parametrize("value", ["0.0.0", "2.0.0"])
def test_unsupported_binding_format_is_rejected(value: str) -> None:
    with pytest.raises(ValidationError):
        ExternalTrustBinding(
            binding_format=value,
            expected_brain_id=BRAIN_ID,
            accepted_generation=1,
        )


@pytest.mark.parametrize("value", [0, -1, True])
def test_invalid_binding_generation_is_rejected(value: object) -> None:
    with pytest.raises(ValidationError):
        ExternalTrustBinding.model_validate(
            {
                "binding_format": BRAIN_TRUST_BINDING_FORMAT,
                "expected_brain_id": BRAIN_ID,
                "accepted_generation": value,
            }
        )


def test_valid_marker_operations() -> None:
    assert _ordinary_marker().to_generation == 2
    adoption = PendingTransition(
        transition_id=TRANSITION_ID,
        brain_id=BRAIN_ID,
        from_generation=None,
        to_generation=1,
        operation_kind=TransitionOperationKind.ADOPTION,
    )
    clone = PendingTransition(
        transition_id=TRANSITION_ID,
        brain_id=BRAIN_ID,
        from_generation=5,
        to_generation=1,
        operation_kind=TransitionOperationKind.CLONE,
        targets=(_target(TargetAction.CREATE),),
    )
    restore = PendingTransition(
        transition_id=TRANSITION_ID,
        brain_id=BRAIN_ID,
        from_generation=5,
        to_generation=6,
        operation_kind=TransitionOperationKind.RESTORE,
        targets=(_target(),),
    )
    rebind = PendingTransition(
        transition_id=TRANSITION_ID,
        brain_id=BRAIN_ID,
        from_generation=5,
        to_generation=5,
        operation_kind=TransitionOperationKind.REBIND,
    )

    assert adoption.to_generation == 1
    assert clone.to_generation == 1
    assert restore.to_generation == 6
    assert rebind.to_generation == 5


@pytest.mark.parametrize(
    "values",
    [
        {"from_generation": 1, "to_generation": 1},
        {"from_generation": None, "to_generation": 2},
    ],
)
def test_ordinary_marker_requires_exact_generation_increment(values: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        _ordinary_marker(**values)


def test_adoption_clone_rebind_and_unknown_operation_rules() -> None:
    with pytest.raises(ValidationError):
        PendingTransition(
            transition_id=TRANSITION_ID,
            brain_id=BRAIN_ID,
            from_generation=1,
            to_generation=2,
            operation_kind=TransitionOperationKind.ADOPTION,
        )
    with pytest.raises(ValidationError):
        PendingTransition(
            transition_id=TRANSITION_ID,
            brain_id=BRAIN_ID,
            from_generation=1,
            to_generation=2,
            operation_kind=TransitionOperationKind.CLONE,
            targets=(_target(),),
        )
    with pytest.raises(ValidationError):
        PendingTransition(
            transition_id=TRANSITION_ID,
            brain_id=BRAIN_ID,
            from_generation=1,
            to_generation=2,
            operation_kind=TransitionOperationKind.REBIND,
        )
    with pytest.raises(ValidationError):
        PendingTransition.model_validate(
            {
                "transition_id": TRANSITION_ID,
                "brain_id": BRAIN_ID,
                "from_generation": 1,
                "to_generation": 2,
                "operation_kind": "unknown",
                "targets": (_target(),),
            }
        )


@pytest.mark.parametrize(
    "relative_path",
    ["", ".", "/tmp/record.json", "../record.json", "a/../record.json"],
)
def test_target_rejects_non_brain_relative_paths(relative_path: str) -> None:
    with pytest.raises(ValidationError):
        TargetDescriptor.model_validate(
            {"relative_path": relative_path, "action": "create", "after_sha256": AFTER}
        )


def test_target_rejects_windows_separator_and_accepts_nested_posix_path() -> None:
    with pytest.raises(ValidationError):
        TargetDescriptor.model_validate(
            {
                "relative_path": "observations\\record.json",
                "action": "create",
                "after_sha256": AFTER,
            }
        )

    target = TargetDescriptor.model_validate(
        {
            "relative_path": "observations/record.json",
            "action": "create",
            "after_sha256": AFTER,
        }
    )
    assert target.relative_path == "observations/record.json"


@pytest.mark.parametrize("value", ["x", "A" * 64, "a" * 63])
def test_target_rejects_invalid_sha256(value: str) -> None:
    with pytest.raises(ValidationError):
        TargetDescriptor.model_validate(
            {
                "relative_path": "observations/record.json",
                "action": "create",
                "after_sha256": value,
            }
        )


def test_target_action_hash_combinations_are_validated() -> None:
    with pytest.raises(ValidationError):
        TargetDescriptor.model_validate(
            {
                "relative_path": "observations/record.json",
                "action": "create",
                "before_sha256": BEFORE,
                "after_sha256": AFTER,
            }
        )
    with pytest.raises(ValidationError):
        TargetDescriptor.model_validate(
            {"relative_path": "observations/record.json", "action": "remove"}
        )
    with pytest.raises(ValidationError):
        TargetDescriptor.model_validate(
            {
                "relative_path": "observations/record.json",
                "action": "replace",
                "before_sha256": BEFORE,
            }
        )


def test_marker_target_paths_must_be_unique() -> None:
    with pytest.raises(ValidationError):
        _ordinary_marker(targets=(_target(), _target()))


def test_format_compatibility_classification_is_read_only() -> None:
    assert classify_metadata_format(None) is BrainTrustCompatibility.OLD_FORMAT_UNADOPTED
    assert (
        classify_metadata_format(BRAIN_TRUST_METADATA_FORMAT)
        is BrainTrustCompatibility.TRUST_METADATA_SUPPORTED
    )
    assert classify_metadata_format("future") is BrainTrustCompatibility.TRUST_METADATA_UNSUPPORTED
    assert (
        classify_binding_format(BRAIN_TRUST_BINDING_FORMAT)
        is BrainTrustCompatibility.BINDING_SUPPORTED
    )
    assert classify_binding_format("future") is BrainTrustCompatibility.BINDING_UNSUPPORTED


def test_models_do_not_add_persisted_phase() -> None:
    assert "phase" not in BrainMetadata.model_fields
    assert "phase" not in PendingTransition.model_fields

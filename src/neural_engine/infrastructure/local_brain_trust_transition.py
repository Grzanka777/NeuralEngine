from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from uuid import UUID, uuid4

from neural_engine.application.brain_trust_inspector import (
    BrainTrustInspection,
    BrainTrustInspector,
    BrainTrustState,
)
from neural_engine.application.brain_trust_transition import (
    BrainTrustMutationNotPermittedError,
    BrainTrustTransitionExecutionError,
)
from neural_engine.core.brain_trust import (
    BrainMetadata,
    ExternalTrustBinding,
    PendingTransition,
    TargetAction,
    TargetDescriptor,
    TransitionOperationKind,
)
from neural_engine.core.paths import NeuralPaths
from neural_engine.infrastructure.durability import atomic_replace_bytes
from neural_engine.ports.brain_trust_transition import (
    ControlledMutationTarget,
    WriteBytes,
)


@dataclass(frozen=True, slots=True)
class TransitionPersistence:
    """Durability dependency used by the coordinator and failure-injection tests."""

    write_bytes: WriteBytes = atomic_replace_bytes


class LocalBrainTrustTransitionCoordinator:
    """Coordinate one ordinary local Brain mutation under Brain Trust."""

    def __init__(
        self,
        paths: NeuralPaths,
        inspector: BrainTrustInspector,
        *,
        binding_path: Path | None = None,
        persistence: TransitionPersistence | None = None,
        transition_id_factory: Callable[[], UUID] = uuid4,
        post_write_verifier: Callable[[], None] | None = None,
    ) -> None:
        self._paths = paths
        self._inspector = inspector
        self._binding_path = binding_path or paths.TRUST_BINDING
        self._persistence = persistence or TransitionPersistence()
        self._transition_id_factory = transition_id_factory
        self._post_write_verifier = post_write_verifier

    def execute(self, target: ControlledMutationTarget) -> None:
        inspection = self._inspector.inspect_paths(self._paths)
        self._require_trusted_current(inspection)

        metadata = self._read_metadata()
        binding = self._read_binding()
        if metadata.brain_id != binding.expected_brain_id:
            raise BrainTrustMutationNotPermittedError(
                BrainTrustState.FOREIGN,
                ("identity changed after trust inspection",),
            )
        if metadata.generation != binding.accepted_generation:
            raise BrainTrustMutationNotPermittedError(
                BrainTrustState.RECOVERY_REQUIRED,
                ("generation changed after trust inspection",),
            )

        target_path = self._target_path(target.relative_path)
        descriptor = self._describe_target(target, target_path)
        transition_id = self._transition_id_factory()
        transition = PendingTransition(
            transition_id=transition_id,
            brain_id=metadata.brain_id,
            from_generation=metadata.generation,
            to_generation=metadata.generation + 1,
            operation_kind=TransitionOperationKind.ORDINARY_MUTATION,
            targets=(descriptor,),
        )

        try:
            self._persist_metadata(metadata.model_copy(update={"pending_transition": transition}))

            target.publish()

            self._verify_target(target_path, descriptor)
            next_metadata = metadata.model_copy(
                update={
                    "generation": transition.to_generation,
                    "pending_transition": transition,
                }
            )
            self._persist_metadata(next_metadata)
            self._verify_transition_state(target_path, descriptor, transition)
            if self._post_write_verifier is not None:
                self._post_write_verifier()

            next_binding = binding.model_copy(
                update={"accepted_generation": transition.to_generation}
            )
            self._persist_binding(next_binding)
            self._verify_binding(next_binding)

            self._persist_metadata(next_metadata.model_copy(update={"pending_transition": None}))
            self._verify_final_state(transition)
        except Exception as error:
            if isinstance(error, BrainTrustTransitionExecutionError):
                raise
            raise BrainTrustTransitionExecutionError(transition_id, error) from error

    @staticmethod
    def _require_trusted_current(inspection: BrainTrustInspection) -> None:
        if inspection.state is not BrainTrustState.TRUSTED_CURRENT:
            raise BrainTrustMutationNotPermittedError(inspection.state, inspection.reasons)

    def _read_metadata(self) -> BrainMetadata:
        return BrainMetadata.model_validate_json(self._paths.BRAIN_METADATA.read_bytes())

    def _read_binding(self) -> ExternalTrustBinding:
        return ExternalTrustBinding.model_validate_json(self._binding_path.read_bytes())

    def _persist_metadata(self, metadata: BrainMetadata) -> None:
        self._persistence.write_bytes(
            self._paths.BRAIN_METADATA,
            _model_bytes(metadata),
        )

    def _persist_binding(self, binding: ExternalTrustBinding) -> None:
        self._persistence.write_bytes(self._binding_path, _model_bytes(binding))

    def _verify_binding(self, expected: ExternalTrustBinding) -> None:
        actual = self._read_binding()
        if actual != expected:
            raise ValueError("Persisted external binding does not match the transition target.")

    def _verify_final_state(self, transition: PendingTransition) -> None:
        metadata = self._read_metadata()
        if (
            metadata.brain_id != transition.brain_id
            or metadata.generation != transition.to_generation
            or metadata.pending_transition is not None
        ):
            raise ValueError("Final Brain metadata does not describe a completed transition.")
        inspection = self._inspector.inspect_paths(self._paths)
        self._require_trusted_current(inspection)

    def _verify_transition_state(
        self,
        target_path: Path,
        descriptor: TargetDescriptor,
        transition: PendingTransition,
    ) -> None:
        self._verify_target(target_path, descriptor)
        metadata = self._read_metadata()
        if (
            metadata.brain_id != transition.brain_id
            or metadata.generation != transition.to_generation
            or metadata.pending_transition != transition
        ):
            raise ValueError("Persisted Brain metadata does not match the active transition.")

    def _describe_target(
        self,
        target: ControlledMutationTarget,
        target_path: Path,
    ) -> TargetDescriptor:
        before_bytes: bytes | None
        if target_path.exists():
            if not target_path.is_file():
                raise ValueError(f"Controlled target is not a regular file: {target.relative_path}")
            before_bytes = target_path.read_bytes()
        else:
            before_bytes = None

        if target.action is TargetAction.CREATE and before_bytes is not None:
            raise ValueError(f"Create target already exists: {target.relative_path}")
        if target.action is TargetAction.REPLACE and before_bytes is None:
            raise ValueError(f"Replace target is absent: {target.relative_path}")
        if target.action is TargetAction.REMOVE and before_bytes is None:
            raise ValueError(f"Remove target is absent: {target.relative_path}")

        if target.action is TargetAction.CREATE and target.after_bytes is None:
            raise ValueError("Create target requires after bytes.")
        if target.action is TargetAction.REPLACE and target.after_bytes is None:
            raise ValueError("Replace target requires after bytes.")

        return TargetDescriptor(
            relative_path=target.relative_path,
            action=target.action,
            before_sha256=_sha256(before_bytes),
            after_sha256=_sha256(target.after_bytes),
        )

    def _verify_target(self, target_path: Path, descriptor: TargetDescriptor) -> None:
        exists = target_path.exists()
        if descriptor.action is TargetAction.REMOVE:
            if exists:
                raise ValueError(f"Removed target still exists: {descriptor.relative_path}")
            return

        if not exists or not target_path.is_file():
            raise ValueError(f"Target is absent or not a regular file: {descriptor.relative_path}")
        actual = target_path.read_bytes()
        if _sha256(actual) != descriptor.after_sha256:
            raise ValueError(f"Target bytes do not match after hash: {descriptor.relative_path}")

    def _target_path(self, relative_path: str) -> Path:
        descriptor = TargetDescriptor(
            relative_path=relative_path,
            action=TargetAction.CREATE,
            after_sha256="0" * 64,
        )
        relative = PurePosixPath(descriptor.relative_path)
        path = self._paths.BRAIN.joinpath(*relative.parts)
        brain_root = self._paths.BRAIN.resolve()
        resolved = path.resolve(strict=False)
        if resolved != brain_root and brain_root not in resolved.parents:
            raise ValueError("Controlled target must remain below the Brain directory.")
        return path


def _model_bytes(model: BrainMetadata | ExternalTrustBinding) -> bytes:
    return model.model_dump_json(indent=2).encode("utf-8")


def _sha256(value: bytes | None) -> str | None:
    if value is None:
        return None
    return hashlib.sha256(value).hexdigest()

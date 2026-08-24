from __future__ import annotations

import hashlib
import stat
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol
from uuid import UUID, uuid4

from neural_engine.application.brain_trust_inspector import (
    BrainTrustInspection,
    BrainTrustInspector,
    BrainTrustState,
)
from neural_engine.application.brain_trust_transition import (
    BrainTrustMutationError,
    BrainTrustMutationNotPermittedError,
    BrainTrustNoRecoverableTransitionError,
    BrainTrustRecoveryError,
    BrainTrustRecoveryExecutionError,
    BrainTrustStalePreimageError,
    BrainTrustTransitionExecutionError,
    BrainTrustUnsafeRecoveryError,
    BrainTrustUnsupportedRecoveryError,
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
from neural_engine.domain import EvolutionProposal
from neural_engine.infrastructure.durability import atomic_replace_bytes
from neural_engine.infrastructure.json_decision_acceptance_repository import (
    JsonDecisionAcceptanceRepository,
)
from neural_engine.infrastructure.json_decision_action_repository import (
    JsonDecisionActionRepository,
)
from neural_engine.infrastructure.json_decision_outcome_repository import (
    JsonDecisionOutcomeRepository,
)
from neural_engine.infrastructure.json_decision_repository import JsonDecisionRepository
from neural_engine.infrastructure.json_decision_review_repository import (
    JsonDecisionReviewRepository,
)
from neural_engine.infrastructure.json_evolution_proposal_repository import (
    JsonEvolutionProposalRepository,
)
from neural_engine.infrastructure.json_experience_repository import JsonExperienceRepository
from neural_engine.infrastructure.json_knowledge_repository import JsonKnowledgeRepository
from neural_engine.infrastructure.json_observation_repository import JsonObservationRepository
from neural_engine.infrastructure.json_playbook_evaluation_repository import (
    JsonPlaybookEvaluationRepository,
)
from neural_engine.infrastructure.json_playbook_repository import JsonPlaybookRepository
from neural_engine.infrastructure.json_playbook_revision_activation_repository import (
    JsonPlaybookRevisionActivationRepository,
)
from neural_engine.infrastructure.json_playbook_revision_application_repository import (
    JsonPlaybookRevisionApplicationRepository,
)
from neural_engine.infrastructure.json_playbook_revision_repository import (
    JsonPlaybookRevisionRepository,
)
from neural_engine.infrastructure.json_playbook_run_repository import JsonPlaybookRunRepository
from neural_engine.ports.brain_trust_transition import (
    ControlledMutationTarget,
    WriteBytes,
)


@dataclass(frozen=True, slots=True)
class TransitionPersistence:
    """Durability dependency used by the coordinator and failure-injection tests."""

    write_bytes: WriteBytes = atomic_replace_bytes


class _UnsafeTargetPathError(ValueError):
    """A controlled target traverses a symbolic-link component."""


class _CurrentStoreReader(Protocol):
    """Read one validated record from a supported recovery store."""

    def get_by_id(self, record_id: UUID) -> object | None: ...


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

            if target.action is TargetAction.REPLACE:
                self._verify_before(target_path, descriptor)
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
            self._verify_final_state(target_path, descriptor, transition)
        except Exception as error:
            if isinstance(error, BrainTrustTransitionExecutionError):
                raise
            if isinstance(error, BrainTrustMutationError):
                raise
            raise BrainTrustTransitionExecutionError(transition_id, error) from error

    def recover_pending_knowledge_create(self) -> UUID:
        """Complete one valid bounded CREATE or proposal REPLACE suffix.

        The historical method name is retained for CLI compatibility. The
        CREATE recovery slice covers every canonical JSON store. The separate
        REPLACE branch is limited to one ordinary evolution-proposal target.
        The marker contains no record payload. Therefore a missing CREATE
        target and an R1 proposal target are deliberately rejected; recovery
        only verifies and completes forward S2-S4 suffixes.
        """

        try:
            metadata = self._read_metadata()
        except Exception as error:
            raise BrainTrustUnsafeRecoveryError("Brain metadata cannot be parsed") from error

        transition = metadata.pending_transition
        if transition is None:
            raise BrainTrustNoRecoverableTransitionError

        try:
            binding = self._read_binding()
        except Exception as error:
            raise BrainTrustUnsafeRecoveryError(
                "external trust binding cannot be parsed"
            ) from error

        target_path, descriptor = self._validate_recovery_evidence(
            metadata,
            binding,
            transition,
        )

        try:
            self._recover_suffix(
                metadata,
                binding,
                transition,
                target_path,
                descriptor,
            )
        except BrainTrustRecoveryError:
            raise
        except Exception as error:
            raise BrainTrustRecoveryExecutionError(transition.transition_id, error) from error

        return transition.transition_id

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

    def _verify_final_state(
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
            or metadata.pending_transition is not None
        ):
            raise ValueError("Final Brain metadata does not describe a completed transition.")
        inspection = self._inspector.inspect_paths(self._paths)
        self._require_trusted_current(inspection)

    def _validate_recovery_evidence(
        self,
        metadata: BrainMetadata,
        binding: ExternalTrustBinding,
        transition: PendingTransition,
    ) -> tuple[Path, TargetDescriptor]:
        if transition.operation_kind is not TransitionOperationKind.ORDINARY_MUTATION:
            raise BrainTrustUnsupportedRecoveryError(
                f"operation kind {transition.operation_kind.value} is outside this slice"
            )
        if len(transition.targets) != 1:
            raise BrainTrustUnsupportedRecoveryError("exactly one target is required")

        descriptor = transition.targets[0]
        if descriptor.action is TargetAction.REMOVE:
            raise BrainTrustUnsupportedRecoveryError(
                f"target action {descriptor.action.value} is outside this slice"
            )

        if transition.brain_id != metadata.brain_id:
            raise BrainTrustUnsafeRecoveryError("pending transition identity differs from metadata")
        if binding.expected_brain_id != metadata.brain_id:
            raise BrainTrustUnsafeRecoveryError("binding identity differs from metadata")
        if metadata.generation not in {
            transition.from_generation,
            transition.to_generation,
        }:
            raise BrainTrustUnsafeRecoveryError(
                "metadata generation is outside the pending transition suffix"
            )
        if binding.accepted_generation not in {
            transition.from_generation,
            transition.to_generation,
        }:
            raise BrainTrustUnsafeRecoveryError(
                "binding generation is outside the pending transition suffix"
            )
        if binding.accepted_generation > metadata.generation:
            raise BrainTrustUnsafeRecoveryError("binding is ahead of metadata")

        relative = PurePosixPath(descriptor.relative_path)
        if descriptor.action is TargetAction.CREATE:
            store = self._supported_create_store(relative)
        else:
            store = self._supported_replace_store(relative)
        if store is None:
            raise BrainTrustUnsupportedRecoveryError(
                "target path is not a supported single-record recovery store"
            )
        store_root, repository, store_name = store
        if relative.parent != PurePosixPath(store_root.relative_to(self._paths.BRAIN).as_posix()):
            raise BrainTrustUnsupportedRecoveryError(
                "target path is not the current supported store shape"
            )
        try:
            record_id = UUID(relative.stem)
        except ValueError as error:
            raise BrainTrustUnsupportedRecoveryError(
                f"{store_name} target filename is not a UUID"
            ) from error
        if relative.name != f"{record_id}.json":
            raise BrainTrustUnsupportedRecoveryError(
                f"{store_name} target filename is not normalized"
            )

        try:
            target_path = self._target_path(descriptor.relative_path)
        except _UnsafeTargetPathError as error:
            raise BrainTrustUnsafeRecoveryError(
                f"{store_name} target path traverses a symbolic link"
            ) from error
        except Exception as error:
            raise BrainTrustUnsupportedRecoveryError(
                "target path cannot be safely resolved below Brain"
            ) from error
        expected_path = store_root / f"{record_id}.json"
        if target_path != expected_path:
            raise BrainTrustUnsupportedRecoveryError(
                "target path does not match the current supported store"
            )

        try:
            target_stat = target_path.lstat()
        except FileNotFoundError as error:
            if descriptor.action is TargetAction.REPLACE:
                raise BrainTrustUnsafeRecoveryError(
                    "MISSING: replacement target bytes are absent"
                ) from error
            raise BrainTrustUnsafeRecoveryError(
                "S1_REJECTED_INSUFFICIENT_EVIDENCE: target bytes are absent and the marker "
                "does not contain a record payload"
            ) from error
        except OSError as error:
            raise BrainTrustUnsafeRecoveryError(
                f"{store_name} target cannot be inspected"
            ) from error
        if not stat.S_ISREG(target_stat.st_mode):
            raise BrainTrustUnsafeRecoveryError(f"{store_name} target is not a regular file")
        try:
            actual = target_path.read_bytes()
        except OSError as error:
            raise BrainTrustUnsafeRecoveryError(f"{store_name} target cannot be read") from error
        actual_sha256 = _sha256(actual)
        if descriptor.action is TargetAction.REPLACE:
            self._validate_replacement_payload(actual, record_id, store_name)
        if descriptor.action is TargetAction.REPLACE and actual_sha256 == descriptor.before_sha256:
            if (
                metadata.generation == transition.from_generation
                and binding.accepted_generation == transition.from_generation
            ):
                raise BrainTrustUnsafeRecoveryError(
                    "R1_REJECTED_INSUFFICIENT_EVIDENCE: exact replacement bytes cannot be "
                    "reconstructed from the pending marker"
                )
            raise BrainTrustUnsafeRecoveryError(
                "BEFORE: replacement target is before publication outside R1"
            )
        if actual_sha256 != descriptor.after_sha256:
            detail = (
                "MISMATCH: target bytes do not match before or after hash"
                if descriptor.action is TargetAction.REPLACE
                else f"{store_name} target bytes do not match after hash"
            )
            raise BrainTrustUnsafeRecoveryError(detail)
        try:
            stored = repository.get_by_id(record_id)
        except Exception as error:
            raise BrainTrustUnsafeRecoveryError(
                f"{store_name} target is not valid current-store data"
            ) from error
        if stored is None:
            raise BrainTrustUnsafeRecoveryError(
                f"{store_name} target is not present in the current store"
            )
        if getattr(stored, "id", None) != record_id:
            raise BrainTrustUnsafeRecoveryError(
                f"{store_name} target filename and payload identity do not match"
            )

        return target_path, descriptor

    def _supported_replace_store(
        self,
        relative: PurePosixPath,
    ) -> tuple[Path, _CurrentStoreReader, str] | None:
        root = self._paths.EVOLUTION_PROPOSALS
        root_relative = PurePosixPath(root.relative_to(self._paths.BRAIN).as_posix())
        if relative.parent != root_relative or relative.suffix != ".json":
            return None
        return root, JsonEvolutionProposalRepository(paths=self._paths), "EvolutionProposal"

    @staticmethod
    def _validate_replacement_payload(actual: bytes, record_id: UUID, store_name: str) -> None:
        try:
            proposal = EvolutionProposal.model_validate_json(actual)
        except Exception as error:
            raise BrainTrustUnsafeRecoveryError(
                f"INVALID: {store_name} replacement payload is malformed"
            ) from error
        if proposal.id != record_id:
            raise BrainTrustUnsafeRecoveryError(
                f"IDENTITY_MISMATCH: {store_name} filename and payload IDs differ"
            )

    def _supported_create_store(
        self,
        relative: PurePosixPath,
    ) -> tuple[Path, _CurrentStoreReader, str] | None:
        stores: tuple[tuple[Path, _CurrentStoreReader, str], ...] = (
            (
                self._paths.OBSERVATIONS,
                JsonObservationRepository(paths=self._paths),
                "Observation",
            ),
            (
                self._paths.EXPERIENCES,
                JsonExperienceRepository(paths=self._paths),
                "Experience",
            ),
            (self._paths.KNOWLEDGE, JsonKnowledgeRepository(paths=self._paths), "Knowledge"),
            (
                self._paths.PLAYBOOKS,
                JsonPlaybookRepository(paths=self._paths),
                "Playbook",
            ),
            (
                self._paths.PLAYBOOK_EVALUATIONS,
                JsonPlaybookEvaluationRepository(paths=self._paths),
                "PlaybookEvaluation",
            ),
            (
                self._paths.EVOLUTION_PROPOSALS,
                JsonEvolutionProposalRepository(paths=self._paths),
                "EvolutionProposal",
            ),
            (
                self._paths.PLAYBOOK_REVISION_ACTIVATIONS,
                JsonPlaybookRevisionActivationRepository(paths=self._paths),
                "PlaybookRevisionActivation",
            ),
            (
                self._paths.PLAYBOOK_REVISION_APPLICATIONS,
                JsonPlaybookRevisionApplicationRepository(paths=self._paths),
                "PlaybookRevisionApplication",
            ),
            (
                self._paths.PLAYBOOK_RUNS,
                JsonPlaybookRunRepository(paths=self._paths),
                "PlaybookRun",
            ),
            (
                self._paths.PLAYBOOK_REVISIONS,
                JsonPlaybookRevisionRepository(paths=self._paths),
                "PlaybookRevision",
            ),
            (self._paths.DECISIONS, JsonDecisionRepository(paths=self._paths), "Decision"),
            (
                self._paths.DECISION_ACCEPTANCES,
                JsonDecisionAcceptanceRepository(paths=self._paths),
                "DecisionAcceptance",
            ),
            (
                self._paths.DECISION_ACTIONS,
                JsonDecisionActionRepository(paths=self._paths),
                "DecisionAction",
            ),
            (
                self._paths.DECISION_OUTCOMES,
                JsonDecisionOutcomeRepository(paths=self._paths),
                "DecisionOutcome",
            ),
            (
                self._paths.DECISION_REVIEWS,
                JsonDecisionReviewRepository(paths=self._paths),
                "DecisionReview",
            ),
        )
        for root, repository, name in stores:
            root_relative = PurePosixPath(root.relative_to(self._paths.BRAIN).as_posix())
            if relative.parent == root_relative and relative.suffix == ".json":
                return root, repository, name
        return None

    def _recover_suffix(
        self,
        metadata: BrainMetadata,
        binding: ExternalTrustBinding,
        transition: PendingTransition,
        target_path: Path,
        descriptor: TargetDescriptor,
    ) -> None:
        next_metadata = metadata.model_copy(
            update={
                "generation": transition.to_generation,
                "pending_transition": transition,
            }
        )
        if metadata.generation == transition.from_generation:
            self._verify_recovery_checkpoint(
                target_path,
                descriptor,
                transition,
                metadata_generation=transition.from_generation,
                binding_generation=transition.from_generation,
            )
            self._persist_metadata(next_metadata)
            self._verify_recovery_checkpoint(
                target_path,
                descriptor,
                transition,
                metadata_generation=transition.to_generation,
                binding_generation=transition.from_generation,
            )
            if self._post_write_verifier is not None:
                self._post_write_verifier()

        if binding.accepted_generation == transition.from_generation:
            self._verify_recovery_checkpoint(
                target_path,
                descriptor,
                transition,
                metadata_generation=transition.to_generation,
                binding_generation=transition.from_generation,
            )
            next_binding = binding.model_copy(
                update={"accepted_generation": transition.to_generation}
            )
            self._persist_binding(next_binding)
            self._verify_binding(next_binding)

        self._verify_recovery_checkpoint(
            target_path,
            descriptor,
            transition,
            metadata_generation=transition.to_generation,
            binding_generation=transition.to_generation,
        )
        self._persist_metadata(next_metadata.model_copy(update={"pending_transition": None}))
        self._verify_final_state(target_path, descriptor, transition)

    def _verify_recovery_checkpoint(
        self,
        target_path: Path,
        descriptor: TargetDescriptor,
        transition: PendingTransition,
        *,
        metadata_generation: int,
        binding_generation: int,
    ) -> None:
        self._verify_target(target_path, descriptor)
        metadata = self._read_metadata()
        binding = self._read_binding()
        if (
            metadata.brain_id != transition.brain_id
            or metadata.generation != metadata_generation
            or metadata.pending_transition != transition
        ):
            raise ValueError("Persisted metadata does not match the recovery checkpoint.")
        if (
            binding.expected_brain_id != transition.brain_id
            or binding.accepted_generation != binding_generation
        ):
            raise ValueError("Persisted binding does not match the recovery checkpoint.")

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
        self._reject_symlink_components(target_path)
        try:
            target_stat = target_path.lstat()
        except FileNotFoundError:
            target_stat = None
        if target_stat is not None:
            if not stat.S_ISREG(target_stat.st_mode):
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

        before_sha256 = _sha256(before_bytes)
        if target.action is TargetAction.REPLACE:
            if target.before_sha256 is None:
                raise ValueError("Replace target requires before bytes hash.")
            if before_sha256 != target.before_sha256:
                raise BrainTrustStalePreimageError(
                    target.relative_path,
                    target.before_sha256,
                    before_sha256,
                )

        if target.action is TargetAction.CREATE and target.after_bytes is None:
            raise ValueError("Create target requires after bytes.")
        if target.action is TargetAction.REPLACE and target.after_bytes is None:
            raise ValueError("Replace target requires after bytes.")

        return TargetDescriptor(
            relative_path=target.relative_path,
            action=target.action,
            before_sha256=target.before_sha256
            if target.action is TargetAction.REPLACE
            else before_sha256,
            after_sha256=_sha256(target.after_bytes),
        )

    def _verify_before(self, target_path: Path, descriptor: TargetDescriptor) -> None:
        self._reject_symlink_components(target_path)
        try:
            target_stat = target_path.lstat()
        except FileNotFoundError:
            actual_sha256 = None
        else:
            if not stat.S_ISREG(target_stat.st_mode):
                actual_sha256 = None
            else:
                actual_sha256 = _sha256(target_path.read_bytes())
        expected_sha256 = descriptor.before_sha256
        if expected_sha256 is None or actual_sha256 != expected_sha256:
            raise BrainTrustStalePreimageError(
                descriptor.relative_path,
                expected_sha256 or "MISSING_EXPECTED_PREIMAGE",
                actual_sha256,
            )

    def _verify_target(self, target_path: Path, descriptor: TargetDescriptor) -> None:
        self._reject_symlink_components(target_path)
        try:
            target_stat = target_path.lstat()
        except FileNotFoundError:
            target_stat = None
        if descriptor.action is TargetAction.REMOVE:
            if target_stat is not None:
                raise ValueError(f"Removed target still exists: {descriptor.relative_path}")
            return

        if target_stat is None or not stat.S_ISREG(target_stat.st_mode):
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
        self._reject_symlink_components(path)
        brain_root = self._paths.BRAIN.resolve()
        resolved = path.resolve(strict=False)
        if resolved != brain_root and brain_root not in resolved.parents:
            raise ValueError("Controlled target must remain below the Brain directory.")
        return path

    def _reject_symlink_components(self, target_path: Path) -> None:
        relative = target_path.relative_to(self._paths.BRAIN)
        current = self._paths.BRAIN
        for component in relative.parts:
            current /= component
            try:
                mode = current.lstat().st_mode
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(mode):
                raise _UnsafeTargetPathError("Controlled target must not traverse symbolic links.")


def _model_bytes(model: BrainMetadata | ExternalTrustBinding) -> bytes:
    return model.model_dump_json(indent=2).encode("utf-8")


def _sha256(value: bytes | None) -> str | None:
    if value is None:
        return None
    return hashlib.sha256(value).hexdigest()

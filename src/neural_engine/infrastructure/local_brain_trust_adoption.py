from __future__ import annotations

import os
import stat
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast
from uuid import UUID, uuid4

from pydantic import BaseModel

from neural_engine.application.brain_trust_adoption import (
    AdoptionAuthorizationError,
    AdoptionErrorCode,
    AdoptionManualInterventionError,
    AdoptionNotEligibleError,
    AdoptionPlan,
    AdoptionResult,
    AdoptionState,
    BrainTrustAdoptionError,
    PreparedAdoption,
)
from neural_engine.application.brain_trust_inspector import (
    BrainTrustInspector,
    BrainTrustState,
)
from neural_engine.core.brain import BRAIN_FORMAT_VERSION
from neural_engine.core.brain_trust import (
    BRAIN_TRUST_BINDING_FORMAT,
    BRAIN_TRUST_METADATA_FORMAT,
    BrainMetadata,
    ExternalTrustBinding,
    PendingTransition,
    TransitionOperationKind,
)
from neural_engine.core.paths import NeuralHomeError, NeuralPaths
from neural_engine.domain import (
    Decision,
    DecisionAcceptance,
    DecisionAction,
    DecisionOutcome,
    DecisionReview,
    EvolutionProposal,
    Experience,
    Knowledge,
    Observation,
    Playbook,
    PlaybookEvaluation,
    PlaybookRevision,
    PlaybookRevisionActivation,
    PlaybookRevisionApplication,
    PlaybookRun,
)
from neural_engine.infrastructure.durability import atomic_replace_bytes, create_once_bytes
from neural_engine.ports.brain_trust_adoption import BrainTrustAdoptionCoordinator


class _RecordWithId(Protocol):
    id: UUID


RecordModel = type[BaseModel]
WriteBytes = Callable[[Path, bytes], None]


@dataclass(frozen=True, slots=True)
class AdoptionPersistence:
    """Durability dependencies for deterministic A1-A6 failure tests."""

    write_bytes: WriteBytes = atomic_replace_bytes
    create_once_bytes: WriteBytes = create_once_bytes


@dataclass(frozen=True, slots=True)
class _TrustArtifact:
    present: bool
    model: BrainMetadata | ExternalTrustBinding | None
    issue: str | None


@dataclass(frozen=True, slots=True)
class _RecordInspection:
    counts: tuple[tuple[str, int], ...]
    snapshot: tuple[tuple[str, bytes], ...]
    issues: tuple[str, ...]


_MODEL_BY_STORE: dict[str, RecordModel] = {
    "observations": Observation,
    "experiences": Experience,
    "knowledge": Knowledge,
    "playbooks": Playbook,
    "playbook-runs": PlaybookRun,
    "playbook-evaluations": PlaybookEvaluation,
    "evolution-proposals": EvolutionProposal,
    "playbook-revisions": PlaybookRevision,
    "playbook-revision-activations": PlaybookRevisionActivation,
    "playbook-revision-applications": PlaybookRevisionApplication,
    "decisions": Decision,
    "decision-acceptances": DecisionAcceptance,
    "decision-actions": DecisionAction,
    "decision-outcomes": DecisionOutcome,
    "decision-reviews": DecisionReview,
}


class LocalBrainTrustAdoptionCoordinator(BrainTrustAdoptionCoordinator):
    """Coordinate only the local, forward-only Brain adoption protocol."""

    def __init__(
        self,
        paths: NeuralPaths,
        inspector: BrainTrustInspector,
        *,
        persistence: AdoptionPersistence | None = None,
        brain_id_factory: Callable[[], UUID] = uuid4,
        transition_id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._paths = paths
        self._inspector = inspector
        self._persistence = persistence or AdoptionPersistence()
        self._brain_id_factory = brain_id_factory
        self._transition_id_factory = transition_id_factory

    def classify(self) -> AdoptionState:
        """Classify exact adoption evidence without writing or repairing it."""

        state, _metadata, _binding = self._classify_evidence()
        return state

    def plan(self, backup_evidence: Path | None = None) -> AdoptionPlan:
        """Return read-only fresh-adoption evidence and all blockers."""

        metadata_artifact, binding_artifact = self._read_trust_artifacts()
        state = self._classify_artifacts(metadata_artifact, binding_artifact)
        blockers: list[str] = []

        home_writable = self._home_ready(blockers)
        self._brain_ready(blockers)
        records = self._inspect_records()
        blockers.extend(records.issues)

        if state is not AdoptionState.UNADOPTED_FRESH:
            blockers.append(
                f"{AdoptionErrorCode.PREEXISTING_TRUST_ARTIFACT.value}: "
                f"current adoption state is {state.value}"
            )

        binding_parent_ready = self._binding_parent_ready(blockers)
        backup_path = self._validate_backup_evidence(backup_evidence, blockers)

        return AdoptionPlan(
            neural_home=self._paths.HOME,
            brain_path=self._paths.BRAIN,
            binding_path=self._paths.TRUST_BINDING,
            binding_parent=self._paths.TRUST_BINDING.parent,
            state=state,
            eligible=not blockers,
            blockers=tuple(dict.fromkeys(blockers)),
            store_counts=records.counts,
            record_snapshot=records.snapshot,
            metadata_present=metadata_artifact.present,
            binding_present=binding_artifact.present,
            home_writable=home_writable,
            binding_parent_ready=binding_parent_ready,
            backup_evidence=backup_path,
        )

    def prepare(self, backup_evidence: Path | None = None) -> PreparedAdoption:
        """Perform final read-only preflight and create an in-memory plan."""

        plan = self.plan(backup_evidence)
        if not plan.eligible:
            raise AdoptionNotEligibleError(plan.blockers)
        return PreparedAdoption(
            plan=plan,
            brain_id=self._brain_id_factory(),
            transition_id=self._transition_id_factory(),
        )

    def execute(self, prepared: PreparedAdoption, confirmation: str) -> AdoptionResult:
        """Revalidate the prepared plan and execute durable steps A1 through A6."""

        current = self.plan(prepared.plan.backup_evidence)
        if not current.eligible:
            raise AdoptionNotEligibleError(current.blockers)
        if current.record_snapshot != prepared.plan.record_snapshot:
            raise AdoptionManualInterventionError(
                "record bytes or topology changed after the identity-bound plan"
            )
        if confirmation != prepared.confirmation_token:
            raise AdoptionAuthorizationError(
                f"expected exact confirmation {prepared.confirmation_token}"
            )

        metadata = self._adoption_metadata(prepared)
        pending_bytes = _model_bytes(metadata)
        final_metadata = metadata.model_copy(update={"pending_transition": None})
        final_bytes = _model_bytes(final_metadata)
        binding = ExternalTrustBinding(
            binding_format=BRAIN_TRUST_BINDING_FORMAT,
            expected_brain_id=prepared.brain_id,
            accepted_generation=1,
        )
        binding_bytes = _model_bytes(binding)

        self._publish_metadata_marker(metadata, pending_bytes)
        self._verify_metadata_marker(metadata, pending_bytes, prepared.plan.record_snapshot)
        self._publish_binding(binding, binding_bytes)
        self._verify_binding(binding, binding_bytes)
        self._clear_marker(
            metadata,
            final_metadata,
            final_bytes,
            binding,
            binding_bytes,
            pending_bytes,
            prepared.plan.record_snapshot,
        )
        self._verify_final(
            final_metadata,
            final_bytes,
            binding,
            binding_bytes,
            prepared.plan.record_snapshot,
        )
        return self._result(prepared, len(prepared.plan.record_snapshot))

    def recover(self, authorization: str) -> AdoptionResult:
        """Continue only exact persisted S1 or S2 adoption evidence."""

        if authorization != "RECOVER ADOPTION":
            raise AdoptionAuthorizationError("expected exact confirmation RECOVER ADOPTION")

        state, metadata, binding = self._classify_evidence()
        if (
            state
            not in {
                AdoptionState.ADOPTION_PENDING_BINDING,
                AdoptionState.ADOPTION_PENDING_FINALIZATION,
            }
            or metadata is None
        ):
            raise AdoptionManualInterventionError(
                f"state {state.value} is not a recoverable adoption suffix"
            )
        try:
            pending_bytes = self._paths.BRAIN_METADATA.read_bytes()
        except OSError as error:
            raise AdoptionManualInterventionError(
                "adoption marker cannot be read before recovery"
            ) from error

        records = self._inspect_records()
        if records.issues:
            raise AdoptionManualInterventionError(
                "record or topology validation failed: " + "; ".join(records.issues)
            )
        blockers: list[str] = []
        self._home_ready(blockers)
        self._brain_ready(blockers)
        self._binding_parent_ready(blockers)
        if blockers:
            raise AdoptionNotEligibleError(tuple(dict.fromkeys(blockers)))

        expected_binding = ExternalTrustBinding(
            binding_format=BRAIN_TRUST_BINDING_FORMAT,
            expected_brain_id=metadata.brain_id,
            accepted_generation=1,
        )
        expected_binding_bytes = _model_bytes(expected_binding)
        if state is AdoptionState.ADOPTION_PENDING_BINDING:
            if binding is not None:
                raise AdoptionManualInterventionError(
                    "binding appeared during pending-binding recovery"
                )
            self._publish_binding(expected_binding, expected_binding_bytes)
            self._verify_binding(expected_binding, expected_binding_bytes)
            binding_bytes = expected_binding_bytes
        elif binding != expected_binding:
            raise AdoptionManualInterventionError(
                "pending-finalization binding does not exactly match metadata"
            )
        else:
            try:
                binding_bytes = self._paths.TRUST_BINDING.read_bytes()
            except OSError as error:
                raise AdoptionManualInterventionError(
                    "pending-finalization binding cannot be read"
                ) from error
            self._verify_binding(expected_binding, binding_bytes)

        final_metadata = metadata.model_copy(update={"pending_transition": None})
        final_bytes = _model_bytes(final_metadata)
        self._clear_marker(
            metadata,
            final_metadata,
            final_bytes,
            expected_binding,
            binding_bytes,
            pending_bytes,
            records.snapshot,
        )
        self._verify_final(
            final_metadata,
            final_bytes,
            expected_binding,
            binding_bytes,
            records.snapshot,
        )
        pending = metadata.pending_transition
        if pending is None:
            raise AdoptionManualInterventionError(
                "recovery metadata lost its adoption transition before completion"
            )
        return AdoptionResult(
            state=AdoptionState.TRUSTED_CURRENT,
            brain_id=metadata.brain_id,
            transition_id=pending.transition_id,
            generation=1,
            record_count=len(records.snapshot),
            neural_home=self._paths.HOME,
            brain_path=self._paths.BRAIN,
            binding_path=self._paths.TRUST_BINDING,
        )

    def _adoption_metadata(self, prepared: PreparedAdoption) -> BrainMetadata:
        transition = PendingTransition(
            transition_id=prepared.transition_id,
            brain_id=prepared.brain_id,
            from_generation=None,
            to_generation=1,
            operation_kind=TransitionOperationKind.ADOPTION,
            targets=(),
        )
        return BrainMetadata(
            metadata_format=BRAIN_TRUST_METADATA_FORMAT,
            brain_id=prepared.brain_id,
            generation=1,
            pending_transition=transition,
        )

    def _publish_metadata_marker(self, metadata: BrainMetadata, data: bytes) -> None:
        if _artifact_present(self._paths.BRAIN_METADATA):
            raise BrainTrustAdoptionError(
                AdoptionErrorCode.METADATA_PUBLICATION_FAILURE,
                "metadata target appeared before A1; no overwrite was attempted",
            )
        try:
            self._persistence.create_once_bytes(self._paths.BRAIN_METADATA, data)
        except Exception as error:
            transition_id = (
                metadata.pending_transition.transition_id
                if metadata.pending_transition is not None
                else UUID(int=0)
            )
            raise BrainTrustAdoptionError(
                AdoptionErrorCode.METADATA_PUBLICATION_FAILURE,
                f"A1 could not publish transition {transition_id}",
            ) from error

    def _verify_metadata_marker(
        self,
        expected: BrainMetadata,
        expected_bytes: bytes,
        snapshot: tuple[tuple[str, bytes], ...],
    ) -> None:
        if not _regular_readable(self._paths.BRAIN_METADATA):
            raise BrainTrustAdoptionError(
                AdoptionErrorCode.METADATA_VERIFICATION_FAILURE,
                "A2 metadata target is not a safe regular file",
            )
        try:
            actual_bytes = self._paths.BRAIN_METADATA.read_bytes()
            actual = BrainMetadata.model_validate_json(actual_bytes)
        except Exception as error:
            raise BrainTrustAdoptionError(
                AdoptionErrorCode.METADATA_VERIFICATION_FAILURE,
                "A2 metadata cannot be read as the expected adoption marker",
            ) from error
        if actual_bytes != expected_bytes or actual != expected:
            raise BrainTrustAdoptionError(
                AdoptionErrorCode.METADATA_VERIFICATION_FAILURE,
                "A2 metadata does not exactly match the adoption marker",
            )
        self._assert_record_snapshot(snapshot, "A2")

    def _publish_binding(self, expected: ExternalTrustBinding, data: bytes) -> None:
        blockers: list[str] = []
        if not self._binding_parent_ready(blockers):
            raise BrainTrustAdoptionError(
                AdoptionErrorCode.BINDING_CREATION_FAILURE,
                "A3 binding parent is not ready: " + "; ".join(blockers),
            )
        if _artifact_present(self._paths.TRUST_BINDING):
            raise AdoptionManualInterventionError(
                "A3 binding target appeared; it was not overwritten"
            )
        try:
            self._persistence.create_once_bytes(self._paths.TRUST_BINDING, data)
        except Exception as error:
            raise BrainTrustAdoptionError(
                AdoptionErrorCode.BINDING_CREATION_FAILURE,
                "A3 create-only binding publication failed; outcome must be inspected",
            ) from error

    def _verify_binding(self, expected: ExternalTrustBinding, expected_bytes: bytes) -> None:
        if not _regular_readable(self._paths.TRUST_BINDING):
            raise BrainTrustAdoptionError(
                AdoptionErrorCode.BINDING_VERIFICATION_FAILURE,
                "A4 binding target is not a safe regular file",
            )
        try:
            actual_bytes = self._paths.TRUST_BINDING.read_bytes()
            actual = ExternalTrustBinding.model_validate_json(actual_bytes)
        except Exception as error:
            raise BrainTrustAdoptionError(
                AdoptionErrorCode.BINDING_VERIFICATION_FAILURE,
                "A4 binding cannot be read as the expected identity binding",
            ) from error
        if actual_bytes != expected_bytes or actual != expected:
            raise AdoptionManualInterventionError(
                "A4 binding exists but does not exactly match the adoption identity"
            )

    def _clear_marker(
        self,
        pending: BrainMetadata,
        final: BrainMetadata,
        final_bytes: bytes,
        binding: ExternalTrustBinding,
        binding_bytes: bytes,
        pending_bytes: bytes,
        snapshot: tuple[tuple[str, bytes], ...],
    ) -> None:
        if not _regular_readable(self._paths.BRAIN_METADATA):
            raise AdoptionManualInterventionError("A5 metadata target is not a safe regular file")
        try:
            current_bytes = self._paths.BRAIN_METADATA.read_bytes()
            current = BrainMetadata.model_validate_json(current_bytes)
        except Exception as error:
            raise BrainTrustAdoptionError(
                AdoptionErrorCode.FINALIZATION_FAILURE,
                "A5 pending metadata cannot be read before marker clear",
            ) from error
        if current != pending or current_bytes != pending_bytes:
            raise AdoptionManualInterventionError("A5 metadata changed before marker clear")
        self._verify_binding(binding, binding_bytes)
        self._assert_record_snapshot(snapshot, "A5")
        try:
            self._persistence.write_bytes(self._paths.BRAIN_METADATA, final_bytes)
        except Exception as error:
            raise BrainTrustAdoptionError(
                AdoptionErrorCode.FINALIZATION_FAILURE,
                "A5 marker clear failed; valid forward-recovery evidence remains",
            ) from error

    def _verify_final(
        self,
        expected_metadata: BrainMetadata,
        expected_metadata_bytes: bytes,
        expected_binding: ExternalTrustBinding,
        expected_binding_bytes: bytes,
        snapshot: tuple[tuple[str, bytes], ...],
    ) -> None:
        if not _regular_readable(self._paths.BRAIN_METADATA) or not _regular_readable(
            self._paths.TRUST_BINDING
        ):
            raise AdoptionManualInterventionError("A6 trust artifacts are not safe regular files")
        try:
            metadata_bytes = self._paths.BRAIN_METADATA.read_bytes()
            metadata = BrainMetadata.model_validate_json(metadata_bytes)
            binding_bytes = self._paths.TRUST_BINDING.read_bytes()
            binding = ExternalTrustBinding.model_validate_json(binding_bytes)
        except Exception as error:
            raise AdoptionManualInterventionError(
                "A6 final trust artifacts cannot be parsed"
            ) from error
        if metadata_bytes != expected_metadata_bytes or metadata != expected_metadata:
            raise AdoptionManualInterventionError("A6 metadata postcondition failed")
        if binding_bytes != expected_binding_bytes or binding != expected_binding:
            raise AdoptionManualInterventionError("A6 binding postcondition failed")
        if metadata.pending_transition is not None:
            raise AdoptionManualInterventionError("A6 adoption marker is still present")
        self._assert_record_snapshot(snapshot, "A6")
        inspection = self._inspector.inspect_paths(self._paths)
        if inspection.state is not BrainTrustState.TRUSTED_CURRENT:
            raise AdoptionManualInterventionError(
                "A6 final inspector state is " + inspection.state.value
            )

    def _result(self, prepared: PreparedAdoption, record_count: int) -> AdoptionResult:
        return AdoptionResult(
            state=AdoptionState.TRUSTED_CURRENT,
            brain_id=prepared.brain_id,
            transition_id=prepared.transition_id,
            generation=1,
            record_count=record_count,
            neural_home=prepared.plan.neural_home,
            brain_path=prepared.plan.brain_path,
            binding_path=prepared.plan.binding_path,
        )

    def _classify_evidence(
        self,
    ) -> tuple[
        AdoptionState,
        BrainMetadata | None,
        ExternalTrustBinding | None,
    ]:
        metadata, binding = self._read_trust_artifacts()
        return self._classify_artifacts(metadata, binding), _metadata(metadata), _binding(binding)

    @staticmethod
    def _classify_artifacts(metadata: _TrustArtifact, binding: _TrustArtifact) -> AdoptionState:
        if not metadata.present and not binding.present:
            return AdoptionState.UNADOPTED_FRESH
        metadata_model = _metadata(metadata)
        binding_model = _binding(binding)
        if metadata.issue is not None or binding.issue is not None:
            return AdoptionState.MANUAL_INTERVENTION_REQUIRED
        if metadata_model is None:
            return AdoptionState.MANUAL_INTERVENTION_REQUIRED
        pending = metadata_model.pending_transition
        if pending is not None:
            if (
                pending.operation_kind is not TransitionOperationKind.ADOPTION
                or metadata_model.generation != 1
                or pending.brain_id != metadata_model.brain_id
            ):
                return AdoptionState.MANUAL_INTERVENTION_REQUIRED
            if binding_model is None:
                return AdoptionState.ADOPTION_PENDING_BINDING
            if (
                binding_model.expected_brain_id == metadata_model.brain_id
                and binding_model.accepted_generation == 1
            ):
                return AdoptionState.ADOPTION_PENDING_FINALIZATION
            return AdoptionState.MANUAL_INTERVENTION_REQUIRED
        if binding_model is None:
            return AdoptionState.MANUAL_INTERVENTION_REQUIRED
        if (
            binding_model.expected_brain_id == metadata_model.brain_id
            and binding_model.accepted_generation == metadata_model.generation
        ):
            return AdoptionState.TRUSTED_CURRENT
        return AdoptionState.MANUAL_INTERVENTION_REQUIRED

    def _read_trust_artifacts(self) -> tuple[_TrustArtifact, _TrustArtifact]:
        return (
            _read_artifact(self._paths.BRAIN_METADATA, BrainMetadata),
            _read_artifact(self._paths.TRUST_BINDING, ExternalTrustBinding),
        )

    def _home_ready(self, blockers: list[str]) -> bool:
        ready = True
        try:
            self._paths.require_available(
                operation="brain adoption",
                writable=True,
                require_brain=True,
            )
        except NeuralHomeError as error:
            ready = False
            code = (
                AdoptionErrorCode.HOME_NOT_WRITABLE
                if error.reason == "home_inaccessible"
                else AdoptionErrorCode.NOT_ELIGIBLE
            )
            blockers.append(f"{code.value}: {error}")

        if not self._paths.HOME.is_absolute() or _has_symlink_component(self._paths.HOME):
            ready = False
            blockers.append(f"{AdoptionErrorCode.UNSAFE_PATH.value}: Neural home path")
        if not _directory_ready(self._paths.HOME, writable=True):
            ready = False
            blockers.append(f"{AdoptionErrorCode.HOME_NOT_WRITABLE.value}: Neural home")
        return ready

    def _brain_ready(self, blockers: list[str]) -> bool:
        ready = True
        if not _directory_ready(self._paths.BRAIN, writable=True):
            ready = False
            blockers.append(f"{AdoptionErrorCode.UNSAFE_PATH.value}: Brain directory")
        for path, label in (
            (self._paths.VERSION, "VERSION"),
            (self._paths.CONFIG, "config.toml"),
        ):
            if not _regular_readable(path) or _has_symlink_component(path):
                ready = False
                blockers.append(f"{AdoptionErrorCode.NOT_ELIGIBLE.value}: {label} is not readable")
        if ready:
            try:
                version = self._paths.VERSION.read_text(encoding="utf-8").strip()
            except OSError, UnicodeError:
                ready = False
                blockers.append(f"{AdoptionErrorCode.NOT_ELIGIBLE.value}: VERSION read failed")
            else:
                if version != BRAIN_FORMAT_VERSION:
                    ready = False
                    blockers.append(
                        f"{AdoptionErrorCode.NOT_ELIGIBLE.value}: unsupported Brain format"
                    )
        return ready

    def _binding_parent_ready(self, blockers: list[str]) -> bool:
        parent = self._paths.TRUST_BINDING.parent
        ready = _directory_ready(parent, writable=True) and not _has_symlink_component(parent)
        if not ready:
            blockers.append(f"{AdoptionErrorCode.BINDING_PARENT_NOT_READY.value}: {parent}")
        return ready

    @staticmethod
    def _validate_backup_evidence(
        value: Path | None,
        blockers: list[str],
    ) -> Path | None:
        if value is None:
            blockers.append(f"{AdoptionErrorCode.BACKUP_MISSING.value}: provide --backup-evidence")
            return None
        path = Path(value)
        if not path.is_absolute():
            path = path.absolute()
        if _has_symlink_component(path) or not path.exists():
            blockers.append(f"{AdoptionErrorCode.BACKUP_MISSING.value}: {path}")
            return path
        if path.is_dir():
            readable = os.access(path, os.R_OK | os.X_OK)
        else:
            readable = path.is_file() and os.access(path, os.R_OK)
        if not readable:
            blockers.append(f"{AdoptionErrorCode.BACKUP_MISSING.value}: {path} is unreadable")
        return path

    def _inspect_records(self) -> _RecordInspection:
        counts: list[tuple[str, int]] = []
        snapshot: list[tuple[str, bytes]] = []
        issues: list[str] = []
        for store_name, store_path in self._paths.record_stores:
            children: tuple[Path, ...]
            if _has_symlink_component(store_path):
                issues.append(f"{AdoptionErrorCode.UNSAFE_PATH.value}: {store_name} store symlink")
                counts.append((store_name, 0))
                continue
            if not _directory_ready(store_path, writable=False):
                issues.append(
                    f"{AdoptionErrorCode.RECORD_VALIDATION_FAILURE.value}: {store_name} store"
                )
                counts.append((store_name, 0))
                continue
            try:
                children = tuple(sorted(store_path.iterdir()))
            except OSError:
                issues.append(
                    f"{AdoptionErrorCode.RECORD_VALIDATION_FAILURE.value}: cannot scan {store_name}"
                )
                counts.append((store_name, 0))
                continue

            counts.append((store_name, len(children)))
            model_type = _MODEL_BY_STORE[store_name]
            record_ids: set[UUID] = set()
            for path in children:
                relative = path.relative_to(self._paths.HOME).as_posix()
                if path.is_symlink() or _has_symlink_component(path):
                    issues.append(f"{AdoptionErrorCode.UNSAFE_PATH.value}: {relative}")
                    continue
                try:
                    is_regular = stat.S_ISREG(path.stat().st_mode)
                except OSError:
                    is_regular = False
                if not is_regular:
                    issues.append(
                        f"{AdoptionErrorCode.RECORD_VALIDATION_FAILURE.value}: "
                        f"{relative} is not a regular file"
                    )
                    continue
                if path.suffix != ".json":
                    issues.append(
                        f"{AdoptionErrorCode.RECORD_VALIDATION_FAILURE.value}: "
                        f"unsupported artifact {relative}"
                    )
                    continue
                try:
                    record_id = UUID(path.stem)
                except ValueError:
                    issues.append(
                        f"{AdoptionErrorCode.RECORD_VALIDATION_FAILURE.value}: "
                        f"{relative} filename is not a UUID"
                    )
                    continue
                if path.name != f"{record_id}.json":
                    issues.append(
                        f"{AdoptionErrorCode.RECORD_VALIDATION_FAILURE.value}: "
                        f"{relative} filename is not normalized"
                    )
                    continue
                try:
                    content = path.read_bytes()
                    record = model_type.model_validate_json(content)
                except Exception:
                    issues.append(
                        f"{AdoptionErrorCode.RECORD_VALIDATION_FAILURE.value}: {relative} schema"
                    )
                    continue
                actual_id = cast(_RecordWithId, record).id
                if actual_id != record_id:
                    issues.append(
                        f"{AdoptionErrorCode.RECORD_VALIDATION_FAILURE.value}: "
                        f"{relative} filename/payload identity"
                    )
                    continue
                if actual_id in record_ids:
                    issues.append(
                        f"{AdoptionErrorCode.RECORD_VALIDATION_FAILURE.value}: "
                        f"{relative} duplicate identity"
                    )
                    continue
                record_ids.add(actual_id)
                snapshot.append((relative, content))
        return _RecordInspection(tuple(counts), tuple(snapshot), tuple(issues))

    def _assert_record_snapshot(
        self,
        expected: tuple[tuple[str, bytes], ...],
        step: str,
    ) -> None:
        current = self._inspect_records()
        if current.issues:
            raise AdoptionManualInterventionError(
                f"{step} record validation failed: " + "; ".join(current.issues)
            )
        if current.snapshot != expected:
            raise AdoptionManualInterventionError(f"{step} record bytes or topology changed")


def _read_artifact(path: Path, model_type: type[BaseModel]) -> _TrustArtifact:
    if not _artifact_present(path):
        return _TrustArtifact(False, None, None)
    if _has_symlink_component(path) or path.is_symlink():
        return _TrustArtifact(True, None, "unsafe_path")
    if not path.is_file():
        return _TrustArtifact(True, None, "not_regular")
    try:
        model = model_type.model_validate_json(path.read_bytes())
    except Exception:
        return _TrustArtifact(True, None, "invalid_artifact")
    return _TrustArtifact(True, cast(BrainMetadata | ExternalTrustBinding, model), None)


def _metadata(artifact: _TrustArtifact) -> BrainMetadata | None:
    return artifact.model if isinstance(artifact.model, BrainMetadata) else None


def _binding(artifact: _TrustArtifact) -> ExternalTrustBinding | None:
    return artifact.model if isinstance(artifact.model, ExternalTrustBinding) else None


def _artifact_present(path: Path) -> bool:
    try:
        return path.exists() or path.is_symlink()
    except OSError:
        return True


def _directory_ready(path: Path, *, writable: bool) -> bool:
    try:
        if _has_symlink_component(path) or not path.is_dir():
            return False
        mode = os.R_OK | os.X_OK
        if writable:
            mode |= os.W_OK
        return os.access(path, mode)
    except OSError:
        return False


def _regular_readable(path: Path) -> bool:
    try:
        return not _has_symlink_component(path) and path.is_file() and os.access(path, os.R_OK)
    except OSError:
        return False


def _has_symlink_component(path: Path) -> bool:
    if not path.is_absolute():
        return True
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            if current.is_symlink():
                return True
        except OSError:
            return True
    return False


def _model_bytes(model: BaseModel) -> bytes:
    return model.model_dump_json(indent=2).encode("utf-8")

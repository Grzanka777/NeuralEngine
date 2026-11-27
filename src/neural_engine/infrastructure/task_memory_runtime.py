"""Local task admission, receipt handling, and independent verifier execution."""

import fcntl
import os
import re
import stat
import subprocess
from collections.abc import Callable
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryFile
from typing import Literal
from uuid import UUID, uuid4

from pydantic import Field

from neural_engine.application.brain_context_service import (
    BrainContextError,
    BrainContextIntegrityError,
)
from neural_engine.application.task_memory_service import (
    Contract,
    Digest,
    Learning,
    NativeClientTrust,
    ProviderDestination,
    TaskMemoryError,
    TaskMemoryIntegrityError,
    TaskMemoryPolicy,
    TaskMemoryService,
    Text,
    VerifiedTaskResult,
    Verifier,
)
from neural_engine.core.paths import NeuralHomeError
from neural_engine.domain import EvidenceReference
from neural_engine.infrastructure.durability import create_once_bytes

_TASK = re.compile(r"Read and execute:[ \t]*\n[ \t]*(\.agent-work/prompts/([\w.-]+)\.md)")
_MAX_RECEIPT = 32_768
_MAX_PROMPT = 131_072
Completion = Literal["completed", "failed", "interrupted"]
OPERATOR_TRUSTED_NATIVE = "OPERATOR_TRUSTED_NATIVE"


class NativeEngine(Contract):
    engine: Literal["codex", "antigravity"]
    requested_model: Text


class TaskStart(Contract):
    cwd: str
    invocation: str
    destination: ProviderDestination | None
    native_engine: NativeEngine | None = None


class TaskFinish(Contract):
    session: UUID
    outcome: Completion
    context_supplied: bool
    native_session: UUID | None = Field(default=None, exclude_if=lambda value: value is None)


class TaskAdmission(Contract):
    session: UUID
    policy_sha256: Digest
    task: str
    task_path: str
    task_sha256: Digest
    context: dict[str, object]
    native_engine: NativeEngine | None = Field(default=None, exclude_if=lambda value: value is None)


class TaskCompletion(Contract):
    admission: TaskAdmission
    outcome: Completion
    context_supplied: bool
    native_session: UUID | None = Field(default=None, exclude_if=lambda value: value is None)
    status: str
    verification_sha256: Digest | None = None
    evidence: EvidenceReference | None = None
    brain_id: UUID | None = None
    learning: Learning | None = None


class TaskMemoryRuntime:
    """Operator-local adapter. Receipt files are outside the worktree and Brain."""

    def __init__(self, policy_path: Path) -> None:
        if (
            not policy_path.is_absolute()
            or policy_path.resolve(strict=True) != policy_path
            or not policy_path.is_file()
        ):
            raise TaskMemoryError("POLICY_PATH_INVALID")
        for path in (policy_path.parent, policy_path):
            metadata = path.stat()
            if metadata.st_uid != os.getuid() or metadata.st_mode & 0o077:
                raise TaskMemoryError("POLICY_MUST_BE_PRIVATE")
        raw = _read(policy_path, _MAX_RECEIPT)
        self.policy = TaskMemoryPolicy.model_validate_json(raw)
        self.policy_digest = sha256(raw).hexdigest()
        self.workspace = _canonical_directory(self.policy.workspace)
        self.receipts = policy_path.parent
        if self.receipts.is_relative_to(self.workspace):
            raise TaskMemoryError("POLICY_MUST_BE_OUTSIDE_WORKSPACE")

    def start(
        self,
        request: TaskStart,
        service: Callable[[], TaskMemoryService],
        *,
        trusted_native: NativeClientTrust | None = None,
    ) -> dict[str, object]:
        parts = _TASK.fullmatch(request.invocation.strip())
        if parts is None or len(parts[2]) > 80 or not parts[2].isascii():
            raise TaskMemoryError("TASK_INVOCATION_INVALID")
        if Path(request.cwd).resolve(strict=True) != self.workspace:
            raise TaskMemoryError("PROJECT_IDENTITY_MISMATCH")
        root = (
            subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=self.workspace,
                env={"PATH": os.defpath},
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                check=True,
                timeout=5,
            )
            .stdout.decode()
            .strip()
        )
        if Path(root).resolve(strict=True) != self.workspace:
            raise TaskMemoryError("PROJECT_IDENTITY_MISMATCH")
        prompt = self._prompt(parts[1])
        rendered = None
        native = request.native_engine
        authorized_native = (
            native is not None
            and trusted_native is not None
            and trusted_native == self.policy.trust_native
            and trusted_native.engine == native.engine
            and trusted_native.model == native.requested_model
        )
        authorized_exact = (
            native is None
            and request.destination is not None
            and request.destination == self.policy.share_with
        )
        context: dict[str, object] = {"state": "DISCLOSURE_DENIED"}
        if native is not None or request.destination is None:
            context["reason"] = "DESTINATION_UNVERIFIED"
        if authorized_native or authorized_exact:
            try:
                context, rendered = service().context(self.policy)
            except BrainContextIntegrityError, TaskMemoryIntegrityError:
                context = {"state": "INTEGRITY_ERROR"}
            except BrainContextError, NeuralHomeError, OSError, TaskMemoryError:
                context = {"state": "RETRIEVAL_ERROR"}
        if authorized_native and trusted_native is not None:
            context.update(
                disclosure=OPERATOR_TRUSTED_NATIVE,
                client_sha256=trusted_native.sha256,
            )
        session = uuid4()
        admission = TaskAdmission(
            session=session,
            policy_sha256=self.policy_digest,
            task=parts[2],
            task_path=parts[1],
            task_sha256=sha256(prompt).hexdigest(),
            context=context,
            native_engine=request.native_engine,
        )
        create_once_bytes(self._receipt_path(session, "started"), _serialize(admission))
        return {
            "session": str(session),
            "state": context["state"],
            "prompt": prompt.decode(),
            "evidence": rendered,
        }

    def finish(
        self, request: TaskFinish, service: Callable[[], TaskMemoryService]
    ) -> tuple[TaskCompletion, str]:
        # Concurrent completion events share one verifiable result.
        started = self._receipt_path(request.session, "started")
        result_path = self._receipt_path(request.session, "result")
        with started.open("rb") as receipt:
            fcntl.flock(receipt, fcntl.LOCK_EX)
            admission = TaskAdmission.model_validate_json(receipt.read(_MAX_RECEIPT))
            if (
                admission.session != request.session
                or admission.policy_sha256 != self.policy_digest
            ):
                raise TaskMemoryError("ADMISSION_IDENTITY_CHANGED")
            if result_path.exists():
                return self.result(request.session)
            result = self._complete(admission, request, service)
            raw = _serialize(result)
            create_once_bytes(result_path, raw)
            return result, sha256(raw).hexdigest()

    def result(self, session: UUID) -> tuple[TaskCompletion, str]:
        path = self._receipt_path(session, "result")
        if not path.exists() and self._receipt_path(session, "started").is_file():
            raise TaskMemoryError("NO_COMPLETION_RECEIPT")
        raw = _read(path, _MAX_RECEIPT)
        result = TaskCompletion.model_validate_json(raw)
        if (
            result.admission.session != session
            or result.admission.policy_sha256 != self.policy_digest
        ):
            raise TaskMemoryError("ADMISSION_IDENTITY_CHANGED")
        return result, sha256(raw).hexdigest()

    def _complete(
        self,
        admission: TaskAdmission,
        request: TaskFinish,
        service: Callable[[], TaskMemoryService],
    ) -> TaskCompletion:
        initial = TaskCompletion(
            admission=admission,
            outcome=request.outcome,
            context_supplied=request.context_supplied,
            native_session=request.native_session,
            status=request.outcome.upper(),
        )
        if admission.native_engine is not None and (
            (
                request.context_supplied
                and (
                    admission.context.get("disclosure") != OPERATOR_TRUSTED_NATIVE
                    or admission.context.get("sha256") is None
                    or request.native_session is None
                )
            )
            or (request.outcome == "completed" and request.native_session is None)
        ):
            raise TaskMemoryError("NATIVE_SETTLEMENT_INVALID")
        if request.outcome != "completed":
            return initial
        verifier = self.policy.verifiers.get(admission.task, self.policy.default_verifier)
        if verifier is None:
            return initial.model_copy(update={"status": "NO_VERIFIER"})
        try:
            if sha256(self._prompt(admission.task_path)).hexdigest() != admission.task_sha256:
                raise TaskMemoryError("TASK_CHANGED")
            verified = self._verify(verifier, admission)
        except ValueError, OSError, TaskMemoryError, subprocess.SubprocessError:
            return initial.model_copy(update={"status": "UNVERIFIED"})
        if not verified.passed:
            return initial.model_copy(update={"status": "VERIFICATION_FAILED"})
        if verified.learning is None:
            return initial.model_copy(update={"status": "NO_LEARNING"})
        try:
            evidence = self._verified_evidence(verified)
        except OSError, TaskMemoryError:
            return initial.model_copy(update={"status": "UNVERIFIED"})
        try:
            memory = service()
            snapshot = memory.trusted_snapshot()
            initial_brain = admission.context.get("brain_id")
            if initial_brain is not None and initial_brain != str(snapshot[0]):
                raise TaskMemoryIntegrityError("BRAIN_IDENTITY_CHANGED")
            status = memory.classify(self.policy.project, verified.learning)
            if memory.trusted_snapshot() != snapshot:
                raise TaskMemoryIntegrityError("INTEGRITY_ERROR")
        except BrainContextIntegrityError, TaskMemoryIntegrityError:
            return initial.model_copy(update={"status": "INTEGRITY_ERROR"})
        except NeuralHomeError, OSError, TaskMemoryError:
            return initial.model_copy(update={"status": "RETRIEVAL_ERROR"})
        return initial.model_copy(
            update={
                "status": status,
                "verification_sha256": verifier.sha256,
                "evidence": evidence,
                "brain_id": snapshot[0],
                "learning": verified.learning if status != "UNVERIFIED" else None,
            }
        )

    def authorise(
        self, session: UUID, confirmation: str, service: Callable[[], TaskMemoryService]
    ) -> tuple[str, UUID | None]:
        result, digest = self.result(session)
        if confirmation != digest:
            raise TaskMemoryError("EXPLICIT_AUTHORIZATION_REQUIRED")
        if (
            result.status != "AWAITING_AUTHORIZATION"
            or result.brain_id is None
            or result.learning is None
            or result.verification_sha256 is None
            or result.evidence is None
        ):
            raise TaskMemoryError("NO_AUTHORIZABLE_CANDIDATE")
        engine = result.admission.native_engine
        engine_name = engine.engine if engine else "pi"
        evidence = EvidenceReference(
            kind="task_memory_verification",
            locator=f"{result.admission.task_path}#{engine_name}-session={session}",
            repository_or_project=self.policy.project,
            content_hash=result.admission.task_sha256,
            source=f"verifier-sha256:{result.verification_sha256}",
        )
        # Serialize task-memory apply calls even when different policies select this Brain.
        brain_home = _canonical_directory(self.policy.brain_home)
        descriptor = os.open(brain_home, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            return service().apply(
                self.policy.project,
                result.learning,
                evidence,
                result.brain_id,
                result.evidence,
                authority_confirmed=True,
            )
        finally:
            os.close(descriptor)

    def _verified_evidence(self, verified: VerifiedTaskResult) -> EvidenceReference:
        if verified.evidence_path is None or verified.evidence_sha256 is None:
            raise TaskMemoryError("VERIFIER_EVIDENCE_REQUIRED")
        relative = Path(verified.evidence_path)
        path = self.workspace / relative
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or path.resolve(strict=True) != path
            or not path.is_relative_to(self.workspace)
            or sha256(_read(path, 8_388_608)).hexdigest() != verified.evidence_sha256
        ):
            raise TaskMemoryError("VERIFIER_EVIDENCE_MISMATCH")
        return EvidenceReference(
            kind="verified_task_artifact",
            locator=relative.as_posix(),
            repository_or_project=self.policy.project,
            content_hash=verified.evidence_sha256,
        )

    def _prompt(self, relative: str) -> bytes:
        path = self.workspace / relative
        if path.resolve(strict=True) != path or not path.is_file():
            raise TaskMemoryError("TASK_PATH_INVALID")
        raw = _read(path, _MAX_PROMPT)
        raw.decode()
        return raw

    def _verify(self, verifier: Verifier, admission: TaskAdmission) -> VerifiedTaskResult:
        program = Path(verifier.executable)
        if (
            not program.is_absolute()
            or program.resolve(strict=True) != program
            or program.is_relative_to(self.workspace)
            or not program.is_file()
            or sha256(_read(program, 1_048_576)).hexdigest() != verifier.sha256
        ):
            raise TaskMemoryError("VERIFIER_IDENTITY_MISMATCH")
        with TemporaryFile() as output:
            subprocess.run(
                [str(program)],
                cwd=self.workspace,
                env={"PATH": os.defpath},
                input=_serialize(admission),
                stdout=output,
                stderr=subprocess.DEVNULL,
                timeout=120,
                check=True,
            )
            output.seek(0)
            raw = output.read(4097)
        if len(raw) > 4096:
            raise TaskMemoryError("VERIFIER_OUTPUT_TOO_LARGE")
        return VerifiedTaskResult.model_validate_json(raw)

    def _receipt_path(self, session: UUID, suffix: str) -> Path:
        return self.receipts / f"{session}.{suffix}.json"


def _read(path: Path, limit: int) -> bytes:
    if not stat.S_ISREG(path.lstat().st_mode):
        raise TaskMemoryError("EXPECTED_REGULAR_FILE")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise TaskMemoryError("INPUT_TOO_LARGE")
    return raw


def _canonical_directory(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute() or path.resolve(strict=True) != path or not path.is_dir():
        raise TaskMemoryError("WORKSPACE_PATH_INVALID")
    return path


def _serialize(value: Contract) -> bytes:
    return value.model_dump_json().encode()

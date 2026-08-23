"""Local, fixed-inventory readers for authority-aware planner context."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from neural_engine.application.planner_context_service import (
    EvidenceState,
    HistoricalEvidenceInput,
    PlannerRepositoryCheckpoint,
    SourceEvidence,
    SourceType,
    content_sha256,
)
from neural_engine.core.paths import NeuralPaths
from neural_engine.infrastructure.json_knowledge_repository import JsonKnowledgeRepository
from neural_engine.ports.knowledge_repository import (
    KnowledgeIdentityMismatchError,
    KnowledgeStoredDataError,
)

_SECRET_PATTERN = re.compile(
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
    r"\b(?:api_key|token|password|secret)\b\s*[:=]\s*\S+",
    re.IGNORECASE,
)


class LocalPlannerContextReaders:
    """Implements the five narrow reader ports with no filesystem mutation."""

    def __init__(
        self,
        paths: NeuralPaths | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._paths = paths
        self._clock = clock or (lambda: datetime.now(UTC))

    def verify(self, checkpoint: PlannerRepositoryCheckpoint) -> SourceEvidence:
        retrieved_at = self._clock()
        root, error = self._root(checkpoint.repository_root)
        if error is not None:
            return self._diagnostic(
                SourceType.REPOSITORY_METADATA,
                "repository",
                checkpoint.repository_identity,
                EvidenceState.UNREADABLE,
                retrieved_at,
                error,
            )
        values: dict[str, str] = {}
        commands = {
            "root": ("rev-parse", "--show-toplevel"),
            "branch": ("branch", "--show-current"),
            "head": ("rev-parse", "HEAD"),
            "remote": ("rev-parse", "origin/main"),
            "status": ("status", "--short"),
        }
        try:
            for name, arguments in commands.items():
                values[name] = self._git(root, *arguments)
        except RuntimeError as error:
            return self._diagnostic(
                SourceType.REPOSITORY_METADATA,
                "repository",
                checkpoint.repository_identity,
                EvidenceState.UNREADABLE,
                retrieved_at,
                str(error),
            )
        actual = {
            "repository_root": str(root),
            "branch": values["branch"],
            "head": values["head"],
            "authoritative_remote_ref": values["remote"],
            "worktree_state": values["status"] or "clean",
        }
        expected = {
            "repository_root": str(root),
            "branch": checkpoint.branch,
            "head": checkpoint.head,
            "authoritative_remote_ref": checkpoint.authoritative_remote_ref,
            "worktree_state": checkpoint.worktree_state,
        }
        if actual != expected:
            return self._diagnostic(
                SourceType.REPOSITORY_METADATA,
                "repository",
                checkpoint.repository_identity,
                EvidenceState.STALE,
                retrieved_at,
                "verified checkpoint does not match live repository",
                content=repr(actual),
                checkpoint=checkpoint.head,
            )
        content = "\n".join(f"{key}={value}" for key, value in sorted(actual.items()))
        return SourceEvidence(
            source_type=SourceType.REPOSITORY_METADATA,
            normalized_locator="repository",
            stable_identity=checkpoint.head,
            external_project_context=checkpoint.repository_identity,
            authority_class="verified live repository",
            evidence_state=EvidenceState.CURRENT,
            retrieved_at=retrieved_at,
            extraction_boundary="verified repository metadata",
            checkpoint_or_version=checkpoint.head,
            excerpt=content,
            content_sha256=content_sha256(content),
        )

    def read_current_documents(
        self, checkpoint: PlannerRepositoryCheckpoint, locators: tuple[str, ...]
    ) -> tuple[SourceEvidence, ...]:
        return self._read_files(checkpoint, locators, SourceType.DESIGNATED_DOCUMENT)

    def read_review_evidence(
        self, checkpoint: PlannerRepositoryCheckpoint, locators: tuple[str, ...]
    ) -> tuple[SourceEvidence, ...]:
        return self._read_files(checkpoint, locators, SourceType.DESIGNATED_REVIEW)

    def read_knowledge(
        self, project_key: str, knowledge_ids: tuple[UUID, ...]
    ) -> tuple[SourceEvidence, ...]:
        retrieved_at = self._clock()
        repository = (
            JsonKnowledgeRepository(paths=self._paths) if self._paths else JsonKnowledgeRepository()
        )
        items: list[SourceEvidence] = []
        for knowledge_id in knowledge_ids:
            locator = f"brain/knowledge/{knowledge_id}.json"
            try:
                knowledge = repository.get_by_id(knowledge_id)
            except KnowledgeStoredDataError, KnowledgeIdentityMismatchError:
                items.append(
                    self._diagnostic(
                        SourceType.BRAIN_KNOWLEDGE,
                        locator,
                        str(knowledge_id),
                        EvidenceState.UNREADABLE,
                        retrieved_at,
                        "selected Knowledge is malformed or unreadable",
                    )
                )
                continue
            if knowledge is None:
                items.append(
                    self._diagnostic(
                        SourceType.BRAIN_KNOWLEDGE,
                        locator,
                        str(knowledge_id),
                        EvidenceState.MISSING,
                        retrieved_at,
                        "selected Knowledge does not exist",
                    )
                )
                continue
            content = knowledge.model_dump_json(indent=2)
            items.append(
                SourceEvidence(
                    source_type=SourceType.BRAIN_KNOWLEDGE,
                    normalized_locator=locator,
                    stable_identity=str(knowledge.id),
                    external_project_context=project_key,
                    authority_class="caller-selected supporting Knowledge",
                    evidence_state=EvidenceState.HISTORICAL,
                    retrieved_at=retrieved_at,
                    extraction_boundary="complete selected Knowledge record",
                    excerpt=self._excerpt(content),
                    content_sha256=content_sha256(content),
                    diagnostic="relevance is caller-selected",
                )
            )
        return tuple(items)

    def read_historical_evidence(
        self, evidence: tuple[HistoricalEvidenceInput, ...]
    ) -> tuple[SourceEvidence, ...]:
        retrieved_at = self._clock()
        return tuple(
            SourceEvidence(
                source_type=SourceType.HISTORICAL_EVIDENCE,
                normalized_locator=item.locator,
                stable_identity=item.stable_identity,
                external_project_context="caller-supplied historical context",
                authority_class=item.authority_class,
                evidence_state=item.evidence_state,
                retrieved_at=retrieved_at,
                extraction_boundary="caller-supplied bounded historical evidence",
                checkpoint_or_version=item.checkpoint_or_version,
                excerpt=self._excerpt(item.content),
                content_sha256=content_sha256(item.content),
            )
            for item in evidence
        )

    def _read_files(
        self,
        checkpoint: PlannerRepositoryCheckpoint,
        locators: tuple[str, ...],
        source_type: SourceType,
    ) -> tuple[SourceEvidence, ...]:
        retrieved_at = self._clock()
        root, root_error = self._root(checkpoint.repository_root)
        if root_error is not None:
            return tuple(
                self._diagnostic(
                    source_type,
                    locator,
                    checkpoint.head,
                    EvidenceState.UNREADABLE,
                    retrieved_at,
                    root_error,
                )
                for locator in locators
            )
        return tuple(
            self._read_file(root, checkpoint, locator, source_type, retrieved_at)
            for locator in locators
        )

    def _read_file(
        self,
        root: Path,
        checkpoint: PlannerRepositoryCheckpoint,
        locator: str,
        source_type: SourceType,
        retrieved_at: datetime,
    ) -> SourceEvidence:
        candidate = root.joinpath(*locator.split("/"))
        try:
            relative = candidate.relative_to(root)
        except ValueError:
            return self._diagnostic(
                source_type,
                locator,
                checkpoint.head,
                EvidenceState.UNREADABLE,
                retrieved_at,
                "path escapes verified repository root",
            )
        if (
            not locator
            or locator.startswith("/")
            or any(part in {"", ".", ".."} for part in relative.parts)
        ):
            return self._diagnostic(
                source_type,
                locator,
                checkpoint.head,
                EvidenceState.UNREADABLE,
                retrieved_at,
                "invalid approved source locator",
            )
        try:
            if candidate.is_symlink() or not candidate.exists():
                state = (
                    EvidenceState.UNREADABLE if candidate.is_symlink() else EvidenceState.MISSING
                )
                reason = (
                    "symlink sources are rejected"
                    if candidate.is_symlink()
                    else "designated source is missing"
                )
                return self._diagnostic(
                    source_type, locator, checkpoint.head, state, retrieved_at, reason
                )
            resolved_candidate = candidate.resolve(strict=True)
            try:
                resolved_candidate.relative_to(root)
            except ValueError:
                return self._diagnostic(
                    source_type,
                    locator,
                    checkpoint.head,
                    EvidenceState.UNREADABLE,
                    retrieved_at,
                    "resolved path escapes verified repository root",
                )
            if not resolved_candidate.is_file() or resolved_candidate.stat().st_size > 65536:
                return self._diagnostic(
                    source_type,
                    locator,
                    checkpoint.head,
                    EvidenceState.UNREADABLE,
                    retrieved_at,
                    "source is not a readable regular UTF-8 file within 64 KiB",
                )
            raw = resolved_candidate.read_bytes()
            content = raw.decode("utf-8")
        except OSError, UnicodeDecodeError:
            return self._diagnostic(
                source_type,
                locator,
                checkpoint.head,
                EvidenceState.UNREADABLE,
                retrieved_at,
                "source cannot be read as UTF-8",
            )
        normalized = content.replace("\r\n", "\n").replace("\r", "\n")
        digest = content_sha256(normalized)
        if _SECRET_PATTERN.search(normalized):
            return self._diagnostic(
                source_type,
                locator,
                checkpoint.head,
                EvidenceState.UNREADABLE,
                retrieved_at,
                "content withheld by secret guard",
                content=normalized,
                checkpoint=checkpoint.head,
            )
        return SourceEvidence(
            source_type=source_type,
            normalized_locator=locator,
            stable_identity=f"{checkpoint.head}:{locator}",
            external_project_context=checkpoint.repository_identity,
            authority_class="verified current repository source",
            evidence_state=EvidenceState.CURRENT,
            retrieved_at=retrieved_at,
            extraction_boundary="first 120 normalized-LF lines, maximum 4096 UTF-8 bytes",
            checkpoint_or_version=checkpoint.head,
            excerpt=self._excerpt(normalized),
            content_sha256=digest,
        )

    @staticmethod
    def _root(value: str) -> tuple[Path, str | None]:
        root = Path(value)
        try:
            if not root.is_absolute() or root.is_symlink() or not root.is_dir():
                return root, "verified repository root is unavailable or invalid"
            resolved = root.resolve(strict=True)
            if resolved != root:
                return root, "verified repository root must already be strictly resolved"
            return root, None
        except OSError:
            return root, "verified repository root cannot be resolved"

    @staticmethod
    def _git(root: Path, *arguments: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(root), *arguments],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if result.returncode != 0:
            raise RuntimeError("Git verification failed")
        return result.stdout.strip()

    @staticmethod
    def _excerpt(content: str) -> str:
        lines = content.split("\n")[:120]
        bounded = "\n".join(lines)
        return bounded.encode("utf-8")[:4096].decode("utf-8", errors="ignore")

    @staticmethod
    def _diagnostic(
        source_type: SourceType,
        locator: str,
        identity: str,
        state: EvidenceState,
        retrieved_at: datetime,
        reason: str,
        *,
        content: str | None = None,
        checkpoint: str | None = None,
    ) -> SourceEvidence:
        return SourceEvidence(
            source_type=source_type,
            normalized_locator=locator,
            stable_identity=identity,
            external_project_context="unavailable source",
            authority_class="no authority established",
            evidence_state=state,
            retrieved_at=retrieved_at,
            checkpoint_or_version=checkpoint,
            content_sha256=content_sha256(content) if content is not None else None,
            diagnostic=reason,
        )

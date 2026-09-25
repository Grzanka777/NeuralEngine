"""Manual, bounded fresh-session handoff rendering for OpenCode."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from neural_engine.domain.opencode_context import ContextSourceQuality
from neural_engine.ports.opencode_handoff_repository import (
    HandoffRepositoryCheckpoint,
    OpencodeHandoffRepository,
)

_SECRET_PATTERN = re.compile(
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
    r"\b(?:api_key|token|password|secret)\b\s*[:=]\s*\S+",
    re.IGNORECASE,
)
_MAX_ITEM_CHARS = 500
_MAX_RENDERED_CHARS = 7_000
_DEFAULT_DO_NOT_DO = "Do not commit, push, stage, reset, or clean."


class OpencodeHandoffError(Exception):
    """A manual handoff could not be assembled safely."""


@dataclass(frozen=True, slots=True)
class OpencodeHandoffRequest:
    """Explicit, caller-reviewed facts for one fresh OpenCode session."""

    repository_root: Path
    task_goal: str
    next_action: str
    verified_decisions: tuple[str, ...] = ()
    files: tuple[str, ...] = ()
    modules: tuple[str, ...] = ()
    validated_evidence: tuple[str, ...] = ()
    uncertainty: tuple[str, ...] = ()
    do_not_do: tuple[str, ...] = ()
    session_observation: HandoffSessionObservation | None = None


@dataclass(frozen=True, slots=True)
class HandoffSessionObservation:
    """Bounded scalar context facts observed by the watch command."""

    session_id: str
    current_tokens: int
    context_limit: int
    source_quality: ContextSourceQuality
    source_description: str


class OpencodeHandoffService:
    """Render only bounded, explicit facts plus a live repository checkpoint."""

    def __init__(
        self,
        repository: OpencodeHandoffRepository,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._clock = clock or (lambda: datetime.now(UTC))

    def render(self, request: OpencodeHandoffRequest) -> str:
        task_goal = self._normalize_required("task goal", request.task_goal)
        next_action = self._normalize_required("next action", request.next_action)
        decisions = self._normalize_items("verified decision", request.verified_decisions)
        modules = self._normalize_items("module", request.modules)
        evidence = self._normalize_items("validated evidence", request.validated_evidence)
        uncertainty = self._normalize_items("uncertainty", request.uncertainty)
        do_not_do = self._normalize_items("constraint", (*request.do_not_do, _DEFAULT_DO_NOT_DO))
        raw_files = self._normalize_items("working-set file", request.files)
        checkpoint = self._repository.inspect(request.repository_root)
        files = self._resolve_files(checkpoint, raw_files)
        session_observation = self._normalize_session_observation(request.session_observation)
        generated_at = self._utc_timestamp()

        lines = [
            "# OPENCODE FRESH-SESSION HANDOFF",
            "",
            "## TASK GOAL",
            f"- {task_goal}",
            "",
            "## VERIFIED DECISIONS",
            *self._items_or_absence(decisions, "No verified decisions were supplied."),
            "",
            "## CURRENT WORKING SET",
            f"- repository: {checkpoint.root}",
            f"- branch: {checkpoint.branch}",
            f"- HEAD: {checkpoint.head}",
            f"- worktree: {self._worktree_state(checkpoint.worktree_entries)}",
        ]
        if files:
            lines.extend(["- relevant files:", *self._indented_items(files)])
        if modules:
            lines.extend(["- relevant modules:", *self._indented_items(modules)])
        if session_observation is not None:
            lines.extend(
                [
                    "",
                    "## OPENCODE SESSION OBSERVATION",
                    f"- session: {session_observation.session_id}",
                    f"- context: {self._session_context(session_observation)} / "
                    f"{session_observation.context_limit}",
                    f"- source: {session_observation.source_quality.value} "
                    f"({session_observation.source_description})",
                ]
            )
        lines.extend(
            [
                "",
                "## VALIDATED EVIDENCE",
                *self._items_or_absence(evidence, "No validated evidence was supplied."),
                "",
                "## OPEN BLOCKERS / UNCERTAINTY",
                *self._items_or_absence(
                    uncertainty,
                    "No uncertainty was supplied; do not assume missing facts are settled.",
                ),
                "",
                "## NEXT ACTION",
                f"- {next_action}",
                "",
                "## DO NOT DO",
                *self._items_or_absence(do_not_do, "No constraints were supplied."),
                "",
                "## CHECKPOINT",
                f"- repo: {checkpoint.root}",
                f"- branch: {checkpoint.branch}",
                f"- HEAD: {checkpoint.head}",
                f"- generated_at: {generated_at}",
                "- source_scope: explicit CLI task/session input; live Git metadata; "
                "caller-selected existing repository files",
                f"- unverified_items: {len(uncertainty)} caller-supplied item(s), listed above",
                "",
            ]
        )
        rendered = "\n".join(lines)
        if len(rendered) > _MAX_RENDERED_CHARS:
            raise OpencodeHandoffError(
                "Handoff exceeds the 7,000-character budget; provide fewer concise verified facts."
            )
        return rendered

    def _resolve_files(
        self, checkpoint: HandoffRepositoryCheckpoint, values: tuple[str, ...]
    ) -> tuple[str, ...]:
        resolved = tuple(self._repository.resolve_file(checkpoint, value) for value in values)
        return self._deduplicate(resolved)

    @staticmethod
    def _worktree_state(entries: int) -> str:
        return "clean" if entries == 0 else f"dirty ({entries} entry(s); details omitted)"

    def _utc_timestamp(self) -> str:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise OpencodeHandoffError("Clock must return a timezone-aware timestamp.")
        return value.astimezone(UTC).isoformat()

    @staticmethod
    def _normalize_session_observation(
        observation: HandoffSessionObservation | None,
    ) -> HandoffSessionObservation | None:
        if observation is None:
            return None
        if not observation.session_id.strip():
            raise OpencodeHandoffError("Observed OpenCode session ID must not be blank.")
        if observation.current_tokens < 0:
            raise OpencodeHandoffError("Observed context tokens must not be negative.")
        if observation.context_limit <= 0:
            raise OpencodeHandoffError("Observed context limit must be positive.")
        source_description = OpencodeHandoffService._normalize(
            "observed context source", observation.source_description
        )
        if not source_description:
            raise OpencodeHandoffError("Observed context source must not be blank.")
        return HandoffSessionObservation(
            session_id=observation.session_id.strip(),
            current_tokens=observation.current_tokens,
            context_limit=observation.context_limit,
            source_quality=observation.source_quality,
            source_description=source_description,
        )

    @staticmethod
    def _session_context(observation: HandoffSessionObservation) -> str:
        prefix = "~" if observation.source_quality is ContextSourceQuality.ESTIMATED else ""
        return f"{prefix}{observation.current_tokens}"

    @classmethod
    def _normalize_required(cls, label: str, value: str) -> str:
        normalized = cls._normalize(label, value)
        if not normalized:
            raise OpencodeHandoffError(f"{label.title()} must not be blank.")
        return normalized

    @classmethod
    def _normalize_items(cls, label: str, values: tuple[str, ...]) -> tuple[str, ...]:
        return cls._deduplicate(
            tuple(normalized for value in values if (normalized := cls._normalize(label, value)))
        )

    @staticmethod
    def _deduplicate(values: tuple[str, ...]) -> tuple[str, ...]:
        seen: set[str] = set()
        unique: list[str] = []
        for value in values:
            key = value.casefold()
            if key not in seen:
                seen.add(key)
                unique.append(value)
        return tuple(unique)

    @staticmethod
    def _normalize(label: str, value: str) -> str:
        normalized = " ".join(unicodedata.normalize("NFC", value).split())
        if not normalized:
            return ""
        if len(normalized) > _MAX_ITEM_CHARS:
            raise OpencodeHandoffError(
                f"{label.title()} must be at most {_MAX_ITEM_CHARS} characters; "
                "provide a concise fact, not raw logs."
            )
        if _SECRET_PATTERN.search(normalized) is not None:
            raise OpencodeHandoffError(
                f"{label.title()} appears to contain a secret and was omitted."
            )
        return normalized

    @staticmethod
    def _items_or_absence(values: tuple[str, ...], absence: str) -> tuple[str, ...]:
        return tuple(f"- {value}" for value in values) or (f"- {absence}",)

    @staticmethod
    def _indented_items(values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(f"  - {value}" for value in values)

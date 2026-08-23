"""Read-only, authority-aware context preparation for planner assessments."""

from __future__ import annotations

import unicodedata
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from neural_engine.ports.planner_context_readers import (
    BrainKnowledgeReader,
    CurrentDocumentReader,
    HistoricalEvidenceReader,
    RepositoryMetadataReader,
    ReviewEvidenceReader,
)

CURRENT_DOCUMENTS = (
    "AGENTS.md",
    "VISION.md",
    "CONTEXT.md",
    "README.md",
    "ABOUT.md",
    "docs/architecture.md",
    "docs/conventions.md",
    "docs/roadmap.md",
    "docs/product/prd-authority-aware-planner-context-package.md",
)
REVIEW_ARTIFACTS = (
    ".agent-work/reviews/review-prd-authority-aware-planner-context-package.md",
    ".agent-work/reviews/review-revise-prd-operator-time-metric.md",
    ".agent-work/reviews/independent-product-rereview-authority-aware-planner-context-package.md",
)


class PlannerContextError(Exception):
    """Base bounded application error for impossible package assembly."""


class PlannerCheckpointMismatchError(PlannerContextError):
    """A reader could not establish the caller-supplied live checkpoint."""


class EvidenceState(StrEnum):
    CURRENT = "CURRENT"
    HISTORICAL = "HISTORICAL"
    FROZEN_RELEASE_EVIDENCE = "FROZEN_RELEASE_EVIDENCE"
    STALE = "STALE"
    CONFLICTING = "CONFLICTING"
    MISSING = "MISSING"
    UNREADABLE = "UNREADABLE"
    AMBIGUOUS = "AMBIGUOUS"


class SourceType(StrEnum):
    REPOSITORY_METADATA = "repository metadata"
    DESIGNATED_DOCUMENT = "designated document"
    DESIGNATED_REVIEW = "designated review"
    BRAIN_KNOWLEDGE = "Brain Knowledge"
    HISTORICAL_EVIDENCE = "historical/frozen evidence"


class PlannerRepositoryCheckpoint(BaseModel):
    """Caller-captured repository fact which must be reverified by the adapter."""

    model_config = ConfigDict(frozen=True)

    repository_root: str
    repository_identity: str
    branch: str
    head: str
    authoritative_remote_ref: str
    worktree_state: str
    verified_at: datetime

    @field_validator(
        "repository_root",
        "repository_identity",
        "branch",
        "head",
        "authoritative_remote_ref",
        "worktree_state",
    )
    @classmethod
    def _required_normalized(cls, value: str) -> str:
        normalized = unicodedata.normalize("NFC", value).strip()
        if not normalized:
            raise ValueError("Checkpoint fields must be non-blank.")
        return normalized

    @field_validator("verified_at")
    @classmethod
    def _aware_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Checkpoint verification timestamp must be timezone-aware.")
        return value.astimezone(UTC)


class HistoricalEvidenceInput(BaseModel):
    """Caller-supplied bounded historical or frozen-release evidence, never a path."""

    model_config = ConfigDict(frozen=True)

    locator: str
    stable_identity: str
    content: str
    evidence_state: EvidenceState
    checkpoint_or_version: str
    authority_class: str = "historical supporting evidence"

    @field_validator("locator", "stable_identity", "content", "checkpoint_or_version")
    @classmethod
    def _non_blank(cls, value: str) -> str:
        normalized = unicodedata.normalize("NFC", value).strip()
        if not normalized:
            raise ValueError("Historical evidence fields must be non-blank.")
        return normalized

    @field_validator("evidence_state")
    @classmethod
    def _historical_state(cls, value: EvidenceState) -> EvidenceState:
        if value not in {EvidenceState.HISTORICAL, EvidenceState.FROZEN_RELEASE_EVIDENCE}:
            raise ValueError("Historical evidence must be HISTORICAL or FROZEN_RELEASE_EVIDENCE.")
        return value


class PlannerSourceFilters(BaseModel):
    """Optional selectors which may only narrow the fixed approved inventory."""

    model_config = ConfigDict(frozen=True)

    current_documents: tuple[str, ...] | None = None
    review_artifacts: tuple[str, ...] | None = None
    knowledge_ids: tuple[UUID, ...] = ()
    historical_evidence: tuple[HistoricalEvidenceInput, ...] = ()

    @field_validator("current_documents", "review_artifacts")
    @classmethod
    def _approved_subset(
        cls, values: tuple[str, ...] | None, info: object
    ) -> tuple[str, ...] | None:
        if values is None:
            return values
        allowed = (
            CURRENT_DOCUMENTS
            if getattr(info, "field_name", "") == "current_documents"
            else REVIEW_ARTIFACTS
        )
        normalized = tuple(unicodedata.normalize("NFC", value) for value in values)
        if len(set(normalized)) != len(normalized) or any(
            value not in allowed for value in normalized
        ):
            raise ValueError(
                "Source filters may only select a unique subset of the approved inventory."
            )
        return normalized

    @model_validator(mode="after")
    def _bounded_source_count(self) -> PlannerSourceFilters:
        selected_documents = len(
            CURRENT_DOCUMENTS if self.current_documents is None else self.current_documents
        )
        selected_reviews = len(
            REVIEW_ARTIFACTS if self.review_artifacts is None else self.review_artifacts
        )
        if (
            selected_documents
            + selected_reviews
            + len(self.knowledge_ids)
            + len(self.historical_evidence)
            > 24
        ):
            raise ValueError("At most 24 non-metadata sources may be selected.")
        return self


class PlannerContextRequest(BaseModel):
    """Validated immutable request; its task statement is data and is never executed."""

    model_config = ConfigDict(frozen=True)

    project_key: str
    task_statement: str
    verified_repository_checkpoint: PlannerRepositoryCheckpoint
    optional_source_filters: PlannerSourceFilters | None = None

    @field_validator("project_key", "task_statement")
    @classmethod
    def _normalized_required(cls, value: str) -> str:
        normalized = unicodedata.normalize("NFC", value).strip()
        if not normalized:
            raise ValueError("Project key and task statement must be non-blank.")
        return normalized


class SourceEvidence(BaseModel):
    """One immutable, bounded source result or visible diagnostic."""

    model_config = ConfigDict(frozen=True)

    source_type: SourceType
    normalized_locator: str
    stable_identity: str
    external_project_context: str
    authority_class: str
    evidence_state: EvidenceState
    retrieved_at: datetime
    extraction_start: int = 0
    extraction_boundary: str = "whole selected record"
    checkpoint_or_version: str | None = None
    excerpt: str | None = None
    content_sha256: str | None = None
    diagnostic: str | None = None
    asserted_subject_key: str | None = None

    @field_validator("normalized_locator", "stable_identity", "external_project_context")
    @classmethod
    def _evidence_required(cls, value: str) -> str:
        normalized = unicodedata.normalize("NFC", value).strip()
        if not normalized:
            raise ValueError("Evidence identity and locator fields must be non-blank.")
        return normalized

    @field_validator("retrieved_at")
    @classmethod
    def _retrieved_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Evidence retrieval time must be timezone-aware.")
        return value.astimezone(UTC)

    @field_validator("extraction_start")
    @classmethod
    def _non_negative_start(cls, value: int) -> int:
        if value < 0:
            raise ValueError("Extraction start must not be negative.")
        return value

    @model_validator(mode="after")
    def _bounded_excerpt(self) -> SourceEvidence:
        if self.excerpt is not None and (
            len(self.excerpt.encode("utf-8")) > 4096 or self.excerpt.count("\n") + 1 > 120
        ):
            raise ValueError("Evidence excerpts must be bounded to 120 lines and 4096 bytes.")
        if self.evidence_state is EvidenceState.UNREADABLE and self.excerpt is not None:
            raise ValueError("Unreadable evidence must not contain an excerpt.")
        return self


class PlannerContextPackage(BaseModel):
    """The exact seven-category, non-persisted planner context response."""

    model_config = ConfigDict(frozen=True)

    current_authoritative_sources: tuple[SourceEvidence, ...] = ()
    supporting_brain_knowledge: tuple[SourceEvidence, ...] = ()
    historical_evidence: tuple[SourceEvidence, ...] = ()
    stale_or_conflicting_sources: tuple[SourceEvidence, ...] = ()
    missing_evidence: tuple[SourceEvidence, ...] = ()
    unreadable_or_inaccessible_sources: tuple[SourceEvidence, ...] = ()
    provenance: tuple[SourceEvidence, ...] = ()
    warnings: tuple[str, ...] = ()


class PlannerContextService:
    """Coordinate five reader-only ports without deciding or authorizing a plan."""

    def __init__(
        self,
        repository_metadata_reader: RepositoryMetadataReader,
        current_document_reader: CurrentDocumentReader,
        brain_knowledge_reader: BrainKnowledgeReader,
        review_evidence_reader: ReviewEvidenceReader,
        historical_evidence_reader: HistoricalEvidenceReader,
    ) -> None:
        self._repository_metadata_reader = repository_metadata_reader
        self._current_document_reader = current_document_reader
        self._brain_knowledge_reader = brain_knowledge_reader
        self._review_evidence_reader = review_evidence_reader
        self._historical_evidence_reader = historical_evidence_reader

    def prepare(self, request: PlannerContextRequest) -> PlannerContextPackage:
        filters = request.optional_source_filters or PlannerSourceFilters()
        checkpoint = request.verified_repository_checkpoint
        before = self._repository_metadata_reader.verify(checkpoint)
        current_documents = self._current_document_reader.read_current_documents(
            checkpoint,
            CURRENT_DOCUMENTS if filters.current_documents is None else filters.current_documents,
        )
        reviews = self._review_evidence_reader.read_review_evidence(
            checkpoint,
            REVIEW_ARTIFACTS if filters.review_artifacts is None else filters.review_artifacts,
        )
        after = self._repository_metadata_reader.verify(checkpoint)
        knowledge = self._brain_knowledge_reader.read_knowledge(
            request.project_key, filters.knowledge_ids
        )
        historical = self._historical_evidence_reader.read_historical_evidence(
            filters.historical_evidence
        )
        checkpoint_valid = (
            before.evidence_state is EvidenceState.CURRENT
            and after.evidence_state is EvidenceState.CURRENT
        )
        all_items = (*knowledge, *historical)
        warnings: list[str] = []
        if checkpoint_valid:
            all_items = (before, *current_documents, *reviews, after, *all_items)
        else:
            warnings.append(
                "verified repository checkpoint did not match before and after current-source reads"
            )
            all_items = (
                *all_items,
                self._checkpoint_invalidated(before),
                self._checkpoint_invalidated(after),
            )
        return self._assemble(all_items, warnings)

    @staticmethod
    def _checkpoint_invalidated(item: SourceEvidence) -> SourceEvidence:
        if item.evidence_state is not EvidenceState.CURRENT:
            return item
        return item.model_copy(
            update={
                "authority_class": "checkpoint-invalidated repository metadata",
                "evidence_state": EvidenceState.STALE,
                "diagnostic": "repository checkpoint changed during current-source reads",
            }
        )

    @staticmethod
    def _sort_key(item: SourceEvidence) -> tuple[int, str, str, int, str]:
        rank = {
            SourceType.REPOSITORY_METADATA: 10,
            SourceType.DESIGNATED_DOCUMENT: 20,
            SourceType.DESIGNATED_REVIEW: 30,
            SourceType.BRAIN_KNOWLEDGE: 40,
            SourceType.HISTORICAL_EVIDENCE: 50,
        }[item.source_type]
        return (
            rank,
            item.normalized_locator,
            item.stable_identity,
            item.extraction_start,
            item.content_sha256 or item.stable_identity,
        )

    def _assemble(
        self, items: tuple[SourceEvidence, ...], warnings: list[str]
    ) -> PlannerContextPackage:
        unique = {
            (
                item.source_type,
                item.normalized_locator,
                item.stable_identity,
                item.extraction_start,
            ): item
            for item in items
        }
        ordered = tuple(sorted(unique.values(), key=self._sort_key))
        current: list[SourceEvidence] = []
        knowledge: list[SourceEvidence] = []
        historical: list[SourceEvidence] = []
        stale: list[SourceEvidence] = []
        missing: list[SourceEvidence] = []
        unreadable: list[SourceEvidence] = []
        for item in ordered:
            if item.evidence_state in {EvidenceState.STALE, EvidenceState.CONFLICTING}:
                stale.append(item)
            elif item.evidence_state in {EvidenceState.MISSING, EvidenceState.AMBIGUOUS}:
                missing.append(item)
            elif item.evidence_state is EvidenceState.UNREADABLE:
                unreadable.append(item)
            elif item.source_type is SourceType.BRAIN_KNOWLEDGE:
                knowledge.append(item)
            elif item.source_type is SourceType.HISTORICAL_EVIDENCE:
                historical.append(item)
            elif item.evidence_state is EvidenceState.CURRENT:
                current.append(item)
        return PlannerContextPackage(
            current_authoritative_sources=tuple(current),
            supporting_brain_knowledge=tuple(knowledge),
            historical_evidence=tuple(historical),
            stale_or_conflicting_sources=tuple(stale),
            missing_evidence=tuple(missing),
            unreadable_or_inaccessible_sources=tuple(unreadable),
            provenance=ordered,
            warnings=tuple(sorted(set(warnings))),
        )


def content_sha256(content: str) -> str:
    """Return the stable content identity used by local reader adapters."""
    return sha256(content.encode("utf-8")).hexdigest()

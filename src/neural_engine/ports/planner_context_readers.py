"""Narrow read-only boundaries for planner context preparation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol
from uuid import UUID

if TYPE_CHECKING:
    from neural_engine.application.planner_context_service import (
        HistoricalEvidenceInput,
        PlannerRepositoryCheckpoint,
        SourceEvidence,
    )


class RepositoryMetadataReader(Protocol):
    """Verify one caller-captured repository checkpoint without mutation."""

    def verify(self, checkpoint: PlannerRepositoryCheckpoint) -> SourceEvidence: ...


class CurrentDocumentReader(Protocol):
    """Read only designated current documents from one verified root."""

    def read_current_documents(
        self, checkpoint: PlannerRepositoryCheckpoint, locators: tuple[str, ...]
    ) -> tuple[SourceEvidence, ...]: ...


class BrainKnowledgeReader(Protocol):
    """Read explicitly selected Knowledge records only."""

    def read_knowledge(
        self, project_key: str, knowledge_ids: tuple[UUID, ...]
    ) -> tuple[SourceEvidence, ...]: ...


class ReviewEvidenceReader(Protocol):
    """Read only designated review artifacts from one verified root."""

    def read_review_evidence(
        self, checkpoint: PlannerRepositoryCheckpoint, locators: tuple[str, ...]
    ) -> tuple[SourceEvidence, ...]: ...


class HistoricalEvidenceReader(Protocol):
    """Convert caller-supplied, already bounded historical evidence."""

    def read_historical_evidence(
        self, evidence: tuple[HistoricalEvidenceInput, ...]
    ) -> tuple[SourceEvidence, ...]: ...

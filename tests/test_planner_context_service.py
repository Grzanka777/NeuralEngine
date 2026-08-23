from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from neural_engine.application.planner_context_service import (
    EvidenceState,
    HistoricalEvidenceInput,
    PlannerContextPackage,
    PlannerContextRequest,
    PlannerContextService,
    PlannerRepositoryCheckpoint,
    PlannerSourceFilters,
    SourceEvidence,
    SourceType,
)
from neural_engine.core.paths import NeuralPaths
from neural_engine.domain.knowledge import Knowledge, KnowledgeConfidence
from neural_engine.infrastructure.local_planner_context_readers import LocalPlannerContextReaders

NOW = datetime(2026, 8, 6, tzinfo=UTC)
KNOWLEDGE_ID = UUID("00000000-0000-0000-0000-000000000001")


@dataclass(frozen=True)
class ExpectedEvidence:
    locator: str
    source_type: SourceType
    evidence_state: EvidenceState
    has_diagnostic: bool


@dataclass(frozen=True)
class FixtureExpectation:
    fixture_id: str
    extra_state: EvidenceState | None
    expected_categories: tuple[tuple[str, tuple[str, ...]], ...]
    expected_provenance: tuple[ExpectedEvidence, ...]
    expected_partial_result: bool


_BASE_PROVENANCE = (
    ExpectedEvidence("repository", SourceType.REPOSITORY_METADATA, EvidenceState.CURRENT, False),
    ExpectedEvidence("README.md", SourceType.DESIGNATED_DOCUMENT, EvidenceState.CURRENT, False),
    ExpectedEvidence(
        ".agent-work/reviews/review-prd-authority-aware-planner-context-package.md",
        SourceType.DESIGNATED_REVIEW,
        EvidenceState.CURRENT,
        False,
    ),
    ExpectedEvidence(
        f"brain/{KNOWLEDGE_ID}", SourceType.BRAIN_KNOWLEDGE, EvidenceState.HISTORICAL, True
    ),
    ExpectedEvidence(
        "release/v1.0.0",
        SourceType.HISTORICAL_EVIDENCE,
        EvidenceState.FROZEN_RELEASE_EVIDENCE,
        True,
    ),
)


def _categories(
    *,
    stale: tuple[str, ...] = (),
    missing: tuple[str, ...] = (),
    unreadable: tuple[str, ...] = (),
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    return (
        (
            "current_authoritative_sources",
            (
                "repository",
                "README.md",
                ".agent-work/reviews/review-prd-authority-aware-planner-context-package.md",
            ),
        ),
        ("supporting_brain_knowledge", (f"brain/{KNOWLEDGE_ID}",)),
        ("historical_evidence", ("release/v1.0.0",)),
        ("stale_or_conflicting_sources", stale),
        ("missing_evidence", missing),
        ("unreadable_or_inaccessible_sources", unreadable),
    )


FIXTURE_EXPECTATIONS = (
    FixtureExpectation(
        "literal-clean-current-plus-knowledge", None, _categories(), _BASE_PROVENANCE, False
    ),
    FixtureExpectation(
        "literal-historical-and-frozen", None, _categories(), _BASE_PROVENANCE, False
    ),
    FixtureExpectation(
        "literal-stale-knowledge",
        EvidenceState.STALE,
        _categories(stale=("stale-knowledge",)),
        (
            *_BASE_PROVENANCE[:4],
            ExpectedEvidence(
                "stale-knowledge", SourceType.BRAIN_KNOWLEDGE, EvidenceState.STALE, True
            ),
            _BASE_PROVENANCE[4],
        ),
        True,
    ),
    FixtureExpectation(
        "literal-conflicting-source",
        EvidenceState.CONFLICTING,
        _categories(stale=("conflicting-source",)),
        (
            *_BASE_PROVENANCE[:4],
            ExpectedEvidence(
                "conflicting-source", SourceType.BRAIN_KNOWLEDGE, EvidenceState.CONFLICTING, True
            ),
            _BASE_PROVENANCE[4],
        ),
        True,
    ),
    FixtureExpectation(
        "literal-missing-source",
        EvidenceState.MISSING,
        _categories(missing=("missing-document",)),
        (
            *_BASE_PROVENANCE[:4],
            ExpectedEvidence(
                "missing-document", SourceType.BRAIN_KNOWLEDGE, EvidenceState.MISSING, True
            ),
            _BASE_PROVENANCE[4],
        ),
        True,
    ),
    FixtureExpectation(
        "literal-unreadable-source",
        EvidenceState.UNREADABLE,
        _categories(unreadable=("corrupt-knowledge",)),
        (
            *_BASE_PROVENANCE[:4],
            ExpectedEvidence(
                "corrupt-knowledge", SourceType.BRAIN_KNOWLEDGE, EvidenceState.UNREADABLE, True
            ),
            _BASE_PROVENANCE[4],
        ),
        True,
    ),
    FixtureExpectation(
        "literal-ambiguous-source",
        EvidenceState.AMBIGUOUS,
        _categories(missing=("explicit-empty-result",)),
        (
            *_BASE_PROVENANCE[:4],
            ExpectedEvidence(
                "explicit-empty-result", SourceType.BRAIN_KNOWLEDGE, EvidenceState.AMBIGUOUS, True
            ),
            _BASE_PROVENANCE[4],
        ),
        True,
    ),
    FixtureExpectation("literal-restrictive-filter", None, _categories(), _BASE_PROVENANCE, False),
    FixtureExpectation(
        "literal-binary-state",
        EvidenceState.UNREADABLE,
        _categories(unreadable=("binary-source",)),
        (
            *_BASE_PROVENANCE[:3],
            ExpectedEvidence(
                "binary-source", SourceType.BRAIN_KNOWLEDGE, EvidenceState.UNREADABLE, True
            ),
            *_BASE_PROVENANCE[3:],
        ),
        True,
    ),
    FixtureExpectation(
        "literal-oversize-state",
        EvidenceState.UNREADABLE,
        _categories(unreadable=("oversize-source",)),
        (
            *_BASE_PROVENANCE[:4],
            ExpectedEvidence(
                "oversize-source", SourceType.BRAIN_KNOWLEDGE, EvidenceState.UNREADABLE, True
            ),
            _BASE_PROVENANCE[4],
        ),
        True,
    ),
    FixtureExpectation(
        "literal-checkpoint-state",
        EvidenceState.STALE,
        _categories(stale=("checkpoint-race",)),
        (
            *_BASE_PROVENANCE[:4],
            ExpectedEvidence(
                "checkpoint-race", SourceType.BRAIN_KNOWLEDGE, EvidenceState.STALE, True
            ),
            _BASE_PROVENANCE[4],
        ),
        True,
    ),
    FixtureExpectation(
        "literal-secret-state",
        EvidenceState.UNREADABLE,
        _categories(unreadable=("secret-guard",)),
        (
            *_BASE_PROVENANCE[:4],
            ExpectedEvidence(
                "secret-guard", SourceType.BRAIN_KNOWLEDGE, EvidenceState.UNREADABLE, True
            ),
            _BASE_PROVENANCE[4],
        ),
        True,
    ),
)


def _checkpoint(root: str = "/tmp/repository") -> PlannerRepositoryCheckpoint:
    return PlannerRepositoryCheckpoint(
        repository_root=root,
        repository_identity="NeuralEngine",
        branch="main",
        head="a" * 40,
        authoritative_remote_ref="a" * 40,
        worktree_state="clean",
        verified_at=NOW,
    )


def _item(source_type: SourceType, state: EvidenceState, locator: str) -> SourceEvidence:
    return SourceEvidence(
        source_type=source_type,
        normalized_locator=locator,
        stable_identity=f"id:{locator}",
        external_project_context="NeuralEngine",
        authority_class="fixture authority",
        evidence_state=state,
        retrieved_at=NOW,
        checkpoint_or_version="a" * 40,
        excerpt=None if state is EvidenceState.UNREADABLE else "fixture excerpt",
        diagnostic="fixture diagnostic" if state is not EvidenceState.CURRENT else None,
    )


class FixtureReaders:
    def __init__(self, extra: tuple[SourceEvidence, ...] = ()) -> None:
        self.extra = extra

    def verify(self, checkpoint: PlannerRepositoryCheckpoint) -> SourceEvidence:
        return _item(SourceType.REPOSITORY_METADATA, EvidenceState.CURRENT, "repository")

    def read_current_documents(
        self, checkpoint: PlannerRepositoryCheckpoint, locators: tuple[str, ...]
    ) -> tuple[SourceEvidence, ...]:
        return tuple(
            _item(SourceType.DESIGNATED_DOCUMENT, EvidenceState.CURRENT, item) for item in locators
        )

    def read_review_evidence(
        self, checkpoint: PlannerRepositoryCheckpoint, locators: tuple[str, ...]
    ) -> tuple[SourceEvidence, ...]:
        return tuple(
            _item(SourceType.DESIGNATED_REVIEW, EvidenceState.CURRENT, item) for item in locators
        )

    def read_knowledge(
        self, project_key: str, knowledge_ids: tuple[UUID, ...]
    ) -> tuple[SourceEvidence, ...]:
        return (
            tuple(
                _item(SourceType.BRAIN_KNOWLEDGE, EvidenceState.HISTORICAL, f"brain/{item}")
                for item in knowledge_ids
            )
            + self.extra
        )

    def read_historical_evidence(
        self, evidence: tuple[HistoricalEvidenceInput, ...]
    ) -> tuple[SourceEvidence, ...]:
        return tuple(
            _item(SourceType.HISTORICAL_EVIDENCE, item.evidence_state, item.locator)
            for item in evidence
        )


class SequencedFixtureReaders(FixtureReaders):
    def __init__(
        self,
        metadata: tuple[SourceEvidence, SourceEvidence],
        extra: tuple[SourceEvidence, ...] = (),
    ) -> None:
        super().__init__(extra)
        self._metadata = metadata
        self._index = 0

    def verify(self, checkpoint: PlannerRepositoryCheckpoint) -> SourceEvidence:
        result = self._metadata[self._index % len(self._metadata)]
        self._index += 1
        return result


@dataclass(frozen=True)
class RepresentativeEvidenceExpectation:
    source_type: SourceType
    state: EvidenceState
    authority: str
    locator: str
    stable_identity: str
    diagnostic: str | None


@dataclass(frozen=True)
class RepresentativeExpectation:
    fixture_id: str
    category: str
    source_type: SourceType
    state: EvidenceState
    authority: str
    locator: str
    stable_identity: str
    diagnostic: str | None
    warnings: tuple[str, ...] = ()
    partial_result: bool = False
    category_locators: tuple[tuple[str, tuple[str, ...]], ...] = ()
    provenance: tuple[RepresentativeEvidenceExpectation, ...] = ()


def _literal_categories(
    *,
    current: tuple[str, ...] = (),
    knowledge: tuple[str, ...] = (),
    historical: tuple[str, ...] = (),
    stale: tuple[str, ...] = (),
    missing: tuple[str, ...] = (),
    unreadable: tuple[str, ...] = (),
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    return (
        ("current_authoritative_sources", current),
        ("supporting_brain_knowledge", knowledge),
        ("historical_evidence", historical),
        ("stale_or_conflicting_sources", stale),
        ("missing_evidence", missing),
        ("unreadable_or_inaccessible_sources", unreadable),
    )


_REPRESENTATIVE_METADATA = RepresentativeEvidenceExpectation(
    SourceType.REPOSITORY_METADATA,
    EvidenceState.CURRENT,
    "fixture authority",
    "repository",
    "id:repository",
    None,
)


REPRESENTATIVE_EXPECTATIONS = (
    RepresentativeExpectation(
        "clean-current-plus-knowledge",
        "supporting_brain_knowledge",
        SourceType.BRAIN_KNOWLEDGE,
        EvidenceState.HISTORICAL,
        "caller-selected supporting Knowledge",
        f"brain/knowledge/{KNOWLEDGE_ID}.json",
        str(KNOWLEDGE_ID),
        "relevance is caller-selected",
        category_locators=_literal_categories(
            current=("repository",), knowledge=(f"brain/knowledge/{KNOWLEDGE_ID}.json",)
        ),
        provenance=(
            _REPRESENTATIVE_METADATA,
            RepresentativeEvidenceExpectation(
                SourceType.BRAIN_KNOWLEDGE,
                EvidenceState.HISTORICAL,
                "caller-selected supporting Knowledge",
                f"brain/knowledge/{KNOWLEDGE_ID}.json",
                str(KNOWLEDGE_ID),
                "relevance is caller-selected",
            ),
        ),
    ),
    RepresentativeExpectation(
        "historical-and-frozen",
        "historical_evidence",
        SourceType.HISTORICAL_EVIDENCE,
        EvidenceState.FROZEN_RELEASE_EVIDENCE,
        "historical supporting evidence",
        "release/v1.0.0",
        "v1.0.0",
        None,
        category_locators=_literal_categories(
            current=("repository",), historical=("release/v1.0.0",)
        ),
        provenance=(
            _REPRESENTATIVE_METADATA,
            RepresentativeEvidenceExpectation(
                SourceType.HISTORICAL_EVIDENCE,
                EvidenceState.FROZEN_RELEASE_EVIDENCE,
                "historical supporting evidence",
                "release/v1.0.0",
                "v1.0.0",
                None,
            ),
        ),
    ),
    RepresentativeExpectation(
        "stale-knowledge",
        "stale_or_conflicting_sources",
        SourceType.BRAIN_KNOWLEDGE,
        EvidenceState.STALE,
        "fixture authority",
        "knowledge/stale",
        "id:knowledge/stale",
        "fixture diagnostic",
        partial_result=True,
        category_locators=_literal_categories(current=("repository",), stale=("knowledge/stale",)),
        provenance=(
            _REPRESENTATIVE_METADATA,
            RepresentativeEvidenceExpectation(
                SourceType.BRAIN_KNOWLEDGE,
                EvidenceState.STALE,
                "fixture authority",
                "knowledge/stale",
                "id:knowledge/stale",
                "fixture diagnostic",
            ),
        ),
    ),
    RepresentativeExpectation(
        "conflicting-evidence",
        "stale_or_conflicting_sources",
        SourceType.HISTORICAL_EVIDENCE,
        EvidenceState.CONFLICTING,
        "fixture authority",
        "history/conflict",
        "id:history/conflict",
        "fixture diagnostic",
        partial_result=True,
        category_locators=_literal_categories(current=("repository",), stale=("history/conflict",)),
        provenance=(
            _REPRESENTATIVE_METADATA,
            RepresentativeEvidenceExpectation(
                SourceType.HISTORICAL_EVIDENCE,
                EvidenceState.CONFLICTING,
                "fixture authority",
                "history/conflict",
                "id:history/conflict",
                "fixture diagnostic",
            ),
        ),
    ),
    RepresentativeExpectation(
        "missing-document",
        "missing_evidence",
        SourceType.DESIGNATED_DOCUMENT,
        EvidenceState.MISSING,
        "no authority established",
        "README.md",
        "a" * 40,
        "designated source is missing",
        partial_result=True,
        category_locators=_literal_categories(current=("repository",), missing=("README.md",)),
        provenance=(
            _REPRESENTATIVE_METADATA,
            RepresentativeEvidenceExpectation(
                SourceType.DESIGNATED_DOCUMENT,
                EvidenceState.MISSING,
                "no authority established",
                "README.md",
                "a" * 40,
                "designated source is missing",
            ),
        ),
    ),
    RepresentativeExpectation(
        "corrupt-knowledge",
        "unreadable_or_inaccessible_sources",
        SourceType.BRAIN_KNOWLEDGE,
        EvidenceState.UNREADABLE,
        "no authority established",
        f"brain/knowledge/{KNOWLEDGE_ID}.json",
        str(KNOWLEDGE_ID),
        "selected Knowledge is malformed or unreadable",
        partial_result=True,
        category_locators=_literal_categories(
            current=("repository",), unreadable=(f"brain/knowledge/{KNOWLEDGE_ID}.json",)
        ),
        provenance=(
            _REPRESENTATIVE_METADATA,
            RepresentativeEvidenceExpectation(
                SourceType.BRAIN_KNOWLEDGE,
                EvidenceState.UNREADABLE,
                "no authority established",
                f"brain/knowledge/{KNOWLEDGE_ID}.json",
                str(KNOWLEDGE_ID),
                "selected Knowledge is malformed or unreadable",
            ),
        ),
    ),
    RepresentativeExpectation(
        "explicit-empty-result",
        "missing_evidence",
        SourceType.HISTORICAL_EVIDENCE,
        EvidenceState.AMBIGUOUS,
        "fixture authority",
        "history/empty",
        "id:history/empty",
        "fixture diagnostic",
        partial_result=True,
        category_locators=_literal_categories(current=("repository",), missing=("history/empty",)),
        provenance=(
            _REPRESENTATIVE_METADATA,
            RepresentativeEvidenceExpectation(
                SourceType.HISTORICAL_EVIDENCE,
                EvidenceState.AMBIGUOUS,
                "fixture authority",
                "history/empty",
                "id:history/empty",
                "fixture diagnostic",
            ),
        ),
    ),
    RepresentativeExpectation(
        "restrictive-filter",
        "current_authoritative_sources",
        SourceType.DESIGNATED_DOCUMENT,
        EvidenceState.CURRENT,
        "verified current repository source",
        "README.md",
        "a" * 40 + ":README.md",
        None,
        category_locators=_literal_categories(current=("repository", "README.md")),
        provenance=(
            _REPRESENTATIVE_METADATA,
            RepresentativeEvidenceExpectation(
                SourceType.DESIGNATED_DOCUMENT,
                EvidenceState.CURRENT,
                "verified current repository source",
                "README.md",
                "a" * 40 + ":README.md",
                None,
            ),
        ),
    ),
    RepresentativeExpectation(
        "binary-source",
        "unreadable_or_inaccessible_sources",
        SourceType.DESIGNATED_DOCUMENT,
        EvidenceState.UNREADABLE,
        "no authority established",
        "README.md",
        "a" * 40,
        "source cannot be read as UTF-8",
        partial_result=True,
        category_locators=_literal_categories(current=("repository",), unreadable=("README.md",)),
        provenance=(
            _REPRESENTATIVE_METADATA,
            RepresentativeEvidenceExpectation(
                SourceType.DESIGNATED_DOCUMENT,
                EvidenceState.UNREADABLE,
                "no authority established",
                "README.md",
                "a" * 40,
                "source cannot be read as UTF-8",
            ),
        ),
    ),
    RepresentativeExpectation(
        "oversize-source",
        "unreadable_or_inaccessible_sources",
        SourceType.DESIGNATED_DOCUMENT,
        EvidenceState.UNREADABLE,
        "no authority established",
        "README.md",
        "a" * 40,
        "source is not a readable regular UTF-8 file within 64 KiB",
        partial_result=True,
        category_locators=_literal_categories(current=("repository",), unreadable=("README.md",)),
        provenance=(
            _REPRESENTATIVE_METADATA,
            RepresentativeEvidenceExpectation(
                SourceType.DESIGNATED_DOCUMENT,
                EvidenceState.UNREADABLE,
                "no authority established",
                "README.md",
                "a" * 40,
                "source is not a readable regular UTF-8 file within 64 KiB",
            ),
        ),
    ),
    RepresentativeExpectation(
        "checkpoint-race",
        "stale_or_conflicting_sources",
        SourceType.REPOSITORY_METADATA,
        EvidenceState.STALE,
        "fixture authority",
        "repository-after",
        "id:repository-after",
        "fixture diagnostic",
        ("verified repository checkpoint did not match before and after current-source reads",),
        True,
        category_locators=_literal_categories(stale=("repository-after", "repository-before")),
        provenance=(
            RepresentativeEvidenceExpectation(
                SourceType.REPOSITORY_METADATA,
                EvidenceState.STALE,
                "fixture authority",
                "repository-after",
                "id:repository-after",
                "fixture diagnostic",
            ),
            RepresentativeEvidenceExpectation(
                SourceType.REPOSITORY_METADATA,
                EvidenceState.STALE,
                "checkpoint-invalidated repository metadata",
                "repository-before",
                "id:repository-before",
                "repository checkpoint changed during current-source reads",
            ),
        ),
    ),
    RepresentativeExpectation(
        "secret-guard",
        "unreadable_or_inaccessible_sources",
        SourceType.DESIGNATED_DOCUMENT,
        EvidenceState.UNREADABLE,
        "no authority established",
        "README.md",
        "a" * 40,
        "content withheld by secret guard",
        partial_result=True,
        category_locators=_literal_categories(current=("repository",), unreadable=("README.md",)),
        provenance=(
            _REPRESENTATIVE_METADATA,
            RepresentativeEvidenceExpectation(
                SourceType.DESIGNATED_DOCUMENT,
                EvidenceState.UNREADABLE,
                "no authority established",
                "README.md",
                "a" * 40,
                "content withheld by secret guard",
            ),
        ),
    ),
)


class DelegatingRepresentativeReaders:
    def __init__(
        self, expectation: RepresentativeExpectation, paths: NeuralPaths | None = None
    ) -> None:
        self.expectation = expectation
        self.local = LocalPlannerContextReaders(paths, clock=lambda: NOW)
        self.calls: dict[str, int] = {}
        self.metadata_calls = 0

    def _called(self, name: str) -> None:
        self.calls[name] = self.calls.get(name, 0) + 1

    def verify(self, checkpoint: PlannerRepositoryCheckpoint) -> SourceEvidence:
        self._called("verify")
        if self.expectation.fixture_id == "checkpoint-race":
            self.metadata_calls += 1
            return _item(
                SourceType.REPOSITORY_METADATA,
                EvidenceState.CURRENT if self.metadata_calls % 2 else EvidenceState.STALE,
                "repository-before" if self.metadata_calls % 2 else "repository-after",
            )
        return _item(SourceType.REPOSITORY_METADATA, EvidenceState.CURRENT, "repository")

    def read_current_documents(
        self, checkpoint: PlannerRepositoryCheckpoint, locators: tuple[str, ...]
    ) -> tuple[SourceEvidence, ...]:
        self._called("documents")
        if self.expectation.source_type is SourceType.DESIGNATED_DOCUMENT:
            return self.local.read_current_documents(checkpoint, locators)
        return ()

    def read_review_evidence(
        self, checkpoint: PlannerRepositoryCheckpoint, locators: tuple[str, ...]
    ) -> tuple[SourceEvidence, ...]:
        self._called("reviews")
        return ()

    def read_knowledge(
        self, project_key: str, knowledge_ids: tuple[UUID, ...]
    ) -> tuple[SourceEvidence, ...]:
        self._called("knowledge")
        if self.expectation.fixture_id in {"clean-current-plus-knowledge", "corrupt-knowledge"}:
            return self.local.read_knowledge(project_key, knowledge_ids)
        if self.expectation.source_type is SourceType.BRAIN_KNOWLEDGE:
            return (
                _item(
                    self.expectation.source_type, self.expectation.state, self.expectation.locator
                ),
            )
        return ()

    def read_historical_evidence(
        self, evidence: tuple[HistoricalEvidenceInput, ...]
    ) -> tuple[SourceEvidence, ...]:
        self._called("historical")
        if self.expectation.fixture_id == "historical-and-frozen":
            return self.local.read_historical_evidence(evidence)
        if self.expectation.source_type is SourceType.HISTORICAL_EVIDENCE:
            return (
                _item(
                    self.expectation.source_type, self.expectation.state, self.expectation.locator
                ),
            )
        return ()


def _service(extra: tuple[SourceEvidence, ...] = ()) -> PlannerContextService:
    readers = FixtureReaders(extra)
    return PlannerContextService(readers, readers, readers, readers, readers)


def _request(filters: dict[str, object] | None = None) -> PlannerContextRequest:
    return PlannerContextRequest.model_validate(
        {
            "project_key": " NeuralEngine ",
            "task_statement": " inspect context only ",
            "verified_repository_checkpoint": _checkpoint(),
            "optional_source_filters": filters
            or {
                "current_documents": ("README.md",),
                "review_artifacts": (
                    ".agent-work/reviews/review-prd-authority-aware-planner-context-package.md",
                ),
                "knowledge_ids": (KNOWLEDGE_ID,),
                "historical_evidence": (
                    {
                        "locator": "release/v1.0.0",
                        "stable_identity": "v1.0.0",
                        "content": "frozen release evidence",
                        "evidence_state": "FROZEN_RELEASE_EVIDENCE",
                        "checkpoint_or_version": "v1.0.0",
                    },
                ),
            },
        }
    )


def _assert_representative_package(
    package: PlannerContextPackage, expectation: RepresentativeExpectation
) -> None:
    actual_categories = (
        (
            "current_authoritative_sources",
            tuple(item.normalized_locator for item in package.current_authoritative_sources),
        ),
        (
            "supporting_brain_knowledge",
            tuple(item.normalized_locator for item in package.supporting_brain_knowledge),
        ),
        (
            "historical_evidence",
            tuple(item.normalized_locator for item in package.historical_evidence),
        ),
        (
            "stale_or_conflicting_sources",
            tuple(item.normalized_locator for item in package.stale_or_conflicting_sources),
        ),
        ("missing_evidence", tuple(item.normalized_locator for item in package.missing_evidence)),
        (
            "unreadable_or_inaccessible_sources",
            tuple(item.normalized_locator for item in package.unreadable_or_inaccessible_sources),
        ),
    )
    assert actual_categories == expectation.category_locators
    actual_provenance = tuple(
        RepresentativeEvidenceExpectation(
            item.source_type,
            item.evidence_state,
            item.authority_class,
            item.normalized_locator,
            item.stable_identity,
            item.diagnostic,
        )
        for item in package.provenance
    )
    assert actual_provenance == expectation.provenance
    assert package.warnings == expectation.warnings
    actual_partial_result = any(
        getattr(package, category)
        for category in (
            "stale_or_conflicting_sources",
            "missing_evidence",
            "unreadable_or_inaccessible_sources",
        )
    ) or bool(package.warnings)
    assert actual_partial_result is expectation.partial_result


def _assert_fixture_expectation(
    package: PlannerContextPackage, expectation: FixtureExpectation
) -> None:
    for category, expected_locators in expectation.expected_categories:
        actual_items = getattr(package, category)
        assert tuple(item.normalized_locator for item in actual_items) == expected_locators

    actual_provenance = tuple(
        ExpectedEvidence(
            item.normalized_locator,
            item.source_type,
            item.evidence_state,
            item.diagnostic is not None,
        )
        for item in package.provenance
    )
    assert actual_provenance == expectation.expected_provenance
    assert all(item.authority_class == "fixture authority" for item in package.provenance)
    assert all(item.normalized_locator for item in package.provenance)
    assert not package.warnings

    has_partial_result = any(
        getattr(package, category)
        for category in (
            "stale_or_conflicting_sources",
            "missing_evidence",
            "unreadable_or_inaccessible_sources",
        )
    )
    assert has_partial_result is expectation.expected_partial_result


@pytest.mark.parametrize("expectation", FIXTURE_EXPECTATIONS, ids=lambda case: case.fixture_id)
def test_twelve_paired_service_fixtures_are_deterministic(
    expectation: FixtureExpectation,
) -> None:
    failure_category = {
        EvidenceState.STALE: "stale_or_conflicting_sources",
        EvidenceState.CONFLICTING: "stale_or_conflicting_sources",
        EvidenceState.MISSING: "missing_evidence",
        EvidenceState.AMBIGUOUS: "missing_evidence",
        EvidenceState.UNREADABLE: "unreadable_or_inaccessible_sources",
    }
    extra = (
        ()
        if expectation.extra_state is None
        else (
            _item(
                SourceType.BRAIN_KNOWLEDGE,
                expectation.extra_state,
                dict(expectation.expected_categories)[failure_category[expectation.extra_state]][0],
            ),
        )
    )
    service = _service(extra)
    request = _request()
    actual = tuple(service.prepare(request).model_dump_json() for _ in range(3))
    package = service.prepare(request)

    assert actual[0] == actual[1] == actual[2]
    _assert_fixture_expectation(package, expectation)


def test_independent_fixture_oracle_rejects_wrong_category_expectation() -> None:
    expectation = FIXTURE_EXPECTATIONS[0]
    wrong_expectation = FixtureExpectation(
        expectation.fixture_id,
        expectation.extra_state,
        (
            ("current_authoritative_sources", ("README.md", "repository")),
            *expectation.expected_categories[1:],
        ),
        expectation.expected_provenance,
        expectation.expected_partial_result,
    )

    with pytest.raises(AssertionError):
        _assert_fixture_expectation(_service().prepare(_request()), wrong_expectation)


def test_historical_brain_knowledge_has_one_exclusive_category_and_provenance_item() -> None:
    package = _service().prepare(_request())
    knowledge_locator = f"brain/{KNOWLEDGE_ID}"

    assert tuple(item.normalized_locator for item in package.supporting_brain_knowledge) == (
        knowledge_locator,
    )
    assert knowledge_locator not in tuple(
        item.normalized_locator for item in package.historical_evidence
    )
    assert sum(item.normalized_locator == knowledge_locator for item in package.provenance) == 1
    assert tuple(item.normalized_locator for item in package.historical_evidence) == (
        "release/v1.0.0",
    )


def test_all_source_categories_and_evidence_states_are_visible() -> None:
    states = (
        EvidenceState.STALE,
        EvidenceState.CONFLICTING,
        EvidenceState.MISSING,
        EvidenceState.UNREADABLE,
        EvidenceState.AMBIGUOUS,
    )
    extras = tuple(_item(SourceType.BRAIN_KNOWLEDGE, state, state.value) for state in states)
    package = _service(extras).prepare(_request())

    assert {item.source_type for item in package.provenance} == set(SourceType)
    assert {item.evidence_state for item in package.provenance} == {
        EvidenceState.CURRENT,
        EvidenceState.HISTORICAL,
        EvidenceState.FROZEN_RELEASE_EVIDENCE,
        *states,
    }
    assert package.stale_or_conflicting_sources
    assert package.missing_evidence
    assert package.unreadable_or_inaccessible_sources


def test_filters_only_narrow_and_source_count_is_bounded() -> None:
    package = _service().prepare(_request({"current_documents": (), "review_artifacts": ()}))
    assert not package.current_authoritative_sources[1:]
    with pytest.raises(ValidationError, match="At most 24"):
        PlannerSourceFilters(knowledge_ids=tuple(UUID(int=index) for index in range(13)))
    with pytest.raises(ValidationError, match="approved inventory"):
        PlannerSourceFilters(current_documents=("/etc/passwd",))


def test_checkpoint_mismatch_invalidates_all_checkpoint_dependent_current_evidence() -> None:
    readers = SequencedFixtureReaders(
        (
            _item(SourceType.REPOSITORY_METADATA, EvidenceState.CURRENT, "repository-before"),
            _item(SourceType.REPOSITORY_METADATA, EvidenceState.STALE, "repository-after"),
        )
    )
    service = PlannerContextService(readers, readers, readers, readers, readers)
    package = service.prepare(_request())

    assert not package.current_authoritative_sources
    assert {item.normalized_locator for item in package.stale_or_conflicting_sources} == {
        "repository-before",
        "repository-after",
    }
    assert package.warnings == (
        "verified repository checkpoint did not match before and after current-source reads",
    )
    assert all(
        item.evidence_state is not EvidenceState.CURRENT
        for item in package.provenance
        if item.source_type
        in {
            SourceType.REPOSITORY_METADATA,
            SourceType.DESIGNATED_DOCUMENT,
            SourceType.DESIGNATED_REVIEW,
        }
    )


def test_local_reader_rejects_path_traversal_absolute_symlink_binary_and_oversize(
    tmp_path: Path,
) -> None:
    reader = LocalPlannerContextReaders(clock=lambda: NOW)
    checkpoint = _checkpoint(str(tmp_path))
    (tmp_path / "ok.md").write_text("ok", encoding="utf-8")
    (tmp_path / "binary.md").write_bytes(b"\xff")
    (tmp_path / "large.md").write_bytes(b"x" * 65537)
    (tmp_path / "target.md").write_text("target", encoding="utf-8")
    (tmp_path / "link.md").symlink_to(tmp_path / "target.md")

    cases = ("../outside", "/etc/passwd", "binary.md", "large.md", "link.md")
    items = reader.read_current_documents(checkpoint, cases)
    assert all(item.evidence_state is EvidenceState.UNREADABLE for item in items)
    assert all(item.excerpt is None for item in items)


def test_local_reader_rejects_parent_symlink_escape_without_affecting_contained_files(
    tmp_path: Path,
) -> None:
    reader = LocalPlannerContextReaders(clock=lambda: NOW)
    checkpoint = _checkpoint(str(tmp_path))
    external = tmp_path.parent / f"{tmp_path.name}-external"
    external.mkdir()
    (external / "outside.md").write_text("outside-controlled-content", encoding="utf-8")
    (tmp_path / "docs").symlink_to(external, target_is_directory=True)
    (tmp_path / "contained.md").write_text("contained", encoding="utf-8")

    escaped, contained = reader.read_current_documents(
        checkpoint, ("docs/outside.md", "contained.md")
    )

    assert escaped.evidence_state is EvidenceState.UNREADABLE
    assert escaped.excerpt is None
    assert escaped.diagnostic == "resolved path escapes verified repository root"
    assert contained.evidence_state is EvidenceState.CURRENT
    assert contained.excerpt == "contained"


def test_local_reader_secret_guard_and_excerpt_limits_are_read_only(tmp_path: Path) -> None:
    reader = LocalPlannerContextReaders(clock=lambda: NOW)
    checkpoint = _checkpoint(str(tmp_path))
    (tmp_path / "secret.md").write_text("token=not-a-real-secret", encoding="utf-8")
    (tmp_path / "long.md").write_text("\n".join("x" * 80 for _ in range(150)), encoding="utf-8")
    before = tuple(sorted(path.name for path in tmp_path.iterdir()))
    secret, long = reader.read_current_documents(checkpoint, ("secret.md", "long.md"))
    after = tuple(sorted(path.name for path in tmp_path.iterdir()))

    assert before == after
    assert secret.evidence_state is EvidenceState.UNREADABLE and secret.excerpt is None
    assert secret.content_sha256
    assert long.evidence_state is EvidenceState.CURRENT
    assert long.excerpt is not None and len(long.excerpt.encode()) <= 4096
    assert long.excerpt.count("\n") + 1 <= 120


@pytest.mark.parametrize(
    ("source_type", "state", "category"),
    [
        (SourceType.REPOSITORY_METADATA, EvidenceState.CURRENT, "current_authoritative_sources"),
        (SourceType.DESIGNATED_DOCUMENT, EvidenceState.CURRENT, "current_authoritative_sources"),
        (SourceType.DESIGNATED_REVIEW, EvidenceState.CURRENT, "current_authoritative_sources"),
        (SourceType.BRAIN_KNOWLEDGE, EvidenceState.CURRENT, "supporting_brain_knowledge"),
        (SourceType.BRAIN_KNOWLEDGE, EvidenceState.HISTORICAL, "supporting_brain_knowledge"),
        (SourceType.HISTORICAL_EVIDENCE, EvidenceState.HISTORICAL, "historical_evidence"),
        (
            SourceType.HISTORICAL_EVIDENCE,
            EvidenceState.FROZEN_RELEASE_EVIDENCE,
            "historical_evidence",
        ),
        (SourceType.BRAIN_KNOWLEDGE, EvidenceState.STALE, "stale_or_conflicting_sources"),
        (
            SourceType.HISTORICAL_EVIDENCE,
            EvidenceState.CONFLICTING,
            "stale_or_conflicting_sources",
        ),
        (SourceType.DESIGNATED_DOCUMENT, EvidenceState.MISSING, "missing_evidence"),
        (SourceType.BRAIN_KNOWLEDGE, EvidenceState.AMBIGUOUS, "missing_evidence"),
        (
            SourceType.HISTORICAL_EVIDENCE,
            EvidenceState.UNREADABLE,
            "unreadable_or_inaccessible_sources",
        ),
    ],
)
def test_assemble_routes_each_source_state_to_one_category(
    source_type: SourceType, state: EvidenceState, category: str
) -> None:
    item = _item(source_type, state, f"matrix/{source_type.value}/{state.value}")
    package = _service()._assemble((item,), [])
    categories = (
        "current_authoritative_sources",
        "supporting_brain_knowledge",
        "historical_evidence",
        "stale_or_conflicting_sources",
        "missing_evidence",
        "unreadable_or_inaccessible_sources",
    )

    assert tuple(getattr(package, category)) == (item,)
    assert sum(item in getattr(package, name) for name in categories) == 1
    assert package.provenance == (item,)
    if source_type is SourceType.BRAIN_KNOWLEDGE:
        assert item not in package.current_authoritative_sources


@pytest.mark.parametrize(
    "fixture_id",
    (
        "clean-current-plus-knowledge",
        "historical-and-frozen",
        "stale-knowledge",
        "conflicting-evidence",
        "missing-document",
        "corrupt-knowledge",
        "explicit-empty-result",
        "restrictive-filter",
        "binary-source",
        "oversize-source",
        "checkpoint-race",
        "secret-guard",
    ),
)
def test_legacy_boundary_examples_are_deterministic(tmp_path: Path, fixture_id: str) -> None:
    """Exercise each named policy boundary before comparing a literal package result."""
    local = LocalPlannerContextReaders(clock=lambda: NOW)
    checkpoint = _checkpoint(str(tmp_path))
    source_item: SourceEvidence
    expected_category: str
    expected_authority: str
    filters: dict[str, object] = {
        "current_documents": (),
        "review_artifacts": (),
        "knowledge_ids": (),
        "historical_evidence": (),
    }

    if fixture_id == "clean-current-plus-knowledge":
        home = tmp_path / "home"
        knowledge_directory = home / "brain" / "knowledge"
        knowledge_directory.mkdir(parents=True)
        knowledge = Knowledge(
            id=KNOWLEDGE_ID,
            timestamp=NOW,
            statement="Selected knowledge",
            rationale="fixture",
            confidence=KnowledgeConfidence.HIGH,
            experience_ids=[],
        )
        (knowledge_directory / f"{KNOWLEDGE_ID}.json").write_text(
            knowledge.model_dump_json(), encoding="utf-8"
        )
        reader = LocalPlannerContextReaders(
            NeuralPaths("default", None, home, lambda _path, _mode: True), clock=lambda: NOW
        )
        source_item = reader.read_knowledge("NeuralEngine", (KNOWLEDGE_ID,))[0]
        expected_category, expected_authority = (
            "supporting_brain_knowledge",
            "caller-selected supporting Knowledge",
        )
    elif fixture_id == "historical-and-frozen":
        source_item = local.read_historical_evidence(
            (
                HistoricalEvidenceInput(
                    locator="release/v1.0.0",
                    stable_identity="v1.0.0",
                    content="frozen release evidence",
                    evidence_state=EvidenceState.FROZEN_RELEASE_EVIDENCE,
                    checkpoint_or_version="v1.0.0",
                ),
            )
        )[0]
        expected_category, expected_authority = (
            "historical_evidence",
            "historical supporting evidence",
        )
    elif fixture_id == "stale-knowledge":
        source_item = _item(SourceType.BRAIN_KNOWLEDGE, EvidenceState.STALE, "knowledge/stale")
        expected_category, expected_authority = "stale_or_conflicting_sources", "fixture authority"
    elif fixture_id == "conflicting-evidence":
        source_item = _item(
            SourceType.HISTORICAL_EVIDENCE, EvidenceState.CONFLICTING, "history/conflict"
        )
        expected_category, expected_authority = "stale_or_conflicting_sources", "fixture authority"
    elif fixture_id == "missing-document":
        source_item = local.read_current_documents(checkpoint, ("missing.md",))[0]
        expected_category, expected_authority = "missing_evidence", "no authority established"
    elif fixture_id == "corrupt-knowledge":
        home = tmp_path / "home"
        knowledge_directory = home / "brain" / "knowledge"
        knowledge_directory.mkdir(parents=True)
        (knowledge_directory / f"{KNOWLEDGE_ID}.json").write_text("{broken", encoding="utf-8")
        reader = LocalPlannerContextReaders(
            NeuralPaths("default", None, home, lambda _path, _mode: True), clock=lambda: NOW
        )
        source_item = reader.read_knowledge("NeuralEngine", (KNOWLEDGE_ID,))[0]
        expected_category, expected_authority = (
            "unreadable_or_inaccessible_sources",
            "no authority established",
        )
    elif fixture_id == "explicit-empty-result":
        source_item = _item(
            SourceType.HISTORICAL_EVIDENCE, EvidenceState.AMBIGUOUS, "history/empty"
        )
        expected_category, expected_authority = "missing_evidence", "fixture authority"
    elif fixture_id == "restrictive-filter":
        filters["current_documents"] = ("README.md",)
        source_item = _item(
            SourceType.BRAIN_KNOWLEDGE, EvidenceState.HISTORICAL, "knowledge/filter"
        )
        expected_category, expected_authority = "supporting_brain_knowledge", "fixture authority"
    elif fixture_id == "binary-source":
        (tmp_path / "binary.md").write_bytes(b"\xff")
        source_item = local.read_current_documents(checkpoint, ("binary.md",))[0]
        expected_category, expected_authority = (
            "unreadable_or_inaccessible_sources",
            "no authority established",
        )
    elif fixture_id == "oversize-source":
        (tmp_path / "large.md").write_bytes(b"x" * 65537)
        source_item = local.read_current_documents(checkpoint, ("large.md",))[0]
        expected_category, expected_authority = (
            "unreadable_or_inaccessible_sources",
            "no authority established",
        )
    elif fixture_id == "checkpoint-race":
        source_item = _item(SourceType.REPOSITORY_METADATA, EvidenceState.STALE, "repository-after")
        expected_category, expected_authority = "stale_or_conflicting_sources", "fixture authority"
    else:
        (tmp_path / "secret.md").write_text("token=not-a-real-secret", encoding="utf-8")
        source_item = local.read_current_documents(checkpoint, ("secret.md",))[0]
        expected_category, expected_authority = (
            "unreadable_or_inaccessible_sources",
            "no authority established",
        )

    if fixture_id == "checkpoint-race":
        readers = SequencedFixtureReaders(
            (
                _item(SourceType.REPOSITORY_METADATA, EvidenceState.CURRENT, "repository-before"),
                source_item,
            )
        )
        service = PlannerContextService(readers, readers, readers, readers, readers)
    else:
        service = _service((source_item,))
    request = _request(filters)
    serializations = tuple(service.prepare(request).model_dump_json() for _ in range(3))
    package = service.prepare(request)

    assert serializations[0] == serializations[1] == serializations[2]
    if fixture_id == "checkpoint-race":
        assert not package.current_authoritative_sources
        assert tuple(item.normalized_locator for item in package.stale_or_conflicting_sources) == (
            "repository-after",
            "repository-before",
        )
    else:
        assert tuple(item.normalized_locator for item in getattr(package, expected_category)) == (
            source_item.normalized_locator,
        )
    assert source_item.authority_class == expected_authority
    assert sum(item == source_item for item in package.provenance) == 1
    if fixture_id == "restrictive-filter":
        assert tuple(item.normalized_locator for item in package.current_authoritative_sources) == (
            "repository",
            "README.md",
        )


@pytest.mark.parametrize(
    "expectation", REPRESENTATIVE_EXPECTATIONS, ids=lambda item: item.fixture_id
)
def test_twelve_representative_fixtures_use_literal_oracles(
    tmp_path: Path, expectation: RepresentativeExpectation
) -> None:
    filters: dict[str, object] = {
        "current_documents": (),
        "review_artifacts": (),
        "knowledge_ids": (),
        "historical_evidence": (),
    }
    paths: NeuralPaths | None = None
    if expectation.fixture_id in {"clean-current-plus-knowledge", "corrupt-knowledge"}:
        home = tmp_path / "home"
        directory = home / "brain" / "knowledge"
        directory.mkdir(parents=True)
        paths = NeuralPaths("default", None, home, lambda _path, _mode: True)
        filters["knowledge_ids"] = (KNOWLEDGE_ID,)
        content = (
            "{broken"
            if expectation.fixture_id == "corrupt-knowledge"
            else Knowledge(
                id=KNOWLEDGE_ID,
                timestamp=NOW,
                statement="Selected knowledge",
                rationale="fixture",
                confidence=KnowledgeConfidence.HIGH,
                experience_ids=[],
            ).model_dump_json()
        )
        (directory / f"{KNOWLEDGE_ID}.json").write_text(content, encoding="utf-8")
    elif expectation.fixture_id == "historical-and-frozen":
        filters["historical_evidence"] = (
            HistoricalEvidenceInput(
                locator="release/v1.0.0",
                stable_identity="v1.0.0",
                content="frozen release evidence",
                evidence_state=EvidenceState.FROZEN_RELEASE_EVIDENCE,
                checkpoint_or_version="v1.0.0",
            ),
        )
    elif expectation.source_type is SourceType.DESIGNATED_DOCUMENT:
        filters["current_documents"] = ("README.md",)
        if expectation.fixture_id == "binary-source":
            (tmp_path / "README.md").write_bytes(b"\xff")
        elif expectation.fixture_id == "oversize-source":
            (tmp_path / "README.md").write_bytes(b"x" * 65537)
        elif expectation.fixture_id == "secret-guard":
            (tmp_path / "README.md").write_text("token=not-a-real-secret", encoding="utf-8")
        elif expectation.fixture_id == "restrictive-filter":
            (tmp_path / "README.md").write_text("selected", encoding="utf-8")
    readers = DelegatingRepresentativeReaders(expectation, paths)
    service = PlannerContextService(readers, readers, readers, readers, readers)
    request = PlannerContextRequest(
        project_key="NeuralEngine",
        task_statement="fixture",
        verified_repository_checkpoint=_checkpoint(str(tmp_path)),
        optional_source_filters=PlannerSourceFilters.model_validate(filters),
    )
    serializations = tuple(service.prepare(request).model_dump_json() for _ in range(3))
    package = service.prepare(request)
    assert serializations[0] == serializations[1] == serializations[2]
    _assert_representative_package(package, expectation)
    assert readers.calls["verify"] >= 2
    if expectation.fixture_id in {
        "missing-document",
        "binary-source",
        "oversize-source",
        "secret-guard",
        "restrictive-filter",
    }:
        assert readers.calls["documents"] == 4
    if expectation.fixture_id in {"clean-current-plus-knowledge", "corrupt-knowledge"}:
        assert readers.calls["knowledge"] == 4


@pytest.mark.parametrize(
    "wrong_expectation",
    (
        replace(
            REPRESENTATIVE_EXPECTATIONS[4],
            provenance=(
                replace(REPRESENTATIVE_EXPECTATIONS[4].provenance[0], stable_identity="wrong-id"),
                REPRESENTATIVE_EXPECTATIONS[4].provenance[1],
            ),
        ),
        replace(
            REPRESENTATIVE_EXPECTATIONS[4],
            provenance=tuple(reversed(REPRESENTATIVE_EXPECTATIONS[4].provenance)),
        ),
        replace(REPRESENTATIVE_EXPECTATIONS[4], partial_result=False),
    ),
    ids=("wrong-stable-identity", "wrong-provenance-order", "wrong-partial-result"),
)
def test_representative_literal_oracle_rejects_wrong_expectation(
    tmp_path: Path, wrong_expectation: RepresentativeExpectation
) -> None:
    expectation = REPRESENTATIVE_EXPECTATIONS[4]
    readers = DelegatingRepresentativeReaders(expectation)
    request = PlannerContextRequest(
        project_key="NeuralEngine",
        task_statement="fixture",
        verified_repository_checkpoint=_checkpoint(str(tmp_path)),
        optional_source_filters=PlannerSourceFilters(
            current_documents=("README.md",), review_artifacts=()
        ),
    )
    package = PlannerContextService(readers, readers, readers, readers, readers).prepare(request)
    with pytest.raises(AssertionError):
        _assert_representative_package(package, wrong_expectation)

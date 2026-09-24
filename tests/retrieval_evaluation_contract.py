"""Test-only fixtures and an independent oracle for retrieval evaluation."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from neural_engine.application.planner_context_service import EvidenceState


class FailureCategory(StrEnum):
    """Observable retrieval-evaluation outcomes and failure classes."""

    CORRECT_HIT = "correct_hit"
    INCORRECT_HIT = "incorrect_hit"
    DANGEROUS_FALSE_POSITIVE = "dangerous_false_positive"
    FALSE_NEGATIVE = "false_negative"
    IRRELEVANT_EXTRA_EVIDENCE = "irrelevant_extra_evidence"
    STALE_EVIDENCE = "stale_evidence"
    AUTHORITY_MISMATCH = "authority_mismatch"
    CONTRADICTION_MISHANDLING = "contradiction_mishandling"
    PROVENANCE_BREAK = "provenance_break"
    INCORRECT_ABSTENTION = "incorrect_abstention"
    CORRECT_ABSTENTION = "correct_abstention"


class ExtraEvidenceKind(StrEnum):
    """Fixture-authored classification for evidence outside the required set."""

    DANGEROUS = "dangerous_false_positive"
    IRRELEVANT = "irrelevant_extra_evidence"


@dataclass(frozen=True)
class FixtureRecord:
    """One ordered, non-persisted record in an evaluation fixture."""

    identity: str
    content: str
    evidence_state: EvidenceState
    authority_class: str
    checkpoint_or_version: str | None = None


@dataclass(frozen=True)
class RelationEdge:
    """One explicit relation edge in a fixture graph."""

    source_identity: str
    relation: str
    target_identity: str


@dataclass(frozen=True)
class ExpectedEvidence:
    """Literal evidence expectation independently authored by a fixture."""

    identity: str
    evidence_state: EvidenceState | None = None
    authority_class: str | None = None
    checkpoint_or_version: str | None = None
    provenance_path: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExtraEvidence:
    """A known returned record that is outside the minimum sufficient set."""

    evidence: ExpectedEvidence
    kind: ExtraEvidenceKind


@dataclass(frozen=True)
class RetrievalFixture:
    """Complete test-only query-to-gold-evidence contract for one case."""

    case_id: str
    query_or_claim: str
    records: tuple[FixtureRecord, ...]
    required_evidence: tuple[ExpectedEvidence, ...] = ()
    relation_edges: tuple[RelationEdge, ...] = ()
    forbidden_or_irrelevant_evidence: tuple[ExtraEvidence, ...] = ()
    abstention_expected: bool = False
    abstention_reason: tuple[EvidenceState, ...] = ()
    ordered_results: bool = False
    baseline_supported: bool = False

    def __post_init__(self) -> None:
        if not self.case_id.strip() or not self.query_or_claim.strip():
            raise ValueError("Retrieval fixture identity and query must be non-blank.")
        if self.abstention_expected and self.required_evidence:
            raise ValueError("Fixtures expecting abstention cannot declare required evidence.")

        record_ids = tuple(record.identity for record in self.records)
        if len(record_ids) != len(set(record_ids)):
            raise ValueError("Fixture record identities must be unique.")

        required_ids = tuple(item.identity for item in self.required_evidence)
        if len(required_ids) != len(set(required_ids)):
            raise ValueError("Required evidence identities must be unique.")

        extra_ids = tuple(item.evidence.identity for item in self.forbidden_or_irrelevant_evidence)
        if len(extra_ids) != len(set(extra_ids)):
            raise ValueError("Extra evidence identities must be unique.")

        record_id_set = set(record_ids)
        if not set(required_ids).issubset(record_id_set) or not set(extra_ids).issubset(
            record_id_set
        ):
            raise ValueError("Every expected evidence identity must exist in fixture records.")
        if set(required_ids) & set(extra_ids):
            raise ValueError("Required and extra evidence identities must be disjoint.")

        edge_pairs = {(edge.source_identity, edge.target_identity) for edge in self.relation_edges}
        for expected in (
            *self.required_evidence,
            *(item.evidence for item in self.forbidden_or_irrelevant_evidence),
        ):
            for source, target in zip(
                expected.provenance_path, expected.provenance_path[1:], strict=False
            ):
                if (source, target) not in edge_pairs:
                    raise ValueError(
                        "Expected provenance paths must follow fixture relation edges."
                    )

    @property
    def minimum_sufficient_evidence(self) -> tuple[str, ...]:
        """Return the fixture-authored minimum sufficient evidence identities."""

        return tuple(item.identity for item in self.required_evidence)


@dataclass(frozen=True)
class RetrievedEvidence:
    """One actual result item supplied to the independent oracle."""

    identity: str
    evidence_state: EvidenceState | None = None
    authority_class: str | None = None
    checkpoint_or_version: str | None = None
    provenance_path: tuple[str, ...] = ()


@dataclass(frozen=True)
class RetrievalResult:
    """Actual retrieval output at the evaluation boundary."""

    evidence: tuple[RetrievedEvidence, ...] = ()
    abstained: bool = False


@dataclass(frozen=True)
class RetrievalFinding:
    """One deterministic oracle finding."""

    category: FailureCategory
    identity: str | None
    detail: str


@dataclass(frozen=True)
class RetrievalEvaluation:
    """Per-case pass/fail result without aggregate scoring."""

    passed: bool
    categories: tuple[FailureCategory, ...]
    findings: tuple[RetrievalFinding, ...]


_DANGEROUS_STATES = frozenset(
    {
        EvidenceState.STALE,
        EvidenceState.CONFLICTING,
        EvidenceState.MISSING,
        EvidenceState.UNREADABLE,
        EvidenceState.AMBIGUOUS,
    }
)


def evaluate_retrieval(fixture: RetrievalFixture, actual: RetrievalResult) -> RetrievalEvaluation:
    """Compare actual evidence with fixture-authored literal expectations."""

    expected_by_id = {item.identity: item for item in fixture.required_evidence}
    extras_by_id = {
        item.evidence.identity: item for item in fixture.forbidden_or_irrelevant_evidence
    }
    findings: list[RetrievalFinding] = []

    if actual.abstained and not fixture.abstention_expected:
        findings.append(
            RetrievalFinding(
                FailureCategory.INCORRECT_ABSTENTION,
                None,
                "retrieval abstained although the fixture requires sufficient evidence",
            )
        )
    elif fixture.abstention_expected and not actual.abstained:
        findings.append(
            RetrievalFinding(
                FailureCategory.INCORRECT_ABSTENTION,
                None,
                "retrieval returned evidence although the fixture requires abstention",
            )
        )

    for item in actual.evidence:
        expected = expected_by_id.get(item.identity)
        if expected is None:
            extra = extras_by_id.get(item.identity)
            if extra is not None and extra.kind is ExtraEvidenceKind.DANGEROUS:
                category = FailureCategory.DANGEROUS_FALSE_POSITIVE
                detail = "fixture marks returned evidence as dangerous"
            elif item.evidence_state in _DANGEROUS_STATES:
                category = FailureCategory.DANGEROUS_FALSE_POSITIVE
                detail = "returned evidence has an unsafe evidence state"
            elif extra is not None:
                category = FailureCategory.IRRELEVANT_EXTRA_EVIDENCE
                detail = "returned evidence is outside the minimum sufficient set"
            else:
                category = FailureCategory.INCORRECT_HIT
                detail = "returned evidence is not part of the fixture"
            findings.append(RetrievalFinding(category, item.identity, detail))
            continue

        findings.extend(_metadata_findings(expected, item))

    if not actual.abstained:
        missing = set(expected_by_id) - {item.identity for item in actual.evidence}
        expected_conflicts = {
            item.identity
            for item in fixture.required_evidence
            if item.evidence_state is EvidenceState.CONFLICTING
        }
        returned_conflicts = {
            item.identity for item in actual.evidence if item.identity in expected_conflicts
        }
        if returned_conflicts and returned_conflicts != expected_conflicts:
            findings.append(
                RetrievalFinding(
                    FailureCategory.CONTRADICTION_MISHANDLING,
                    None,
                    "only part of the expected conflicting evidence was returned",
                )
            )
            missing -= expected_conflicts

        findings.extend(
            RetrievalFinding(
                FailureCategory.FALSE_NEGATIVE,
                identity,
                "required evidence was not returned",
            )
            for identity in sorted(missing)
        )

    if fixture.ordered_results and not actual.abstained:
        actual_ids = tuple(item.identity for item in actual.evidence)
        expected_ids = tuple(item.identity for item in fixture.required_evidence)
        if actual_ids != expected_ids:
            findings.append(
                RetrievalFinding(
                    FailureCategory.INCORRECT_HIT,
                    None,
                    "returned evidence order differs from the literal fixture order",
                )
            )

    if not findings:
        if fixture.abstention_expected and actual.abstained and not actual.evidence:
            return RetrievalEvaluation(True, (FailureCategory.CORRECT_ABSTENTION,), ())
        if not fixture.abstention_expected and not actual.abstained:
            return RetrievalEvaluation(True, (FailureCategory.CORRECT_HIT,), ())

    categories = _ordered_unique(item.category for item in findings)
    return RetrievalEvaluation(bool(not findings), categories, tuple(findings))


def _metadata_findings(
    expected: ExpectedEvidence, actual: RetrievedEvidence
) -> tuple[RetrievalFinding, ...]:
    findings: list[RetrievalFinding] = []
    if expected.evidence_state is not None and actual.evidence_state != expected.evidence_state:
        category = (
            FailureCategory.STALE_EVIDENCE
            if expected.evidence_state is EvidenceState.CURRENT
            and actual.evidence_state is EvidenceState.STALE
            else FailureCategory.AUTHORITY_MISMATCH
        )
        findings.append(
            RetrievalFinding(category, actual.identity, "evidence state differs from the fixture")
        )
    if expected.authority_class is not None and actual.authority_class != expected.authority_class:
        findings.append(
            RetrievalFinding(
                category=FailureCategory.AUTHORITY_MISMATCH,
                identity=actual.identity,
                detail="authority class differs from the fixture",
            )
        )
    if (
        expected.checkpoint_or_version is not None
        and actual.checkpoint_or_version != expected.checkpoint_or_version
    ):
        findings.append(
            RetrievalFinding(
                FailureCategory.AUTHORITY_MISMATCH,
                actual.identity,
                "checkpoint or version differs from the fixture",
            )
        )
    if expected.provenance_path and actual.provenance_path != expected.provenance_path:
        findings.append(
            RetrievalFinding(
                FailureCategory.PROVENANCE_BREAK,
                actual.identity,
                "provenance path differs from the fixture",
            )
        )
    return tuple(findings)


def _ordered_unique(
    values: Iterable[FailureCategory],
) -> tuple[FailureCategory, ...]:
    result: list[FailureCategory] = []
    for value in values:
        if value not in result:
            result.append(value)
    return tuple(result)

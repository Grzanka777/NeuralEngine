from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import pytest
from retrieval_evaluation_contract import (
    ExpectedEvidence,
    ExtraEvidence,
    ExtraEvidenceKind,
    FailureCategory,
    FixtureRecord,
    RelationEdge,
    RetrievalEvaluation,
    RetrievalFixture,
    RetrievalResult,
    RetrievedEvidence,
    evaluate_retrieval,
)

from neural_engine.application.knowledge_service import (
    ExperienceNotFoundError,
    KnowledgeService,
)
from neural_engine.application.planner_context_service import EvidenceState
from neural_engine.domain import Experience, ExperienceResult, Knowledge, KnowledgeConfidence
from neural_engine.ports.experience_repository import ExperienceRepository
from neural_engine.ports.knowledge_repository import KnowledgeRepository

NOW = datetime(2026, 9, 22, tzinfo=UTC)
VALID_EXPERIENCE_ID = UUID("10000000-0000-0000-0000-000000000001")
INVALID_EXPERIENCE_ID = UUID("10000000-0000-0000-0000-000000000099")

CURRENT_AUTHORITY = "verified current repository source"
HISTORICAL_AUTHORITY = "caller-selected supporting Knowledge"


class FixtureExperienceRepository(ExperienceRepository):
    def __init__(self, experiences: tuple[Experience, ...]) -> None:
        self._experiences = {experience.id: experience for experience in experiences}

    def save(self, experience: Experience) -> None:
        self._experiences[experience.id] = experience

    def load_all(self) -> list[Experience]:
        return list(self._experiences.values())

    def get_by_id(self, experience_id: UUID) -> Experience | None:
        return self._experiences.get(experience_id)


class FixtureKnowledgeRepository(KnowledgeRepository):
    def __init__(self, knowledge_items: tuple[Knowledge, ...]) -> None:
        self._knowledge_items = list(knowledge_items)

    def save(self, knowledge: Knowledge) -> None:
        self._knowledge_items.append(knowledge)

    def load_all(self) -> list[Knowledge]:
        return list(self._knowledge_items)

    def get_by_id(self, knowledge_id: UUID) -> Knowledge | None:
        return next(
            (knowledge for knowledge in self._knowledge_items if knowledge.id == knowledge_id),
            None,
        )


@dataclass(frozen=True)
class BaselineCase:
    fixture: RetrievalFixture
    knowledge_items: tuple[Knowledge, ...]


def _experience() -> Experience:
    return Experience(
        id=VALID_EXPERIENCE_ID,
        timestamp=NOW,
        title="Retrieval fixture experience",
        context="Deterministic retrieval evaluation",
        action="Run a literal search",
        outcome="Fixture is available",
        result=ExperienceResult.SUCCESS,
    )


def _knowledge(
    identifier: str,
    statement: str,
    rationale: str,
    *,
    experience_id: UUID = VALID_EXPERIENCE_ID,
    confidence: KnowledgeConfidence = KnowledgeConfidence.MEDIUM,
    tags: tuple[str, ...] = (),
) -> Knowledge:
    return Knowledge(
        id=UUID(identifier),
        timestamp=NOW,
        statement=statement,
        rationale=rationale,
        confidence=confidence,
        experience_ids=[experience_id],
        tags=list(tags),
    )


def _baseline_fixture(
    case_id: str,
    query: str,
    knowledge_items: tuple[Knowledge, ...],
    required_ids: tuple[str, ...],
    *,
    ordered_results: bool = False,
) -> RetrievalFixture:
    return RetrievalFixture(
        case_id=case_id,
        query_or_claim=query,
        records=tuple(
            FixtureRecord(
                identity=str(item.id),
                content=f"{item.statement}\n{item.rationale}",
                evidence_state=EvidenceState.HISTORICAL,
                authority_class=HISTORICAL_AUTHORITY,
            )
            for item in knowledge_items
        ),
        required_evidence=tuple(ExpectedEvidence(identifier) for identifier in required_ids),
        abstention_expected=not required_ids,
        ordered_results=ordered_results,
        baseline_supported=True,
    )


STATEMENT_ITEM = _knowledge(
    "20000000-0000-0000-0000-000000000001",
    "Create-once persistence must fail closed",
    "Reject conflicting writes",
)
RATIONALE_ITEM = _knowledge(
    "20000000-0000-0000-0000-000000000002",
    "Stable identity",
    "Create-once semantics preserve one payload",
)
FIRST_ORDERED_ITEM = _knowledge(
    "20000000-0000-0000-0000-000000000003",
    "First create-once item",
    "First rationale",
)
SECOND_ORDERED_ITEM = _knowledge(
    "20000000-0000-0000-0000-000000000004",
    "Second create-once item",
    "Second rationale",
)
LEXICAL_DISTRACTOR = _knowledge(
    "20000000-0000-0000-0000-000000000005",
    "Cache invalidation is useful",
    "This record is related to memory retention but lacks the literal query",
)
EXCLUDED_FIELD_ITEM = _knowledge(
    "20000000-0000-0000-0000-000000000006",
    "No searchable field contains the query",
    "The searchable text remains unrelated",
    confidence=KnowledgeConfidence.LOW,
    tags=("secret-term",),
)


BASELINE_CASES = (
    BaselineCase(
        _baseline_fixture(
            "statement-substring",
            "create-once",
            (STATEMENT_ITEM,),
            (str(STATEMENT_ITEM.id),),
        ),
        (STATEMENT_ITEM,),
    ),
    BaselineCase(
        _baseline_fixture(
            "rationale-substring",
            "create-once",
            (RATIONALE_ITEM,),
            (str(RATIONALE_ITEM.id),),
        ),
        (RATIONALE_ITEM,),
    ),
    BaselineCase(
        _baseline_fixture(
            "case-insensitive",
            "CREATE-ONCE",
            (STATEMENT_ITEM,),
            (str(STATEMENT_ITEM.id),),
        ),
        (STATEMENT_ITEM,),
    ),
    BaselineCase(
        _baseline_fixture(
            "repository-order",
            "create-once",
            (FIRST_ORDERED_ITEM, SECOND_ORDERED_ITEM),
            (str(FIRST_ORDERED_ITEM.id), str(SECOND_ORDERED_ITEM.id)),
            ordered_results=True,
        ),
        (FIRST_ORDERED_ITEM, SECOND_ORDERED_ITEM),
    ),
    BaselineCase(
        _baseline_fixture(
            "no-match",
            "nonesuch",
            (STATEMENT_ITEM,),
            (),
        ),
        (STATEMENT_ITEM,),
    ),
    BaselineCase(
        _baseline_fixture(
            "lexical-distractor",
            "caching",
            (LEXICAL_DISTRACTOR,),
            (),
        ),
        (LEXICAL_DISTRACTOR,),
    ),
    BaselineCase(
        _baseline_fixture(
            "excluded-field",
            "secret-term",
            (EXCLUDED_FIELD_ITEM,),
            (),
        ),
        (EXCLUDED_FIELD_ITEM,),
    ),
)


def _knowledge_service(knowledge_items: tuple[Knowledge, ...]) -> KnowledgeService:
    experience_repository = FixtureExperienceRepository((_experience(),))
    return KnowledgeService(
        FixtureKnowledgeRepository(knowledge_items),
        experience_repository,
    )


def _knowledge_result(knowledge_items: list[Knowledge], *, abstained: bool) -> RetrievalResult:
    return RetrievalResult(
        evidence=tuple(RetrievedEvidence(str(item.id)) for item in knowledge_items),
        abstained=abstained,
    )


@pytest.mark.parametrize("case", BASELINE_CASES, ids=lambda case: case.fixture.case_id)
def test_current_substring_baseline_matches_literal_gold_evidence(case: BaselineCase) -> None:
    service = _knowledge_service(case.knowledge_items)

    actual_items = service.search(case.fixture.query_or_claim)
    evaluation = evaluate_retrieval(
        case.fixture,
        _knowledge_result(actual_items, abstained=not actual_items),
    )

    assert evaluation == RetrievalEvaluation(
        passed=True,
        categories=(FailureCategory.CORRECT_ABSTENTION,)
        if not case.fixture.required_evidence
        else (FailureCategory.CORRECT_HIT,),
        findings=(),
    )


def test_current_substring_baseline_fails_closed_on_invalid_non_matching_relation() -> None:
    valid = _knowledge(
        "20000000-0000-0000-0000-000000000007",
        "Create-once persistence",
        "This record matches the query",
    )
    invalid = _knowledge(
        "20000000-0000-0000-0000-000000000008",
        "Unrelated record",
        "This record must still be validated",
        experience_id=INVALID_EXPERIENCE_ID,
    )
    service = _knowledge_service((valid, invalid))

    with pytest.raises(ExperienceNotFoundError) as error:
        service.search("create-once")

    assert error.value.experience_id == INVALID_EXPERIENCE_ID


def _future_fixtures() -> tuple[RetrievalFixture, ...]:
    observation = "observation-1"
    experience = "experience-1"
    knowledge = "knowledge-1"
    return (
        RetrievalFixture(
            case_id="one-hop-observation-to-experience",
            query_or_claim="experience linked to observation-1",
            records=(
                FixtureRecord(
                    observation, "Observation", EvidenceState.HISTORICAL, "durable record"
                ),
                FixtureRecord(experience, "Experience", EvidenceState.HISTORICAL, "durable record"),
            ),
            relation_edges=(
                RelationEdge(observation, "Experience.observation_ids reverse lookup", experience),
            ),
            required_evidence=(
                ExpectedEvidence(
                    experience,
                    EvidenceState.HISTORICAL,
                    "durable record",
                    provenance_path=(observation, experience),
                ),
            ),
        ),
        RetrievalFixture(
            case_id="multi-hop-observation-to-knowledge-provenance",
            query_or_claim="knowledge derived from observation-1",
            records=tuple(
                FixtureRecord(identity, identity, EvidenceState.HISTORICAL, "durable record")
                for identity in (observation, experience, knowledge)
            ),
            relation_edges=(
                RelationEdge(observation, "Experience.observation_ids reverse lookup", experience),
                RelationEdge(experience, "Knowledge.experience_ids reverse lookup", knowledge),
            ),
            required_evidence=(
                ExpectedEvidence(
                    knowledge,
                    EvidenceState.HISTORICAL,
                    "durable record",
                    provenance_path=(observation, experience, knowledge),
                ),
            ),
        ),
        RetrievalFixture(
            case_id="current-versus-historical",
            query_or_claim="current repository rule",
            records=(
                FixtureRecord(
                    "current-rule", "Current rule", EvidenceState.CURRENT, CURRENT_AUTHORITY, "HEAD"
                ),
                FixtureRecord(
                    "historical-rule",
                    "Historical rule",
                    EvidenceState.HISTORICAL,
                    HISTORICAL_AUTHORITY,
                    "v1.0.0",
                ),
            ),
            required_evidence=(
                ExpectedEvidence("current-rule", EvidenceState.CURRENT, CURRENT_AUTHORITY, "HEAD"),
            ),
            forbidden_or_irrelevant_evidence=(
                ExtraEvidence(
                    ExpectedEvidence(
                        "historical-rule",
                        EvidenceState.HISTORICAL,
                        HISTORICAL_AUTHORITY,
                        "v1.0.0",
                    ),
                    ExtraEvidenceKind.DANGEROUS,
                ),
            ),
        ),
        RetrievalFixture(
            case_id="stale-current-evidence",
            query_or_claim="current rule after checkpoint change",
            records=(
                FixtureRecord(
                    "current-rule", "Current rule", EvidenceState.CURRENT, CURRENT_AUTHORITY, "HEAD"
                ),
            ),
            required_evidence=(
                ExpectedEvidence("current-rule", EvidenceState.CURRENT, CURRENT_AUTHORITY, "HEAD"),
            ),
        ),
        RetrievalFixture(
            case_id="conflicting-evidence",
            query_or_claim="which incompatible claims remain visible",
            records=(
                FixtureRecord(
                    "claim-a", "Claim A", EvidenceState.CONFLICTING, "unresolved sources"
                ),
                FixtureRecord(
                    "claim-b", "Claim B", EvidenceState.CONFLICTING, "unresolved sources"
                ),
            ),
            required_evidence=(
                ExpectedEvidence("claim-a", EvidenceState.CONFLICTING, "unresolved sources"),
                ExpectedEvidence("claim-b", EvidenceState.CONFLICTING, "unresolved sources"),
            ),
        ),
        RetrievalFixture(
            case_id="ambiguous-evidence",
            query_or_claim="claim with unresolved identity",
            records=(
                FixtureRecord(
                    "ambiguous",
                    "Ambiguous source",
                    EvidenceState.AMBIGUOUS,
                    "no authority established",
                ),
            ),
            forbidden_or_irrelevant_evidence=(
                ExtraEvidence(
                    ExpectedEvidence(
                        "ambiguous", EvidenceState.AMBIGUOUS, "no authority established"
                    ),
                    ExtraEvidenceKind.DANGEROUS,
                ),
            ),
            abstention_expected=True,
            abstention_reason=(EvidenceState.AMBIGUOUS,),
        ),
        RetrievalFixture(
            case_id="historical-as-of-selection",
            query_or_claim="rule as of v1.0.0",
            records=(
                FixtureRecord(
                    "rule-v1", "Rule v1", EvidenceState.HISTORICAL, HISTORICAL_AUTHORITY, "v1.0.0"
                ),
                FixtureRecord(
                    "rule-v2", "Rule v2", EvidenceState.CURRENT, CURRENT_AUTHORITY, "HEAD"
                ),
            ),
            required_evidence=(
                ExpectedEvidence(
                    "rule-v1", EvidenceState.HISTORICAL, HISTORICAL_AUTHORITY, "v1.0.0"
                ),
            ),
            forbidden_or_irrelevant_evidence=(
                ExtraEvidence(
                    ExpectedEvidence("rule-v2", EvidenceState.CURRENT, CURRENT_AUTHORITY, "HEAD"),
                    ExtraEvidenceKind.IRRELEVANT,
                ),
            ),
        ),
        RetrievalFixture(
            case_id="correct-abstention-missing-evidence",
            query_or_claim="claim with no sufficient source",
            records=(
                FixtureRecord(
                    "missing", "Missing source", EvidenceState.MISSING, "no authority established"
                ),
            ),
            forbidden_or_irrelevant_evidence=(
                ExtraEvidence(
                    ExpectedEvidence("missing", EvidenceState.MISSING, "no authority established"),
                    ExtraEvidenceKind.DANGEROUS,
                ),
            ),
            abstention_expected=True,
            abstention_reason=(EvidenceState.MISSING,),
        ),
    )


FUTURE_FIXTURES = _future_fixtures()


def _gold_result(fixture: RetrievalFixture) -> RetrievalResult:
    return RetrievalResult(
        evidence=tuple(
            RetrievedEvidence(
                identity=item.identity,
                evidence_state=item.evidence_state,
                authority_class=item.authority_class,
                checkpoint_or_version=item.checkpoint_or_version,
                provenance_path=item.provenance_path,
            )
            for item in fixture.required_evidence
        ),
        abstained=fixture.abstention_expected,
    )


@pytest.mark.parametrize("fixture", FUTURE_FIXTURES, ids=lambda fixture: fixture.case_id)
def test_future_capability_fixtures_define_literal_gold_results(
    fixture: RetrievalFixture,
) -> None:
    evaluation = evaluate_retrieval(fixture, _gold_result(fixture))

    assert not fixture.baseline_supported
    assert evaluation.passed
    assert evaluation.categories in {
        (FailureCategory.CORRECT_HIT,),
        (FailureCategory.CORRECT_ABSTENTION,),
    }


@pytest.mark.parametrize(
    ("fixture", "actual", "category"),
    (
        (
            FUTURE_FIXTURES[0],
            RetrievalResult((RetrievedEvidence("wrong-record"),)),
            FailureCategory.INCORRECT_HIT,
        ),
        (
            FUTURE_FIXTURES[2],
            RetrievalResult((RetrievedEvidence("historical-rule", EvidenceState.HISTORICAL),)),
            FailureCategory.DANGEROUS_FALSE_POSITIVE,
        ),
        (
            FUTURE_FIXTURES[0],
            RetrievalResult(),
            FailureCategory.FALSE_NEGATIVE,
        ),
        (
            FUTURE_FIXTURES[6],
            RetrievalResult(
                (
                    RetrievedEvidence(
                        "rule-v1", EvidenceState.HISTORICAL, HISTORICAL_AUTHORITY, "v1.0.0"
                    ),
                    RetrievedEvidence("rule-v2", EvidenceState.CURRENT, CURRENT_AUTHORITY, "HEAD"),
                )
            ),
            FailureCategory.IRRELEVANT_EXTRA_EVIDENCE,
        ),
        (
            FUTURE_FIXTURES[3],
            RetrievalResult(
                (RetrievedEvidence("current-rule", EvidenceState.STALE, CURRENT_AUTHORITY, "HEAD"),)
            ),
            FailureCategory.STALE_EVIDENCE,
        ),
        (
            FUTURE_FIXTURES[2],
            RetrievalResult(
                (
                    RetrievedEvidence(
                        "current-rule", EvidenceState.CURRENT, HISTORICAL_AUTHORITY, "HEAD"
                    ),
                )
            ),
            FailureCategory.AUTHORITY_MISMATCH,
        ),
        (
            FUTURE_FIXTURES[4],
            RetrievalResult(
                (RetrievedEvidence("claim-a", EvidenceState.CONFLICTING, "unresolved sources"),)
            ),
            FailureCategory.CONTRADICTION_MISHANDLING,
        ),
        (
            FUTURE_FIXTURES[1],
            RetrievalResult(
                (
                    RetrievedEvidence(
                        "knowledge-1",
                        EvidenceState.HISTORICAL,
                        "durable record",
                        provenance_path=("observation-1", "knowledge-1"),
                    ),
                )
            ),
            FailureCategory.PROVENANCE_BREAK,
        ),
        (
            FUTURE_FIXTURES[0],
            RetrievalResult(abstained=True),
            FailureCategory.INCORRECT_ABSTENTION,
        ),
    ),
    ids=(
        "incorrect-hit",
        "dangerous-false-positive",
        "false-negative",
        "irrelevant-extra-evidence",
        "stale-evidence",
        "authority-mismatch",
        "contradiction-mishandling",
        "provenance-break",
        "incorrect-abstention",
    ),
)
def test_oracle_identifies_failure_categories(
    fixture: RetrievalFixture,
    actual: RetrievalResult,
    category: FailureCategory,
) -> None:
    evaluation = evaluate_retrieval(fixture, actual)

    assert not evaluation.passed
    assert category in evaluation.categories
    assert evaluation.findings


def test_minimum_sufficient_evidence_is_fixture_data_only() -> None:
    fixture = FUTURE_FIXTURES[1]

    assert fixture.minimum_sufficient_evidence == ("knowledge-1",)
    assert fixture.relation_edges == (
        RelationEdge("observation-1", "Experience.observation_ids reverse lookup", "experience-1"),
        RelationEdge("experience-1", "Knowledge.experience_ids reverse lookup", "knowledge-1"),
    )


def test_fixture_rejects_provenance_paths_that_are_not_in_the_relation_graph() -> None:
    with pytest.raises(ValueError, match="relation edges"):
        RetrievalFixture(
            case_id="invalid-path",
            query_or_claim="invalid path",
            records=(
                FixtureRecord("a", "A", EvidenceState.HISTORICAL, "fixture"),
                FixtureRecord("b", "B", EvidenceState.HISTORICAL, "fixture"),
            ),
            required_evidence=(
                ExpectedEvidence(
                    "b",
                    EvidenceState.HISTORICAL,
                    "fixture",
                    provenance_path=("a", "b"),
                ),
            ),
        )


def _contradictory_abstention_fixture() -> RetrievalFixture:
    return RetrievalFixture(
        case_id="contradictory-abstention",
        query_or_claim="query with required evidence but expected abstention",
        records=(
            FixtureRecord("required", "Required evidence", EvidenceState.HISTORICAL, "fixture"),
        ),
        required_evidence=(ExpectedEvidence("required"),),
        abstention_expected=True,
    )


def test_fixture_rejects_abstention_with_required_evidence() -> None:
    with pytest.raises(
        ValueError,
        match="Fixtures expecting abstention cannot declare required evidence\\.",
    ):
        _contradictory_abstention_fixture()


def test_valid_abstention_fixture_evaluates_as_correct_abstention() -> None:
    fixture = RetrievalFixture(
        case_id="valid-abstention",
        query_or_claim="query with no sufficient evidence",
        records=(FixtureRecord("missing", "Missing evidence", EvidenceState.MISSING, "fixture"),),
        abstention_expected=True,
        abstention_reason=(EvidenceState.MISSING,),
    )

    assert fixture.required_evidence == ()
    assert evaluate_retrieval(fixture, RetrievalResult(abstained=True)) == RetrievalEvaluation(
        passed=True,
        categories=(FailureCategory.CORRECT_ABSTENTION,),
        findings=(),
    )


def test_positive_evidence_fixture_evaluates_as_correct_hit() -> None:
    fixture = RetrievalFixture(
        case_id="valid-positive-evidence",
        query_or_claim="query with sufficient evidence",
        records=(
            FixtureRecord("required", "Required evidence", EvidenceState.HISTORICAL, "fixture"),
        ),
        required_evidence=(ExpectedEvidence("required"),),
        abstention_expected=False,
    )

    assert evaluate_retrieval(
        fixture,
        RetrievalResult(evidence=(RetrievedEvidence("required"),)),
    ) == RetrievalEvaluation(
        passed=True,
        categories=(FailureCategory.CORRECT_HIT,),
        findings=(),
    )


def test_former_false_pass_case_is_rejected_before_oracle_evaluation() -> None:
    """The old contract passed when required evidence accompanied abstention."""
    actual = RetrievalResult(
        evidence=(RetrievedEvidence("required"),),
        abstained=True,
    )

    assert actual.abstained
    assert tuple(item.identity for item in actual.evidence) == ("required",)
    with pytest.raises(
        ValueError,
        match="Fixtures expecting abstention cannot declare required evidence\\.",
    ):
        fixture = _contradictory_abstention_fixture()
        evaluate_retrieval(fixture, actual)

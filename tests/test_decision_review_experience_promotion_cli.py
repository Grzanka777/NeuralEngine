from datetime import UTC, datetime
from uuid import UUID

import pytest
from typer.testing import CliRunner

from neural_engine import cli
from neural_engine.application.decision_review_service import DecisionReviewNotFoundError
from neural_engine.application.experience_service import (
    DecisionReviewPromotionIdempotencyAmbiguityError,
    DecisionReviewPromotionIdempotencyConflictError,
    DecisionReviewPromotionSelector,
    DecisionReviewPromotionSourceIndexError,
    ObservationNotFoundError,
)
from neural_engine.domain import (
    DecisionReviewPromotion,
    DecisionReviewPromotionSourceKind,
    DecisionReviewPromotionSourceStatement,
    Experience,
    ExperienceResult,
)

REVIEW_ID = UUID("11111111-1111-1111-1111-111111111111")
EXPERIENCE_ID = UUID("22222222-2222-2222-2222-222222222222")


class FakePromotionService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.error: Exception | None = None
        self.read_error: Exception | None = None
        self.experience = Experience(
            id=EXPERIENCE_ID,
            timestamp=datetime(2026, 7, 18, 14, 0, tzinfo=UTC),
            title="Promoted review",
            context="Explicit CLI input",
            action="Promote statements",
            outcome="Experience stored",
            result=ExperienceResult.MIXED,
            decision_review_promotion=DecisionReviewPromotion(
                decision_review_id=REVIEW_ID,
                source_statements=(
                    DecisionReviewPromotionSourceStatement(
                        kind=DecisionReviewPromotionSourceKind.CANDIDATE_LESSON,
                        index=1,
                        text="Second candidate",
                    ),
                    DecisionReviewPromotionSourceStatement(
                        kind=DecisionReviewPromotionSourceKind.FINDING,
                        index=0,
                        text="First finding",
                    ),
                ),
                promoted_by="learning-owner",
                promotion_reason="Explicitly authorized",
                idempotency_key="promotion-cli",
            ),
        )

    def add_from_decision_review(self, **values: object) -> Experience:
        self.calls.append(values)
        if self.error is not None:
            raise self.error
        return self.experience

    def list_experiences(self) -> list[Experience]:
        if self.read_error is not None:
            raise self.read_error
        return [
            Experience(
                title="Plain",
                context="Direct",
                action="Record",
                outcome="Stored",
                result=ExperienceResult.SUCCESS,
            ),
            self.experience,
        ]

    def get_by_id(self, experience_id: UUID) -> Experience | None:
        if self.read_error is not None:
            raise self.read_error
        return self.experience if experience_id == self.experience.id else None


class PromotionContainer:
    def __init__(self, service: FakePromotionService) -> None:
        self.service = service

    def experience_service(self) -> FakePromotionService:
        return self.service


def command_args() -> list[str]:
    return [
        "experience",
        "from-review",
        str(REVIEW_ID),
        "--source",
        "candidate_lesson:2",
        "--source",
        "finding:1",
        "--promoted-by",
        "learning-owner",
        "--promotion-reason",
        "Explicitly authorized",
        "--idempotency-key",
        "promotion-cli",
        "--title",
        "Promoted review",
        "--context",
        "Explicit CLI input",
        "--action",
        "Promote statements",
        "--outcome",
        "Experience stored",
        "--result",
        "mixed",
    ]


def test_from_review_help_makes_selector_ordinal_contract_explicit() -> None:
    result = CliRunner().invoke(cli.app, ["experience", "from-review", "--help"])

    assert result.exit_code == 0
    assert "KIND:ORDINAL" in result.output
    assert "1-based" in result.output
    assert "finding" in result.output
    assert "candidate_lesson" in result.output


def test_from_review_converts_ordered_one_based_selectors_and_prints_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakePromotionService()
    monkeypatch.setattr(cli, "container", PromotionContainer(service))

    result = CliRunner().invoke(cli.app, command_args())

    assert result.exit_code == 0
    selectors = service.calls[0]["source_selectors"]
    assert selectors == [
        DecisionReviewPromotionSelector(DecisionReviewPromotionSourceKind.CANDIDATE_LESSON, 1),
        DecisionReviewPromotionSelector(DecisionReviewPromotionSourceKind.FINDING, 0),
    ]
    assert service.calls[0]["result"] is ExperienceResult.MIXED
    assert f"ID: {EXPERIENCE_ID}" in result.output
    assert f"Decision review promotion: {REVIEW_ID}" in result.output
    assert "candidate_lesson:2 (stored index 1) Second candidate" in result.output
    assert "finding:1 (stored index 0) First finding" in result.output


@pytest.mark.parametrize(
    "selector",
    ["finding:0", "candidate_lesson:-1", "finding:not-a-number", "lesson:1", "finding"],
)
def test_from_review_rejects_invalid_selector_syntax_before_service_call(
    monkeypatch: pytest.MonkeyPatch, selector: str
) -> None:
    service = FakePromotionService()
    monkeypatch.setattr(cli, "container", PromotionContainer(service))
    args = command_args()
    first_source = args.index("--source") + 1
    args[first_source] = selector

    result = CliRunner().invoke(cli.app, args)

    assert result.exit_code == 1
    assert service.calls == []


def test_from_review_rejects_invalid_review_uuid_before_service_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakePromotionService()
    monkeypatch.setattr(cli, "container", PromotionContainer(service))
    args = command_args()
    args[2] = "not-a-uuid"

    result = CliRunner().invoke(cli.app, args)

    assert result.exit_code == 2
    assert service.calls == []


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (DecisionReviewNotFoundError(REVIEW_ID), "Decision review not found"),
        (
            DecisionReviewPromotionSourceIndexError(
                REVIEW_ID, DecisionReviewPromotionSourceKind.FINDING, 9
            ),
            "zero-based index 9",
        ),
        (
            ObservationNotFoundError(UUID("99999999-9999-9999-9999-999999999999")),
            "Observation not found",
        ),
        (
            DecisionReviewPromotionIdempotencyConflictError(REVIEW_ID, "promotion-cli"),
            "different",
        ),
        (
            DecisionReviewPromotionIdempotencyAmbiguityError(REVIEW_ID, "promotion-cli", 2),
            "ambiguous",
        ),
    ],
)
def test_from_review_renders_controlled_service_errors(
    monkeypatch: pytest.MonkeyPatch, error: Exception, message: str
) -> None:
    service = FakePromotionService()
    service.error = error
    monkeypatch.setattr(cli, "container", PromotionContainer(service))

    result = CliRunner().invoke(cli.app, command_args())

    assert result.exit_code == 1
    assert message in result.output


def test_from_review_equivalent_replay_renders_existing_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakePromotionService()
    monkeypatch.setattr(cli, "container", PromotionContainer(service))

    first = CliRunner().invoke(cli.app, command_args())
    second = CliRunner().invoke(cli.app, command_args())

    assert first.exit_code == second.exit_code == 0
    assert str(EXPERIENCE_ID) in first.output
    assert str(EXPERIENCE_ID) in second.output
    assert len(service.calls) == 2


def test_list_and_show_distinguish_promoted_and_plain_experiences(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakePromotionService()
    monkeypatch.setattr(cli, "container", PromotionContainer(service))
    runner = CliRunner()

    listed = runner.invoke(cli.app, ["experience", "list"])
    shown = runner.invoke(cli.app, ["experience", "show", str(EXPERIENCE_ID)])

    assert listed.exit_code == shown.exit_code == 0
    assert "Title: Plain" in listed.output
    assert f"Decision review promotion: {REVIEW_ID}" in listed.output
    assert f"Decision review promotion: {REVIEW_ID}" in shown.output
    assert "Promoted by: learning-owner" in shown.output


@pytest.mark.parametrize(
    "command", [["experience", "list"], ["experience", "show", str(EXPERIENCE_ID)]]
)
def test_list_and_show_render_promotion_integrity_failures_as_controlled_errors(
    monkeypatch: pytest.MonkeyPatch, command: list[str]
) -> None:
    service = FakePromotionService()
    service.read_error = DecisionReviewPromotionSourceIndexError(
        REVIEW_ID, DecisionReviewPromotionSourceKind.FINDING, 9
    )
    monkeypatch.setattr(cli, "container", PromotionContainer(service))

    result = CliRunner().invoke(cli.app, command)

    assert result.exit_code == 1
    assert "zero-based index 9" in result.output

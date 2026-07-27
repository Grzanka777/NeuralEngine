from datetime import UTC, datetime

import pytest
from typer.testing import CliRunner

import neural_engine.cli as cli
from neural_engine.application.development_evidence_service import (
    DevelopmentEvidenceCandidate,
    DevelopmentEvidenceMismatchError,
    DevelopmentEvidenceRecordInput,
    DevelopmentEvidenceRequest,
)
from neural_engine.domain import (
    DecisionOutcomeResult,
    DecisionReviewAssessment,
    DecisionReviewConfidence,
)


class RejectingService:
    def __init__(self) -> None:
        self.request: DevelopmentEvidenceRequest | None = None
        self.records: DevelopmentEvidenceRecordInput | None = None

    def preview(
        self,
        request: DevelopmentEvidenceRequest,
        records: DevelopmentEvidenceRecordInput,
    ) -> DevelopmentEvidenceCandidate:
        self.request = request
        self.records = records
        raise DevelopmentEvidenceMismatchError("fixture correlation mismatch")


class FakeContainer:
    def __init__(self, service: RejectingService) -> None:
        self.service = service

    def development_evidence_service(self) -> RejectingService:
        return self.service


def _records_json() -> str:
    return DevelopmentEvidenceRecordInput(
        project_key="NeuralEngine",
        title="Title",
        objective="Objective",
        context_summary="Caller context",
        alternatives=("No change", "Implement"),
        proposed_option="Implement",
        rationale="Explicit rationale",
        proposed_by="proposer",
        accepted_by="acceptor",
        acceptance_reason="Explicit acceptance",
        action_type="implementation",
        action_summary="Implemented",
        performed_by="implementer",
        started_at=datetime(2026, 7, 20, 10, tzinfo=UTC),
        completed_at=datetime(2026, 7, 20, 11, tzinfo=UTC),
        outcome_result=DecisionOutcomeResult.UNKNOWN,
        outcome_summary="Explicit outcome",
        validated_by="validator",
        validated_at=datetime(2026, 7, 20, 12, tzinfo=UTC),
        reviewed_by="reviewer",
        reviewed_at=datetime(2026, 7, 20, 13, tzinfo=UTC),
        review_assessment=DecisionReviewAssessment.SOUND,
        review_summary="Explicit review",
        findings=("Finding",),
        review_confidence=DecisionReviewConfidence.MEDIUM,
    ).model_dump_json()


def test_development_evidence_preview_delegates_and_controls_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = RejectingService()
    monkeypatch.setattr(cli, "container", FakeContainer(service))

    result = CliRunner().invoke(
        cli.app,
        [
            "development-evidence",
            "preview",
            "--repository-root",
            "/tmp/NeuralEngine",
            "--prompt-path",
            ".agent-work/prompts/task.md",
            "--review-path",
            ".agent-work/reviews/review.md",
            "--commit-sha",
            "2" * 40,
            "--records-json",
            _records_json(),
        ],
    )

    assert result.exit_code == 1
    assert "fixture correlation mismatch" in result.stdout
    assert "Traceback" not in result.stdout
    assert service.request is not None
    assert service.request.commit_sha == "2" * 40
    assert service.records is not None
    assert service.records.proposed_by == "proposer"


def test_development_evidence_surface_has_separate_preview_and_apply_modes() -> None:
    result = CliRunner().invoke(cli.app, ["development-evidence", "--help"])

    assert result.exit_code == 0
    assert "preview" in result.stdout
    assert "apply" in result.stdout

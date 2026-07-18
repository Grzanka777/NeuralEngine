from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from neural_engine.core.paths import NeuralPaths
from neural_engine.domain import DecisionOutcome, DecisionOutcomeResult, EvidenceReference
from neural_engine.infrastructure.json_decision_outcome_repository import (
    JsonDecisionOutcomeRepository,
)


def make_outcome(outcome_id: UUID) -> DecisionOutcome:
    return DecisionOutcome(
        id=outcome_id,
        recorded_at=datetime(2026, 7, 18, 10, 0, tzinfo=UTC),
        decision_id=UUID("11111111-1111-1111-1111-111111111111"),
        acceptance_id=UUID("22222222-2222-2222-2222-222222222222"),
        action_ids=(UUID("33333333-3333-3333-3333-333333333333"),),
        result=DecisionOutcomeResult.PARTIAL,
        summary="Some checks passed.",
        validated_by="pytest",
        validated_at=datetime(2026, 7, 18, 11, 0, tzinfo=UTC),
        evidence_references=(EvidenceReference(kind="test", locator="pytest:outcome"),),
        metrics={"zeta": True, "alpha": 3},
        idempotency_key="outcome-repository",
        tags=("test",),
    )


def test_save_load_and_get_complete_round_trip(tmp_path: Path) -> None:
    repository = JsonDecisionOutcomeRepository(tmp_path)
    outcome = make_outcome(UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"))

    repository.save(outcome)

    assert repository.load_all() == [outcome]
    assert repository.get_by_id(outcome.id) == outcome
    payload = (tmp_path / f"{outcome.id}.json").read_text(encoding="utf-8")
    assert payload.index('"alpha"') < payload.index('"zeta"')


def test_load_all_is_sorted_by_file_name(tmp_path: Path) -> None:
    repository = JsonDecisionOutcomeRepository(tmp_path)
    high = make_outcome(UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"))
    low = make_outcome(UUID("00000000-0000-0000-0000-000000000001"))
    repository.save(high)
    repository.save(low)

    assert repository.load_all() == [low, high]


def test_missing_directory_or_id_returns_controlled_empty_result(tmp_path: Path) -> None:
    repository = JsonDecisionOutcomeRepository(tmp_path / "missing")

    assert repository.load_all() == []
    assert repository.get_by_id(UUID("11111111-1111-1111-1111-111111111111")) is None


def test_malformed_data_fails_visibly(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text('{"result":"succeeded"}', encoding="utf-8")

    with pytest.raises(ValidationError):
        JsonDecisionOutcomeRepository(tmp_path).load_all()


def test_default_path_uses_decision_outcomes_constant() -> None:
    assert JsonDecisionOutcomeRepository()._directory == NeuralPaths.DECISION_OUTCOMES

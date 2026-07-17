from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from neural_engine.core.paths import NeuralPaths
from neural_engine.domain import DecisionAction, EvidenceReference
from neural_engine.infrastructure.json_decision_action_repository import (
    JsonDecisionActionRepository,
)


def make_action(action_id: UUID, **updates: object) -> DecisionAction:
    values: dict[str, object] = {
        "id": action_id,
        "decision_id": UUID("11111111-1111-1111-1111-111111111111"),
        "acceptance_id": UUID("22222222-2222-2222-2222-222222222222"),
        "action_type": "implementation",
        "summary": "Implemented the action foundation.",
        "performed_by": "codex",
        "started_at": datetime(2026, 7, 17, 10, 0, tzinfo=UTC),
        "idempotency_key": f"action-{action_id}",
    }
    values.update(updates)
    return DecisionAction.model_validate(values)


def test_save_load_and_get_by_id(tmp_path: Path) -> None:
    repository = JsonDecisionActionRepository(tmp_path)
    action = make_action(UUID("11111111-2222-3333-4444-555555555555"))
    repository.save(action)

    assert (tmp_path / f"{action.id}.json").exists()
    assert repository.load_all() == [action]
    assert repository.get_by_id(action.id) == action


def test_missing_directory_and_id_return_empty_values(tmp_path: Path) -> None:
    repository = JsonDecisionActionRepository(tmp_path / "missing")

    assert repository.load_all() == []
    assert repository.get_by_id(UUID("22222222-2222-2222-2222-222222222222")) is None


def test_load_all_is_sorted_by_file_name(tmp_path: Path) -> None:
    repository = JsonDecisionActionRepository(tmp_path)
    later = make_action(UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"))
    earlier = make_action(UUID("00000000-0000-0000-0000-000000000001"))
    repository.save(later)
    repository.save(earlier)

    assert repository.load_all() == [earlier, later]


def test_full_round_trip_preserves_optional_values(tmp_path: Path) -> None:
    repository = JsonDecisionActionRepository(tmp_path)
    action = make_action(
        UUID("33333333-3333-3333-3333-333333333333"),
        completed_at=datetime(2026, 7, 17, 11, 0, tzinfo=UTC),
        evidence_references=(EvidenceReference(kind="review", locator="review:1"),),
        playbook_run_id=UUID("44444444-4444-4444-4444-444444444444"),
        tags=("implementation", "decision"),
    )
    repository.save(action)

    assert repository.get_by_id(action.id) == action


def test_malformed_data_surfaces_validation_error(tmp_path: Path) -> None:
    repository = JsonDecisionActionRepository(tmp_path)
    (tmp_path / "55555555-5555-5555-5555-555555555555.json").write_text(
        '{"action_type":"implementation"}',
        encoding="utf-8",
    )

    with pytest.raises(ValidationError):
        repository.load_all()


def test_default_path_uses_decision_actions_constant() -> None:
    assert JsonDecisionActionRepository()._directory == NeuralPaths.DECISION_ACTIONS

from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from neural_engine.core.paths import resolve_neural_paths
from neural_engine.domain import DecisionAcceptance, EvidenceReference
from neural_engine.infrastructure.json_decision_acceptance_repository import (
    JsonDecisionAcceptanceRepository,
)


def make_acceptance(acceptance_id: UUID, **updates: object) -> DecisionAcceptance:
    values: dict[str, object] = {
        "id": acceptance_id,
        "decision_id": UUID("11111111-1111-1111-1111-111111111111"),
        "accepted_by": "architecture-owner",
        "reason": "Approved after review.",
        "idempotency_key": f"acceptance-{acceptance_id}",
    }
    values.update(updates)
    return DecisionAcceptance.model_validate(values)


def test_save_and_get_by_id_round_trip(tmp_path: Path) -> None:
    repository = JsonDecisionAcceptanceRepository(tmp_path)
    acceptance = make_acceptance(UUID("11111111-2222-3333-4444-555555555555"))

    repository.save(acceptance)

    assert (tmp_path / f"{acceptance.id}.json").exists()
    assert repository.get_by_id(acceptance.id) == acceptance


def test_load_all_returns_empty_and_get_returns_none_when_missing(tmp_path: Path) -> None:
    repository = JsonDecisionAcceptanceRepository(tmp_path / "missing")

    assert repository.load_all() == []
    assert repository.get_by_id(UUID("22222222-2222-2222-2222-222222222222")) is None


def test_load_all_is_sorted_by_file_name(tmp_path: Path) -> None:
    repository = JsonDecisionAcceptanceRepository(tmp_path)
    later = make_acceptance(UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"))
    earlier = make_acceptance(UUID("00000000-0000-0000-0000-000000000001"))
    repository.save(later)
    repository.save(earlier)

    assert repository.load_all() == [earlier, later]


def test_round_trip_preserves_evidence_and_tags(tmp_path: Path) -> None:
    repository = JsonDecisionAcceptanceRepository(tmp_path)
    acceptance = make_acceptance(
        UUID("33333333-3333-3333-3333-333333333333"),
        evidence_references=(
            EvidenceReference(
                kind="manual_decision",
                locator="approval:architecture-review",
                summary="Explicit approval",
            ),
        ),
        tags=("architecture", "review"),
    )

    repository.save(acceptance)
    restored = repository.get_by_id(acceptance.id)

    assert restored == acceptance
    assert restored is not None
    assert restored.evidence_references == acceptance.evidence_references
    assert restored.tags == ("architecture", "review")


def test_malformed_data_surfaces_validation_error(tmp_path: Path) -> None:
    repository = JsonDecisionAcceptanceRepository(tmp_path)
    path = tmp_path / "44444444-4444-4444-4444-444444444444.json"
    path.write_text('{"accepted_by": "owner"}', encoding="utf-8")

    with pytest.raises(ValidationError):
        repository.load_all()


def test_default_path_uses_decision_acceptances_constant() -> None:
    repository = JsonDecisionAcceptanceRepository()

    assert repository._directory == resolve_neural_paths().DECISION_ACCEPTANCES

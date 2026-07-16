from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from neural_engine.core.paths import NeuralPaths
from neural_engine.domain import Decision, EvidenceReference
from neural_engine.infrastructure.json_decision_repository import JsonDecisionRepository

DEFAULT_DECISION_ID = UUID("11111111-1111-1111-1111-111111111111")


def make_decision(
    decision_id: UUID = DEFAULT_DECISION_ID,
    title: str = "Persist Decision",
    **updates: object,
) -> Decision:
    values: dict[str, object] = {
        "id": decision_id,
        "project_key": "NeuralEngine",
        "title": title,
        "objective": "Verify Decision persistence",
        "context_summary": "The Decision foundation needs deterministic JSON storage.",
        "alternatives": ("Use JSON files", "Use another storage format"),
        "proposed_option": "Use JSON files",
        "rationale": "JSON matches current repository conventions.",
        "proposed_by": "repository-test",
        "idempotency_key": f"decision-{decision_id}",
    }
    values.update(updates)
    return Decision.model_validate(values)


def test_save_writes_one_json_file_per_decision(tmp_path: Path) -> None:
    repository = JsonDecisionRepository(tmp_path)
    decision = make_decision()

    repository.save(decision)

    path = tmp_path / f"{decision.id}.json"
    assert path.exists()
    assert Decision.model_validate_json(path.read_text(encoding="utf-8")) == decision


def test_load_all_returns_empty_when_directory_is_missing(tmp_path: Path) -> None:
    repository = JsonDecisionRepository(tmp_path / "missing")

    assert repository.load_all() == []


def test_load_all_returns_decisions_sorted_by_file_name(tmp_path: Path) -> None:
    repository = JsonDecisionRepository(tmp_path)
    later = make_decision(UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"), "Later")
    earlier = make_decision(UUID("00000000-0000-0000-0000-000000000001"), "Earlier")

    repository.save(later)
    repository.save(earlier)

    assert repository.load_all() == [earlier, later]


def test_get_by_id_returns_saved_decision(tmp_path: Path) -> None:
    repository = JsonDecisionRepository(tmp_path)
    decision = make_decision()
    repository.save(decision)

    assert repository.get_by_id(decision.id) == decision


def test_get_by_id_returns_none_for_missing_decision(tmp_path: Path) -> None:
    repository = JsonDecisionRepository(tmp_path)

    assert repository.get_by_id(UUID("22222222-2222-2222-2222-222222222222")) is None


def test_repository_round_trip_preserves_evidence_and_optional_fields(tmp_path: Path) -> None:
    repository = JsonDecisionRepository(tmp_path)
    superseded_id = UUID("33333333-3333-3333-3333-333333333333")
    observation_id = UUID("44444444-4444-4444-4444-444444444444")
    decision = make_decision(
        observation_ids=(observation_id,),
        evidence_references=(
            EvidenceReference(
                kind="agent_review",
                locator=".agent-work/reviews/review.md",
                repository_or_project="NeuralEngine",
                content_hash="sha256:review",
                source="reviewer",
                summary="Architecture finding",
            ),
        ),
        supersedes_decision_id=superseded_id,
        tags=("architecture", "review"),
    )

    repository.save(decision)
    restored = repository.get_by_id(decision.id)

    assert restored == decision
    assert restored is not None
    assert restored.observation_ids == (observation_id,)
    assert restored.supersedes_decision_id == superseded_id
    assert restored.evidence_references[0] == decision.evidence_references[0]
    assert restored.tags == ("architecture", "review")


def test_malformed_decision_data_surfaces_validation_error(tmp_path: Path) -> None:
    repository = JsonDecisionRepository(tmp_path)
    path = tmp_path / "55555555-5555-5555-5555-555555555555.json"
    path.write_text('{"project_key": "NeuralEngine"}', encoding="utf-8")

    with pytest.raises(ValidationError):
        repository.load_all()


def test_repository_default_path_uses_decisions_constant() -> None:
    repository = JsonDecisionRepository()

    assert repository._directory == NeuralPaths.DECISIONS

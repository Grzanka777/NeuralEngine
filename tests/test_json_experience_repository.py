import json
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from neural_engine.domain import (
    DecisionReviewPromotion,
    DecisionReviewPromotionSourceKind,
    DecisionReviewPromotionSourceStatement,
    Experience,
    ExperienceResult,
)
from neural_engine.infrastructure.json_experience_repository import JsonExperienceRepository


def test_save_writes_one_json_file_per_experience(tmp_path: Path) -> None:
    repository = JsonExperienceRepository(tmp_path)
    experience = Experience(
        title="Persist me",
        context="Repository test",
        action="Save experience",
        outcome="JSON file is written",
        result=ExperienceResult.SUCCESS,
    )

    repository.save(experience)

    path = tmp_path / f"{experience.id}.json"
    assert path.exists()
    assert Experience.model_validate_json(path.read_text(encoding="utf-8")) == experience


def test_load_all_returns_saved_experiences_sorted_by_file_name(tmp_path: Path) -> None:
    repository = JsonExperienceRepository(tmp_path)
    first = Experience(
        title="First",
        context="Repository test",
        action="Save first",
        outcome="First file exists",
        result=ExperienceResult.SUCCESS,
    )
    second = Experience(
        title="Second",
        context="Repository test",
        action="Save second",
        outcome="Second file exists",
        result=ExperienceResult.FAILURE,
    )

    repository.save(second)
    repository.save(first)

    assert repository.load_all() == sorted([first, second], key=lambda item: str(item.id))


def test_load_all_returns_empty_list_when_directory_does_not_exist(tmp_path: Path) -> None:
    repository = JsonExperienceRepository(tmp_path / "missing")

    assert repository.load_all() == []


def test_get_by_id_returns_saved_experience(tmp_path: Path) -> None:
    repository = JsonExperienceRepository(tmp_path)
    experience = Experience(
        title="Load me",
        context="Repository test",
        action="Read experience by id",
        outcome="Experience is returned",
        result=ExperienceResult.MIXED,
    )
    repository.save(experience)

    assert repository.get_by_id(experience.id) == experience


def test_get_by_id_returns_none_when_file_is_missing(tmp_path: Path) -> None:
    repository = JsonExperienceRepository(tmp_path)
    experience = Experience(
        title="Missing",
        context="Repository test",
        action="Read missing experience",
        outcome="No experience is returned",
        result=ExperienceResult.UNKNOWN,
    )

    assert repository.get_by_id(experience.id) is None


def test_old_json_without_promotion_loads_and_round_trips_without_inventing_provenance(
    tmp_path: Path,
) -> None:
    experience = Experience(
        title="Legacy",
        context="Before promotion schema",
        action="Load old JSON",
        outcome="Compatibility preserved",
        result=ExperienceResult.SUCCESS,
    )
    legacy_json = experience.model_dump_json(exclude={"decision_review_promotion"})
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / f"{experience.id}.json").write_text(legacy_json, encoding="utf-8")
    repository = JsonExperienceRepository(tmp_path)

    loaded = repository.get_by_id(experience.id)

    assert loaded is not None
    assert loaded.decision_review_promotion is None
    repository.save(loaded)
    reloaded = repository.get_by_id(experience.id)
    assert reloaded is not None
    assert reloaded.decision_review_promotion is None


def test_promoted_experience_round_trips_exact_ordered_provenance(tmp_path: Path) -> None:
    repository = JsonExperienceRepository(tmp_path)
    experience = Experience(
        title="Promoted",
        context="Review",
        action="Promote",
        outcome="Stored",
        result=ExperienceResult.MIXED,
        decision_review_promotion=DecisionReviewPromotion(
            decision_review_id=UUID("11111111-1111-1111-1111-111111111111"),
            source_statements=(
                DecisionReviewPromotionSourceStatement(
                    kind=DecisionReviewPromotionSourceKind.CANDIDATE_LESSON,
                    index=1,
                    text="Second candidate",
                ),
                DecisionReviewPromotionSourceStatement(
                    kind=DecisionReviewPromotionSourceKind.FINDING,
                    index=0,
                    text="First",
                ),
            ),
            promoted_by="owner",
            promotion_reason="Explicit learning decision",
            idempotency_key="promotion-json",
        ),
    )

    repository.save(experience)

    assert repository.get_by_id(experience.id) == experience
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_malformed_nested_promotion_fails_visibly(tmp_path: Path) -> None:
    experience = Experience(
        title="Malformed",
        context="Review",
        action="Load",
        outcome="Rejected",
        result=ExperienceResult.FAILURE,
    )
    payload = experience.model_dump(mode="json")
    payload["decision_review_promotion"] = {
        "decision_review_id": "11111111-1111-1111-1111-111111111111",
        "source_statements": [],
        "promoted_by": "owner",
        "promotion_reason": "reason",
        "idempotency_key": "key",
    }
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / f"{experience.id}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValidationError):
        JsonExperienceRepository(tmp_path).get_by_id(experience.id)

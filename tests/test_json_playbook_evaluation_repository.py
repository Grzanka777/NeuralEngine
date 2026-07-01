from pathlib import Path
from uuid import UUID

from neural_engine.domain import PlaybookEffectiveness, PlaybookEvaluation
from neural_engine.infrastructure.json_playbook_evaluation_repository import (
    JsonPlaybookEvaluationRepository,
)


def make_evaluation(finding: str = "Persist evaluation") -> PlaybookEvaluation:
    return PlaybookEvaluation(
        run_id=UUID("11111111-1111-1111-1111-111111111111"),
        effectiveness=PlaybookEffectiveness.EFFECTIVE,
        findings=[finding],
    )


def test_save_writes_one_json_file_per_playbook_evaluation(tmp_path: Path) -> None:
    repository = JsonPlaybookEvaluationRepository(tmp_path)
    evaluation = make_evaluation()

    repository.save(evaluation)

    path = tmp_path / f"{evaluation.id}.json"
    assert path.exists()
    assert PlaybookEvaluation.model_validate_json(path.read_text(encoding="utf-8")) == evaluation


def test_load_all_returns_saved_evaluations_sorted_by_file_name(tmp_path: Path) -> None:
    repository = JsonPlaybookEvaluationRepository(tmp_path)
    first = make_evaluation("First")
    second = make_evaluation("Second")

    repository.save(second)
    repository.save(first)

    assert repository.load_all() == sorted([first, second], key=lambda item: str(item.id))


def test_load_all_returns_empty_list_when_directory_does_not_exist(tmp_path: Path) -> None:
    repository = JsonPlaybookEvaluationRepository(tmp_path / "missing")

    assert repository.load_all() == []


def test_get_by_id_returns_saved_evaluation(tmp_path: Path) -> None:
    repository = JsonPlaybookEvaluationRepository(tmp_path)
    evaluation = make_evaluation("Load me")
    repository.save(evaluation)

    assert repository.get_by_id(evaluation.id) == evaluation


def test_get_by_id_returns_none_when_file_is_missing(tmp_path: Path) -> None:
    repository = JsonPlaybookEvaluationRepository(tmp_path)
    evaluation = make_evaluation("Missing")

    assert repository.get_by_id(evaluation.id) is None

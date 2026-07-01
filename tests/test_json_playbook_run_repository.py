from pathlib import Path
from uuid import UUID

from neural_engine.domain import PlaybookRun
from neural_engine.infrastructure.json_playbook_run_repository import (
    JsonPlaybookRunRepository,
)


def make_run(situation: str = "Persist playbook run") -> PlaybookRun:
    return PlaybookRun(
        playbook_id=UUID("11111111-1111-1111-1111-111111111111"),
        situation=situation,
        actions_taken=["Applied playbook manually"],
        outcome="Outcome was recorded",
        success=True,
    )


def test_save_writes_one_json_file_per_playbook_run(tmp_path: Path) -> None:
    repository = JsonPlaybookRunRepository(tmp_path)
    run = make_run()

    repository.save(run)

    path = tmp_path / f"{run.id}.json"
    assert path.exists()
    assert PlaybookRun.model_validate_json(path.read_text(encoding="utf-8")) == run


def test_load_all_returns_saved_runs_sorted_by_file_name(tmp_path: Path) -> None:
    repository = JsonPlaybookRunRepository(tmp_path)
    first = make_run("First")
    second = make_run("Second")

    repository.save(second)
    repository.save(first)

    assert repository.load_all() == sorted([first, second], key=lambda item: str(item.id))


def test_load_all_returns_empty_list_when_directory_does_not_exist(tmp_path: Path) -> None:
    repository = JsonPlaybookRunRepository(tmp_path / "missing")

    assert repository.load_all() == []


def test_get_by_id_returns_saved_run(tmp_path: Path) -> None:
    repository = JsonPlaybookRunRepository(tmp_path)
    run = make_run("Load me")
    repository.save(run)

    assert repository.get_by_id(run.id) == run


def test_get_by_id_returns_none_when_file_is_missing(tmp_path: Path) -> None:
    repository = JsonPlaybookRunRepository(tmp_path)
    run = make_run("Missing")

    assert repository.get_by_id(run.id) is None

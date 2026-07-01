from pathlib import Path
from uuid import UUID

from neural_engine.domain import Playbook
from neural_engine.infrastructure.json_playbook_repository import JsonPlaybookRepository


def make_playbook(title: str = "Persist playbook") -> Playbook:
    return Playbook(
        title=title,
        situation="Repository test situation",
        objective="Persist and load a playbook",
        steps=["Save playbook"],
        success_criteria=["Playbook is readable"],
        knowledge_ids=[UUID("11111111-1111-1111-1111-111111111111")],
    )


def test_save_writes_one_json_file_per_playbook(tmp_path: Path) -> None:
    repository = JsonPlaybookRepository(tmp_path)
    playbook = make_playbook()

    repository.save(playbook)

    path = tmp_path / f"{playbook.id}.json"
    assert path.exists()
    assert Playbook.model_validate_json(path.read_text(encoding="utf-8")) == playbook


def test_load_all_returns_saved_playbooks_sorted_by_file_name(tmp_path: Path) -> None:
    repository = JsonPlaybookRepository(tmp_path)
    first = make_playbook("First")
    second = make_playbook("Second")

    repository.save(second)
    repository.save(first)

    assert repository.load_all() == sorted([first, second], key=lambda item: str(item.id))


def test_load_all_returns_empty_list_when_directory_does_not_exist(tmp_path: Path) -> None:
    repository = JsonPlaybookRepository(tmp_path / "missing")

    assert repository.load_all() == []


def test_get_by_id_returns_saved_playbook(tmp_path: Path) -> None:
    repository = JsonPlaybookRepository(tmp_path)
    playbook = make_playbook("Load me")
    repository.save(playbook)

    assert repository.get_by_id(playbook.id) == playbook


def test_get_by_id_returns_none_when_file_is_missing(tmp_path: Path) -> None:
    repository = JsonPlaybookRepository(tmp_path)
    playbook = make_playbook("Missing")

    assert repository.get_by_id(playbook.id) is None

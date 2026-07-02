from pathlib import Path
from uuid import UUID

from neural_engine.domain import PlaybookRevision
from neural_engine.infrastructure.json_playbook_revision_repository import (
    JsonPlaybookRevisionRepository,
)


def make_revision(title: str = "Persist revision") -> PlaybookRevision:
    return PlaybookRevision(
        playbook_id=UUID("11111111-1111-1111-1111-111111111111"),
        proposal_id=UUID("22222222-2222-2222-2222-222222222222"),
        title=title,
        situation="Repository test situation",
        objective="Persist a candidate revision",
        steps=["Save revision"],
        success_criteria=["Revision is readable"],
        knowledge_ids=[UUID("33333333-3333-3333-3333-333333333333")],
    )


def test_save_writes_one_json_file_per_playbook_revision(tmp_path: Path) -> None:
    repository = JsonPlaybookRevisionRepository(tmp_path)
    revision = make_revision()

    repository.save(revision)

    path = tmp_path / f"{revision.id}.json"
    assert path.exists()
    assert PlaybookRevision.model_validate_json(path.read_text(encoding="utf-8")) == revision


def test_load_all_returns_saved_revisions_sorted_by_file_name(tmp_path: Path) -> None:
    repository = JsonPlaybookRevisionRepository(tmp_path)
    first = make_revision("First")
    second = make_revision("Second")

    repository.save(second)
    repository.save(first)

    assert repository.load_all() == sorted([first, second], key=lambda item: str(item.id))


def test_load_all_returns_empty_list_when_directory_does_not_exist(tmp_path: Path) -> None:
    repository = JsonPlaybookRevisionRepository(tmp_path / "missing")

    assert repository.load_all() == []


def test_get_by_id_returns_saved_revision(tmp_path: Path) -> None:
    repository = JsonPlaybookRevisionRepository(tmp_path)
    revision = make_revision("Load me")
    repository.save(revision)

    assert repository.get_by_id(revision.id) == revision


def test_get_by_id_returns_none_when_file_is_missing(tmp_path: Path) -> None:
    repository = JsonPlaybookRevisionRepository(tmp_path)
    revision = make_revision("Missing")

    assert repository.get_by_id(revision.id) is None

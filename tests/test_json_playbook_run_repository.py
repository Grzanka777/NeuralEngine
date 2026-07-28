import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from neural_engine.domain import PlaybookRun
from neural_engine.infrastructure.json_playbook_run_repository import (
    JsonPlaybookRunRepository,
)
from neural_engine.ports.playbook_run_repository import (
    PlaybookRunIdentityMismatchError,
    PlaybookRunPersistenceConflictError,
    PlaybookRunStoredDataError,
)

RUN_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
PLAYBOOK_ID = UUID("11111111-1111-1111-1111-111111111111")
REVISION_ID = UUID("22222222-2222-2222-2222-222222222222")


def make_run(situation: str = "Persist playbook run") -> PlaybookRun:
    return PlaybookRun(
        id=RUN_ID,
        timestamp=datetime(2026, 7, 28, 10, 0, tzinfo=UTC),
        playbook_id=PLAYBOOK_ID,
        situation=situation,
        actions_taken=["Applied playbook manually"],
        outcome="Outcome was recorded",
        success=True,
        evidence=["Repository evidence"],
        notes="Repository fixture",
        tags=["persistence", "run"],
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
    second = make_run("Second").model_copy(
        update={"id": UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")}
    )

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


def test_revision_relation_round_trips(tmp_path: Path) -> None:
    repository = JsonPlaybookRunRepository(tmp_path)
    run = make_run().model_copy(update={"revision_id": REVISION_ID})

    repository.save(run)

    assert repository.get_by_id(run.id) == run


def test_old_json_without_revision_relation_loads_as_absent(tmp_path: Path) -> None:
    repository = JsonPlaybookRunRepository(tmp_path)
    run = make_run()
    payload = run.model_dump(mode="json")
    payload.pop("revision_id")
    (tmp_path / f"{run.id}.json").write_text(json.dumps(payload), encoding="utf-8")

    loaded = repository.get_by_id(run.id)

    assert loaded is not None
    assert loaded.revision_id is None


def test_malformed_revision_relation_is_rejected(tmp_path: Path) -> None:
    repository = JsonPlaybookRunRepository(tmp_path)
    run = make_run()
    payload = run.model_dump(mode="json")
    payload["revision_id"] = "not-a-uuid"
    (tmp_path / f"{run.id}.json").write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(PlaybookRunStoredDataError):
        repository.get_by_id(run.id)


def test_identical_replay_preserves_bytes_and_filesystem_metadata(tmp_path: Path) -> None:
    repository = JsonPlaybookRunRepository(tmp_path)
    run = make_run("Replay")
    repository.save(run)
    path = tmp_path / f"{run.id}.json"
    legacy_bytes = run.model_dump_json().encode()
    path.write_bytes(legacy_bytes)
    before = path.stat()

    repository.save(run.model_copy(deep=True))

    after = path.stat()
    assert path.read_bytes() == legacy_bytes
    assert (
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    ) == (
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    assert repository.get_by_id(run.id) == run


@pytest.mark.parametrize(
    "updates",
    [
        {"timestamp": datetime(2026, 7, 28, 11, 0, tzinfo=UTC)},
        {"playbook_id": UUID("33333333-3333-3333-3333-333333333333")},
        {"revision_id": REVISION_ID},
        {"situation": "Changed situation"},
        {"actions_taken": ["Changed action"]},
        {"outcome": "Changed outcome"},
        {"success": False},
        {"evidence": ["Changed evidence"]},
        {"notes": "Changed notes"},
        {"tags": ["run", "persistence"]},
    ],
    ids=[
        "timestamp",
        "playbook-id",
        "revision-id",
        "situation",
        "actions",
        "outcome",
        "success",
        "evidence",
        "notes",
        "tags",
    ],
)
def test_same_id_different_complete_payload_conflicts_and_preserves_original(
    tmp_path: Path,
    updates: dict[str, object],
) -> None:
    repository = JsonPlaybookRunRepository(tmp_path)
    original = make_run()
    repository.save(original)
    path = tmp_path / f"{original.id}.json"
    original_bytes = path.read_bytes()
    before = path.stat()

    with pytest.raises(PlaybookRunPersistenceConflictError) as error:
        repository.save(original.model_copy(update=updates))

    after = path.stat()
    assert error.value.run_id == original.id
    assert path.read_bytes() == original_bytes
    assert (
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    ) == (
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    assert repository.get_by_id(original.id) == original


@pytest.mark.parametrize(
    "corrupt_bytes",
    [
        b"{not valid json",
        b'{"id":"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"}',
    ],
    ids=["malformed-json", "invalid-model"],
)
def test_corrupt_existing_content_is_not_repaired_or_overwritten(
    tmp_path: Path,
    corrupt_bytes: bytes,
) -> None:
    repository = JsonPlaybookRunRepository(tmp_path)
    run = make_run("Collision")
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / f"{run.id}.json"
    path.write_bytes(corrupt_bytes)
    before = path.stat()

    with pytest.raises(PlaybookRunStoredDataError):
        repository.save(run)

    after = path.stat()
    assert path.read_bytes() == corrupt_bytes
    assert (
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    ) == (
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )


def test_save_does_not_repair_or_replace_identity_mismatch(tmp_path: Path) -> None:
    repository = JsonPlaybookRunRepository(tmp_path)
    candidate = make_run("Candidate")
    mismatched = candidate.model_copy(update={"id": UUID("44444444-4444-4444-4444-444444444444")})
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / f"{candidate.id}.json"
    mismatched_bytes = mismatched.model_dump_json().encode()
    path.write_bytes(mismatched_bytes)
    before = path.stat()

    with pytest.raises(PlaybookRunIdentityMismatchError) as error:
        repository.save(candidate)

    after = path.stat()
    assert error.value.expected_id == candidate.id
    assert error.value.actual_id == mismatched.id
    assert path.read_bytes() == mismatched_bytes
    assert (
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    ) == (
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )


def test_get_by_id_rejects_filename_payload_identity_mismatch(tmp_path: Path) -> None:
    repository = JsonPlaybookRunRepository(tmp_path)
    expected_id = UUID("55555555-5555-5555-5555-555555555555")
    stored = make_run("Mismatched")
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / f"{expected_id}.json").write_text(
        stored.model_dump_json(),
        encoding="utf-8",
    )

    with pytest.raises(PlaybookRunIdentityMismatchError) as error:
        repository.get_by_id(expected_id)

    assert error.value.expected_id == expected_id
    assert error.value.actual_id == stored.id


def test_load_all_rejects_filename_payload_identity_mismatch(tmp_path: Path) -> None:
    repository = JsonPlaybookRunRepository(tmp_path)
    expected_id = UUID("66666666-6666-6666-6666-666666666666")
    stored = make_run("Mismatched")
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / f"{expected_id}.json").write_text(
        stored.model_dump_json(),
        encoding="utf-8",
    )

    with pytest.raises(PlaybookRunIdentityMismatchError):
        repository.load_all()


def test_load_all_rejects_non_uuid_filename_stem(tmp_path: Path) -> None:
    repository = JsonPlaybookRunRepository(tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "not-a-uuid.json").write_text(
        make_run().model_dump_json(),
        encoding="utf-8",
    )

    with pytest.raises(PlaybookRunStoredDataError) as error:
        repository.load_all()

    assert error.value.identity == "not-a-uuid"


def test_valid_existing_json_requires_no_migration(tmp_path: Path) -> None:
    repository = JsonPlaybookRunRepository(tmp_path)
    run = make_run("Existing")
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / f"{run.id}.json"
    existing_bytes = run.model_dump_json().encode()
    path.write_bytes(existing_bytes)

    assert repository.get_by_id(run.id) == run
    assert repository.load_all() == [run]
    assert path.read_bytes() == existing_bytes


def test_repository_owned_temporary_files_are_cleaned_up(tmp_path: Path) -> None:
    repository = JsonPlaybookRunRepository(tmp_path)
    run = make_run("Temporary cleanup")

    repository.save(run)
    repository.save(run.model_copy(deep=True))

    assert list(tmp_path.glob(f".{run.id}.*.tmp")) == []


def test_conflict_cleans_up_repository_owned_temporary_file(tmp_path: Path) -> None:
    repository = JsonPlaybookRunRepository(tmp_path)
    run = make_run("Temporary cleanup conflict")
    repository.save(run)

    with pytest.raises(PlaybookRunPersistenceConflictError):
        repository.save(run.model_copy(update={"outcome": "Different"}))

    assert list(tmp_path.glob(f".{run.id}.*.tmp")) == []

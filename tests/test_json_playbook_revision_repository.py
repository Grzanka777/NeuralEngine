from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from neural_engine.domain import PlaybookRevision
from neural_engine.infrastructure.json_playbook_revision_repository import (
    JsonPlaybookRevisionRepository,
)
from neural_engine.ports.playbook_revision_repository import (
    PlaybookRevisionIdentityMismatchError,
    PlaybookRevisionPersistenceConflictError,
    PlaybookRevisionStoredDataError,
)

REVISION_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
PLAYBOOK_ID = UUID("11111111-1111-1111-1111-111111111111")
PROPOSAL_ID = UUID("22222222-2222-2222-2222-222222222222")
KNOWLEDGE_ID = UUID("33333333-3333-3333-3333-333333333333")


def make_revision(title: str = "Persist revision") -> PlaybookRevision:
    return PlaybookRevision(
        id=REVISION_ID,
        timestamp=datetime(2026, 7, 27, 10, 0, tzinfo=UTC),
        playbook_id=PLAYBOOK_ID,
        proposal_id=PROPOSAL_ID,
        title=title,
        situation="Repository test situation",
        objective="Persist a candidate revision",
        steps=["Inspect evidence", "Save revision"],
        success_criteria=["Revision is readable", "History is stable"],
        knowledge_ids=[KNOWLEDGE_ID],
        notes="Repository fixture",
        tags=["persistence", "revision"],
    )


def test_save_writes_one_json_file_per_playbook_revision(tmp_path: Path) -> None:
    repository = JsonPlaybookRevisionRepository(tmp_path)
    revision = make_revision()

    repository.save(revision)

    path = tmp_path / f"{revision.id}.json"
    assert path.exists()
    assert PlaybookRevision.model_validate_json(path.read_text(encoding="utf-8")) == revision
    assert repository.get_by_id(revision.id) == revision


def test_load_all_returns_saved_revisions_sorted_by_file_name(tmp_path: Path) -> None:
    repository = JsonPlaybookRevisionRepository(tmp_path)
    first = make_revision("First")
    second = make_revision("Second").model_copy(
        update={"id": UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")}
    )

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

    assert repository.get_by_id(REVISION_ID) is None


def test_identical_replay_succeeds_without_rewriting_existing_file(tmp_path: Path) -> None:
    repository = JsonPlaybookRevisionRepository(tmp_path)
    revision = make_revision("Replay")
    repository.save(revision)
    path = tmp_path / f"{revision.id}.json"
    legacy_bytes = revision.model_dump_json().encode()
    path.write_bytes(legacy_bytes)

    repository.save(revision.model_copy(deep=True))

    assert path.read_bytes() == legacy_bytes
    assert repository.get_by_id(revision.id) == revision


@pytest.mark.parametrize(
    "updates",
    [
        {"timestamp": datetime(2026, 7, 27, 11, 0, tzinfo=UTC)},
        {"playbook_id": UUID("44444444-4444-4444-4444-444444444444")},
        {"proposal_id": UUID("55555555-5555-5555-5555-555555555555")},
        {"title": "Changed title"},
        {"situation": "Changed situation"},
        {"objective": "Changed objective"},
        {"steps": ["Save revision", "Inspect evidence"]},
        {"success_criteria": ["History is stable", "Revision is readable"]},
        {
            "knowledge_ids": [
                UUID("66666666-6666-6666-6666-666666666666"),
                KNOWLEDGE_ID,
            ]
        },
        {"notes": "Changed notes"},
        {"tags": ["revision", "persistence"]},
    ],
    ids=[
        "timestamp",
        "playbook-id",
        "proposal-id",
        "title",
        "situation",
        "objective",
        "steps",
        "success-criteria",
        "knowledge-ids",
        "notes",
        "tags",
    ],
)
def test_same_id_different_complete_payload_conflicts_and_preserves_original_bytes(
    tmp_path: Path,
    updates: dict[str, object],
) -> None:
    repository = JsonPlaybookRevisionRepository(tmp_path)
    original = make_revision()
    repository.save(original)
    path = tmp_path / f"{original.id}.json"
    original_bytes = path.read_bytes()

    with pytest.raises(PlaybookRevisionPersistenceConflictError) as error:
        repository.save(original.model_copy(update=updates))

    assert error.value.revision_id == original.id
    assert path.read_bytes() == original_bytes
    assert repository.get_by_id(original.id) == original


def test_nested_list_mutation_followed_by_same_id_save_conflicts(tmp_path: Path) -> None:
    repository = JsonPlaybookRevisionRepository(tmp_path)
    original = make_revision()
    repository.save(original)
    path = tmp_path / f"{original.id}.json"
    original_bytes = path.read_bytes()
    mutated = original.model_copy(deep=True)
    mutated.steps.append("Mutated after construction")

    with pytest.raises(PlaybookRevisionPersistenceConflictError):
        repository.save(mutated)

    assert path.read_bytes() == original_bytes


def test_same_id_model_copy_with_changed_content_conflicts(tmp_path: Path) -> None:
    repository = JsonPlaybookRevisionRepository(tmp_path)
    original = make_revision()
    repository.save(original)

    with pytest.raises(PlaybookRevisionPersistenceConflictError):
        repository.save(original.model_copy(update={"title": "Copied replacement"}))


def test_same_content_with_new_id_is_stored_as_distinct_revision(tmp_path: Path) -> None:
    repository = JsonPlaybookRevisionRepository(tmp_path)
    original = make_revision("Shared content")
    distinct = original.model_copy(update={"id": UUID("77777777-7777-7777-7777-777777777777")})

    repository.save(original)
    repository.save(distinct)

    assert repository.load_all() == sorted(
        [original, distinct],
        key=lambda item: str(item.id),
    )


@pytest.mark.parametrize(
    "corrupt_bytes",
    [
        b"{not valid json",
        b'{"id":"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"}',
    ],
    ids=["malformed-json", "invalid-model"],
)
def test_corrupt_existing_content_is_not_overwritten(
    tmp_path: Path,
    corrupt_bytes: bytes,
) -> None:
    repository = JsonPlaybookRevisionRepository(tmp_path)
    revision = make_revision("Collision")
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / f"{revision.id}.json"
    path.write_bytes(corrupt_bytes)

    with pytest.raises(PlaybookRevisionStoredDataError):
        repository.save(revision)

    assert path.read_bytes() == corrupt_bytes


def test_get_by_id_rejects_filename_payload_identity_mismatch(tmp_path: Path) -> None:
    repository = JsonPlaybookRevisionRepository(tmp_path)
    expected_id = UUID("88888888-8888-8888-8888-888888888888")
    stored = make_revision("Mismatched")
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / f"{expected_id}.json").write_text(
        stored.model_dump_json(),
        encoding="utf-8",
    )

    with pytest.raises(PlaybookRevisionIdentityMismatchError) as error:
        repository.get_by_id(expected_id)

    assert error.value.expected_id == expected_id
    assert error.value.actual_id == stored.id


def test_load_all_rejects_filename_payload_identity_mismatch(tmp_path: Path) -> None:
    repository = JsonPlaybookRevisionRepository(tmp_path)
    expected_id = UUID("99999999-9999-9999-9999-999999999999")
    stored = make_revision("Mismatched")
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / f"{expected_id}.json").write_text(
        stored.model_dump_json(),
        encoding="utf-8",
    )

    with pytest.raises(PlaybookRevisionIdentityMismatchError):
        repository.load_all()


def test_save_does_not_repair_or_replace_identity_mismatch(tmp_path: Path) -> None:
    repository = JsonPlaybookRevisionRepository(tmp_path)
    candidate = make_revision("Candidate")
    mismatched = candidate.model_copy(update={"id": UUID("abababab-abab-abab-abab-abababababab")})
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / f"{candidate.id}.json"
    mismatched_bytes = mismatched.model_dump_json().encode()
    path.write_bytes(mismatched_bytes)

    with pytest.raises(PlaybookRevisionIdentityMismatchError):
        repository.save(candidate)

    assert path.read_bytes() == mismatched_bytes


def test_load_all_rejects_non_uuid_filename_stem(tmp_path: Path) -> None:
    repository = JsonPlaybookRevisionRepository(tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "not-a-uuid.json").write_text(
        make_revision().model_dump_json(),
        encoding="utf-8",
    )

    with pytest.raises(PlaybookRevisionStoredDataError) as error:
        repository.load_all()

    assert error.value.identity == "not-a-uuid"


def test_valid_legacy_json_requires_no_migration(tmp_path: Path) -> None:
    repository = JsonPlaybookRevisionRepository(tmp_path)
    revision = make_revision("Legacy")
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / f"{revision.id}.json"
    legacy_bytes = revision.model_dump_json().encode()
    path.write_bytes(legacy_bytes)

    assert repository.get_by_id(revision.id) == revision
    assert repository.load_all() == [revision]
    assert path.read_bytes() == legacy_bytes

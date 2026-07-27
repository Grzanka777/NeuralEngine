from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from neural_engine.domain import Knowledge, KnowledgeConfidence
from neural_engine.infrastructure.json_knowledge_repository import JsonKnowledgeRepository
from neural_engine.ports.knowledge_repository import (
    KnowledgeIdentityMismatchError,
    KnowledgePersistenceConflictError,
    KnowledgeStoredDataError,
)


def make_knowledge(statement: str = "Persist knowledge") -> Knowledge:
    return Knowledge(
        statement=statement,
        rationale="Repository test rationale",
        confidence=KnowledgeConfidence.MEDIUM,
        experience_ids=[UUID("11111111-1111-1111-1111-111111111111")],
    )


def test_save_writes_one_json_file_per_knowledge(tmp_path: Path) -> None:
    repository = JsonKnowledgeRepository(tmp_path)
    knowledge = make_knowledge()

    repository.save(knowledge)

    path = tmp_path / f"{knowledge.id}.json"
    assert path.exists()
    assert Knowledge.model_validate_json(path.read_text(encoding="utf-8")) == knowledge


def test_load_all_returns_saved_knowledge_sorted_by_file_name(tmp_path: Path) -> None:
    repository = JsonKnowledgeRepository(tmp_path)
    first = make_knowledge("First")
    second = make_knowledge("Second")

    repository.save(second)
    repository.save(first)

    assert repository.load_all() == sorted([first, second], key=lambda item: str(item.id))


def test_load_all_returns_empty_list_when_directory_does_not_exist(tmp_path: Path) -> None:
    repository = JsonKnowledgeRepository(tmp_path / "missing")

    assert repository.load_all() == []


def test_get_by_id_returns_saved_knowledge(tmp_path: Path) -> None:
    repository = JsonKnowledgeRepository(tmp_path)
    knowledge = make_knowledge("Load me")
    repository.save(knowledge)

    assert repository.get_by_id(knowledge.id) == knowledge


def test_get_by_id_returns_none_when_file_is_missing(tmp_path: Path) -> None:
    repository = JsonKnowledgeRepository(tmp_path)
    knowledge = make_knowledge("Missing")

    assert repository.get_by_id(knowledge.id) is None


def test_identical_replay_succeeds_without_rewriting_existing_file(tmp_path: Path) -> None:
    repository = JsonKnowledgeRepository(tmp_path)
    knowledge = make_knowledge("Replay")
    repository.save(knowledge)
    path = tmp_path / f"{knowledge.id}.json"
    legacy_bytes = knowledge.model_dump_json().encode()
    path.write_bytes(legacy_bytes)

    repository.save(knowledge.model_copy(deep=True))

    assert path.read_bytes() == legacy_bytes
    assert repository.get_by_id(knowledge.id) == knowledge


@pytest.mark.parametrize(
    "updates",
    [
        {"statement": "Changed statement"},
        {"rationale": "Changed rationale"},
        {"confidence": KnowledgeConfidence.HIGH},
        {"timestamp": datetime(2025, 1, 1, tzinfo=UTC)},
        {
            "experience_ids": [
                UUID("22222222-2222-2222-2222-222222222222"),
                UUID("11111111-1111-1111-1111-111111111111"),
            ]
        },
        {"tags": ["changed", "order"]},
    ],
    ids=["statement", "rationale", "confidence", "timestamp", "experience-ids", "tags"],
)
def test_same_id_different_payload_conflicts_and_preserves_original_bytes(
    tmp_path: Path,
    updates: dict[str, object],
) -> None:
    repository = JsonKnowledgeRepository(tmp_path)
    original = make_knowledge()
    repository.save(original)
    path = tmp_path / f"{original.id}.json"
    original_bytes = path.read_bytes()

    with pytest.raises(KnowledgePersistenceConflictError) as error:
        repository.save(original.model_copy(update=updates))

    assert error.value.knowledge_id == original.id
    assert path.read_bytes() == original_bytes
    assert repository.get_by_id(original.id) == original


def test_same_content_with_new_id_is_stored_as_distinct_knowledge(tmp_path: Path) -> None:
    repository = JsonKnowledgeRepository(tmp_path)
    original = make_knowledge("Shared content")
    distinct = original.model_copy(update={"id": UUID("33333333-3333-3333-3333-333333333333")})

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
        b'{"id":"99999999-9999-9999-9999-999999999999"}',
    ],
    ids=["malformed-json", "invalid-model"],
)
def test_corrupt_existing_content_is_not_overwritten(
    tmp_path: Path,
    corrupt_bytes: bytes,
) -> None:
    repository = JsonKnowledgeRepository(tmp_path)
    knowledge = make_knowledge("Collision")
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / f"{knowledge.id}.json"
    path.write_bytes(corrupt_bytes)

    with pytest.raises(KnowledgeStoredDataError):
        repository.save(knowledge)

    assert path.read_bytes() == corrupt_bytes


def test_get_by_id_rejects_filename_payload_identity_mismatch(tmp_path: Path) -> None:
    repository = JsonKnowledgeRepository(tmp_path)
    expected_id = UUID("44444444-4444-4444-4444-444444444444")
    stored = make_knowledge("Mismatched").model_copy(
        update={"id": UUID("55555555-5555-5555-5555-555555555555")}
    )
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / f"{expected_id}.json").write_text(
        stored.model_dump_json(),
        encoding="utf-8",
    )

    with pytest.raises(KnowledgeIdentityMismatchError) as error:
        repository.get_by_id(expected_id)

    assert error.value.expected_id == expected_id
    assert error.value.actual_id == stored.id


def test_load_all_rejects_filename_payload_identity_mismatch(tmp_path: Path) -> None:
    repository = JsonKnowledgeRepository(tmp_path)
    expected_id = UUID("66666666-6666-6666-6666-666666666666")
    stored = make_knowledge("Mismatched").model_copy(
        update={"id": UUID("77777777-7777-7777-7777-777777777777")}
    )
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / f"{expected_id}.json").write_text(
        stored.model_dump_json(),
        encoding="utf-8",
    )

    with pytest.raises(KnowledgeIdentityMismatchError):
        repository.load_all()


def test_save_does_not_repair_or_replace_identity_mismatch(tmp_path: Path) -> None:
    repository = JsonKnowledgeRepository(tmp_path)
    candidate = make_knowledge("Candidate").model_copy(
        update={"id": UUID("88888888-8888-8888-8888-888888888888")}
    )
    mismatched = make_knowledge("Existing mismatch")
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / f"{candidate.id}.json"
    mismatched_bytes = mismatched.model_dump_json().encode()
    path.write_bytes(mismatched_bytes)

    with pytest.raises(KnowledgeIdentityMismatchError):
        repository.save(candidate)

    assert path.read_bytes() == mismatched_bytes

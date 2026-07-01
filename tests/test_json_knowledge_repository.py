from pathlib import Path
from uuid import UUID

from neural_engine.domain import Knowledge, KnowledgeConfidence
from neural_engine.infrastructure.json_knowledge_repository import JsonKnowledgeRepository


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

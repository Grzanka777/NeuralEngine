from pathlib import Path

from neural_engine.domain import Experience, ExperienceResult
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

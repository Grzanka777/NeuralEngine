from pathlib import Path
from uuid import UUID

from neural_engine.core.paths import NeuralPaths
from neural_engine.domain import PlaybookRevisionApplication
from neural_engine.infrastructure.json_playbook_revision_application_repository import (
    JsonPlaybookRevisionApplicationRepository,
)


def make_application(
    reason: str = "Persist application",
    applied_by: str | None = None,
    notes: str | None = None,
    tags: tuple[str, ...] = (),
    source_activation_id: UUID | None = None,
    idempotency_key: str | None = None,
) -> PlaybookRevisionApplication:
    return PlaybookRevisionApplication(
        playbook_id=UUID("11111111-1111-1111-1111-111111111111"),
        revision_id=UUID("22222222-2222-2222-2222-222222222222"),
        proposal_id=UUID("33333333-3333-3333-3333-333333333333"),
        reason=reason,
        applied_by=applied_by,
        notes=notes,
        tags=tags,
        source_activation_id=source_activation_id,
        idempotency_key=idempotency_key,
    )


def test_save_writes_one_json_file_per_playbook_revision_application(
    tmp_path: Path,
) -> None:
    repository = JsonPlaybookRevisionApplicationRepository(tmp_path)
    application = make_application()

    repository.save(application)

    path = tmp_path / f"{application.id}.json"
    assert path.exists()
    assert (
        PlaybookRevisionApplication.model_validate_json(path.read_text(encoding="utf-8"))
        == application
    )


def test_load_all_returns_empty_list_when_directory_does_not_exist(tmp_path: Path) -> None:
    repository = JsonPlaybookRevisionApplicationRepository(tmp_path / "missing")

    assert repository.load_all() == []


def test_load_all_returns_saved_applications_sorted_by_file_name(tmp_path: Path) -> None:
    repository = JsonPlaybookRevisionApplicationRepository(tmp_path)
    first = make_application("First")
    second = make_application("Second")

    repository.save(second)
    repository.save(first)

    assert repository.load_all() == sorted([first, second], key=lambda item: str(item.id))


def test_get_by_id_returns_saved_application(tmp_path: Path) -> None:
    repository = JsonPlaybookRevisionApplicationRepository(tmp_path)
    application = make_application("Load me")
    repository.save(application)

    assert repository.get_by_id(application.id) == application


def test_get_by_id_returns_none_when_file_is_missing(tmp_path: Path) -> None:
    repository = JsonPlaybookRevisionApplicationRepository(tmp_path)
    application = make_application("Missing")

    assert repository.get_by_id(application.id) is None


def test_save_updated_application_overwrites_same_json_file(tmp_path: Path) -> None:
    repository = JsonPlaybookRevisionApplicationRepository(tmp_path)
    application = make_application("Update notes")
    repository.save(application)

    updated = application.model_copy(update={"notes": "Updated notes"})
    repository.save(updated)

    files = list(tmp_path.glob("*.json"))
    assert files == [tmp_path / f"{application.id}.json"]
    assert repository.get_by_id(application.id) == updated


def test_repository_persists_and_restores_optional_fields_and_timestamp(
    tmp_path: Path,
) -> None:
    repository = JsonPlaybookRevisionApplicationRepository(tmp_path)
    source_activation_id = UUID("44444444-4444-4444-4444-444444444444")
    application = make_application(
        reason="Record explicit application",
        applied_by="manual-review",
        notes="Foundation record",
        tags=("manual", "application"),
        source_activation_id=source_activation_id,
        idempotency_key="apply-1",
    )

    repository.save(application)
    restored = repository.get_by_id(application.id)

    assert restored == application
    assert restored is not None
    assert restored.applied_at == application.applied_at
    assert restored.applied_by == "manual-review"
    assert restored.notes == "Foundation record"
    assert restored.tags == ("manual", "application")
    assert restored.source_activation_id == source_activation_id
    assert restored.idempotency_key == "apply-1"
    assert restored.content_changed is False


def test_repository_does_not_perform_cross_aggregate_validation(tmp_path: Path) -> None:
    repository = JsonPlaybookRevisionApplicationRepository(tmp_path)
    application = PlaybookRevisionApplication(
        playbook_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        revision_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        proposal_id=UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
        reason="Repository persists local-valid application only",
    )

    repository.save(application)

    assert repository.get_by_id(application.id) == application


def test_repository_default_path_uses_neural_paths_constant() -> None:
    repository = JsonPlaybookRevisionApplicationRepository()

    assert repository._directory == NeuralPaths.PLAYBOOK_REVISION_APPLICATIONS

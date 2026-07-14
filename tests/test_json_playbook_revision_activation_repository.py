from pathlib import Path
from uuid import UUID

from neural_engine.core.paths import NeuralPaths
from neural_engine.domain import (
    PlaybookRevisionActivation,
    PlaybookRevisionActivationDecision,
)
from neural_engine.infrastructure.json_playbook_revision_activation_repository import (
    JsonPlaybookRevisionActivationRepository,
)


def make_activation(
    reason: str = "Persist activation",
    decision: PlaybookRevisionActivationDecision = PlaybookRevisionActivationDecision.ACTIVE,
    previous_revision_id: UUID | None = None,
    decided_by: str | None = None,
    notes: str | None = None,
    tags: list[str] | None = None,
) -> PlaybookRevisionActivation:
    return PlaybookRevisionActivation(
        playbook_id=UUID("11111111-1111-1111-1111-111111111111"),
        revision_id=UUID("22222222-2222-2222-2222-222222222222"),
        proposal_id=UUID("33333333-3333-3333-3333-333333333333"),
        decision=decision,
        reason=reason,
        previous_revision_id=previous_revision_id,
        decided_by=decided_by,
        notes=notes,
        tags=tags or [],
    )


def test_save_writes_one_json_file_per_playbook_revision_activation(
    tmp_path: Path,
) -> None:
    repository = JsonPlaybookRevisionActivationRepository(tmp_path)
    activation = make_activation()

    repository.save(activation)

    path = tmp_path / f"{activation.id}.json"
    assert path.exists()
    assert (
        PlaybookRevisionActivation.model_validate_json(path.read_text(encoding="utf-8"))
        == activation
    )


def test_load_all_returns_saved_activations_sorted_by_file_name(tmp_path: Path) -> None:
    repository = JsonPlaybookRevisionActivationRepository(tmp_path)
    first = make_activation("First")
    second = make_activation("Second")

    repository.save(second)
    repository.save(first)

    assert repository.load_all() == sorted([first, second], key=lambda item: str(item.id))


def test_load_all_returns_empty_list_when_directory_does_not_exist(tmp_path: Path) -> None:
    repository = JsonPlaybookRevisionActivationRepository(tmp_path / "missing")

    assert repository.load_all() == []


def test_get_by_id_returns_saved_activation(tmp_path: Path) -> None:
    repository = JsonPlaybookRevisionActivationRepository(tmp_path)
    activation = make_activation("Load me")
    repository.save(activation)

    assert repository.get_by_id(activation.id) == activation


def test_get_by_id_returns_none_when_file_is_missing(tmp_path: Path) -> None:
    repository = JsonPlaybookRevisionActivationRepository(tmp_path)
    activation = make_activation("Missing")

    assert repository.get_by_id(activation.id) is None


def test_save_updated_activation_overwrites_same_json_file(tmp_path: Path) -> None:
    repository = JsonPlaybookRevisionActivationRepository(tmp_path)
    activation = make_activation("Update notes")
    repository.save(activation)

    updated = activation.model_copy(update={"notes": "Updated notes"})
    repository.save(updated)

    files = list(tmp_path.glob("*.json"))
    assert files == [tmp_path / f"{activation.id}.json"]
    assert repository.get_by_id(activation.id) == updated


def test_repository_persists_and_restores_decision_optional_fields_and_timestamp(
    tmp_path: Path,
) -> None:
    repository = JsonPlaybookRevisionActivationRepository(tmp_path)
    previous_revision_id = UUID("44444444-4444-4444-4444-444444444444")
    activation = make_activation(
        reason="Supersede previous selection",
        decision=PlaybookRevisionActivationDecision.SUPERSEDED,
        previous_revision_id=previous_revision_id,
        decided_by="manual-review",
        notes="Lifecycle record",
        tags=["manual", "superseded"],
    )

    repository.save(activation)
    restored = repository.get_by_id(activation.id)

    assert restored == activation
    assert restored is not None
    assert restored.timestamp == activation.timestamp
    assert restored.decision == PlaybookRevisionActivationDecision.SUPERSEDED
    assert restored.previous_revision_id == previous_revision_id
    assert restored.decided_by == "manual-review"
    assert restored.notes == "Lifecycle record"
    assert restored.tags == ["manual", "superseded"]


def test_repository_does_not_perform_cross_aggregate_validation(tmp_path: Path) -> None:
    repository = JsonPlaybookRevisionActivationRepository(tmp_path)
    activation = PlaybookRevisionActivation(
        playbook_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        revision_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        proposal_id=UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
        decision=PlaybookRevisionActivationDecision.ACTIVE,
        reason="Repository persists local-valid activation only",
    )

    repository.save(activation)

    assert repository.get_by_id(activation.id) == activation


def test_repository_default_path_uses_neural_paths_constant() -> None:
    repository = JsonPlaybookRevisionActivationRepository()

    assert repository._directory == NeuralPaths.PLAYBOOK_REVISION_ACTIVATIONS

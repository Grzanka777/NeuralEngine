from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from neural_engine.core.paths import (
    RECORD_STORE_NAMES,
    NeuralHomeError,
    resolve_neural_paths,
)


def test_default_is_exactly_dot_neural_below_path_home(tmp_path: Path) -> None:
    paths = resolve_neural_paths(environ={}, default_home=tmp_path)

    assert paths.source == "default"
    assert paths.configured_value is None
    assert tmp_path / ".neural" == paths.HOME


def test_valid_absolute_override_selects_one_resolved_home(tmp_path: Path) -> None:
    configured = tmp_path / "portable"
    configured.mkdir()

    paths = resolve_neural_paths(environ={"NEURAL_HOME": str(configured)})

    assert paths.source == "override"
    assert paths.configured_value == str(configured)
    assert configured.resolve() == paths.HOME


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("", "must not be blank"),
        (" ", "leading or trailing whitespace"),
        ("relative/path", "must be absolute"),
        ("~/portable", "not expanded or allowed"),
        ("/tmp/~/portable", "not expanded or allowed"),
        ("/tmp/portable\x00root", "NUL characters"),
    ],
)
def test_invalid_override_is_rejected_without_fallback(value: str, message: str) -> None:
    with pytest.raises(NeuralHomeError, match=message) as captured:
        resolve_neural_paths(environ={"NEURAL_HOME": value})

    assert captured.value.reason == "invalid_configuration"
    assert captured.value.source == "override"
    assert "No fallback was used" in str(captured.value)


def test_nonexistent_override_is_rejected_without_creation(tmp_path: Path) -> None:
    configured = tmp_path / "missing"

    with pytest.raises(NeuralHomeError) as captured:
        resolve_neural_paths(environ={"NEURAL_HOME": str(configured)})

    assert captured.value.reason == "home_unavailable"
    assert not configured.exists()


def test_regular_file_override_is_rejected(tmp_path: Path) -> None:
    configured = tmp_path / "not-a-directory"
    configured.write_text("content", encoding="utf-8")

    with pytest.raises(NeuralHomeError) as captured:
        resolve_neural_paths(environ={"NEURAL_HOME": str(configured)})

    assert captured.value.reason == "home_not_directory"


def test_inaccessible_override_uses_deterministic_access_seam(tmp_path: Path) -> None:
    configured = tmp_path / "portable"
    configured.mkdir()

    with pytest.raises(NeuralHomeError) as captured:
        resolve_neural_paths(
            environ={"NEURAL_HOME": str(configured)},
            access_checker=lambda _path, _mode: False,
        )

    assert captured.value.reason == "home_inaccessible"


def test_valid_symlinked_override_resolves_to_available_directory(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    configured = tmp_path / "configured"
    configured.symlink_to(target, target_is_directory=True)

    paths = resolve_neural_paths(environ={"NEURAL_HOME": str(configured)})

    assert paths.configured_value == str(configured)
    assert target.resolve() == paths.HOME


def test_dangling_symlink_override_is_rejected(tmp_path: Path) -> None:
    configured = tmp_path / "configured"
    configured.symlink_to(tmp_path / "missing", target_is_directory=True)

    with pytest.raises(NeuralHomeError) as captured:
        resolve_neural_paths(environ={"NEURAL_HOME": str(configured)})

    assert captured.value.reason == "home_unavailable"


def test_all_derived_paths_share_one_resolved_home(tmp_path: Path) -> None:
    configured = tmp_path / "portable"
    configured.mkdir()
    paths = resolve_neural_paths(environ={"NEURAL_HOME": str(configured)})

    assert paths.BRAIN == paths.HOME / "brain"
    assert paths.EXPERIENCES == paths.BRAIN / "experiences"
    assert paths.OBSERVATIONS == paths.BRAIN / "observations"
    assert paths.KNOWLEDGE == paths.BRAIN / "knowledge"
    assert paths.PLAYBOOKS == paths.BRAIN / "playbooks"
    assert paths.PLAYBOOK_RUNS == paths.BRAIN / "playbook-runs"
    assert paths.PLAYBOOK_EVALUATIONS == paths.BRAIN / "playbook-evaluations"
    assert paths.EVOLUTION_PROPOSALS == paths.BRAIN / "evolution-proposals"
    assert paths.PLAYBOOK_REVISIONS == paths.BRAIN / "playbook-revisions"
    assert paths.PLAYBOOK_REVISION_ACTIVATIONS == paths.BRAIN / ("playbook-revision-activations")
    assert paths.PLAYBOOK_REVISION_APPLICATIONS == paths.BRAIN / ("playbook-revision-applications")
    assert paths.DECISIONS == paths.BRAIN / "decisions"
    assert paths.DECISION_ACCEPTANCES == paths.BRAIN / "decision-acceptances"
    assert paths.DECISION_ACTIONS == paths.BRAIN / "decision-actions"
    assert paths.DECISION_OUTCOMES == paths.BRAIN / "decision-outcomes"
    assert paths.DECISION_REVIEWS == paths.BRAIN / "decision-reviews"
    assert paths.PROJECTS == paths.HOME / "projects"
    assert paths.LOGS == paths.HOME / "logs"
    assert paths.CONFIG == paths.HOME / "config.toml"
    assert paths.VERSION == paths.HOME / "VERSION"
    assert paths.BRAIN_METADATA == paths.BRAIN / "brain-trust-metadata.json"
    assert paths.BRAIN_METADATA not in {path for _name, path in paths.record_stores}
    assert paths.TRUST_BINDING.name == "brain-trust-binding.json"
    assert paths.TRUST_BINDING != paths.BRAIN_METADATA
    assert paths.BRAIN not in paths.TRUST_BINDING.parents
    assert tuple(name for name, _path in paths.record_stores) == RECORD_STORE_NAMES
    assert tuple(path for _name, path in paths.record_stores) == (
        paths.OBSERVATIONS,
        paths.EXPERIENCES,
        paths.KNOWLEDGE,
        paths.PLAYBOOKS,
        paths.PLAYBOOK_RUNS,
        paths.PLAYBOOK_EVALUATIONS,
        paths.EVOLUTION_PROPOSALS,
        paths.PLAYBOOK_REVISIONS,
        paths.PLAYBOOK_REVISION_ACTIVATIONS,
        paths.PLAYBOOK_REVISION_APPLICATIONS,
        paths.DECISIONS,
        paths.DECISION_ACCEPTANCES,
        paths.DECISION_ACTIONS,
        paths.DECISION_OUTCOMES,
        paths.DECISION_REVIEWS,
    )


def test_trust_paths_are_deterministic_and_do_not_create_files(tmp_path: Path) -> None:
    configured = tmp_path / "portable"
    configured.mkdir()
    paths = resolve_neural_paths(environ={"NEURAL_HOME": str(configured)})
    before = {path.relative_to(tmp_path) for path in tmp_path.rglob("*")}

    same_paths = resolve_neural_paths(environ={"NEURAL_HOME": str(configured)})

    assert paths.BRAIN_METADATA == same_paths.BRAIN_METADATA
    assert paths.TRUST_BINDING == same_paths.TRUST_BINDING
    assert paths.TRUST_BINDING.parent == Path.home() / ".config" / "neural-engine"
    assert {path.relative_to(tmp_path) for path in tmp_path.rglob("*")} == before


def test_trust_binding_path_is_independent_of_brain_path(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()

    first_paths = resolve_neural_paths(environ={"NEURAL_HOME": str(first)})
    second_paths = resolve_neural_paths(environ={"NEURAL_HOME": str(second)})

    assert first_paths.TRUST_BINDING == second_paths.TRUST_BINDING
    assert first_paths.BRAIN_METADATA != second_paths.BRAIN_METADATA


def test_resolution_is_not_frozen_between_calls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()

    monkeypatch.setenv("NEURAL_HOME", str(first))
    first_paths = resolve_neural_paths()
    monkeypatch.setenv("NEURAL_HOME", str(second))
    second_paths = resolve_neural_paths()

    assert first.resolve() == first_paths.HOME
    assert second.resolve() == second_paths.HOME


def test_resolved_path_set_is_immutable(tmp_path: Path) -> None:
    paths = resolve_neural_paths(environ={}, default_home=tmp_path)

    with pytest.raises(FrozenInstanceError):
        paths.HOME = tmp_path / "other"  # type: ignore[misc]


def test_existing_default_file_is_unusable(tmp_path: Path) -> None:
    selected_home = tmp_path / ".neural"
    selected_home.write_text("not a directory", encoding="utf-8")
    paths = resolve_neural_paths(environ={}, default_home=tmp_path)

    with pytest.raises(NeuralHomeError) as captured:
        paths.require_available(operation="read")

    assert captured.value.reason == "home_not_directory"

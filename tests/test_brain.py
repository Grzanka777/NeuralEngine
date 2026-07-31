from pathlib import Path

import pytest

from neural_engine.core.brain import BRAIN_FORMAT_VERSION, Brain
from neural_engine.core.paths import NeuralHomeError, resolve_neural_paths


def test_brain_exists_after_default_initialization(tmp_path: Path) -> None:
    paths = resolve_neural_paths(environ={}, default_home=tmp_path)
    brain = Brain(paths)

    brain.initialize()

    assert brain.exists()


def test_default_initialization_creates_only_approved_paths(tmp_path: Path) -> None:
    paths = resolve_neural_paths(environ={}, default_home=tmp_path)

    Brain(paths).initialize()

    expected = {
        "VERSION",
        "brain",
        "brain/decision-acceptances",
        "brain/decision-actions",
        "brain/decision-outcomes",
        "brain/decision-reviews",
        "brain/decisions",
        "brain/evolution-proposals",
        "brain/experiences",
        "brain/knowledge",
        "brain/observations",
        "brain/playbook-evaluations",
        "brain/playbook-revision-activations",
        "brain/playbook-revision-applications",
        "brain/playbook-revisions",
        "brain/playbook-runs",
        "brain/playbooks",
        "config.toml",
        "logs",
        "projects",
    }
    actual = {str(path.relative_to(paths.HOME)) for path in paths.HOME.rglob("*")}
    assert actual == expected


def test_initialization_writes_supported_brain_format_version(tmp_path: Path) -> None:
    paths = resolve_neural_paths(environ={}, default_home=tmp_path)

    Brain(paths).initialize()

    assert BRAIN_FORMAT_VERSION == "1.0.0"
    assert paths.VERSION.read_text(encoding="utf-8") == "1.0.0\n"


def test_override_initialization_requires_preexisting_root(tmp_path: Path) -> None:
    configured = tmp_path / "missing"

    with pytest.raises(NeuralHomeError):
        resolve_neural_paths(environ={"NEURAL_HOME": str(configured)})

    assert not configured.exists()


def test_override_initialization_creates_children_inside_existing_root(tmp_path: Path) -> None:
    configured = tmp_path / "portable"
    configured.mkdir()
    paths = resolve_neural_paths(environ={"NEURAL_HOME": str(configured)})

    Brain(paths).initialize()

    assert paths.BRAIN.is_dir()
    assert paths.PLAYBOOK_REVISION_ACTIVATIONS.is_dir()
    assert paths.PLAYBOOK_REVISION_APPLICATIONS.is_dir()


def test_partial_initialization_is_idempotent_and_preserves_existing_content(
    tmp_path: Path,
) -> None:
    configured = tmp_path / "portable"
    configured.mkdir()
    paths = resolve_neural_paths(environ={"NEURAL_HOME": str(configured)})
    paths.BRAIN.mkdir()
    paths.OBSERVATIONS.mkdir()
    record = paths.OBSERVATIONS / "existing.json"
    record.write_text('{"preserved": true}', encoding="utf-8")
    paths.CONFIG.write_text("custom = true\n", encoding="utf-8")

    brain = Brain(paths)
    brain.initialize()
    brain.initialize()

    assert record.read_text(encoding="utf-8") == '{"preserved": true}'
    assert paths.CONFIG.read_text(encoding="utf-8") == "custom = true\n"
    assert paths.PLAYBOOK_REVISION_ACTIVATIONS.is_dir()
    assert paths.PLAYBOOK_REVISION_APPLICATIONS.is_dir()


def test_wrong_type_child_fails_without_replacement(tmp_path: Path) -> None:
    configured = tmp_path / "portable"
    configured.mkdir()
    paths = resolve_neural_paths(environ={"NEURAL_HOME": str(configured)})
    paths.BRAIN.mkdir()
    paths.OBSERVATIONS.write_text("not a directory", encoding="utf-8")

    with pytest.raises(FileExistsError):
        Brain(paths).initialize()

    assert paths.OBSERVATIONS.is_file()
    assert paths.OBSERVATIONS.read_text(encoding="utf-8") == "not a directory"

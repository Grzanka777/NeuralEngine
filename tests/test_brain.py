from pathlib import Path

import pytest

from neural_engine.core.brain import Brain
from neural_engine.core.paths import NeuralPaths


def test_brain_exists() -> None:
    brain = Brain()
    brain.initialize()

    assert brain.exists()


def test_brain_initializes_playbook_evaluations_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / ".neural"
    brain_path = home / "brain"
    monkeypatch.setattr(NeuralPaths, "HOME", home)
    monkeypatch.setattr(NeuralPaths, "BRAIN", brain_path)
    monkeypatch.setattr(NeuralPaths, "EXPERIENCES", brain_path / "experiences")
    monkeypatch.setattr(NeuralPaths, "OBSERVATIONS", brain_path / "observations")
    monkeypatch.setattr(NeuralPaths, "KNOWLEDGE", brain_path / "knowledge")
    monkeypatch.setattr(NeuralPaths, "PLAYBOOKS", brain_path / "playbooks")
    monkeypatch.setattr(NeuralPaths, "PLAYBOOK_RUNS", brain_path / "playbook-runs")
    monkeypatch.setattr(
        NeuralPaths,
        "PLAYBOOK_EVALUATIONS",
        brain_path / "playbook-evaluations",
    )
    monkeypatch.setattr(
        NeuralPaths,
        "EVOLUTION_PROPOSALS",
        brain_path / "evolution-proposals",
    )
    monkeypatch.setattr(
        NeuralPaths,
        "PLAYBOOK_REVISIONS",
        brain_path / "playbook-revisions",
    )
    monkeypatch.setattr(NeuralPaths, "DECISIONS", brain_path / "decisions")
    monkeypatch.setattr(
        NeuralPaths,
        "DECISION_ACCEPTANCES",
        brain_path / "decision-acceptances",
    )
    monkeypatch.setattr(NeuralPaths, "DECISION_ACTIONS", brain_path / "decision-actions")
    monkeypatch.setattr(NeuralPaths, "DECISION_OUTCOMES", brain_path / "decision-outcomes")
    monkeypatch.setattr(NeuralPaths, "PROJECTS", home / "projects")
    monkeypatch.setattr(NeuralPaths, "LOGS", home / "logs")
    monkeypatch.setattr(NeuralPaths, "CONFIG", home / "config.toml")
    monkeypatch.setattr(NeuralPaths, "VERSION", home / "VERSION")

    Brain().initialize()

    assert NeuralPaths.PLAYBOOK_EVALUATIONS.exists()
    assert NeuralPaths.EVOLUTION_PROPOSALS.exists()
    assert NeuralPaths.PLAYBOOK_REVISIONS.exists()
    assert NeuralPaths.DECISION_ACCEPTANCES.exists()
    assert NeuralPaths.DECISION_ACTIONS.exists()
    assert NeuralPaths.DECISION_OUTCOMES.exists()

from pathlib import Path

from neural_engine.core.paths import NeuralPaths


class Brain:
    """Represents the local Neural Engine brain."""

    def initialize(self) -> None:
        directories: list[Path] = [
            NeuralPaths.BRAIN,
            NeuralPaths.EXPERIENCES,
            NeuralPaths.OBSERVATIONS,
            NeuralPaths.KNOWLEDGE,
            NeuralPaths.PLAYBOOKS,
            NeuralPaths.PLAYBOOK_RUNS,
            NeuralPaths.PLAYBOOK_EVALUATIONS,
            NeuralPaths.EVOLUTION_PROPOSALS,
            NeuralPaths.PLAYBOOK_REVISIONS,
            NeuralPaths.DECISIONS,
            NeuralPaths.DECISION_ACCEPTANCES,
            NeuralPaths.DECISION_ACTIONS,
            NeuralPaths.PROJECTS,
            NeuralPaths.LOGS,
        ]

        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)

        NeuralPaths.VERSION.write_text("0.0.1a1\n")

        if not NeuralPaths.CONFIG.exists():
            NeuralPaths.CONFIG.write_text("# Neural Engine configuration\n")

    def exists(self) -> bool:
        return NeuralPaths.HOME.exists()

from pathlib import Path


class NeuralPaths:
    """Central definition of all Neural Engine filesystem paths."""

    HOME = Path.home() / ".neural"

    BRAIN = HOME / "brain"

    EXPERIENCES = BRAIN / "experiences"
    OBSERVATIONS = BRAIN / "observations"
    KNOWLEDGE = BRAIN / "knowledge"
    PLAYBOOKS = BRAIN / "playbooks"
    PLAYBOOK_RUNS = BRAIN / "playbook-runs"
    PLAYBOOK_EVALUATIONS = BRAIN / "playbook-evaluations"
    DECISIONS = BRAIN / "decisions"

    PROJECTS = HOME / "projects"
    LOGS = HOME / "logs"

    CONFIG = HOME / "config.toml"
    VERSION = HOME / "VERSION"

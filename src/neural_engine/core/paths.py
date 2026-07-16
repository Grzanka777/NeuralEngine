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
    EVOLUTION_PROPOSALS = BRAIN / "evolution-proposals"
    PLAYBOOK_REVISIONS = BRAIN / "playbook-revisions"
    PLAYBOOK_REVISION_ACTIVATIONS = BRAIN / "playbook-revision-activations"
    PLAYBOOK_REVISION_APPLICATIONS = BRAIN / "playbook-revision-applications"
    DECISIONS = BRAIN / "decisions"

    PROJECTS = HOME / "projects"
    LOGS = HOME / "logs"

    CONFIG = HOME / "config.toml"
    VERSION = HOME / "VERSION"

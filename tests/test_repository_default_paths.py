from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from neural_engine.core.paths import NeuralHomeError, NeuralPaths, resolve_neural_paths
from neural_engine.domain import Observation
from neural_engine.infrastructure.json_decision_acceptance_repository import (
    JsonDecisionAcceptanceRepository,
)
from neural_engine.infrastructure.json_decision_action_repository import (
    JsonDecisionActionRepository,
)
from neural_engine.infrastructure.json_decision_outcome_repository import (
    JsonDecisionOutcomeRepository,
)
from neural_engine.infrastructure.json_decision_repository import JsonDecisionRepository
from neural_engine.infrastructure.json_decision_review_repository import (
    JsonDecisionReviewRepository,
)
from neural_engine.infrastructure.json_evolution_proposal_repository import (
    JsonEvolutionProposalRepository,
)
from neural_engine.infrastructure.json_experience_repository import JsonExperienceRepository
from neural_engine.infrastructure.json_knowledge_repository import JsonKnowledgeRepository
from neural_engine.infrastructure.json_observation_repository import JsonObservationRepository
from neural_engine.infrastructure.json_playbook_evaluation_repository import (
    JsonPlaybookEvaluationRepository,
)
from neural_engine.infrastructure.json_playbook_repository import JsonPlaybookRepository
from neural_engine.infrastructure.json_playbook_revision_activation_repository import (
    JsonPlaybookRevisionActivationRepository,
)
from neural_engine.infrastructure.json_playbook_revision_application_repository import (
    JsonPlaybookRevisionApplicationRepository,
)
from neural_engine.infrastructure.json_playbook_revision_repository import (
    JsonPlaybookRevisionRepository,
)
from neural_engine.infrastructure.json_playbook_run_repository import JsonPlaybookRunRepository

RepositoryFactory = Callable[..., Any]

REPOSITORIES: list[tuple[RepositoryFactory, str]] = [
    (JsonObservationRepository, "OBSERVATIONS"),
    (JsonExperienceRepository, "EXPERIENCES"),
    (JsonKnowledgeRepository, "KNOWLEDGE"),
    (JsonPlaybookRepository, "PLAYBOOKS"),
    (JsonPlaybookRunRepository, "PLAYBOOK_RUNS"),
    (JsonPlaybookEvaluationRepository, "PLAYBOOK_EVALUATIONS"),
    (JsonEvolutionProposalRepository, "EVOLUTION_PROPOSALS"),
    (JsonPlaybookRevisionRepository, "PLAYBOOK_REVISIONS"),
    (JsonPlaybookRevisionActivationRepository, "PLAYBOOK_REVISION_ACTIVATIONS"),
    (JsonPlaybookRevisionApplicationRepository, "PLAYBOOK_REVISION_APPLICATIONS"),
    (JsonDecisionRepository, "DECISIONS"),
    (JsonDecisionAcceptanceRepository, "DECISION_ACCEPTANCES"),
    (JsonDecisionActionRepository, "DECISION_ACTIONS"),
    (JsonDecisionOutcomeRepository, "DECISION_OUTCOMES"),
    (JsonDecisionReviewRepository, "DECISION_REVIEWS"),
]


def _initialized_override(tmp_path: Path) -> NeuralPaths:
    home = tmp_path / "portable"
    home.mkdir()
    (home / "brain").mkdir()
    return resolve_neural_paths(environ={"NEURAL_HOME": str(home)})


@pytest.mark.parametrize(("factory", "attribute"), REPOSITORIES)
def test_all_default_repositories_derive_from_selected_home(
    factory: RepositoryFactory,
    attribute: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _initialized_override(tmp_path)
    monkeypatch.setenv("NEURAL_HOME", str(paths.HOME))

    repository = factory()

    assert repository._directory == getattr(paths, attribute)


@pytest.mark.parametrize(("factory", "_attribute"), REPOSITORIES)
def test_all_default_repositories_recheck_vanished_root_before_read(
    factory: RepositoryFactory,
    _attribute: str,
    tmp_path: Path,
) -> None:
    paths = _initialized_override(tmp_path)
    repository = factory(paths=paths)
    paths.BRAIN.rmdir()
    paths.HOME.rmdir()

    with pytest.raises(NeuralHomeError) as captured:
        repository.load_all()

    assert captured.value.reason == "home_unavailable"


def test_vanished_override_cannot_be_recreated_by_save(tmp_path: Path) -> None:
    paths = _initialized_override(tmp_path)
    repository = JsonObservationRepository(paths=paths)
    paths.BRAIN.rmdir()
    paths.HOME.rmdir()

    with pytest.raises(NeuralHomeError):
        repository.save(Observation(content="must not be written"))

    assert not paths.HOME.exists()


def test_explicit_directory_injection_remains_independent(tmp_path: Path) -> None:
    directory = tmp_path / "nested" / "observations"
    repository = JsonObservationRepository(directory)

    repository.save(Observation(content="explicit directory"))

    assert len(list(directory.glob("*.json"))) == 1


def test_missing_store_under_available_override_brain_is_empty(tmp_path: Path) -> None:
    paths = _initialized_override(tmp_path)
    repository = JsonObservationRepository(paths=paths)

    assert repository.load_all() == []

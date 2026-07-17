from neural_engine.application.container import Container
from neural_engine.application.decision_acceptance_service import DecisionAcceptanceService
from neural_engine.application.decision_service import DecisionService
from neural_engine.application.playbook_revision_activation_service import (
    PlaybookRevisionActivationService,
)
from neural_engine.application.playbook_revision_application_service import (
    PlaybookRevisionApplicationService,
)
from neural_engine.application.playbook_revision_service import PlaybookRevisionService
from neural_engine.application.playbook_service import PlaybookService
from neural_engine.core.paths import NeuralPaths
from neural_engine.infrastructure.json_decision_acceptance_repository import (
    JsonDecisionAcceptanceRepository,
)
from neural_engine.infrastructure.json_decision_repository import JsonDecisionRepository
from neural_engine.infrastructure.json_evolution_proposal_repository import (
    JsonEvolutionProposalRepository,
)
from neural_engine.infrastructure.json_knowledge_repository import JsonKnowledgeRepository
from neural_engine.infrastructure.json_observation_repository import JsonObservationRepository
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


def test_container_wires_playbook_revision_service_with_json_repositories() -> None:
    service = Container().playbook_revision_service()

    assert isinstance(service, PlaybookRevisionService)
    assert isinstance(service._revision_repository, JsonPlaybookRevisionRepository)
    assert isinstance(service._playbook_repository, JsonPlaybookRepository)
    assert isinstance(service._proposal_repository, JsonEvolutionProposalRepository)
    assert isinstance(service._knowledge_repository, JsonKnowledgeRepository)


def test_container_wires_decision_repository() -> None:
    repository = Container().decision_repository()

    assert isinstance(repository, JsonDecisionRepository)
    assert repository._directory == NeuralPaths.DECISIONS


def test_container_wires_decision_service_with_json_repositories() -> None:
    service = Container().decision_service()

    assert isinstance(service, DecisionService)
    assert isinstance(service._decision_repository, JsonDecisionRepository)
    assert isinstance(service._observation_repository, JsonObservationRepository)


def test_container_wires_decision_acceptance_repository() -> None:
    repository = Container().decision_acceptance_repository()

    assert isinstance(repository, JsonDecisionAcceptanceRepository)
    assert repository._directory == NeuralPaths.DECISION_ACCEPTANCES


def test_container_wires_decision_acceptance_service_with_json_repositories() -> None:
    service = Container().decision_acceptance_service()

    assert isinstance(service, DecisionAcceptanceService)
    assert isinstance(service._acceptance_repository, JsonDecisionAcceptanceRepository)
    assert isinstance(service._decision_repository, JsonDecisionRepository)


def test_container_wires_playbook_service_without_playbook_revision_repository() -> None:
    service = Container().playbook_service()

    assert isinstance(service, PlaybookService)
    assert not hasattr(service, "_revision_repository")


def test_container_wires_playbook_revision_activation_repository() -> None:
    repository = Container().playbook_revision_activation_repository()

    assert isinstance(repository, JsonPlaybookRevisionActivationRepository)
    assert repository._directory == NeuralPaths.PLAYBOOK_REVISION_ACTIVATIONS


def test_container_wires_playbook_revision_activation_service_with_json_repositories() -> None:
    service = Container().playbook_revision_activation_service()

    assert isinstance(service, PlaybookRevisionActivationService)
    assert isinstance(service._activation_repository, JsonPlaybookRevisionActivationRepository)
    assert isinstance(service._revision_repository, JsonPlaybookRevisionRepository)
    assert isinstance(service._playbook_repository, JsonPlaybookRepository)
    assert isinstance(service._proposal_repository, JsonEvolutionProposalRepository)


def test_container_wires_playbook_revision_application_repository() -> None:
    repository = Container().playbook_revision_application_repository()

    assert isinstance(repository, JsonPlaybookRevisionApplicationRepository)
    assert repository._directory == NeuralPaths.PLAYBOOK_REVISION_APPLICATIONS


def test_container_wires_playbook_revision_application_service_with_json_repositories() -> None:
    service = Container().playbook_revision_application_service()

    assert isinstance(service, PlaybookRevisionApplicationService)
    assert isinstance(service._application_repository, JsonPlaybookRevisionApplicationRepository)
    assert isinstance(service._revision_repository, JsonPlaybookRevisionRepository)
    assert isinstance(service._playbook_repository, JsonPlaybookRepository)
    assert isinstance(service._proposal_repository, JsonEvolutionProposalRepository)
    assert isinstance(service._activation_repository, JsonPlaybookRevisionActivationRepository)
    assert isinstance(service._activation_service, PlaybookRevisionActivationService)

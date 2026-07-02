from neural_engine.application.container import Container
from neural_engine.application.playbook_revision_service import PlaybookRevisionService
from neural_engine.infrastructure.json_evolution_proposal_repository import (
    JsonEvolutionProposalRepository,
)
from neural_engine.infrastructure.json_knowledge_repository import JsonKnowledgeRepository
from neural_engine.infrastructure.json_playbook_repository import JsonPlaybookRepository
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

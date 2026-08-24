from pathlib import Path

import pytest

from neural_engine.application.brain_trust_inspector import BrainTrustInspector
from neural_engine.application.container import Container
from neural_engine.application.decision_acceptance_service import DecisionAcceptanceService
from neural_engine.application.decision_action_service import DecisionActionService
from neural_engine.application.decision_lifecycle_service import DecisionLifecycleService
from neural_engine.application.decision_outcome_service import DecisionOutcomeService
from neural_engine.application.decision_review_service import DecisionReviewService
from neural_engine.application.decision_service import DecisionService
from neural_engine.application.development_evidence_service import DevelopmentEvidenceService
from neural_engine.application.evolution_proposal_service import EvolutionProposalService
from neural_engine.application.experience_service import ExperienceService
from neural_engine.application.knowledge_service import KnowledgeService
from neural_engine.application.neural_doctor_service import NeuralDoctorService
from neural_engine.application.playbook_evaluation_service import PlaybookEvaluationService
from neural_engine.application.playbook_revision_activation_service import (
    PlaybookRevisionActivationService,
)
from neural_engine.application.playbook_revision_application_service import (
    PlaybookRevisionApplicationService,
)
from neural_engine.application.playbook_revision_service import PlaybookRevisionService
from neural_engine.application.playbook_run_service import PlaybookRunService
from neural_engine.application.playbook_service import PlaybookService
from neural_engine.core.brain import BRAIN_FORMAT_VERSION
from neural_engine.core.paths import NeuralPaths, resolve_neural_paths
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
from neural_engine.infrastructure.local_brain_trust_probe import LocalBrainTrustProbe
from neural_engine.infrastructure.local_development_evidence_source import (
    LocalDevelopmentEvidenceSource,
)
from neural_engine.infrastructure.local_neural_doctor_probe import LocalNeuralDoctorProbe


def test_container_wires_playbook_revision_service_with_json_repositories() -> None:
    service = Container().playbook_revision_service()

    assert isinstance(service, PlaybookRevisionService)
    assert isinstance(service._revision_repository, JsonPlaybookRevisionRepository)
    assert isinstance(service._playbook_repository, JsonPlaybookRepository)
    assert isinstance(service._proposal_repository, JsonEvolutionProposalRepository)
    assert isinstance(service._knowledge_repository, JsonKnowledgeRepository)
    assert service._controlled_writer is service._revision_repository
    assert service._mutation_coordinator is not None


def test_container_wires_playbook_run_service_without_lifecycle_dependencies() -> None:
    service = Container().playbook_run_service()

    assert isinstance(service, PlaybookRunService)
    assert isinstance(service._run_repository, JsonPlaybookRunRepository)
    assert isinstance(service._playbook_repository, JsonPlaybookRepository)
    assert isinstance(service._revision_repository, JsonPlaybookRevisionRepository)
    assert service._controlled_writer is service._run_repository
    assert service._mutation_coordinator is not None
    assert not hasattr(service, "_activation_service")
    assert not hasattr(service, "_application_repository")


def test_container_wires_downstream_run_consumers_to_validated_boundary() -> None:
    evaluation_service = Container().playbook_evaluation_service()
    proposal_service = Container().evolution_proposal_service()

    assert isinstance(evaluation_service, PlaybookEvaluationService)
    assert isinstance(evaluation_service._run_repository, PlaybookRunService)
    assert isinstance(proposal_service, EvolutionProposalService)
    assert isinstance(proposal_service._run_repository, PlaybookRunService)


def test_container_wires_decision_repository() -> None:
    repository = Container().decision_repository()

    assert isinstance(repository, JsonDecisionRepository)
    assert repository._directory == resolve_neural_paths().DECISIONS


def test_container_wires_decision_service_with_json_repositories() -> None:
    service = Container().decision_service()

    assert isinstance(service, DecisionService)
    assert isinstance(service._decision_repository, JsonDecisionRepository)
    assert isinstance(service._observation_repository, JsonObservationRepository)
    assert service._controlled_writer is service._decision_repository
    assert service._mutation_coordinator is not None


def test_container_wires_local_development_evidence_orchestration() -> None:
    service = Container().development_evidence_service()

    assert isinstance(service, DevelopmentEvidenceService)
    assert isinstance(service._source, LocalDevelopmentEvidenceSource)
    assert isinstance(service._decision_service, DecisionService)
    assert isinstance(service._acceptance_service, DecisionAcceptanceService)
    assert isinstance(service._action_service, DecisionActionService)
    assert isinstance(service._outcome_service, DecisionOutcomeService)
    assert isinstance(service._review_service, DecisionReviewService)
    assert isinstance(service._experience_service, ExperienceService)


def test_container_wires_read_only_neural_doctor_boundary() -> None:
    service = Container().neural_doctor_service()

    assert isinstance(service, NeuralDoctorService)
    assert isinstance(service._probe, LocalNeuralDoctorProbe)
    assert service._supported_brain_format_version == BRAIN_FORMAT_VERSION
    assert isinstance(service._brain_trust_inspector, BrainTrustInspector)
    assert isinstance(service._brain_trust_inspector._probe, LocalBrainTrustProbe)


def test_container_exposes_one_read_only_brain_trust_inspector() -> None:
    inspector = Container().brain_trust_inspector()

    assert isinstance(inspector, BrainTrustInspector)
    assert isinstance(inspector._probe, LocalBrainTrustProbe)


def test_container_defers_path_resolution_for_doctor_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_resolution() -> NeuralPaths:
        raise AssertionError("Doctor service construction must not resolve paths")

    monkeypatch.setattr(
        "neural_engine.application.container.resolve_neural_paths",
        unexpected_resolution,
    )

    service = Container().neural_doctor_service()

    assert isinstance(service, NeuralDoctorService)


def test_container_wires_decision_acceptance_repository() -> None:
    repository = Container().decision_acceptance_repository()

    assert isinstance(repository, JsonDecisionAcceptanceRepository)
    assert repository._directory == resolve_neural_paths().DECISION_ACCEPTANCES


def test_container_wires_decision_acceptance_service_with_json_repositories() -> None:
    service = Container().decision_acceptance_service()

    assert isinstance(service, DecisionAcceptanceService)
    assert isinstance(service._acceptance_repository, JsonDecisionAcceptanceRepository)
    assert isinstance(service._decision_repository, JsonDecisionRepository)
    assert service._controlled_writer is service._acceptance_repository
    assert service._mutation_coordinator is not None


def test_container_wires_decision_action_repository() -> None:
    repository = Container().decision_action_repository()

    assert isinstance(repository, JsonDecisionActionRepository)
    assert repository._directory == resolve_neural_paths().DECISION_ACTIONS


def test_container_wires_decision_action_service_with_json_repositories() -> None:
    service = Container().decision_action_service()

    assert isinstance(service, DecisionActionService)
    assert isinstance(service._action_repository, JsonDecisionActionRepository)
    assert isinstance(service._decision_repository, JsonDecisionRepository)
    assert isinstance(service._acceptance_repository, JsonDecisionAcceptanceRepository)
    assert isinstance(service._playbook_run_repository, PlaybookRunService)
    assert service._controlled_writer is service._action_repository
    assert service._mutation_coordinator is not None


def test_container_wires_decision_outcome_repository_and_service() -> None:
    repository = Container().decision_outcome_repository()
    service = Container().decision_outcome_service()

    assert isinstance(repository, JsonDecisionOutcomeRepository)
    assert repository._directory == resolve_neural_paths().DECISION_OUTCOMES
    assert isinstance(service, DecisionOutcomeService)
    assert isinstance(service._outcome_repository, JsonDecisionOutcomeRepository)
    assert isinstance(service._action_repository, JsonDecisionActionRepository)
    assert isinstance(service._decision_repository, JsonDecisionRepository)
    assert isinstance(service._acceptance_repository, JsonDecisionAcceptanceRepository)
    assert service._controlled_writer is service._outcome_repository
    assert service._mutation_coordinator is not None


def test_container_wires_canonical_decision_lifecycle_service() -> None:
    service = Container().decision_lifecycle_service()

    assert isinstance(service, DecisionLifecycleService)
    assert isinstance(service._decision_repository, JsonDecisionRepository)
    assert isinstance(service._acceptance_repository, JsonDecisionAcceptanceRepository)
    assert isinstance(service._action_repository, JsonDecisionActionRepository)
    assert isinstance(service._outcome_repository, JsonDecisionOutcomeRepository)
    assert not hasattr(service, "_review_repository")


def test_container_wires_decision_review_repository_and_service() -> None:
    repository = Container().decision_review_repository()
    service = Container().decision_review_service()

    assert isinstance(repository, JsonDecisionReviewRepository)
    assert repository._directory == resolve_neural_paths().DECISION_REVIEWS
    assert isinstance(service, DecisionReviewService)
    assert isinstance(service._review_repository, JsonDecisionReviewRepository)
    assert isinstance(service._decision_repository, JsonDecisionRepository)
    assert isinstance(service._acceptance_repository, JsonDecisionAcceptanceRepository)
    assert isinstance(service._outcome_repository, JsonDecisionOutcomeRepository)
    assert service._controlled_writer is service._review_repository
    assert service._mutation_coordinator is not None


def test_container_wires_experience_service_with_review_validation_boundary() -> None:
    service = Container().experience_service()

    assert isinstance(service, ExperienceService)
    assert isinstance(service._experience_repository, JsonExperienceRepository)
    assert isinstance(service._observation_repository, JsonObservationRepository)
    assert isinstance(service._decision_review_service, DecisionReviewService)
    assert service._controlled_writer is service._experience_repository
    assert service._mutation_coordinator is not None


def test_container_wires_knowledge_service_to_validated_experience_service() -> None:
    service = Container().knowledge_service()

    assert isinstance(service, KnowledgeService)
    assert isinstance(service._knowledge_repository, JsonKnowledgeRepository)
    assert isinstance(service._experience_reader, ExperienceService)
    assert not isinstance(service._experience_reader, JsonExperienceRepository)
    assert service._controlled_writer is service._knowledge_repository
    assert service._mutation_coordinator is not None


def test_container_wires_playbook_service_without_playbook_revision_repository() -> None:
    service = Container().playbook_service()

    assert isinstance(service, PlaybookService)
    assert not hasattr(service, "_revision_repository")
    assert service._controlled_writer is not None
    assert isinstance(service._controlled_writer, JsonPlaybookRepository)
    assert service._mutation_coordinator is not None


def test_container_wires_playbook_evaluation_service_with_controlled_writer() -> None:
    service = Container().playbook_evaluation_service()

    assert isinstance(service._evaluation_repository, JsonPlaybookEvaluationRepository)
    assert service._controlled_writer is service._evaluation_repository
    assert service._mutation_coordinator is not None


def test_container_wires_evolution_proposal_service_with_controlled_writer() -> None:
    service = Container().evolution_proposal_service()

    assert isinstance(service._proposal_repository, JsonEvolutionProposalRepository)
    assert service._controlled_writer is service._proposal_repository
    assert isinstance(service._controlled_replace_writer, JsonEvolutionProposalRepository)
    assert service._mutation_coordinator is not None


def test_container_wires_playbook_revision_activation_repository() -> None:
    repository = Container().playbook_revision_activation_repository()

    assert isinstance(repository, JsonPlaybookRevisionActivationRepository)
    assert repository._directory == resolve_neural_paths().PLAYBOOK_REVISION_ACTIVATIONS


def test_container_wires_playbook_revision_activation_service_with_json_repositories() -> None:
    service = Container().playbook_revision_activation_service()

    assert isinstance(service, PlaybookRevisionActivationService)
    assert isinstance(service._activation_repository, JsonPlaybookRevisionActivationRepository)
    assert isinstance(service._revision_repository, JsonPlaybookRevisionRepository)
    assert isinstance(service._playbook_repository, JsonPlaybookRepository)
    assert isinstance(service._proposal_repository, JsonEvolutionProposalRepository)
    assert service._controlled_writer is service._activation_repository
    assert service._mutation_coordinator is not None


def test_container_wires_playbook_revision_application_repository() -> None:
    repository = Container().playbook_revision_application_repository()

    assert isinstance(repository, JsonPlaybookRevisionApplicationRepository)
    assert repository._directory == resolve_neural_paths().PLAYBOOK_REVISION_APPLICATIONS


def test_container_reuses_one_resolved_path_set_through_nested_graph(
    tmp_path: Path,
) -> None:
    home = tmp_path / "portable"
    home.mkdir()
    paths = resolve_neural_paths(environ={"NEURAL_HOME": str(home)})

    service = Container(paths).development_evidence_service()

    decision_repository = service._decision_service._decision_repository
    action_repository = service._action_service._action_repository
    experience_repository = service._experience_service._experience_repository
    assert isinstance(decision_repository, JsonDecisionRepository)
    assert isinstance(action_repository, JsonDecisionActionRepository)
    assert isinstance(experience_repository, JsonExperienceRepository)
    assert decision_repository._path.paths is paths
    assert action_repository._path.paths is paths
    assert experience_repository._path.paths is paths


def test_container_wires_playbook_revision_application_service_with_json_repositories() -> None:
    service = Container().playbook_revision_application_service()

    assert isinstance(service, PlaybookRevisionApplicationService)
    assert isinstance(service._application_repository, JsonPlaybookRevisionApplicationRepository)
    assert isinstance(service._revision_repository, JsonPlaybookRevisionRepository)
    assert isinstance(service._playbook_repository, JsonPlaybookRepository)
    assert isinstance(service._proposal_repository, JsonEvolutionProposalRepository)
    assert isinstance(service._activation_repository, JsonPlaybookRevisionActivationRepository)
    assert isinstance(service._activation_service, PlaybookRevisionActivationService)
    assert service._controlled_writer is service._application_repository
    assert service._mutation_coordinator is not None

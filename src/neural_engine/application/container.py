from neural_engine.application.decision_acceptance_service import DecisionAcceptanceService
from neural_engine.application.decision_action_service import DecisionActionService
from neural_engine.application.decision_lifecycle_service import DecisionLifecycleService
from neural_engine.application.decision_outcome_service import DecisionOutcomeService
from neural_engine.application.decision_service import DecisionService
from neural_engine.application.evolution_proposal_service import EvolutionProposalService
from neural_engine.application.experience_service import ExperienceService
from neural_engine.application.knowledge_service import KnowledgeService
from neural_engine.application.observation_service import ObservationService
from neural_engine.application.playbook_evaluation_service import (
    PlaybookEvaluationService,
)
from neural_engine.application.playbook_revision_activation_service import (
    PlaybookRevisionActivationService,
)
from neural_engine.application.playbook_revision_application_service import (
    PlaybookRevisionApplicationService,
)
from neural_engine.application.playbook_revision_service import PlaybookRevisionService
from neural_engine.application.playbook_run_service import PlaybookRunService
from neural_engine.application.playbook_service import PlaybookService
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
from neural_engine.infrastructure.json_evolution_proposal_repository import (
    JsonEvolutionProposalRepository,
)
from neural_engine.infrastructure.json_experience_repository import (
    JsonExperienceRepository,
)
from neural_engine.infrastructure.json_knowledge_repository import (
    JsonKnowledgeRepository,
)
from neural_engine.infrastructure.json_observation_repository import (
    JsonObservationRepository,
)
from neural_engine.infrastructure.json_playbook_evaluation_repository import (
    JsonPlaybookEvaluationRepository,
)
from neural_engine.infrastructure.json_playbook_repository import (
    JsonPlaybookRepository,
)
from neural_engine.infrastructure.json_playbook_revision_activation_repository import (
    JsonPlaybookRevisionActivationRepository,
)
from neural_engine.infrastructure.json_playbook_revision_application_repository import (
    JsonPlaybookRevisionApplicationRepository,
)
from neural_engine.infrastructure.json_playbook_revision_repository import (
    JsonPlaybookRevisionRepository,
)
from neural_engine.infrastructure.json_playbook_run_repository import (
    JsonPlaybookRunRepository,
)


class Container:
    """Application dependency container."""

    def decision_action_service(self) -> DecisionActionService:
        return DecisionActionService(
            JsonDecisionActionRepository(),
            JsonDecisionRepository(),
            JsonDecisionAcceptanceRepository(),
            JsonPlaybookRunRepository(),
        )

    def decision_lifecycle_service(self) -> DecisionLifecycleService:
        return DecisionLifecycleService(
            JsonDecisionRepository(),
            JsonDecisionAcceptanceRepository(),
            JsonDecisionActionRepository(),
            JsonDecisionOutcomeRepository(),
        )

    def decision_outcome_service(self) -> DecisionOutcomeService:
        return DecisionOutcomeService(
            JsonDecisionOutcomeRepository(),
            JsonDecisionRepository(),
            JsonDecisionAcceptanceRepository(),
            JsonDecisionActionRepository(),
        )

    def decision_acceptance_service(self) -> DecisionAcceptanceService:
        return DecisionAcceptanceService(
            JsonDecisionAcceptanceRepository(),
            JsonDecisionRepository(),
        )

    def decision_service(self) -> DecisionService:
        return DecisionService(
            JsonDecisionRepository(),
            JsonObservationRepository(),
        )

    def observation_service(self) -> ObservationService:
        return ObservationService(
            JsonObservationRepository(),
        )

    def experience_service(self) -> ExperienceService:
        return ExperienceService(
            JsonExperienceRepository(),
            JsonObservationRepository(),
        )

    def knowledge_service(self) -> KnowledgeService:
        return KnowledgeService(
            JsonKnowledgeRepository(),
            JsonExperienceRepository(),
        )

    def playbook_service(self) -> PlaybookService:
        return PlaybookService(
            JsonPlaybookRepository(),
            JsonKnowledgeRepository(),
        )

    def playbook_run_service(self) -> PlaybookRunService:
        return PlaybookRunService(
            JsonPlaybookRunRepository(),
            JsonPlaybookRepository(),
        )

    def playbook_evaluation_service(self) -> PlaybookEvaluationService:
        return PlaybookEvaluationService(
            JsonPlaybookEvaluationRepository(),
            JsonPlaybookRunRepository(),
        )

    def evolution_proposal_service(self) -> EvolutionProposalService:
        return EvolutionProposalService(
            JsonEvolutionProposalRepository(),
            JsonPlaybookRepository(),
            JsonPlaybookEvaluationRepository(),
            JsonPlaybookRunRepository(),
        )

    def playbook_revision_service(self) -> PlaybookRevisionService:
        return PlaybookRevisionService(
            JsonPlaybookRevisionRepository(),
            JsonPlaybookRepository(),
            JsonEvolutionProposalRepository(),
            JsonKnowledgeRepository(),
        )

    def playbook_revision_activation_service(self) -> PlaybookRevisionActivationService:
        return PlaybookRevisionActivationService(
            JsonPlaybookRevisionActivationRepository(),
            JsonPlaybookRevisionRepository(),
            JsonPlaybookRepository(),
            JsonEvolutionProposalRepository(),
        )

    def playbook_revision_application_service(self) -> PlaybookRevisionApplicationService:
        return PlaybookRevisionApplicationService(
            JsonPlaybookRevisionApplicationRepository(),
            JsonPlaybookRevisionRepository(),
            JsonPlaybookRepository(),
            JsonEvolutionProposalRepository(),
            JsonPlaybookRevisionActivationRepository(),
            self.playbook_revision_activation_service(),
        )

    def playbook_revision_activation_repository(
        self,
    ) -> JsonPlaybookRevisionActivationRepository:
        return JsonPlaybookRevisionActivationRepository()

    def playbook_revision_application_repository(
        self,
    ) -> JsonPlaybookRevisionApplicationRepository:
        return JsonPlaybookRevisionApplicationRepository()

    def decision_repository(self) -> JsonDecisionRepository:
        return JsonDecisionRepository()

    def decision_acceptance_repository(self) -> JsonDecisionAcceptanceRepository:
        return JsonDecisionAcceptanceRepository()

    def decision_action_repository(self) -> JsonDecisionActionRepository:
        return JsonDecisionActionRepository()

    def decision_outcome_repository(self) -> JsonDecisionOutcomeRepository:
        return JsonDecisionOutcomeRepository()

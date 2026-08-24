from neural_engine.application.brain_trust_inspector import BrainTrustInspector
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
from neural_engine.application.observation_service import ObservationService
from neural_engine.application.planner_context_service import PlannerContextService
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
from neural_engine.infrastructure.local_brain_trust_probe import LocalBrainTrustProbe
from neural_engine.infrastructure.local_brain_trust_transition import (
    LocalBrainTrustTransitionCoordinator,
)
from neural_engine.infrastructure.local_development_evidence_source import (
    LocalDevelopmentEvidenceSource,
)
from neural_engine.infrastructure.local_neural_doctor_probe import LocalNeuralDoctorProbe
from neural_engine.infrastructure.local_planner_context_readers import LocalPlannerContextReaders
from neural_engine.ports.brain_trust_transition import BrainTrustRecoveryCoordinator


class Container:
    """Application dependency container."""

    def __init__(self, paths: NeuralPaths | None = None) -> None:
        self._paths = paths

    def _resolved_paths(self) -> NeuralPaths:
        return self._paths if self._paths is not None else resolve_neural_paths()

    def neural_doctor_service(self) -> NeuralDoctorService:
        return NeuralDoctorService(
            self._resolved_paths,
            LocalNeuralDoctorProbe(),
            BRAIN_FORMAT_VERSION,
            self.brain_trust_inspector(),
        )

    def brain_trust_inspector(self, paths: NeuralPaths | None = None) -> BrainTrustInspector:
        return BrainTrustInspector(
            lambda: paths if paths is not None else self._resolved_paths(),
            LocalBrainTrustProbe(),
        )

    def brain_trust_transition_coordinator(self) -> LocalBrainTrustTransitionCoordinator:
        paths = self._resolved_paths()
        return LocalBrainTrustTransitionCoordinator(paths, self.brain_trust_inspector(paths))

    def brain_trust_recovery_coordinator(self) -> BrainTrustRecoveryCoordinator:
        return self.brain_trust_transition_coordinator()

    def development_evidence_service(self) -> DevelopmentEvidenceService:
        paths = self._resolved_paths()
        scoped = Container(paths)
        return DevelopmentEvidenceService(
            LocalDevelopmentEvidenceSource(),
            scoped.decision_service(),
            scoped.decision_acceptance_service(),
            scoped.decision_action_service(),
            scoped.decision_outcome_service(),
            scoped.decision_review_service(),
            scoped.experience_service(),
        )

    def planner_context_service(self) -> PlannerContextService:
        """Build the bounded read-only planner-context use case (no CLI exposure)."""
        readers = LocalPlannerContextReaders(self._resolved_paths())
        return PlannerContextService(readers, readers, readers, readers, readers)

    def decision_action_service(self) -> DecisionActionService:
        paths = self._resolved_paths()
        action_repository = JsonDecisionActionRepository(paths=paths)
        return DecisionActionService(
            action_repository,
            JsonDecisionRepository(paths=paths),
            JsonDecisionAcceptanceRepository(paths=paths),
            Container(paths).playbook_run_service(),
            controlled_writer=action_repository,
            mutation_coordinator=Container(paths).brain_trust_transition_coordinator(),
        )

    def decision_lifecycle_service(self) -> DecisionLifecycleService:
        paths = self._resolved_paths()
        return DecisionLifecycleService(
            JsonDecisionRepository(paths=paths),
            JsonDecisionAcceptanceRepository(paths=paths),
            JsonDecisionActionRepository(paths=paths),
            JsonDecisionOutcomeRepository(paths=paths),
        )

    def decision_outcome_service(self) -> DecisionOutcomeService:
        paths = self._resolved_paths()
        outcome_repository = JsonDecisionOutcomeRepository(paths=paths)
        return DecisionOutcomeService(
            outcome_repository,
            JsonDecisionRepository(paths=paths),
            JsonDecisionAcceptanceRepository(paths=paths),
            JsonDecisionActionRepository(paths=paths),
            controlled_writer=outcome_repository,
            mutation_coordinator=Container(paths).brain_trust_transition_coordinator(),
        )

    def decision_acceptance_service(self) -> DecisionAcceptanceService:
        paths = self._resolved_paths()
        acceptance_repository = JsonDecisionAcceptanceRepository(paths=paths)
        return DecisionAcceptanceService(
            acceptance_repository,
            JsonDecisionRepository(paths=paths),
            controlled_writer=acceptance_repository,
            mutation_coordinator=Container(paths).brain_trust_transition_coordinator(),
        )

    def decision_service(self) -> DecisionService:
        paths = self._resolved_paths()
        decision_repository = JsonDecisionRepository(paths=paths)
        return DecisionService(
            decision_repository,
            JsonObservationRepository(paths=paths),
            controlled_writer=decision_repository,
            mutation_coordinator=Container(paths).brain_trust_transition_coordinator(),
        )

    def observation_service(self) -> ObservationService:
        paths = self._resolved_paths()
        observation_repository = JsonObservationRepository(paths=paths)
        return ObservationService(
            observation_repository,
            controlled_writer=observation_repository,
            mutation_coordinator=Container(paths).brain_trust_transition_coordinator(),
        )

    def experience_service(self) -> ExperienceService:
        paths = self._resolved_paths()
        experience_repository = JsonExperienceRepository(paths=paths)
        return ExperienceService(
            experience_repository,
            JsonObservationRepository(paths=paths),
            Container(paths).decision_review_service(),
            controlled_writer=experience_repository,
            mutation_coordinator=Container(paths).brain_trust_transition_coordinator(),
        )

    def knowledge_service(self) -> KnowledgeService:
        paths = self._resolved_paths()
        knowledge_repository = JsonKnowledgeRepository(paths=paths)
        return KnowledgeService(
            knowledge_repository,
            Container(paths).experience_service(),
            controlled_writer=knowledge_repository,
            mutation_coordinator=Container(paths).brain_trust_transition_coordinator(),
        )

    def playbook_service(self) -> PlaybookService:
        paths = self._resolved_paths()
        playbook_repository = JsonPlaybookRepository(paths=paths)
        return PlaybookService(
            playbook_repository,
            JsonKnowledgeRepository(paths=paths),
            controlled_writer=playbook_repository,
            mutation_coordinator=Container(paths).brain_trust_transition_coordinator(),
        )

    def playbook_run_service(self) -> PlaybookRunService:
        paths = self._resolved_paths()
        run_repository = JsonPlaybookRunRepository(paths=paths)
        return PlaybookRunService(
            run_repository,
            JsonPlaybookRepository(paths=paths),
            JsonPlaybookRevisionRepository(paths=paths),
            controlled_writer=run_repository,
            mutation_coordinator=Container(paths).brain_trust_transition_coordinator(),
        )

    def playbook_evaluation_service(self) -> PlaybookEvaluationService:
        paths = self._resolved_paths()
        evaluation_repository = JsonPlaybookEvaluationRepository(paths=paths)
        return PlaybookEvaluationService(
            evaluation_repository,
            Container(paths).playbook_run_service(),
            controlled_writer=evaluation_repository,
            mutation_coordinator=Container(paths).brain_trust_transition_coordinator(),
        )

    def evolution_proposal_service(self) -> EvolutionProposalService:
        paths = self._resolved_paths()
        proposal_repository = JsonEvolutionProposalRepository(paths=paths)
        return EvolutionProposalService(
            proposal_repository,
            JsonPlaybookRepository(paths=paths),
            JsonPlaybookEvaluationRepository(paths=paths),
            Container(paths).playbook_run_service(),
            controlled_writer=proposal_repository,
            controlled_replace_writer=proposal_repository,
            mutation_coordinator=Container(paths).brain_trust_transition_coordinator(),
        )

    def playbook_revision_service(self) -> PlaybookRevisionService:
        paths = self._resolved_paths()
        revision_repository = JsonPlaybookRevisionRepository(paths=paths)
        return PlaybookRevisionService(
            revision_repository,
            JsonPlaybookRepository(paths=paths),
            JsonEvolutionProposalRepository(paths=paths),
            JsonKnowledgeRepository(paths=paths),
            controlled_writer=revision_repository,
            mutation_coordinator=Container(paths).brain_trust_transition_coordinator(),
        )

    def playbook_revision_activation_service(self) -> PlaybookRevisionActivationService:
        paths = self._resolved_paths()
        activation_repository = JsonPlaybookRevisionActivationRepository(paths=paths)
        return PlaybookRevisionActivationService(
            activation_repository,
            JsonPlaybookRevisionRepository(paths=paths),
            JsonPlaybookRepository(paths=paths),
            JsonEvolutionProposalRepository(paths=paths),
            controlled_writer=activation_repository,
            mutation_coordinator=Container(paths).brain_trust_transition_coordinator(),
        )

    def playbook_revision_application_service(self) -> PlaybookRevisionApplicationService:
        paths = self._resolved_paths()
        application_repository = JsonPlaybookRevisionApplicationRepository(paths=paths)
        return PlaybookRevisionApplicationService(
            application_repository,
            JsonPlaybookRevisionRepository(paths=paths),
            JsonPlaybookRepository(paths=paths),
            JsonEvolutionProposalRepository(paths=paths),
            JsonPlaybookRevisionActivationRepository(paths=paths),
            Container(paths).playbook_revision_activation_service(),
            controlled_writer=application_repository,
            mutation_coordinator=Container(paths).brain_trust_transition_coordinator(),
        )

    def playbook_revision_activation_repository(
        self,
    ) -> JsonPlaybookRevisionActivationRepository:
        return JsonPlaybookRevisionActivationRepository(paths=self._resolved_paths())

    def playbook_revision_application_repository(
        self,
    ) -> JsonPlaybookRevisionApplicationRepository:
        return JsonPlaybookRevisionApplicationRepository(paths=self._resolved_paths())

    def decision_repository(self) -> JsonDecisionRepository:
        return JsonDecisionRepository(paths=self._resolved_paths())

    def decision_acceptance_repository(self) -> JsonDecisionAcceptanceRepository:
        return JsonDecisionAcceptanceRepository(paths=self._resolved_paths())

    def decision_action_repository(self) -> JsonDecisionActionRepository:
        return JsonDecisionActionRepository(paths=self._resolved_paths())

    def decision_outcome_repository(self) -> JsonDecisionOutcomeRepository:
        return JsonDecisionOutcomeRepository(paths=self._resolved_paths())

    def decision_review_repository(self) -> JsonDecisionReviewRepository:
        return JsonDecisionReviewRepository(paths=self._resolved_paths())

    def decision_review_service(self) -> DecisionReviewService:
        paths = self._resolved_paths()
        review_repository = JsonDecisionReviewRepository(paths=paths)
        return DecisionReviewService(
            review_repository,
            JsonDecisionRepository(paths=paths),
            JsonDecisionAcceptanceRepository(paths=paths),
            JsonDecisionOutcomeRepository(paths=paths),
            controlled_writer=review_repository,
            mutation_coordinator=Container(paths).brain_trust_transition_coordinator(),
        )

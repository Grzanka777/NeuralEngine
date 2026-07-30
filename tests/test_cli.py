from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from uuid import UUID

import pytest
from typer.testing import CliRunner

import neural_engine.cli as cli
from neural_engine.application.decision_acceptance_service import (
    DecisionAcceptanceDecisionNotFoundError,
    DecisionAcceptanceIdempotencyConflictError,
    DecisionAlreadyAcceptedError,
)
from neural_engine.application.decision_action_service import (
    DecisionActionAcceptanceMismatchError,
    DecisionActionAcceptanceNotFoundError,
    DecisionActionDecisionNotFoundError,
    DecisionActionIdempotencyConflictError,
    DecisionActionNotFoundError,
)
from neural_engine.application.decision_lifecycle_service import (
    DecisionLifecycleDecisionNotFoundError,
    DecisionLifecycleState,
)
from neural_engine.application.decision_outcome_service import (
    DecisionOutcomeDecisionNotFoundError,
    DecisionOutcomeIdempotencyConflictError,
    DecisionOutcomeNotFoundError,
    DecisionOutcomeSummary,
)
from neural_engine.application.decision_review_service import DecisionReviewNotFoundError
from neural_engine.application.decision_service import (
    DecisionIdempotencyConflictError,
    DecisionNotFoundError,
    DecisionObservationNotFoundError,
)
from neural_engine.application.evolution_proposal_service import (
    EvolutionProposalChangesRequiredError,
    EvolutionProposalEvaluationPlaybookMismatchError,
    EvolutionProposalEvaluationRunNotFoundError,
    EvolutionProposalEvaluationsRequiredError,
    EvolutionProposalNotFoundError,
    PlaybookEvaluationNotFoundError,
)
from neural_engine.application.evolution_proposal_service import (
    PlaybookNotFoundError as ProposalPlaybookNotFoundError,
)
from neural_engine.application.experience_service import (
    DecisionReviewPromotionSourceIndexError,
    ObservationNotFoundError,
)
from neural_engine.application.knowledge_service import (
    ExperienceNotFoundError,
    KnowledgeEvidenceRequiredError,
)
from neural_engine.application.observation_service import AddObservationResult
from neural_engine.application.playbook_evaluation_service import (
    PlaybookEvaluationFindingsRequiredError,
    PlaybookRunNotFoundError,
)
from neural_engine.application.playbook_revision_activation_service import (
    PlaybookRevisionActivationPlaybookNotFoundError,
    PlaybookRevisionActivationPreviousRevisionForbiddenError,
    PlaybookRevisionActivationPreviousRevisionNotFoundError,
    PlaybookRevisionActivationPreviousRevisionPlaybookMismatchError,
    PlaybookRevisionActivationPreviousRevisionRequiredError,
    PlaybookRevisionActivationProposalNotFoundError,
    PlaybookRevisionActivationRevisionNotFoundError,
    PlaybookRevisionActivationRevisionPlaybookMismatchError,
    PlaybookRevisionActivationRevisionProposalMismatchError,
)
from neural_engine.application.playbook_revision_service import (
    KnowledgeNotFoundError as RevisionKnowledgeNotFoundError,
)
from neural_engine.application.playbook_revision_service import (
    PlaybookNotFoundError as RevisionPlaybookNotFoundError,
)
from neural_engine.application.playbook_revision_service import (
    PlaybookRevisionProposalMismatchError,
    PlaybookRevisionProposalNotAcceptedError,
    PlaybookRevisionStepsRequiredError,
    PlaybookRevisionSuccessCriteriaRequiredError,
)
from neural_engine.application.playbook_run_service import (
    PlaybookNotFoundError,
    PlaybookRevisionNotFoundError,
    PlaybookRunActionsRequiredError,
    PlaybookRunRevisionPlaybookMismatchError,
)
from neural_engine.application.playbook_service import (
    KnowledgeNotFoundError,
    PlaybookKnowledgeRequiredError,
    PlaybookStepsRequiredError,
)
from neural_engine.core.brain import Brain
from neural_engine.core.paths import resolve_neural_paths
from neural_engine.domain import (
    Decision,
    DecisionAcceptance,
    DecisionAction,
    DecisionOutcome,
    DecisionOutcomeResult,
    DecisionReviewPromotionSourceKind,
    EvidenceReference,
    EvolutionProposal,
    EvolutionProposalStatus,
    Experience,
    ExperienceResult,
    Knowledge,
    KnowledgeConfidence,
    Observation,
    Playbook,
    PlaybookEffectiveness,
    PlaybookEvaluation,
    PlaybookRevision,
    PlaybookRevisionActivation,
    PlaybookRevisionActivationDecision,
    PlaybookRun,
)
from neural_engine.ports.knowledge_repository import KnowledgePersistenceConflictError
from neural_engine.ports.playbook_revision_repository import (
    PlaybookRevisionIdentityMismatchError,
    PlaybookRevisionPersistenceConflictError,
    PlaybookRevisionRepositoryError,
    PlaybookRevisionStoredDataError,
)


class CliResult(Protocol):
    @property
    def exit_code(self) -> int: ...

    @property
    def output(self) -> str: ...


class FakeObservationService:
    def __init__(self, observations: list[Observation]) -> None:
        self.observations = observations
        self.queries: list[str] = []
        self.requested_ids: list[UUID] = []
        self.add_calls: list[tuple[str, list[str] | None]] = []

    def list_observations(self) -> list[Observation]:
        return self.observations

    def add(
        self,
        content: str,
        tags: list[str] | None = None,
    ) -> AddObservationResult:
        self.add_calls.append((content, tags))
        duplicate_ids = [
            observation.id for observation in self.observations if observation.content == content
        ]
        observation = Observation(content=content, tags=tags or [])
        self.observations.append(observation)

        return AddObservationResult(
            observation=observation,
            duplicate_ids=duplicate_ids,
        )

    def search(self, query: str) -> list[Observation]:
        self.queries.append(query)
        return self.observations

    def get_by_id(self, observation_id: UUID) -> Observation | None:
        self.requested_ids.append(observation_id)

        for observation in self.observations:
            if observation.id == observation_id:
                return observation

        return None


class FakeDecisionService:
    def __init__(
        self,
        decisions: list[Decision] | None = None,
        missing_observation_id: UUID | None = None,
        conflict: tuple[str, str] | None = None,
    ) -> None:
        self.decisions = decisions or []
        self.missing_observation_id = missing_observation_id
        self.conflict = conflict
        self.add_calls: list[dict[str, object]] = []
        self.list_calls: list[str | None] = []
        self.show_calls: list[UUID] = []

    def add(
        self,
        project_key: str,
        title: str,
        objective: str,
        context_summary: str,
        alternatives: list[str],
        proposed_option: str,
        rationale: str,
        proposed_by: str,
        idempotency_key: str,
        observation_ids: list[UUID] | None = None,
        evidence_references: list[EvidenceReference] | None = None,
        supersedes_decision_id: UUID | None = None,
        tags: list[str] | None = None,
    ) -> Decision:
        call: dict[str, object] = {
            "project_key": project_key,
            "title": title,
            "objective": objective,
            "context_summary": context_summary,
            "alternatives": alternatives,
            "proposed_option": proposed_option,
            "rationale": rationale,
            "proposed_by": proposed_by,
            "idempotency_key": idempotency_key,
            "observation_ids": observation_ids,
            "evidence_references": evidence_references,
            "supersedes_decision_id": supersedes_decision_id,
            "tags": tags,
        }
        self.add_calls.append(call)

        if self.missing_observation_id is not None:
            raise DecisionObservationNotFoundError(self.missing_observation_id)

        if self.conflict is not None:
            raise DecisionIdempotencyConflictError(*self.conflict)

        for decision in self.decisions:
            if decision.project_key == project_key and decision.idempotency_key == idempotency_key:
                return decision

        decision = Decision(
            project_key=project_key,
            title=title,
            objective=objective,
            context_summary=context_summary,
            alternatives=tuple(alternatives),
            proposed_option=proposed_option,
            rationale=rationale,
            proposed_by=proposed_by,
            idempotency_key=idempotency_key,
            observation_ids=tuple(observation_ids or []),
            evidence_references=tuple(evidence_references or []),
            supersedes_decision_id=supersedes_decision_id,
            tags=tuple(tags or []),
        )
        self.decisions.append(decision)
        return decision

    def list_decisions(self, project_key: str | None = None) -> list[Decision]:
        self.list_calls.append(project_key)
        if project_key is None:
            return self.decisions
        return [decision for decision in self.decisions if decision.project_key == project_key]

    def show(self, decision_id: UUID) -> Decision:
        self.show_calls.append(decision_id)
        for decision in self.decisions:
            if decision.id == decision_id:
                return decision
        raise DecisionNotFoundError(decision_id)


class FakeDecisionAcceptanceService:
    def __init__(
        self,
        acceptances: list[DecisionAcceptance] | None = None,
        missing_decision_id: UUID | None = None,
        already_accepted: tuple[UUID, UUID] | None = None,
        conflict: tuple[UUID, str] | None = None,
    ) -> None:
        self.acceptances = acceptances or []
        self.missing_decision_id = missing_decision_id
        self.already_accepted = already_accepted
        self.conflict = conflict
        self.accept_calls: list[dict[str, object]] = []
        self.list_calls: list[UUID] = []

    def accept(
        self,
        decision_id: UUID,
        accepted_by: str,
        reason: str,
        idempotency_key: str,
        evidence_references: list[EvidenceReference] | None = None,
        tags: list[str] | None = None,
    ) -> DecisionAcceptance:
        self.accept_calls.append(
            {
                "decision_id": decision_id,
                "accepted_by": accepted_by,
                "reason": reason,
                "idempotency_key": idempotency_key,
                "evidence_references": evidence_references,
                "tags": tags,
            }
        )
        if self.missing_decision_id is not None:
            raise DecisionAcceptanceDecisionNotFoundError(self.missing_decision_id)
        if self.already_accepted is not None:
            raise DecisionAlreadyAcceptedError(*self.already_accepted)
        if self.conflict is not None:
            raise DecisionAcceptanceIdempotencyConflictError(*self.conflict)

        for acceptance in self.acceptances:
            if (
                acceptance.decision_id == decision_id
                and acceptance.idempotency_key == idempotency_key
            ):
                return acceptance

        acceptance = DecisionAcceptance(
            decision_id=decision_id,
            accepted_by=accepted_by,
            reason=reason,
            idempotency_key=idempotency_key,
            evidence_references=tuple(evidence_references or []),
            tags=tuple(tags or []),
        )
        self.acceptances.append(acceptance)
        return acceptance

    def list_for_decision(self, decision_id: UUID) -> list[DecisionAcceptance]:
        self.list_calls.append(decision_id)
        if self.missing_decision_id is not None:
            raise DecisionAcceptanceDecisionNotFoundError(self.missing_decision_id)
        return [item for item in self.acceptances if item.decision_id == decision_id]


class FakeDecisionActionService:
    def __init__(
        self,
        actions: list[DecisionAction] | None = None,
        missing_decision_id: UUID | None = None,
        missing_acceptance_id: UUID | None = None,
        mismatch: tuple[UUID, UUID, UUID] | None = None,
        conflict: tuple[UUID, str] | None = None,
    ) -> None:
        self.actions = actions or []
        self.missing_decision_id = missing_decision_id
        self.missing_acceptance_id = missing_acceptance_id
        self.mismatch = mismatch
        self.conflict = conflict
        self.add_calls: list[dict[str, object]] = []
        self.list_calls: list[UUID] = []
        self.show_calls: list[UUID] = []

    def add(self, **values: object) -> DecisionAction:
        self.add_calls.append(values)
        if self.missing_decision_id is not None:
            raise DecisionActionDecisionNotFoundError(self.missing_decision_id)
        if self.missing_acceptance_id is not None:
            raise DecisionActionAcceptanceNotFoundError(self.missing_acceptance_id)
        if self.mismatch is not None:
            raise DecisionActionAcceptanceMismatchError(*self.mismatch)
        if self.conflict is not None:
            raise DecisionActionIdempotencyConflictError(*self.conflict)

        decision_id = values["decision_id"]
        idempotency_key = values["idempotency_key"]
        for action in self.actions:
            if action.decision_id == decision_id and action.idempotency_key == idempotency_key:
                return action

        action = DecisionAction.model_validate(values)
        self.actions.append(action)
        return action

    def list_for_decision(self, decision_id: UUID) -> list[DecisionAction]:
        self.list_calls.append(decision_id)
        if self.missing_decision_id is not None:
            raise DecisionActionDecisionNotFoundError(self.missing_decision_id)
        return [action for action in self.actions if action.decision_id == decision_id]

    def show(self, action_id: UUID) -> DecisionAction:
        self.show_calls.append(action_id)
        for action in self.actions:
            if action.id == action_id:
                return action
        raise DecisionActionNotFoundError(action_id)


class FakeDecisionLifecycleService:
    def __init__(
        self,
        state_value: DecisionLifecycleState,
        missing_decision_id: UUID | None = None,
    ) -> None:
        self.state_value = state_value
        self.missing_decision_id = missing_decision_id
        self.state_calls: list[UUID] = []

    def state(self, decision_id: UUID) -> DecisionLifecycleState:
        self.state_calls.append(decision_id)
        if self.missing_decision_id is not None:
            raise DecisionLifecycleDecisionNotFoundError(self.missing_decision_id)
        return self.state_value


class FakeExperienceService:
    def __init__(
        self,
        experiences: list[Experience],
        missing_observation_id: UUID | None = None,
    ) -> None:
        self.experiences = experiences
        self.missing_observation_id = missing_observation_id
        self.add_calls: list[
            tuple[str, str, str, str, ExperienceResult, list[UUID] | None, list[str] | None]
        ] = []
        self.add_from_observation_calls: list[
            tuple[UUID, str, str, str, ExperienceResult, list[str] | None]
        ] = []
        self.requested_ids: list[UUID] = []
        self.list_for_observation_calls: list[UUID] = []

    def add(
        self,
        title: str,
        context: str,
        action: str,
        outcome: str,
        result: ExperienceResult,
        observation_ids: list[UUID] | None = None,
        tags: list[str] | None = None,
    ) -> Experience:
        self.add_calls.append((title, context, action, outcome, result, observation_ids, tags))

        if self.missing_observation_id is not None:
            raise ObservationNotFoundError(self.missing_observation_id)

        experience = Experience(
            title=title,
            context=context,
            action=action,
            outcome=outcome,
            result=result,
            observation_ids=observation_ids or [],
            tags=tags or [],
        )
        self.experiences.append(experience)

        return experience

    def add_from_observation(
        self,
        observation_id: UUID,
        title: str,
        action: str,
        outcome: str,
        result: ExperienceResult,
        tags: list[str] | None = None,
    ) -> Experience:
        self.add_from_observation_calls.append(
            (observation_id, title, action, outcome, result, tags)
        )

        if self.missing_observation_id is not None:
            raise ObservationNotFoundError(self.missing_observation_id)

        experience = Experience(
            title=title,
            context="Observation content from service",
            action=action,
            outcome=outcome,
            result=result,
            observation_ids=[observation_id],
            tags=tags or [],
        )
        self.experiences.append(experience)

        return experience

    def list_experiences(self) -> list[Experience]:
        return self.experiences

    def list_for_observation(self, observation_id: UUID) -> list[Experience]:
        self.list_for_observation_calls.append(observation_id)

        if self.missing_observation_id is not None:
            raise ObservationNotFoundError(self.missing_observation_id)

        return [
            experience
            for experience in self.experiences
            if observation_id in experience.observation_ids
        ]

    def get_by_id(self, experience_id: UUID) -> Experience | None:
        self.requested_ids.append(experience_id)

        for experience in self.experiences:
            if experience.id == experience_id:
                return experience

        return None


class FakeKnowledgeService:
    def __init__(
        self,
        knowledge_items: list[Knowledge],
        missing_experience_id: UUID | None = None,
        integrity_error: Exception | None = None,
    ) -> None:
        self.knowledge_items = knowledge_items
        self.missing_experience_id = missing_experience_id
        self.integrity_error = integrity_error
        self.add_calls: list[
            tuple[str, str, KnowledgeConfidence, list[UUID], list[str] | None]
        ] = []
        self.add_from_experience_calls: list[
            tuple[UUID, str, str, KnowledgeConfidence, list[str] | None]
        ] = []
        self.list_for_experience_calls: list[UUID] = []
        self.requested_ids: list[UUID] = []

    def add(
        self,
        statement: str,
        rationale: str,
        confidence: KnowledgeConfidence,
        experience_ids: list[UUID],
        tags: list[str] | None = None,
    ) -> Knowledge:
        self.add_calls.append((statement, rationale, confidence, experience_ids, tags))

        if not experience_ids:
            raise KnowledgeEvidenceRequiredError()

        if self.missing_experience_id is not None:
            raise ExperienceNotFoundError(self.missing_experience_id)
        if self.integrity_error is not None:
            raise self.integrity_error

        knowledge = Knowledge(
            statement=statement,
            rationale=rationale,
            confidence=confidence,
            experience_ids=experience_ids,
            tags=tags or [],
        )
        self.knowledge_items.append(knowledge)

        return knowledge

    def add_from_experience(
        self,
        experience_id: UUID,
        statement: str,
        rationale: str,
        confidence: KnowledgeConfidence,
        tags: list[str] | None = None,
    ) -> Knowledge:
        self.add_from_experience_calls.append(
            (experience_id, statement, rationale, confidence, tags)
        )

        if self.missing_experience_id is not None:
            raise ExperienceNotFoundError(self.missing_experience_id)
        if self.integrity_error is not None:
            raise self.integrity_error

        knowledge = Knowledge(
            statement=statement,
            rationale=rationale,
            confidence=confidence,
            experience_ids=[experience_id],
            tags=tags or [],
        )
        self.knowledge_items.append(knowledge)

        return knowledge

    def list_knowledge(self) -> list[Knowledge]:
        if self.integrity_error is not None:
            raise self.integrity_error
        return self.knowledge_items

    def list_for_experience(self, experience_id: UUID) -> list[Knowledge]:
        self.list_for_experience_calls.append(experience_id)

        if self.missing_experience_id is not None:
            raise ExperienceNotFoundError(self.missing_experience_id)
        if self.integrity_error is not None:
            raise self.integrity_error

        return [
            knowledge
            for knowledge in self.knowledge_items
            if experience_id in knowledge.experience_ids
        ]

    def get_by_id(self, knowledge_id: UUID) -> Knowledge | None:
        self.requested_ids.append(knowledge_id)

        if self.integrity_error is not None:
            raise self.integrity_error

        for knowledge in self.knowledge_items:
            if knowledge.id == knowledge_id:
                return knowledge

        return None


class FakePlaybookService:
    def __init__(
        self,
        playbooks: list[Playbook],
        missing_knowledge_id: UUID | None = None,
    ) -> None:
        self.playbooks = playbooks
        self.missing_knowledge_id = missing_knowledge_id
        self.add_calls: list[
            tuple[
                str,
                str,
                str,
                list[str],
                list[str],
                list[UUID],
                list[str] | None,
                list[str] | None,
            ]
        ] = []
        self.list_for_knowledge_calls: list[UUID] = []
        self.requested_ids: list[UUID] = []

    def add(
        self,
        title: str,
        situation: str,
        objective: str,
        steps: list[str],
        success_criteria: list[str],
        knowledge_ids: list[UUID],
        constraints: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> Playbook:
        self.add_calls.append(
            (
                title,
                situation,
                objective,
                steps,
                success_criteria,
                knowledge_ids,
                constraints,
                tags,
            )
        )

        if not knowledge_ids:
            raise PlaybookKnowledgeRequiredError()

        if not steps:
            raise PlaybookStepsRequiredError()

        if self.missing_knowledge_id is not None:
            raise KnowledgeNotFoundError(self.missing_knowledge_id)

        playbook = Playbook(
            title=title,
            situation=situation,
            objective=objective,
            steps=steps,
            success_criteria=success_criteria,
            constraints=constraints or [],
            knowledge_ids=knowledge_ids,
            tags=tags or [],
        )
        self.playbooks.append(playbook)

        return playbook

    def list_playbooks(self) -> list[Playbook]:
        return self.playbooks

    def list_for_knowledge(self, knowledge_id: UUID) -> list[Playbook]:
        self.list_for_knowledge_calls.append(knowledge_id)

        if self.missing_knowledge_id is not None:
            raise KnowledgeNotFoundError(self.missing_knowledge_id)

        return [playbook for playbook in self.playbooks if knowledge_id in playbook.knowledge_ids]

    def get_by_id(self, playbook_id: UUID) -> Playbook | None:
        self.requested_ids.append(playbook_id)

        for playbook in self.playbooks:
            if playbook.id == playbook_id:
                return playbook

        return None


class FakePlaybookRunService:
    def __init__(
        self,
        runs: list[PlaybookRun],
        missing_playbook_id: UUID | None = None,
        missing_revision_id: UUID | None = None,
        read_error: PlaybookRevisionNotFoundError
        | PlaybookRunRevisionPlaybookMismatchError
        | None = None,
    ) -> None:
        self.runs = runs
        self.missing_playbook_id = missing_playbook_id
        self.missing_revision_id = missing_revision_id
        self.read_error = read_error
        self.add_calls: list[
            tuple[
                UUID,
                str,
                list[str],
                str,
                bool,
                list[str] | None,
                str | None,
                list[str] | None,
                UUID | None,
            ]
        ] = []
        self.list_for_playbook_calls: list[UUID] = []
        self.requested_ids: list[UUID] = []

    def add(
        self,
        playbook_id: UUID,
        situation: str,
        actions_taken: list[str],
        outcome: str,
        success: bool,
        evidence: list[str] | None = None,
        notes: str | None = None,
        tags: list[str] | None = None,
        revision_id: UUID | None = None,
    ) -> PlaybookRun:
        self.add_calls.append(
            (
                playbook_id,
                situation,
                actions_taken,
                outcome,
                success,
                evidence,
                notes,
                tags,
                revision_id,
            )
        )

        if not actions_taken:
            raise PlaybookRunActionsRequiredError()

        if self.missing_playbook_id is not None:
            raise PlaybookNotFoundError(self.missing_playbook_id)

        if self.missing_revision_id is not None:
            raise PlaybookRevisionNotFoundError(self.missing_revision_id)

        run = PlaybookRun(
            playbook_id=playbook_id,
            revision_id=revision_id,
            situation=situation,
            actions_taken=actions_taken,
            outcome=outcome,
            success=success,
            evidence=evidence or [],
            notes=notes,
            tags=tags or [],
        )
        self.runs.append(run)

        return run

    def list_runs(self) -> list[PlaybookRun]:
        if self.read_error is not None:
            raise self.read_error
        return self.runs

    def list_for_playbook(self, playbook_id: UUID) -> list[PlaybookRun]:
        self.list_for_playbook_calls.append(playbook_id)

        if self.missing_playbook_id is not None:
            raise PlaybookNotFoundError(self.missing_playbook_id)

        return [run for run in self.runs if run.playbook_id == playbook_id]

    def list_for_revision(self, revision_id: UUID) -> list[PlaybookRun]:
        if self.missing_revision_id is not None:
            raise PlaybookRevisionNotFoundError(self.missing_revision_id)
        return [run for run in self.runs if run.revision_id == revision_id]

    def get_by_id(self, run_id: UUID) -> PlaybookRun | None:
        self.requested_ids.append(run_id)
        if self.read_error is not None:
            raise self.read_error

        for run in self.runs:
            if run.id == run_id:
                return run

        return None


class FakePlaybookEvaluationService:
    def __init__(
        self,
        evaluations: list[PlaybookEvaluation],
        missing_run_id: UUID | None = None,
    ) -> None:
        self.evaluations = evaluations
        self.missing_run_id = missing_run_id
        self.add_calls: list[
            tuple[
                UUID,
                PlaybookEffectiveness,
                list[str],
                list[str] | None,
                list[str] | None,
                str | None,
                list[str] | None,
            ]
        ] = []
        self.requested_ids: list[UUID] = []
        self.list_for_run_calls: list[UUID] = []

    def add(
        self,
        run_id: UUID,
        effectiveness: PlaybookEffectiveness,
        findings: list[str],
        improvements: list[str] | None = None,
        evidence: list[str] | None = None,
        notes: str | None = None,
        tags: list[str] | None = None,
    ) -> PlaybookEvaluation:
        self.add_calls.append(
            (
                run_id,
                effectiveness,
                findings,
                improvements,
                evidence,
                notes,
                tags,
            )
        )

        if not findings:
            raise PlaybookEvaluationFindingsRequiredError()

        if self.missing_run_id is not None:
            raise PlaybookRunNotFoundError(self.missing_run_id)

        evaluation = PlaybookEvaluation(
            run_id=run_id,
            effectiveness=effectiveness,
            findings=findings,
            improvements=improvements or [],
            evidence=evidence or [],
            notes=notes,
            tags=tags or [],
        )
        self.evaluations.append(evaluation)

        return evaluation

    def list_evaluations(self) -> list[PlaybookEvaluation]:
        return self.evaluations

    def list_for_run(self, run_id: UUID) -> list[PlaybookEvaluation]:
        self.list_for_run_calls.append(run_id)

        if self.missing_run_id is not None:
            raise PlaybookRunNotFoundError(self.missing_run_id)

        return [evaluation for evaluation in self.evaluations if evaluation.run_id == run_id]

    def get_by_id(self, evaluation_id: UUID) -> PlaybookEvaluation | None:
        self.requested_ids.append(evaluation_id)

        for evaluation in self.evaluations:
            if evaluation.id == evaluation_id:
                return evaluation

        return None


class FakeEvolutionProposalService:
    def __init__(
        self,
        proposals: list[EvolutionProposal],
        missing_playbook_id: UUID | None = None,
        missing_evaluation_id: UUID | None = None,
        missing_run: tuple[UUID, UUID] | None = None,
        playbook_mismatch: tuple[UUID, UUID, UUID] | None = None,
    ) -> None:
        self.proposals = proposals
        self.missing_playbook_id = missing_playbook_id
        self.missing_evaluation_id = missing_evaluation_id
        self.missing_run = missing_run
        self.playbook_mismatch = playbook_mismatch
        self.add_calls: list[
            tuple[
                UUID,
                list[UUID],
                str,
                str,
                list[str],
                list[str],
                list[str] | None,
                EvolutionProposalStatus,
                str | None,
                list[str] | None,
            ]
        ] = []
        self.requested_ids: list[UUID] = []
        self.list_for_playbook_calls: list[UUID] = []
        self.list_for_evaluation_calls: list[UUID] = []
        self.set_status_calls: list[tuple[UUID, EvolutionProposalStatus]] = []

    def add(
        self,
        playbook_id: UUID,
        evaluation_ids: list[UUID],
        summary: str,
        rationale: str,
        proposed_changes: list[str],
        expected_benefits: list[str],
        risks: list[str] | None = None,
        status: EvolutionProposalStatus = EvolutionProposalStatus.DRAFT,
        notes: str | None = None,
        tags: list[str] | None = None,
    ) -> EvolutionProposal:
        self.add_calls.append(
            (
                playbook_id,
                evaluation_ids,
                summary,
                rationale,
                proposed_changes,
                expected_benefits,
                risks,
                status,
                notes,
                tags,
            )
        )

        if not evaluation_ids:
            raise EvolutionProposalEvaluationsRequiredError()

        if not proposed_changes:
            raise EvolutionProposalChangesRequiredError()

        if self.missing_playbook_id is not None:
            raise ProposalPlaybookNotFoundError(self.missing_playbook_id)

        if self.missing_evaluation_id is not None:
            raise PlaybookEvaluationNotFoundError(self.missing_evaluation_id)

        if self.missing_run is not None:
            evaluation_id, run_id = self.missing_run
            raise EvolutionProposalEvaluationRunNotFoundError(evaluation_id, run_id)

        if self.playbook_mismatch is not None:
            evaluation_id, expected_playbook_id, actual_playbook_id = self.playbook_mismatch
            raise EvolutionProposalEvaluationPlaybookMismatchError(
                evaluation_id,
                expected_playbook_id,
                actual_playbook_id,
            )

        proposal = EvolutionProposal(
            playbook_id=playbook_id,
            evaluation_ids=evaluation_ids,
            summary=summary,
            rationale=rationale,
            proposed_changes=proposed_changes,
            expected_benefits=expected_benefits,
            risks=risks or [],
            status=status,
            notes=notes,
            tags=tags or [],
        )
        self.proposals.append(proposal)

        return proposal

    def list_proposals(self) -> list[EvolutionProposal]:
        return self.proposals

    def list_for_playbook(self, playbook_id: UUID) -> list[EvolutionProposal]:
        self.list_for_playbook_calls.append(playbook_id)

        if self.missing_playbook_id is not None:
            raise ProposalPlaybookNotFoundError(self.missing_playbook_id)

        return [proposal for proposal in self.proposals if proposal.playbook_id == playbook_id]

    def list_for_evaluation(self, evaluation_id: UUID) -> list[EvolutionProposal]:
        self.list_for_evaluation_calls.append(evaluation_id)

        if self.missing_evaluation_id is not None:
            raise PlaybookEvaluationNotFoundError(self.missing_evaluation_id)

        return [proposal for proposal in self.proposals if evaluation_id in proposal.evaluation_ids]

    def set_status(
        self,
        proposal_id: UUID,
        status: EvolutionProposalStatus,
    ) -> EvolutionProposal:
        self.set_status_calls.append((proposal_id, status))

        for index, proposal in enumerate(self.proposals):
            if proposal.id == proposal_id:
                updated = proposal.model_copy(update={"status": status})
                self.proposals[index] = updated
                return updated

        raise EvolutionProposalNotFoundError(proposal_id)

    def get_by_id(self, proposal_id: UUID) -> EvolutionProposal | None:
        self.requested_ids.append(proposal_id)

        for proposal in self.proposals:
            if proposal.id == proposal_id:
                return proposal

        return None


class FakePlaybookRevisionService:
    def __init__(
        self,
        revisions: list[PlaybookRevision],
        missing_proposal_id: UUID | None = None,
        not_accepted: tuple[UUID, EvolutionProposalStatus] | None = None,
        proposal_mismatch: tuple[UUID, UUID, UUID] | None = None,
        missing_playbook_id: UUID | None = None,
        missing_knowledge_id: UUID | None = None,
        integrity_error: PlaybookRevisionRepositoryError | None = None,
    ) -> None:
        self.revisions = revisions
        self.missing_proposal_id = missing_proposal_id
        self.not_accepted = not_accepted
        self.proposal_mismatch = proposal_mismatch
        self.missing_playbook_id = missing_playbook_id
        self.missing_knowledge_id = missing_knowledge_id
        self.integrity_error = integrity_error
        self.add_calls: list[
            tuple[
                UUID,
                UUID,
                str,
                str,
                str,
                list[str],
                list[str],
                list[UUID],
                str | None,
                list[str] | None,
            ]
        ] = []
        self.list_revisions_calls = 0
        self.list_for_playbook_calls: list[UUID] = []
        self.list_for_proposal_calls: list[UUID] = []
        self.list_for_knowledge_calls: list[UUID] = []
        self.requested_ids: list[UUID] = []

    def add(
        self,
        playbook_id: UUID,
        proposal_id: UUID,
        title: str,
        situation: str,
        objective: str,
        steps: list[str],
        success_criteria: list[str],
        knowledge_ids: list[UUID],
        notes: str | None = None,
        tags: list[str] | None = None,
    ) -> PlaybookRevision:
        self.add_calls.append(
            (
                playbook_id,
                proposal_id,
                title,
                situation,
                objective,
                steps,
                success_criteria,
                knowledge_ids,
                notes,
                tags,
            )
        )

        if not steps:
            raise PlaybookRevisionStepsRequiredError()

        if not success_criteria:
            raise PlaybookRevisionSuccessCriteriaRequiredError()

        if self.missing_proposal_id is not None:
            raise EvolutionProposalNotFoundError(self.missing_proposal_id)

        if self.not_accepted is not None:
            error_proposal_id, actual_status = self.not_accepted
            raise PlaybookRevisionProposalNotAcceptedError(error_proposal_id, actual_status)

        if self.proposal_mismatch is not None:
            error_proposal_id, expected_playbook_id, actual_playbook_id = self.proposal_mismatch
            raise PlaybookRevisionProposalMismatchError(
                error_proposal_id,
                expected_playbook_id,
                actual_playbook_id,
            )

        if self.missing_playbook_id is not None:
            raise RevisionPlaybookNotFoundError(self.missing_playbook_id)

        if self.missing_knowledge_id is not None:
            raise RevisionKnowledgeNotFoundError(self.missing_knowledge_id)

        if self.integrity_error is not None:
            raise self.integrity_error

        revision = PlaybookRevision(
            playbook_id=playbook_id,
            proposal_id=proposal_id,
            title=title,
            situation=situation,
            objective=objective,
            steps=steps,
            success_criteria=success_criteria,
            knowledge_ids=knowledge_ids,
            notes=notes,
            tags=tags or [],
        )
        self.revisions.append(revision)

        return revision

    def list_revisions(self) -> list[PlaybookRevision]:
        self.list_revisions_calls += 1
        if self.integrity_error is not None:
            raise self.integrity_error
        return self.revisions

    def list_for_playbook(self, playbook_id: UUID) -> list[PlaybookRevision]:
        self.list_for_playbook_calls.append(playbook_id)

        if self.integrity_error is not None:
            raise self.integrity_error

        if self.missing_playbook_id is not None and self.missing_playbook_id == playbook_id:
            raise RevisionPlaybookNotFoundError(self.missing_playbook_id)

        return [revision for revision in self.revisions if revision.playbook_id == playbook_id]

    def list_for_proposal(self, proposal_id: UUID) -> list[PlaybookRevision]:
        self.list_for_proposal_calls.append(proposal_id)

        if self.integrity_error is not None:
            raise self.integrity_error

        if self.missing_proposal_id is not None and self.missing_proposal_id == proposal_id:
            raise EvolutionProposalNotFoundError(self.missing_proposal_id)

        return [revision for revision in self.revisions if revision.proposal_id == proposal_id]

    def list_for_knowledge(self, knowledge_id: UUID) -> list[PlaybookRevision]:
        self.list_for_knowledge_calls.append(knowledge_id)

        if self.integrity_error is not None:
            raise self.integrity_error

        if self.missing_knowledge_id is not None and self.missing_knowledge_id == knowledge_id:
            raise RevisionKnowledgeNotFoundError(self.missing_knowledge_id)

        return [revision for revision in self.revisions if knowledge_id in revision.knowledge_ids]

    def get_by_id(self, revision_id: UUID) -> PlaybookRevision | None:
        self.requested_ids.append(revision_id)

        if self.integrity_error is not None:
            raise self.integrity_error

        for revision in self.revisions:
            if revision.id == revision_id:
                return revision

        return None


class FakePlaybookRevisionActivationService:
    def __init__(
        self,
        activations: list[PlaybookRevisionActivation],
        active_revision: PlaybookRevision | None = None,
        missing_playbook_id: UUID | None = None,
        missing_revision_id: UUID | None = None,
        missing_proposal_id: UUID | None = None,
        revision_mismatch: tuple[UUID, UUID, UUID] | None = None,
        proposal_mismatch: tuple[UUID, UUID, UUID] | None = None,
        previous_revision_required: bool = False,
        missing_previous_revision_id: UUID | None = None,
        previous_revision_mismatch: tuple[UUID, UUID, UUID] | None = None,
        forbidden_previous_revision_id: UUID | None = None,
    ) -> None:
        self.activations = activations
        self.active_revision = active_revision
        self.missing_playbook_id = missing_playbook_id
        self.missing_revision_id = missing_revision_id
        self.missing_proposal_id = missing_proposal_id
        self.revision_mismatch = revision_mismatch
        self.proposal_mismatch = proposal_mismatch
        self.previous_revision_required = previous_revision_required
        self.missing_previous_revision_id = missing_previous_revision_id
        self.previous_revision_mismatch = previous_revision_mismatch
        self.forbidden_previous_revision_id = forbidden_previous_revision_id
        self.list_for_playbook_calls: list[UUID] = []
        self.list_for_revision_calls: list[UUID] = []
        self.list_for_proposal_calls: list[UUID] = []
        self.get_active_revision_for_playbook_calls: list[UUID] = []
        self.add_calls: list[
            tuple[
                UUID,
                UUID,
                UUID,
                PlaybookRevisionActivationDecision,
                str,
                UUID | None,
                str | None,
                str | None,
                list[str] | None,
            ]
        ] = []

    def add(
        self,
        playbook_id: UUID,
        revision_id: UUID,
        proposal_id: UUID,
        decision: PlaybookRevisionActivationDecision,
        reason: str,
        previous_revision_id: UUID | None = None,
        decided_by: str | None = None,
        notes: str | None = None,
        tags: list[str] | None = None,
    ) -> PlaybookRevisionActivation:
        self.add_calls.append(
            (
                playbook_id,
                revision_id,
                proposal_id,
                decision,
                reason,
                previous_revision_id,
                decided_by,
                notes,
                tags,
            )
        )

        if self.missing_playbook_id is not None:
            raise PlaybookRevisionActivationPlaybookNotFoundError(self.missing_playbook_id)

        if self.missing_revision_id is not None:
            raise PlaybookRevisionActivationRevisionNotFoundError(self.missing_revision_id)

        if self.missing_proposal_id is not None:
            raise PlaybookRevisionActivationProposalNotFoundError(self.missing_proposal_id)

        if self.revision_mismatch is not None:
            error_revision_id, expected_playbook_id, actual_playbook_id = self.revision_mismatch
            raise PlaybookRevisionActivationRevisionPlaybookMismatchError(
                error_revision_id,
                expected_playbook_id,
                actual_playbook_id,
            )

        if self.proposal_mismatch is not None:
            error_revision_id, expected_proposal_id, actual_proposal_id = self.proposal_mismatch
            raise PlaybookRevisionActivationRevisionProposalMismatchError(
                error_revision_id,
                expected_proposal_id,
                actual_proposal_id,
            )

        if self.previous_revision_required:
            raise PlaybookRevisionActivationPreviousRevisionRequiredError()

        if self.missing_previous_revision_id is not None:
            raise PlaybookRevisionActivationPreviousRevisionNotFoundError(
                self.missing_previous_revision_id
            )

        if self.previous_revision_mismatch is not None:
            (
                error_previous_revision_id,
                expected_playbook_id,
                actual_playbook_id,
            ) = self.previous_revision_mismatch
            raise PlaybookRevisionActivationPreviousRevisionPlaybookMismatchError(
                error_previous_revision_id,
                expected_playbook_id,
                actual_playbook_id,
            )

        if self.forbidden_previous_revision_id is not None:
            raise PlaybookRevisionActivationPreviousRevisionForbiddenError(
                self.forbidden_previous_revision_id
            )

        activation = PlaybookRevisionActivation(
            playbook_id=playbook_id,
            revision_id=revision_id,
            proposal_id=proposal_id,
            decision=decision,
            reason=reason,
            previous_revision_id=previous_revision_id,
            decided_by=decided_by,
            notes=notes,
            tags=tags or [],
        )
        self.activations.append(activation)

        return activation

    def list_for_playbook(self, playbook_id: UUID) -> list[PlaybookRevisionActivation]:
        self.list_for_playbook_calls.append(playbook_id)

        if self.missing_playbook_id is not None:
            raise PlaybookRevisionActivationPlaybookNotFoundError(self.missing_playbook_id)

        return [
            activation for activation in self.activations if activation.playbook_id == playbook_id
        ]

    def list_for_revision(self, revision_id: UUID) -> list[PlaybookRevisionActivation]:
        self.list_for_revision_calls.append(revision_id)

        if self.missing_revision_id is not None:
            raise PlaybookRevisionActivationRevisionNotFoundError(self.missing_revision_id)

        return [
            activation for activation in self.activations if activation.revision_id == revision_id
        ]

    def list_for_proposal(self, proposal_id: UUID) -> list[PlaybookRevisionActivation]:
        self.list_for_proposal_calls.append(proposal_id)

        if self.missing_proposal_id is not None:
            raise PlaybookRevisionActivationProposalNotFoundError(self.missing_proposal_id)

        return [
            activation for activation in self.activations if activation.proposal_id == proposal_id
        ]

    def get_active_revision_for_playbook(self, playbook_id: UUID) -> PlaybookRevision | None:
        self.get_active_revision_for_playbook_calls.append(playbook_id)

        if self.missing_playbook_id is not None:
            raise PlaybookRevisionActivationPlaybookNotFoundError(self.missing_playbook_id)

        if self.missing_revision_id is not None:
            raise PlaybookRevisionActivationRevisionNotFoundError(self.missing_revision_id)

        if self.revision_mismatch is not None:
            revision_id, expected_playbook_id, actual_playbook_id = self.revision_mismatch
            raise PlaybookRevisionActivationRevisionPlaybookMismatchError(
                revision_id,
                expected_playbook_id,
                actual_playbook_id,
            )

        return self.active_revision


class FakeContainer:
    def __init__(
        self,
        decision_service: FakeDecisionService | None = None,
        decision_acceptance_service: FakeDecisionAcceptanceService | None = None,
        decision_action_service: FakeDecisionActionService | None = None,
        decision_lifecycle_service: FakeDecisionLifecycleService | None = None,
        observation_service: FakeObservationService | None = None,
        experience_service: FakeExperienceService | None = None,
        knowledge_service: FakeKnowledgeService | None = None,
        playbook_service: FakePlaybookService | None = None,
        playbook_run_service: FakePlaybookRunService | None = None,
        playbook_evaluation_service: FakePlaybookEvaluationService | None = None,
        evolution_proposal_service: FakeEvolutionProposalService | None = None,
        playbook_revision_service: FakePlaybookRevisionService | None = None,
        playbook_revision_activation_service: FakePlaybookRevisionActivationService | None = None,
    ) -> None:
        self._decision_service = decision_service
        self._decision_acceptance_service = decision_acceptance_service
        self._decision_action_service = decision_action_service
        self._decision_lifecycle_service = decision_lifecycle_service
        self._observation_service = observation_service
        self._experience_service = experience_service
        self._knowledge_service = knowledge_service
        self._playbook_service = playbook_service
        self._playbook_run_service = playbook_run_service
        self._playbook_evaluation_service = playbook_evaluation_service
        self._evolution_proposal_service = evolution_proposal_service
        self._playbook_revision_service = playbook_revision_service
        self._playbook_revision_activation_service = playbook_revision_activation_service

    def decision_service(self) -> FakeDecisionService:
        if self._decision_service is None:
            raise AssertionError("Decision service was not expected")

        return self._decision_service

    def decision_acceptance_service(self) -> FakeDecisionAcceptanceService:
        if self._decision_acceptance_service is None:
            raise AssertionError("Decision acceptance service was not expected")

        return self._decision_acceptance_service

    def decision_action_service(self) -> FakeDecisionActionService:
        if self._decision_action_service is None:
            raise AssertionError("Decision action service was not expected")
        return self._decision_action_service

    def decision_lifecycle_service(self) -> FakeDecisionLifecycleService:
        if self._decision_lifecycle_service is None:
            raise AssertionError("Decision lifecycle service was not expected")
        return self._decision_lifecycle_service

    def observation_service(self) -> FakeObservationService:
        if self._observation_service is None:
            raise AssertionError("Observation service was not expected")

        return self._observation_service

    def experience_service(self) -> FakeExperienceService:
        if self._experience_service is None:
            raise AssertionError("Experience service was not expected")

        return self._experience_service

    def knowledge_service(self) -> FakeKnowledgeService:
        if self._knowledge_service is None:
            raise AssertionError("Knowledge service was not expected")

        return self._knowledge_service

    def playbook_service(self) -> FakePlaybookService:
        if self._playbook_service is None:
            raise AssertionError("Playbook service was not expected")

        return self._playbook_service

    def playbook_run_service(self) -> FakePlaybookRunService:
        if self._playbook_run_service is None:
            raise AssertionError("Playbook run service was not expected")

        return self._playbook_run_service

    def playbook_evaluation_service(self) -> FakePlaybookEvaluationService:
        if self._playbook_evaluation_service is None:
            raise AssertionError("Playbook evaluation service was not expected")

        return self._playbook_evaluation_service

    def evolution_proposal_service(self) -> FakeEvolutionProposalService:
        if self._evolution_proposal_service is None:
            raise AssertionError("Evolution proposal service was not expected")

        return self._evolution_proposal_service

    def playbook_revision_service(self) -> FakePlaybookRevisionService:
        if self._playbook_revision_service is None:
            raise AssertionError("Playbook revision service was not expected")

        return self._playbook_revision_service

    def playbook_revision_activation_service(self) -> FakePlaybookRevisionActivationService:
        if self._playbook_revision_activation_service is None:
            raise AssertionError("Playbook revision activation service was not expected")

        return self._playbook_revision_activation_service


def test_search_displays_matching_observations(monkeypatch: pytest.MonkeyPatch) -> None:
    observation = Observation(content="Python testing notes", tags=["python", "testing"])
    service = FakeObservationService([observation])
    monkeypatch.setattr(cli, "container", FakeContainer(observation_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["search", "python"])

    assert result.exit_code == 0
    assert service.queries == ["python"]
    assert "Python testing notes" in result.output
    assert "Tags: python, testing" in result.output


def test_search_handles_no_matching_observations(monkeypatch: pytest.MonkeyPatch) -> None:
    service = FakeObservationService([])
    monkeypatch.setattr(cli, "container", FakeContainer(observation_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["search", "missing"])

    assert result.exit_code == 0
    assert service.queries == ["missing"]
    assert "No matching observations found." in result.output


def test_observe_stores_observation_without_duplicate_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakeObservationService([])
    monkeypatch.setattr(cli, "container", FakeContainer(observation_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["observe", "New content", "--tags", "new"])

    assert result.exit_code == 0
    assert service.add_calls == [("New content", ["new"])]
    assert len(service.observations) == 1
    assert "Observation stored." in result.output
    assert "Warning: exact duplicate observations already exist:" not in result.output


def test_observe_prints_duplicate_warning_and_existing_duplicate_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = Observation(content="Duplicate content")
    second = Observation(content="Duplicate content")
    service = FakeObservationService([first, second])
    monkeypatch.setattr(cli, "container", FakeContainer(observation_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["observe", "Duplicate content"])

    assert result.exit_code == 0
    assert service.add_calls == [("Duplicate content", None)]
    assert len(service.observations) == 3
    assert "Observation stored." in result.output
    assert "Warning: exact duplicate observations already exist:" in result.output
    assert f"- {first.id}" in result.output
    assert f"- {second.id}" in result.output
    assert f"- {service.observations[-1].id}" not in result.output


def test_list_displays_observation_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    observation = Observation(content="Observation content", tags=["one", "two"])
    service = FakeObservationService([observation])
    monkeypatch.setattr(cli, "container", FakeContainer(observation_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["list"])

    assert result.exit_code == 0
    assert f"ID: {observation.id}" in result.output
    assert f"Timestamp: {observation.timestamp}" in result.output
    assert "Content: Observation content" in result.output
    assert "Tags: one, two" in result.output


def test_list_handles_empty_observation_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    service = FakeObservationService([])
    monkeypatch.setattr(cli, "container", FakeContainer(observation_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["list"])

    assert result.exit_code == 0
    assert "No observations found." in result.output


def test_show_observation_delegates_and_displays_all_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observation = Observation(
        source="test",
        content="Detailed observation",
        tags=["detail"],
    )
    service = FakeObservationService([observation])
    monkeypatch.setattr(cli, "container", FakeContainer(observation_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["show", str(observation.id)])

    assert result.exit_code == 0
    assert service.requested_ids == [observation.id]
    assert f"ID: {observation.id}" in result.output
    assert f"Timestamp: {observation.timestamp}" in result.output
    assert "Source: test" in result.output
    assert "Content: Detailed observation" in result.output
    assert "Tags: detail" in result.output


def test_show_observation_handles_missing_observation(monkeypatch: pytest.MonkeyPatch) -> None:
    missing_id = UUID("77777777-7777-7777-7777-777777777777")
    service = FakeObservationService([])
    monkeypatch.setattr(cli, "container", FakeContainer(observation_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["show", str(missing_id)])

    assert result.exit_code == 1
    assert service.requested_ids == [missing_id]
    assert f"Observation not found: {missing_id}" in result.output


def test_experience_add_delegates_to_service_with_parsed_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observation_id = UUID("11111111-1111-1111-1111-111111111111")
    service = FakeExperienceService([])
    monkeypatch.setattr(cli, "container", FakeContainer(experience_service=service))
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "experience",
            "add",
            "--title",
            "Ship feature",
            "--context",
            "CLI surface",
            "--action",
            "Added commands",
            "--outcome",
            "Users can record experiences",
            "--result",
            "success",
            "--observation-id",
            str(observation_id),
            "--tag",
            "cli",
            "--tag",
            "experience",
        ],
    )

    assert result.exit_code == 0
    assert len(service.add_calls) == 1
    assert service.add_calls[0] == (
        "Ship feature",
        "CLI surface",
        "Added commands",
        "Users can record experiences",
        ExperienceResult.SUCCESS,
        [observation_id],
        ["cli", "experience"],
    )
    assert "Experience stored." in result.output
    assert str(service.experiences[0].id) in result.output


def test_experience_add_handles_missing_observation_without_storing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_id = UUID("44444444-4444-4444-4444-444444444444")
    service = FakeExperienceService([], missing_observation_id=missing_id)
    monkeypatch.setattr(cli, "container", FakeContainer(experience_service=service))
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "experience",
            "add",
            "--title",
            "Ship feature",
            "--context",
            "CLI surface",
            "--action",
            "Added commands",
            "--outcome",
            "Users can record experiences",
            "--result",
            "success",
            "--observation-id",
            str(missing_id),
        ],
    )

    assert result.exit_code == 1
    assert len(service.add_calls) == 1
    assert service.experiences == []
    assert f"Observation not found: {missing_id}" in result.output


def test_experience_add_rejects_invalid_result(monkeypatch: pytest.MonkeyPatch) -> None:
    service = FakeExperienceService([])
    monkeypatch.setattr(cli, "container", FakeContainer(experience_service=service))
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "experience",
            "add",
            "--title",
            "Ship feature",
            "--context",
            "CLI surface",
            "--action",
            "Added commands",
            "--outcome",
            "Users can record experiences",
            "--result",
            "invalid",
        ],
    )

    assert result.exit_code != 0
    assert service.add_calls == []


def test_experience_from_observation_delegates_with_parsed_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observation_id = UUID("55555555-5555-5555-5555-555555555555")
    service = FakeExperienceService([])
    monkeypatch.setattr(cli, "container", FakeContainer(experience_service=service))
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "experience",
            "from-observation",
            str(observation_id),
            "--title",
            "From observation",
            "--action",
            "Create linked experience",
            "--outcome",
            "Experience is created",
            "--result",
            "mixed",
            "--tag",
            "manual",
            "--tag",
            "linked",
        ],
    )

    assert result.exit_code == 0
    assert service.add_from_observation_calls == [
        (
            observation_id,
            "From observation",
            "Create linked experience",
            "Experience is created",
            ExperienceResult.MIXED,
            ["manual", "linked"],
        )
    ]
    assert "Experience stored from observation." in result.output
    assert str(service.experiences[0].id) in result.output


def test_experience_from_observation_handles_missing_observation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_id = UUID("66666666-6666-6666-6666-666666666666")
    service = FakeExperienceService([], missing_observation_id=missing_id)
    monkeypatch.setattr(cli, "container", FakeContainer(experience_service=service))
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "experience",
            "from-observation",
            str(missing_id),
            "--title",
            "From observation",
            "--action",
            "Create linked experience",
            "--outcome",
            "Experience is created",
            "--result",
            "success",
        ],
    )

    assert result.exit_code == 1
    assert len(service.add_from_observation_calls) == 1
    assert service.experiences == []
    assert f"Observation not found: {missing_id}" in result.output


def test_experience_list_displays_experiences(monkeypatch: pytest.MonkeyPatch) -> None:
    experience = Experience(
        title="Listed experience",
        context="CLI list",
        action="Fetch experiences",
        outcome="Experience is displayed",
        result=ExperienceResult.MIXED,
    )
    service = FakeExperienceService([experience])
    monkeypatch.setattr(cli, "container", FakeContainer(experience_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["experience", "list"])

    assert result.exit_code == 0
    assert str(experience.id) in result.output
    assert str(experience.timestamp) in result.output
    assert "Listed experience" in result.output
    assert "mixed" in result.output


def test_experience_list_handles_empty_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    service = FakeExperienceService([])
    monkeypatch.setattr(cli, "container", FakeContainer(experience_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["experience", "list"])

    assert result.exit_code == 0
    assert "No experiences found." in result.output


def test_observation_experiences_delegates_and_displays_linked_experiences(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observation_id = UUID("88888888-8888-8888-8888-888888888888")
    experience = Experience(
        title="Linked experience",
        context="CLI relation",
        action="List linked experiences",
        outcome="Experience is displayed",
        result=ExperienceResult.SUCCESS,
        observation_ids=[observation_id],
    )
    service = FakeExperienceService([experience])
    monkeypatch.setattr(cli, "container", FakeContainer(experience_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["observation", "experiences", str(observation_id)])

    assert result.exit_code == 0
    assert service.list_for_observation_calls == [observation_id]
    assert f"ID: {experience.id}" in result.output
    assert f"Timestamp: {experience.timestamp}" in result.output
    assert "Title: Linked experience" in result.output
    assert "Result: success" in result.output


def test_observation_experiences_empty_state_returns_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observation_id = UUID("99999999-9999-9999-9999-999999999999")
    service = FakeExperienceService([])
    monkeypatch.setattr(cli, "container", FakeContainer(experience_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["observation", "experiences", str(observation_id)])

    assert result.exit_code == 0
    assert service.list_for_observation_calls == [observation_id]
    assert f"No experiences linked to observation: {observation_id}" in result.output


def test_observation_experiences_missing_observation_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    service = FakeExperienceService([], missing_observation_id=missing_id)
    monkeypatch.setattr(cli, "container", FakeContainer(experience_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["observation", "experiences", str(missing_id)])

    assert result.exit_code == 1
    assert service.list_for_observation_calls == [missing_id]
    assert f"Observation not found: {missing_id}" in result.output


def test_experience_show_displays_existing_experience(monkeypatch: pytest.MonkeyPatch) -> None:
    observation_id = UUID("22222222-2222-2222-2222-222222222222")
    experience = Experience(
        title="Shown experience",
        context="CLI show",
        action="Fetch by id",
        outcome="All fields are displayed",
        result=ExperienceResult.FAILURE,
        observation_ids=[observation_id],
        tags=["debug"],
    )
    service = FakeExperienceService([experience])
    monkeypatch.setattr(cli, "container", FakeContainer(experience_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["experience", "show", str(experience.id)])

    assert result.exit_code == 0
    assert service.requested_ids == [experience.id]
    assert f"ID: {experience.id}" in result.output
    assert f"Timestamp: {experience.timestamp}" in result.output
    assert "Title: Shown experience" in result.output
    assert "Context: CLI show" in result.output
    assert "Action: Fetch by id" in result.output
    assert "Outcome: All fields are displayed" in result.output
    assert "Result: failure" in result.output
    assert f"Observation IDs: {observation_id}" in result.output
    assert "Tags: debug" in result.output


def test_experience_show_handles_missing_experience(monkeypatch: pytest.MonkeyPatch) -> None:
    missing_id = UUID("33333333-3333-3333-3333-333333333333")
    service = FakeExperienceService([])
    monkeypatch.setattr(cli, "container", FakeContainer(experience_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["experience", "show", str(missing_id)])

    assert result.exit_code == 1
    assert service.requested_ids == [missing_id]
    assert f"Experience not found: {missing_id}" in result.output


def test_experience_knowledge_delegates_and_displays_linked_knowledge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    experience_id = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    knowledge = Knowledge(
        statement="Linked knowledge",
        rationale="CLI relation test",
        confidence=KnowledgeConfidence.HIGH,
        experience_ids=[experience_id],
    )
    service = FakeKnowledgeService([knowledge])
    monkeypatch.setattr(cli, "container", FakeContainer(knowledge_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["experience", "knowledge", str(experience_id)])

    assert result.exit_code == 0
    assert service.list_for_experience_calls == [experience_id]
    assert f"ID: {knowledge.id}" in result.output
    assert f"Timestamp: {knowledge.timestamp}" in result.output
    assert "Statement: Linked knowledge" in result.output
    assert "Confidence: high" in result.output


def test_experience_knowledge_empty_state_returns_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    experience_id = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
    service = FakeKnowledgeService([])
    monkeypatch.setattr(cli, "container", FakeContainer(knowledge_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["experience", "knowledge", str(experience_id)])

    assert result.exit_code == 0
    assert service.list_for_experience_calls == [experience_id]
    assert f"No knowledge linked to experience: {experience_id}" in result.output


def test_experience_knowledge_missing_experience_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_id = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
    service = FakeKnowledgeService([], missing_experience_id=missing_id)
    monkeypatch.setattr(cli, "container", FakeContainer(knowledge_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["experience", "knowledge", str(missing_id)])

    assert result.exit_code == 1
    assert service.list_for_experience_calls == [missing_id]
    assert f"Experience not found: {missing_id}" in result.output


def test_knowledge_add_delegates_with_parsed_values_and_prints_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_experience_id = UUID("11111111-1111-1111-1111-111111111111")
    second_experience_id = UUID("22222222-2222-2222-2222-222222222222")
    service = FakeKnowledgeService([])
    monkeypatch.setattr(cli, "container", FakeContainer(knowledge_service=service))
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "knowledge",
            "add",
            "--statement",
            "Focused tests reduce debugging time",
            "--rationale",
            "Two experiences showed faster isolation with narrow test runs.",
            "--confidence",
            "high",
            "--experience-id",
            str(first_experience_id),
            "--experience-id",
            str(second_experience_id),
            "--tag",
            "testing",
            "--tag",
            "quality",
        ],
    )

    assert result.exit_code == 0
    assert service.add_calls == [
        (
            "Focused tests reduce debugging time",
            "Two experiences showed faster isolation with narrow test runs.",
            KnowledgeConfidence.HIGH,
            [first_experience_id, second_experience_id],
            ["testing", "quality"],
        )
    ]
    assert "Knowledge stored." in result.output
    assert str(service.knowledge_items[0].id) in result.output


def test_knowledge_add_handles_empty_experience_ids_without_storing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakeKnowledgeService([])
    monkeypatch.setattr(cli, "container", FakeContainer(knowledge_service=service))
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "knowledge",
            "add",
            "--statement",
            "Needs evidence",
            "--rationale",
            "Knowledge must be linked to experience.",
            "--confidence",
            "low",
        ],
    )

    assert result.exit_code == 1
    assert service.add_calls == [
        (
            "Needs evidence",
            "Knowledge must be linked to experience.",
            KnowledgeConfidence.LOW,
            [],
            None,
        )
    ]
    assert service.knowledge_items == []
    assert "Knowledge requires at least one experience ID." in result.output


def test_knowledge_add_handles_missing_experience_without_storing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_id = UUID("33333333-3333-3333-3333-333333333333")
    service = FakeKnowledgeService([], missing_experience_id=missing_id)
    monkeypatch.setattr(cli, "container", FakeContainer(knowledge_service=service))
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "knowledge",
            "add",
            "--statement",
            "Invalid evidence",
            "--rationale",
            "The experience reference is missing.",
            "--confidence",
            "medium",
            "--experience-id",
            str(missing_id),
        ],
    )

    assert result.exit_code == 1
    assert len(service.add_calls) == 1
    assert service.knowledge_items == []
    assert f"Experience not found: {missing_id}" in result.output


def test_knowledge_from_experience_delegates_with_parsed_values_and_prints_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    experience_id = UUID("99999999-9999-9999-9999-999999999999")
    service = FakeKnowledgeService([])
    monkeypatch.setattr(cli, "container", FakeContainer(knowledge_service=service))
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "knowledge",
            "from-experience",
            str(experience_id),
            "--statement",
            "Use focused regression tests",
            "--rationale",
            "The source experience showed they isolate defects quickly.",
            "--confidence",
            "medium",
            "--tag",
            "testing",
            "--tag",
            "regression",
        ],
    )

    assert result.exit_code == 0
    assert service.add_from_experience_calls == [
        (
            experience_id,
            "Use focused regression tests",
            "The source experience showed they isolate defects quickly.",
            KnowledgeConfidence.MEDIUM,
            ["testing", "regression"],
        )
    ]
    assert service.knowledge_items[0].experience_ids == [experience_id]
    assert "Knowledge stored from experience." in result.output
    assert str(service.knowledge_items[0].id) in result.output


def test_knowledge_from_experience_handles_missing_experience_without_storing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    service = FakeKnowledgeService([], missing_experience_id=missing_id)
    monkeypatch.setattr(cli, "container", FakeContainer(knowledge_service=service))
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "knowledge",
            "from-experience",
            str(missing_id),
            "--statement",
            "Missing source",
            "--rationale",
            "The source experience is absent.",
            "--confidence",
            "low",
        ],
    )

    assert result.exit_code == 1
    assert len(service.add_from_experience_calls) == 1
    assert service.knowledge_items == []
    assert f"Experience not found: {missing_id}" in result.output


def test_knowledge_list_displays_knowledge(monkeypatch: pytest.MonkeyPatch) -> None:
    experience_id = UUID("44444444-4444-4444-4444-444444444444")
    knowledge = Knowledge(
        statement="Listed knowledge",
        rationale="CLI list test",
        confidence=KnowledgeConfidence.MEDIUM,
        experience_ids=[experience_id],
    )
    service = FakeKnowledgeService([knowledge])
    monkeypatch.setattr(cli, "container", FakeContainer(knowledge_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["knowledge", "list"])

    assert result.exit_code == 0
    assert f"ID: {knowledge.id}" in result.output
    assert f"Timestamp: {knowledge.timestamp}" in result.output
    assert "Statement: Listed knowledge" in result.output
    assert "Confidence: medium" in result.output


def test_knowledge_list_handles_empty_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    service = FakeKnowledgeService([])
    monkeypatch.setattr(cli, "container", FakeContainer(knowledge_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["knowledge", "list"])

    assert result.exit_code == 0
    assert "No knowledge found." in result.output


def test_knowledge_playbooks_delegates_and_displays_linked_playbooks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    knowledge_id = UUID("45454545-4545-4545-4545-454545454545")
    playbook = Playbook(
        title="Linked playbook",
        situation="CLI relation test",
        objective="Display linked playbooks",
        steps=["List playbooks"],
        success_criteria=["Playbook is displayed"],
        knowledge_ids=[knowledge_id],
    )
    service = FakePlaybookService([playbook])
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["knowledge", "playbooks", str(knowledge_id)])

    assert result.exit_code == 0
    assert service.list_for_knowledge_calls == [knowledge_id]
    assert f"ID: {playbook.id}" in result.output
    assert f"Timestamp: {playbook.timestamp}" in result.output
    assert "Title: Linked playbook" in result.output
    assert "Objective: Display linked playbooks" in result.output


def test_knowledge_playbooks_empty_state_returns_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    knowledge_id = UUID("67676767-6767-6767-6767-676767676767")
    service = FakePlaybookService([])
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["knowledge", "playbooks", str(knowledge_id)])

    assert result.exit_code == 0
    assert service.list_for_knowledge_calls == [knowledge_id]
    assert f"No playbooks linked to knowledge: {knowledge_id}" in result.output


def test_knowledge_playbooks_missing_knowledge_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_id = UUID("78787878-7878-7878-7878-787878787878")
    service = FakePlaybookService([], missing_knowledge_id=missing_id)
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["knowledge", "playbooks", str(missing_id)])

    assert result.exit_code == 1
    assert service.list_for_knowledge_calls == [missing_id]
    assert f"Knowledge not found: {missing_id}" in result.output


def test_knowledge_show_delegates_and_displays_all_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_experience_id = UUID("55555555-5555-5555-5555-555555555555")
    second_experience_id = UUID("66666666-6666-6666-6666-666666666666")
    knowledge = Knowledge(
        statement="Shown knowledge",
        rationale="CLI show should display every field.",
        confidence=KnowledgeConfidence.HIGH,
        experience_ids=[first_experience_id, second_experience_id],
        tags=["manual", "lesson"],
    )
    service = FakeKnowledgeService([knowledge])
    monkeypatch.setattr(cli, "container", FakeContainer(knowledge_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["knowledge", "show", str(knowledge.id)])

    assert result.exit_code == 0
    assert service.requested_ids == [knowledge.id]
    assert f"ID: {knowledge.id}" in result.output
    assert f"Timestamp: {knowledge.timestamp}" in result.output
    assert "Statement: Shown knowledge" in result.output
    assert "Rationale: CLI show should display every field." in result.output
    assert "Confidence: high" in result.output
    assert "Experience IDs:" in result.output
    assert str(first_experience_id) in result.output
    assert str(second_experience_id) in result.output
    assert "Tags: manual, lesson" in result.output


def test_knowledge_show_displays_dash_for_empty_tags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    experience_id = UUID("77777777-7777-7777-7777-777777777777")
    knowledge = Knowledge(
        statement="No tags",
        rationale="Empty tags should render consistently.",
        confidence=KnowledgeConfidence.LOW,
        experience_ids=[experience_id],
    )
    service = FakeKnowledgeService([knowledge])
    monkeypatch.setattr(cli, "container", FakeContainer(knowledge_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["knowledge", "show", str(knowledge.id)])

    assert result.exit_code == 0
    assert "Tags: -" in result.output


def test_knowledge_show_handles_missing_knowledge(monkeypatch: pytest.MonkeyPatch) -> None:
    missing_id = UUID("88888888-8888-8888-8888-888888888888")
    service = FakeKnowledgeService([])
    monkeypatch.setattr(cli, "container", FakeContainer(knowledge_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["knowledge", "show", str(missing_id)])

    assert result.exit_code == 1
    assert service.requested_ids == [missing_id]
    assert f"Knowledge not found: {missing_id}" in result.output


@pytest.mark.parametrize(
    "command",
    [
        [
            "knowledge",
            "add",
            "--statement",
            "Rejected knowledge",
            "--rationale",
            "Promoted ancestry is corrupt.",
            "--confidence",
            "high",
            "--experience-id",
            "11111111-1111-1111-1111-111111111111",
        ],
        [
            "knowledge",
            "from-experience",
            "11111111-1111-1111-1111-111111111111",
            "--statement",
            "Rejected knowledge",
            "--rationale",
            "Promoted ancestry is corrupt.",
            "--confidence",
            "high",
        ],
        ["knowledge", "list"],
        ["knowledge", "show", "22222222-2222-2222-2222-222222222222"],
        ["experience", "knowledge", "11111111-1111-1111-1111-111111111111"],
    ],
    ids=[
        "knowledge-add",
        "knowledge-from-experience",
        "knowledge-list",
        "knowledge-show",
        "experience-knowledge",
    ],
)
@pytest.mark.parametrize(
    "integrity_error",
    [
        DecisionReviewNotFoundError(UUID("33333333-3333-3333-3333-333333333333")),
        DecisionReviewPromotionSourceIndexError(
            UUID("33333333-3333-3333-3333-333333333333"),
            DecisionReviewPromotionSourceKind.FINDING,
            4,
        ),
    ],
    ids=["review-relation", "promotion-source"],
)
def test_knowledge_surfaces_render_controlled_ancestry_integrity_errors(
    monkeypatch: pytest.MonkeyPatch,
    command: list[str],
    integrity_error: Exception,
) -> None:
    service = FakeKnowledgeService([], integrity_error=integrity_error)
    monkeypatch.setattr(cli, "container", FakeContainer(knowledge_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, command)

    assert result.exit_code == 1
    assert " ".join(str(integrity_error).split()) in " ".join(result.output.split())
    assert "Traceback" not in result.output


@pytest.mark.parametrize(
    "command",
    [
        [
            "knowledge",
            "add",
            "--statement",
            "Collision",
            "--rationale",
            "A generated UUID already has a different payload.",
            "--confidence",
            "high",
            "--experience-id",
            "11111111-1111-1111-1111-111111111111",
        ],
        [
            "knowledge",
            "from-experience",
            "11111111-1111-1111-1111-111111111111",
            "--statement",
            "Collision",
            "--rationale",
            "A generated UUID already has a different payload.",
            "--confidence",
            "high",
        ],
    ],
    ids=["knowledge-add", "knowledge-from-experience"],
)
def test_knowledge_creation_renders_controlled_persistence_conflict_without_storing(
    monkeypatch: pytest.MonkeyPatch,
    command: list[str],
) -> None:
    knowledge_id = UUID("99999999-9999-9999-9999-999999999999")
    conflict = KnowledgePersistenceConflictError(knowledge_id)
    service = FakeKnowledgeService([], integrity_error=conflict)
    monkeypatch.setattr(cli, "container", FakeContainer(knowledge_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, command)

    assert result.exit_code == 1
    assert service.knowledge_items == []
    assert " ".join(str(conflict).split()) in " ".join(result.output.split())
    assert "Traceback" not in result.output


def test_playbook_add_delegates_with_parsed_repeatable_values_and_prints_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_knowledge_id = UUID("99999999-9999-9999-9999-999999999999")
    second_knowledge_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    service = FakePlaybookService([])
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_service=service))
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "playbook",
            "add",
            "--title",
            "Debug flaky tests",
            "--situation",
            "A test fails intermittently",
            "--objective",
            "Find the unstable dependency",
            "--step",
            "Run the failing test repeatedly",
            "--step",
            "Inspect shared state",
            "--success-criterion",
            "Failure source is isolated",
            "--success-criterion",
            "The fix is verified",
            "--knowledge-id",
            str(first_knowledge_id),
            "--knowledge-id",
            str(second_knowledge_id),
            "--constraint",
            "Do not skip the test",
            "--constraint",
            "Keep changes focused",
            "--tag",
            "testing",
            "--tag",
            "debugging",
        ],
    )

    assert result.exit_code == 0
    assert service.add_calls == [
        (
            "Debug flaky tests",
            "A test fails intermittently",
            "Find the unstable dependency",
            ["Run the failing test repeatedly", "Inspect shared state"],
            ["Failure source is isolated", "The fix is verified"],
            [first_knowledge_id, second_knowledge_id],
            ["Do not skip the test", "Keep changes focused"],
            ["testing", "debugging"],
        )
    ]
    assert "Playbook stored." in result.output
    assert str(service.playbooks[0].id) in result.output


def test_playbook_add_handles_empty_knowledge_ids_without_storing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakePlaybookService([])
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_service=service))
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "playbook",
            "add",
            "--title",
            "Needs knowledge",
            "--situation",
            "No knowledge was supplied",
            "--objective",
            "Reject the playbook",
            "--step",
            "Do one thing",
            "--success-criterion",
            "It is rejected",
        ],
    )

    assert result.exit_code == 1
    assert service.add_calls == [
        (
            "Needs knowledge",
            "No knowledge was supplied",
            "Reject the playbook",
            ["Do one thing"],
            ["It is rejected"],
            [],
            None,
            None,
        )
    ]
    assert service.playbooks == []
    assert "Playbook requires at least one knowledge ID." in result.output


def test_playbook_add_handles_empty_steps_without_storing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    knowledge_id = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    service = FakePlaybookService([])
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_service=service))
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "playbook",
            "add",
            "--title",
            "Needs steps",
            "--situation",
            "No steps were supplied",
            "--objective",
            "Reject the playbook",
            "--success-criterion",
            "It is rejected",
            "--knowledge-id",
            str(knowledge_id),
        ],
    )

    assert result.exit_code == 1
    assert len(service.add_calls) == 1
    assert service.add_calls[0][3] == []
    assert service.playbooks == []
    assert "Playbook requires at least one step." in result.output


def test_playbook_add_requires_success_criterion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    knowledge_id = UUID("56565656-5656-5656-5656-565656565656")
    service = FakePlaybookService([])
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_service=service))
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "playbook",
            "add",
            "--title",
            "Missing criterion",
            "--situation",
            "No success criterion was supplied",
            "--objective",
            "Reject incomplete CLI input",
            "--step",
            "Perform one action",
            "--knowledge-id",
            str(knowledge_id),
        ],
    )

    assert result.exit_code != 0
    assert service.add_calls == []


def test_playbook_add_handles_missing_knowledge_without_storing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_id = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
    service = FakePlaybookService([], missing_knowledge_id=missing_id)
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_service=service))
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "playbook",
            "add",
            "--title",
            "Missing knowledge",
            "--situation",
            "A linked knowledge item is absent",
            "--objective",
            "Reject the playbook",
            "--step",
            "Validate knowledge",
            "--success-criterion",
            "It is rejected",
            "--knowledge-id",
            str(missing_id),
        ],
    )

    assert result.exit_code == 1
    assert len(service.add_calls) == 1
    assert service.playbooks == []
    assert f"Knowledge not found: {missing_id}" in result.output


def test_playbook_list_displays_playbooks(monkeypatch: pytest.MonkeyPatch) -> None:
    knowledge_id = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
    playbook = Playbook(
        title="Listed playbook",
        situation="CLI list",
        objective="Display summary fields",
        steps=["List playbooks"],
        success_criteria=["Playbook is visible"],
        knowledge_ids=[knowledge_id],
    )
    service = FakePlaybookService([playbook])
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["playbook", "list"])

    assert result.exit_code == 0
    assert f"ID: {playbook.id}" in result.output
    assert f"Timestamp: {playbook.timestamp}" in result.output
    assert "Title: Listed playbook" in result.output
    assert "Objective: Display summary fields" in result.output


def test_playbook_list_handles_empty_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    service = FakePlaybookService([])
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["playbook", "list"])

    assert result.exit_code == 0
    assert "No playbooks found." in result.output


def test_playbook_show_delegates_and_displays_all_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_knowledge_id = UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
    second_knowledge_id = UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
    playbook = Playbook(
        title="Shown playbook",
        situation="A production issue repeats",
        objective="Resolve it consistently",
        steps=["Collect evidence", "Apply the fix"],
        success_criteria=["Root cause is known", "Regression is covered"],
        constraints=["No broad refactor", "Keep logs"],
        knowledge_ids=[first_knowledge_id, second_knowledge_id],
        tags=["ops", "debugging"],
    )
    service = FakePlaybookService([playbook])
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["playbook", "show", str(playbook.id)])

    assert result.exit_code == 0
    assert service.requested_ids == [playbook.id]
    assert f"ID: {playbook.id}" in result.output
    assert f"Timestamp: {playbook.timestamp}" in result.output
    assert "Title: Shown playbook" in result.output
    assert "Situation: A production issue repeats" in result.output
    assert "Objective: Resolve it consistently" in result.output
    assert "Steps:" in result.output
    assert "- Collect evidence" in result.output
    assert "- Apply the fix" in result.output
    assert "Success criteria:" in result.output
    assert "- Root cause is known" in result.output
    assert "- Regression is covered" in result.output
    assert "Constraints:" in result.output
    assert "- No broad refactor" in result.output
    assert "- Keep logs" in result.output
    assert "Knowledge IDs:" in result.output
    assert str(first_knowledge_id) in result.output
    assert str(second_knowledge_id) in result.output
    assert "Tags: ops, debugging" in result.output


def test_playbook_show_displays_dash_for_empty_constraints_and_tags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    knowledge_id = UUID("12121212-1212-1212-1212-121212121212")
    playbook = Playbook(
        title="No optional fields",
        situation="Optional fields are empty",
        objective="Render empty fields clearly",
        steps=["Show playbook"],
        success_criteria=["Output is clear"],
        knowledge_ids=[knowledge_id],
    )
    service = FakePlaybookService([playbook])
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["playbook", "show", str(playbook.id)])

    assert result.exit_code == 0
    assert "Constraints:\n-" in result.output
    assert "Tags: -" in result.output


def test_playbook_show_handles_missing_playbook(monkeypatch: pytest.MonkeyPatch) -> None:
    missing_id = UUID("34343434-3434-3434-3434-343434343434")
    service = FakePlaybookService([])
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["playbook", "show", str(missing_id)])

    assert result.exit_code == 1
    assert service.requested_ids == [missing_id]
    assert f"Playbook not found: {missing_id}" in result.output


def test_playbook_runs_delegates_positional_uuid_and_displays_linked_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playbook_id = UUID("45454545-4545-4545-4545-454545454545")
    run = PlaybookRun(
        playbook_id=playbook_id,
        situation="Linked playbook run",
        actions_taken=["Applied playbook manually"],
        outcome="Run outcome recorded",
        success=True,
    )
    service = FakePlaybookRunService([run])
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_run_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["playbook", "runs", str(playbook_id)])

    assert result.exit_code == 0
    assert service.list_for_playbook_calls == [playbook_id]
    assert f"ID: {run.id}" in result.output
    assert f"Timestamp: {run.timestamp}" in result.output
    assert "Situation: Linked playbook run" in result.output
    assert "Success: true" in result.output


def test_playbook_runs_empty_state_returns_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playbook_id = UUID("56565656-5656-5656-5656-565656565656")
    service = FakePlaybookRunService([])
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_run_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["playbook", "runs", str(playbook_id)])

    assert result.exit_code == 0
    assert service.list_for_playbook_calls == [playbook_id]
    assert f"No playbook runs linked to playbook: {playbook_id}" in result.output


def test_playbook_runs_missing_playbook_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_id = UUID("67676767-6767-6767-6767-676767676767")
    service = FakePlaybookRunService([], missing_playbook_id=missing_id)
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_run_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["playbook", "runs", str(missing_id)])

    assert result.exit_code == 1
    assert service.list_for_playbook_calls == [missing_id]
    assert f"Playbook not found: {missing_id}" in result.output


def test_playbook_proposals_delegates_positional_uuid_and_displays_linked_proposals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playbook_id = UUID("78787878-7878-7878-7878-787878787878")
    proposal = EvolutionProposal(
        playbook_id=playbook_id,
        evaluation_ids=[UUID("89898989-8989-8989-8989-898989898989")],
        summary="Linked proposal",
        rationale="Manual relation lookup",
        proposed_changes=["Clarify step"],
        expected_benefits=["Clearer manual use"],
        status=EvolutionProposalStatus.ACCEPTED,
    )
    service = FakeEvolutionProposalService([proposal])
    monkeypatch.setattr(cli, "container", FakeContainer(evolution_proposal_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["playbook", "proposals", str(playbook_id)])

    assert result.exit_code == 0
    assert service.list_for_playbook_calls == [playbook_id]
    assert f"ID: {proposal.id}" in result.output
    assert f"Timestamp: {proposal.timestamp}" in result.output
    assert "Summary: Linked proposal" in result.output
    assert "Status: accepted" in result.output


def test_playbook_proposals_empty_state_returns_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playbook_id = UUID("90909090-9090-9090-9090-909090909090")
    service = FakeEvolutionProposalService([])
    monkeypatch.setattr(cli, "container", FakeContainer(evolution_proposal_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["playbook", "proposals", str(playbook_id)])

    assert result.exit_code == 0
    assert service.list_for_playbook_calls == [playbook_id]
    assert f"No evolution proposals linked to playbook: {playbook_id}" in result.output


def test_playbook_proposals_missing_playbook_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_id = UUID("91919191-9191-9191-9191-919191919191")
    service = FakeEvolutionProposalService([], missing_playbook_id=missing_id)
    monkeypatch.setattr(cli, "container", FakeContainer(evolution_proposal_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["playbook", "proposals", str(missing_id)])

    assert result.exit_code == 1
    assert service.list_for_playbook_calls == [missing_id]
    assert f"Playbook not found: {missing_id}" in result.output


def test_playbook_revisions_delegates_positional_uuid_and_displays_linked_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playbook_id = UUID("92929292-9292-9292-9292-929292929292")
    revision = make_revision("Linked playbook revision", playbook_id=playbook_id)
    service = FakePlaybookRevisionService([revision])
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_revision_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["playbook", "revisions", str(playbook_id)])

    assert result.exit_code == 0
    assert service.list_for_playbook_calls == [playbook_id]
    assert f"ID: {revision.id}" in result.output
    assert f"Timestamp: {revision.timestamp}" in result.output
    assert f"Playbook ID: {playbook_id}" in result.output
    assert f"Proposal ID: {revision.proposal_id}" in result.output
    assert "Title: Linked playbook revision" in result.output


def test_playbook_revisions_displays_multiple_revisions_in_service_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playbook_id = UUID("93939393-9393-9393-9393-939393939393")
    first = make_revision("First linked revision", playbook_id=playbook_id)
    second = make_revision("Second linked revision", playbook_id=playbook_id)
    service = FakePlaybookRevisionService([first, second])
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_revision_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["playbook", "revisions", str(playbook_id)])

    assert result.exit_code == 0
    assert service.list_for_playbook_calls == [playbook_id]
    assert result.output.index("Title: First linked revision") < result.output.index(
        "Title: Second linked revision"
    )


def test_playbook_revisions_empty_state_returns_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playbook_id = UUID("94949494-9494-9494-9494-949494949494")
    service = FakePlaybookRevisionService([])
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_revision_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["playbook", "revisions", str(playbook_id)])

    assert result.exit_code == 0
    assert service.list_for_playbook_calls == [playbook_id]
    assert f"No playbook revisions linked to playbook: {playbook_id}" in result.output


def test_playbook_revisions_missing_playbook_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_id = UUID("95959595-9595-9595-9595-959595959595")
    service = FakePlaybookRevisionService([], missing_playbook_id=missing_id)
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_revision_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["playbook", "revisions", str(missing_id)])

    assert result.exit_code == 1
    assert service.list_for_playbook_calls == [missing_id]
    assert f"Playbook not found: {missing_id}" in result.output


def test_playbook_revisions_invalid_uuid_returns_usage_error_without_calling_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakePlaybookRevisionService([])
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_revision_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["playbook", "revisions", "not-a-uuid"])

    assert result.exit_code == 2
    assert "Invalid value" in result.output
    assert service.list_for_playbook_calls == []


def test_playbook_revision_history_empty_state_returns_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playbook_id = UUID("11111111-1111-2222-3333-aaaaaaaaaaaa")
    service = FakePlaybookRevisionActivationService([])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_activation_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(cli.app, ["playbook", "revision-history", str(playbook_id)])

    assert result.exit_code == 0
    assert service.list_for_playbook_calls == [playbook_id]
    assert "No playbook revision lifecycle records linked to playbook:" in result.output
    assert str(playbook_id) in result.output
    assert service.add_calls == []


def test_playbook_revision_history_displays_one_activation_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playbook_id = UUID("22222222-1111-2222-3333-aaaaaaaaaaaa")
    revision_id = UUID("33333333-1111-2222-3333-aaaaaaaaaaaa")
    proposal_id = UUID("44444444-1111-2222-3333-aaaaaaaaaaaa")
    activation = make_activation(playbook_id, revision_id, proposal_id)
    service = FakePlaybookRevisionActivationService([activation])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_activation_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(cli.app, ["playbook", "revision-history", str(playbook_id)])

    assert result.exit_code == 0
    assert service.list_for_playbook_calls == [playbook_id]
    assert f"ID: {activation.id}" in result.output
    assert f"Timestamp: {activation.timestamp}" in result.output
    assert f"Playbook ID: {playbook_id}" in result.output
    assert f"Revision ID: {revision_id}" in result.output
    assert f"Proposal ID: {proposal_id}" in result.output
    assert "Decision: active" in result.output
    assert "Reason: Manual lifecycle decision" in result.output
    assert service.add_calls == []


def test_playbook_revision_history_displays_multiple_records_in_service_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playbook_id = UUID("55555555-1111-2222-3333-aaaaaaaaaaaa")
    proposal_id = UUID("66666666-1111-2222-3333-aaaaaaaaaaaa")
    first = make_activation(
        playbook_id,
        UUID("77777777-1111-2222-3333-aaaaaaaaaaaa"),
        proposal_id,
        reason="First decision",
    )
    second = make_activation(
        playbook_id,
        UUID("88888888-1111-2222-3333-aaaaaaaaaaaa"),
        proposal_id,
        reason="Second decision",
    )
    service = FakePlaybookRevisionActivationService([first, second])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_activation_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(cli.app, ["playbook", "revision-history", str(playbook_id)])

    assert result.exit_code == 0
    assert result.output.index("Reason: First decision") < result.output.index(
        "Reason: Second decision"
    )


def test_playbook_revision_history_displays_optional_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playbook_id = UUID("99999999-1111-2222-3333-aaaaaaaaaaaa")
    revision_id = UUID("aaaaaaaa-1111-2222-3333-aaaaaaaaaaaa")
    proposal_id = UUID("bbbbbbbb-1111-2222-3333-aaaaaaaaaaaa")
    previous_revision_id = UUID("cccccccc-1111-2222-3333-aaaaaaaaaaaa")
    activation = make_activation(
        playbook_id,
        revision_id,
        proposal_id,
        decision=PlaybookRevisionActivationDecision.SUPERSEDED,
        previous_revision_id=previous_revision_id,
        decided_by="reviewer",
        notes="Lifecycle note",
        tags=["manual", "history"],
    )
    service = FakePlaybookRevisionActivationService([activation])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_activation_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(cli.app, ["playbook", "revision-history", str(playbook_id)])

    assert result.exit_code == 0
    assert f"Previous revision ID: {previous_revision_id}" in result.output
    assert "Decided by: reviewer" in result.output
    assert "Notes: Lifecycle note" in result.output
    assert "Tags: manual, history" in result.output


def test_playbook_revision_history_missing_playbook_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_id = UUID("dddddddd-1111-2222-3333-aaaaaaaaaaaa")
    service = FakePlaybookRevisionActivationService([], missing_playbook_id=missing_id)
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_activation_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(cli.app, ["playbook", "revision-history", str(missing_id)])

    assert result.exit_code == 1
    assert service.list_for_playbook_calls == [missing_id]
    assert f"Playbook not found: {missing_id}" in result.output
    assert service.add_calls == []


def test_playbook_active_revision_no_active_revision_returns_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playbook_id = UUID("eeeeeeee-1111-2222-3333-aaaaaaaaaaaa")
    service = FakePlaybookRevisionActivationService([])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_activation_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(cli.app, ["playbook", "active-revision", str(playbook_id)])

    assert result.exit_code == 0
    assert service.get_active_revision_for_playbook_calls == [playbook_id]
    assert f"No active playbook revision for playbook: {playbook_id}" in result.output
    assert service.add_calls == []


def test_playbook_active_revision_displays_revision_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playbook_id = UUID("ffffffff-1111-2222-3333-aaaaaaaaaaaa")
    revision = make_revision("Current active revision", playbook_id=playbook_id)
    service = FakePlaybookRevisionActivationService([], active_revision=revision)
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_activation_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(cli.app, ["playbook", "active-revision", str(playbook_id)])

    assert result.exit_code == 0
    assert service.get_active_revision_for_playbook_calls == [playbook_id]
    assert f"ID: {revision.id}" in result.output
    assert f"Playbook ID: {playbook_id}" in result.output
    assert f"Proposal ID: {revision.proposal_id}" in result.output
    assert "Title: Current active revision" in result.output
    assert "Situation: Revision situation" in result.output
    assert "Objective: Revision objective" in result.output
    assert "Steps:" in result.output
    assert "- First revised step" in result.output
    assert "Success criteria:" in result.output
    assert "- First success criterion" in result.output
    assert "Knowledge IDs:" in result.output
    assert str(revision.knowledge_ids[0]) in result.output
    assert service.add_calls == []


def test_playbook_active_revision_missing_playbook_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_id = UUID("12121212-2222-3333-4444-aaaaaaaaaaaa")
    service = FakePlaybookRevisionActivationService([], missing_playbook_id=missing_id)
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_activation_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(cli.app, ["playbook", "active-revision", str(missing_id)])

    assert result.exit_code == 1
    assert service.get_active_revision_for_playbook_calls == [missing_id]
    assert f"Playbook not found: {missing_id}" in result.output
    assert service.add_calls == []


def test_playbook_active_revision_missing_derived_revision_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playbook_id = UUID("23232323-2222-3333-4444-aaaaaaaaaaaa")
    missing_revision_id = UUID("34343434-2222-3333-4444-aaaaaaaaaaaa")
    service = FakePlaybookRevisionActivationService(
        [],
        missing_revision_id=missing_revision_id,
    )
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_activation_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(cli.app, ["playbook", "active-revision", str(playbook_id)])

    assert result.exit_code == 1
    assert service.get_active_revision_for_playbook_calls == [playbook_id]
    assert f"Playbook revision not found: {missing_revision_id}" in result.output
    assert service.add_calls == []


def test_playbook_active_revision_mismatched_derived_revision_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playbook_id = UUID("45454545-2222-3333-4444-aaaaaaaaaaaa")
    revision_id = UUID("56565656-2222-3333-4444-aaaaaaaaaaaa")
    actual_playbook_id = UUID("67676767-2222-3333-4444-aaaaaaaaaaaa")
    service = FakePlaybookRevisionActivationService(
        [],
        revision_mismatch=(revision_id, playbook_id, actual_playbook_id),
    )
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_activation_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(cli.app, ["playbook", "active-revision", str(playbook_id)])

    assert result.exit_code == 1
    assert service.get_active_revision_for_playbook_calls == [playbook_id]
    assert str(revision_id) in result.output
    assert str(playbook_id) in result.output
    assert str(actual_playbook_id) in result.output
    assert service.add_calls == []


def test_proposal_revisions_delegates_positional_uuid_and_displays_linked_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal_id = UUID("96969696-9696-9696-9696-969696969696")
    revision = make_revision("Linked proposal revision", proposal_id=proposal_id)
    service = FakePlaybookRevisionService([revision])
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_revision_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["proposal", "revisions", str(proposal_id)])

    assert result.exit_code == 0
    assert service.list_for_proposal_calls == [proposal_id]
    assert f"ID: {revision.id}" in result.output
    assert f"Timestamp: {revision.timestamp}" in result.output
    assert f"Playbook ID: {revision.playbook_id}" in result.output
    assert f"Proposal ID: {proposal_id}" in result.output
    assert "Title: Linked proposal revision" in result.output


def test_proposal_revisions_displays_multiple_revisions_in_service_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal_id = UUID("97979797-9797-9797-9797-979797979797")
    first = make_revision("First linked revision", proposal_id=proposal_id)
    second = make_revision("Second linked revision", proposal_id=proposal_id)
    service = FakePlaybookRevisionService([first, second])
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_revision_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["proposal", "revisions", str(proposal_id)])

    assert result.exit_code == 0
    assert service.list_for_proposal_calls == [proposal_id]
    assert result.output.index("Title: First linked revision") < result.output.index(
        "Title: Second linked revision"
    )


def test_proposal_revisions_empty_state_returns_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal_id = UUID("98989898-9898-9898-9898-989898989898")
    service = FakePlaybookRevisionService([])
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_revision_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["proposal", "revisions", str(proposal_id)])

    assert result.exit_code == 0
    assert service.list_for_proposal_calls == [proposal_id]
    assert f"No playbook revisions linked to proposal: {proposal_id}" in result.output


def test_proposal_revisions_missing_proposal_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_id = UUID("99999999-9999-9999-9999-999999999999")
    service = FakePlaybookRevisionService([], missing_proposal_id=missing_id)
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_revision_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["proposal", "revisions", str(missing_id)])

    assert result.exit_code == 1
    assert service.list_for_proposal_calls == [missing_id]
    assert f"Evolution proposal not found: {missing_id}" in result.output


def test_proposal_revisions_invalid_uuid_returns_usage_error_without_calling_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakePlaybookRevisionService([])
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_revision_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["proposal", "revisions", "not-a-uuid"])

    assert result.exit_code == 2
    assert "Invalid value" in result.output
    assert service.list_for_proposal_calls == []


def test_proposal_activation_history_delegates_uuid_and_displays_records_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal_id = UUID("11111111-2222-3333-4444-bbbbbbbbbbbb")
    first = make_activation(
        UUID("22222222-2222-3333-4444-bbbbbbbbbbbb"),
        UUID("33333333-2222-3333-4444-bbbbbbbbbbbb"),
        proposal_id,
        reason="First proposal decision",
    )
    second = make_activation(
        UUID("44444444-2222-3333-4444-bbbbbbbbbbbb"),
        UUID("55555555-2222-3333-4444-bbbbbbbbbbbb"),
        proposal_id,
        reason="Second proposal decision",
    )
    service = FakePlaybookRevisionActivationService([first, second])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_activation_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(cli.app, ["proposal", "activation-history", str(proposal_id)])

    assert result.exit_code == 0
    assert service.list_for_proposal_calls == [proposal_id]
    assert f"ID: {first.id}" in result.output
    assert f"ID: {second.id}" in result.output
    assert result.output.index("Reason: First proposal decision") < result.output.index(
        "Reason: Second proposal decision"
    )
    assert service.add_calls == []
    assert service.list_for_playbook_calls == []
    assert service.list_for_revision_calls == []
    assert service.get_active_revision_for_playbook_calls == []


def test_proposal_activation_history_empty_state_returns_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal_id = UUID("66666666-2222-3333-4444-bbbbbbbbbbbb")
    service = FakePlaybookRevisionActivationService([])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_activation_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(cli.app, ["proposal", "activation-history", str(proposal_id)])

    assert result.exit_code == 0
    assert service.list_for_proposal_calls == [proposal_id]
    assert "No playbook revision activation records found for proposal:" in result.output
    assert str(proposal_id) in result.output
    assert service.add_calls == []


def test_proposal_activation_history_missing_proposal_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_proposal_id = UUID("77777777-2222-3333-4444-bbbbbbbbbbbb")
    service = FakePlaybookRevisionActivationService([], missing_proposal_id=missing_proposal_id)
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_activation_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(cli.app, ["proposal", "activation-history", str(missing_proposal_id)])

    assert result.exit_code == 1
    assert service.list_for_proposal_calls == [missing_proposal_id]
    assert f"Evolution proposal not found: {missing_proposal_id}" in result.output
    assert service.add_calls == []


def test_proposal_activation_history_invalid_uuid_returns_usage_error_without_calling_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakePlaybookRevisionActivationService([])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_activation_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(cli.app, ["proposal", "activation-history", "not-a-uuid"])

    assert result.exit_code == 2
    assert "Invalid value" in result.output
    assert service.list_for_proposal_calls == []
    assert service.add_calls == []


def test_knowledge_revisions_delegates_positional_uuid_and_displays_linked_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    knowledge_id = UUID("9a9a9a9a-9a9a-9a9a-9a9a-9a9a9a9a9a9a")
    revision = make_revision("Linked knowledge revision", knowledge_ids=[knowledge_id])
    service = FakePlaybookRevisionService([revision])
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_revision_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["knowledge", "revisions", str(knowledge_id)])

    assert result.exit_code == 0
    assert service.list_for_knowledge_calls == [knowledge_id]
    assert f"ID: {revision.id}" in result.output
    assert f"Timestamp: {revision.timestamp}" in result.output
    assert f"Playbook ID: {revision.playbook_id}" in result.output
    assert f"Proposal ID: {revision.proposal_id}" in result.output
    assert "Title: Linked knowledge revision" in result.output


def test_knowledge_revisions_displays_multiple_revisions_in_service_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    knowledge_id = UUID("9b9b9b9b-9b9b-9b9b-9b9b-9b9b9b9b9b9b")
    first = make_revision("First linked revision", knowledge_ids=[knowledge_id])
    second = make_revision("Second linked revision", knowledge_ids=[knowledge_id])
    service = FakePlaybookRevisionService([first, second])
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_revision_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["knowledge", "revisions", str(knowledge_id)])

    assert result.exit_code == 0
    assert service.list_for_knowledge_calls == [knowledge_id]
    assert result.output.index("Title: First linked revision") < result.output.index(
        "Title: Second linked revision"
    )


def test_knowledge_revisions_empty_state_returns_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    knowledge_id = UUID("9c9c9c9c-9c9c-9c9c-9c9c-9c9c9c9c9c9c")
    service = FakePlaybookRevisionService([])
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_revision_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["knowledge", "revisions", str(knowledge_id)])

    assert result.exit_code == 0
    assert service.list_for_knowledge_calls == [knowledge_id]
    assert f"No playbook revisions linked to knowledge: {knowledge_id}" in result.output


def test_knowledge_revisions_missing_knowledge_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_id = UUID("9d9d9d9d-9d9d-9d9d-9d9d-9d9d9d9d9d9d")
    service = FakePlaybookRevisionService([], missing_knowledge_id=missing_id)
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_revision_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["knowledge", "revisions", str(missing_id)])

    assert result.exit_code == 1
    assert service.list_for_knowledge_calls == [missing_id]
    assert f"Knowledge not found: {missing_id}" in result.output


def test_knowledge_revisions_invalid_uuid_returns_usage_error_without_calling_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakePlaybookRevisionService([])
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_revision_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["knowledge", "revisions", "not-a-uuid"])

    assert result.exit_code == 2
    assert "Invalid value" in result.output
    assert service.list_for_knowledge_calls == []


def test_run_add_delegates_with_parsed_values_and_prints_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playbook_id = UUID("45454545-4545-4545-4545-454545454545")
    service = FakePlaybookRunService([])
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_run_service=service))
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "run",
            "add",
            "--playbook-id",
            str(playbook_id),
            "--situation",
            "Production incident repeated",
            "--action",
            "Applied the playbook manually",
            "--action",
            "Collected follow-up evidence",
            "--outcome",
            "Service recovered",
            "--success",
            "true",
            "--evidence",
            "Incident log",
            "--evidence",
            "Recovery metric",
            "--notes",
            "Manual run recorded after incident",
            "--tag",
            "ops",
            "--tag",
            "manual",
        ],
    )

    assert result.exit_code == 0
    assert service.add_calls == [
        (
            playbook_id,
            "Production incident repeated",
            ["Applied the playbook manually", "Collected follow-up evidence"],
            "Service recovered",
            True,
            ["Incident log", "Recovery metric"],
            "Manual run recorded after incident",
            ["ops", "manual"],
            None,
        )
    ]
    assert "Playbook run stored." in result.output
    assert str(service.runs[0].id) in result.output


def test_run_add_parses_success_false(monkeypatch: pytest.MonkeyPatch) -> None:
    playbook_id = UUID("56565656-5656-5656-5656-565656565656")
    service = FakePlaybookRunService([])
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_run_service=service))
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "run",
            "add",
            "--playbook-id",
            str(playbook_id),
            "--situation",
            "Manual application did not work",
            "--action",
            "Tried the documented procedure",
            "--outcome",
            "Issue remained unresolved",
            "--success",
            "false",
        ],
    )

    assert result.exit_code == 0
    assert service.add_calls[0][4] is False


def test_run_add_passes_explicit_revision_selector(monkeypatch: pytest.MonkeyPatch) -> None:
    playbook_id = UUID("11111111-2222-3333-4444-555555555555")
    revision_id = UUID("66666666-7777-8888-9999-aaaaaaaaaaaa")
    service = FakePlaybookRunService([])
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_run_service=service))

    result = CliRunner().invoke(
        cli.app,
        [
            "run",
            "add",
            "--playbook-id",
            str(playbook_id),
            "--revision-id",
            str(revision_id),
            "--situation",
            "Explicit revision",
            "--action",
            "Applied revision",
            "--outcome",
            "Recorded",
            "--success",
            "true",
        ],
    )

    assert result.exit_code == 0
    assert service.add_calls[0][-1] == revision_id
    assert service.runs[0].revision_id == revision_id


def test_run_and_revision_help_expose_revision_provenance_surfaces() -> None:
    runner = CliRunner()

    run_add_help = runner.invoke(cli.app, ["run", "add", "--help"])
    revision_help = runner.invoke(cli.app, ["revision", "--help"])

    assert run_add_help.exit_code == 0
    assert "--revision-id" in run_add_help.output
    assert revision_help.exit_code == 0
    assert "runs" in revision_help.output


def test_run_add_handles_empty_actions_without_storing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playbook_id = UUID("67676767-6767-6767-6767-676767676767")
    service = FakePlaybookRunService([])
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_run_service=service))
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "run",
            "add",
            "--playbook-id",
            str(playbook_id),
            "--situation",
            "No action was supplied",
            "--outcome",
            "Run rejected",
            "--success",
            "false",
        ],
    )

    assert result.exit_code == 1
    assert service.add_calls == [
        (
            playbook_id,
            "No action was supplied",
            [],
            "Run rejected",
            False,
            None,
            None,
            None,
            None,
        )
    ]
    assert service.runs == []
    assert "Playbook run requires at least one action taken." in result.output


def test_run_add_handles_missing_playbook_without_storing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_id = UUID("78787878-7878-7878-7878-787878787878")
    service = FakePlaybookRunService([], missing_playbook_id=missing_id)
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_run_service=service))
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "run",
            "add",
            "--playbook-id",
            str(missing_id),
            "--situation",
            "Missing playbook",
            "--action",
            "Tried to record the run",
            "--outcome",
            "Run rejected",
            "--success",
            "false",
        ],
    )

    assert result.exit_code == 1
    assert len(service.add_calls) == 1
    assert service.runs == []
    assert f"Playbook not found: {missing_id}" in result.output


def test_run_list_displays_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    playbook_id = UUID("89898989-8989-8989-8989-898989898989")
    run = PlaybookRun(
        playbook_id=playbook_id,
        situation="Listed run",
        actions_taken=["Applied playbook"],
        outcome="Outcome recorded",
        success=True,
    )
    service = FakePlaybookRunService([run])
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_run_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["run", "list"])

    assert result.exit_code == 0
    assert f"ID: {run.id}" in result.output
    assert f"Timestamp: {run.timestamp}" in result.output
    assert f"Playbook ID: {playbook_id}" in result.output
    assert "Revision ID: -" in result.output
    assert "Situation: Listed run" in result.output
    assert "Success: true" in result.output


def test_run_list_handles_empty_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    service = FakePlaybookRunService([])
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_run_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["run", "list"])

    assert result.exit_code == 0
    assert "No playbook runs found." in result.output


def test_run_show_delegates_and_displays_all_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playbook_id = UUID("90909090-9090-9090-9090-909090909090")
    revision_id = UUID("91919191-9191-9191-9191-919191919191")
    run = PlaybookRun(
        playbook_id=playbook_id,
        revision_id=revision_id,
        situation="Shown run",
        actions_taken=["Applied first step", "Recorded result"],
        outcome="The procedure worked",
        success=True,
        evidence=["Log entry", "Metric improved"],
        notes="No automation was involved",
        tags=["manual", "ops"],
    )
    service = FakePlaybookRunService([run])
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_run_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["run", "show", str(run.id)])

    assert result.exit_code == 0
    assert service.requested_ids == [run.id]
    assert f"ID: {run.id}" in result.output
    assert f"Timestamp: {run.timestamp}" in result.output
    assert f"Playbook ID: {playbook_id}" in result.output
    assert f"Revision ID: {revision_id}" in result.output
    assert "Situation: Shown run" in result.output
    assert "Actions taken:" in result.output
    assert "- Applied first step" in result.output
    assert "- Recorded result" in result.output
    assert "Outcome: The procedure worked" in result.output
    assert "Success: true" in result.output
    assert "Evidence:" in result.output
    assert "- Log entry" in result.output
    assert "- Metric improved" in result.output
    assert "Notes: No automation was involved" in result.output
    assert "Tags: manual, ops" in result.output


def test_run_show_displays_false_and_empty_optional_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = PlaybookRun(
        playbook_id=UUID("abababab-abab-abab-abab-abababababab"),
        situation="Unsuccessful run",
        actions_taken=["Applied playbook manually"],
        outcome="The problem remained",
        success=False,
    )
    service = FakePlaybookRunService([run])
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_run_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["run", "show", str(run.id)])

    assert result.exit_code == 0
    assert "Success: false" in result.output
    assert "Evidence:\n-" in result.output
    assert "Notes: -" in result.output
    assert "Tags: -" in result.output


def test_run_show_handles_missing_run(monkeypatch: pytest.MonkeyPatch) -> None:
    missing_id = UUID("cdcdcdcd-cdcd-cdcd-cdcd-cdcdcdcdcdcd")
    service = FakePlaybookRunService([])
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_run_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["run", "show", str(missing_id)])

    assert result.exit_code == 1
    assert service.requested_ids == [missing_id]
    assert f"Playbook run not found: {missing_id}" in result.output


def test_run_show_handles_corrupt_revision_relation_without_traceback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision_id = UUID("90909090-aaaa-bbbb-cccc-909090909090")
    error = PlaybookRunRevisionPlaybookMismatchError(
        revision_id=revision_id,
        expected_playbook_id=UUID("11111111-aaaa-bbbb-cccc-111111111111"),
        actual_playbook_id=UUID("22222222-aaaa-bbbb-cccc-222222222222"),
    )
    service = FakePlaybookRunService([], read_error=error)
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_run_service=service))

    result = CliRunner().invoke(
        cli.app,
        ["run", "show", "33333333-aaaa-bbbb-cccc-333333333333"],
    )

    assert result.exit_code == 1
    assert str(revision_id) in result.output
    assert str(error.actual_playbook_id) in result.output
    assert str(error.expected_playbook_id) in result.output
    assert "Traceback" not in result.output


def test_revision_runs_lists_only_explicit_matches(monkeypatch: pytest.MonkeyPatch) -> None:
    playbook_id = UUID("12121212-1212-1212-1212-121212121212")
    revision_id = UUID("34343434-3434-3434-3434-343434343434")
    linked = PlaybookRun(
        playbook_id=playbook_id,
        revision_id=revision_id,
        situation="Linked",
        actions_taken=["Applied revision"],
        outcome="Recorded",
        success=True,
    )
    legacy = linked.model_copy(
        update={
            "id": UUID("78787878-7878-7878-7878-787878787878"),
            "revision_id": None,
        }
    )
    service = FakePlaybookRunService([legacy, linked])
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_run_service=service))

    result = CliRunner().invoke(cli.app, ["revision", "runs", str(revision_id)])

    assert result.exit_code == 0
    assert str(linked.id) in result.output
    assert str(legacy.id) not in result.output
    assert f"Revision ID: {revision_id}" in result.output


def test_revision_runs_missing_revision_is_controlled(monkeypatch: pytest.MonkeyPatch) -> None:
    missing_id = UUID("56565656-5656-5656-5656-565656565656")
    service = FakePlaybookRunService([], missing_revision_id=missing_id)
    monkeypatch.setattr(cli, "container", FakeContainer(playbook_run_service=service))

    result = CliRunner().invoke(cli.app, ["revision", "runs", str(missing_id)])

    assert result.exit_code == 1
    assert f"Playbook revision not found: {missing_id}" in result.output
    assert "Traceback" not in result.output


def test_run_evaluations_delegates_positional_uuid_and_displays_linked_evaluations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = UUID("11111111-2222-3333-4444-555555555555")
    evaluation = PlaybookEvaluation(
        run_id=run_id,
        effectiveness=PlaybookEffectiveness.EFFECTIVE,
        findings=["The run was effective"],
    )
    service = FakePlaybookEvaluationService([evaluation])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_evaluation_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(cli.app, ["run", "evaluations", str(run_id)])

    assert result.exit_code == 0
    assert service.list_for_run_calls == [run_id]
    assert f"ID: {evaluation.id}" in result.output
    assert f"Timestamp: {evaluation.timestamp}" in result.output
    assert "Effectiveness: effective" in result.output


def test_run_evaluations_empty_state_returns_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = UUID("22222222-3333-4444-5555-666666666666")
    service = FakePlaybookEvaluationService([])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_evaluation_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(cli.app, ["run", "evaluations", str(run_id)])

    assert result.exit_code == 0
    assert service.list_for_run_calls == [run_id]
    assert f"No playbook evaluations linked to run: {run_id}" in result.output


def test_run_evaluations_missing_run_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_id = UUID("33333333-4444-5555-6666-777777777777")
    service = FakePlaybookEvaluationService([], missing_run_id=missing_id)
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_evaluation_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(cli.app, ["run", "evaluations", str(missing_id)])

    assert result.exit_code == 1
    assert service.list_for_run_calls == [missing_id]
    assert f"Playbook run not found: {missing_id}" in result.output


@pytest.mark.parametrize(
    ("effectiveness_value", "effectiveness"),
    [
        ("ineffective", PlaybookEffectiveness.INEFFECTIVE),
        ("partial", PlaybookEffectiveness.PARTIAL),
        ("effective", PlaybookEffectiveness.EFFECTIVE),
    ],
)
def test_evaluation_add_delegates_with_parsed_values_and_prints_id(
    effectiveness_value: str,
    effectiveness: PlaybookEffectiveness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = UUID("11111111-2222-3333-4444-555555555555")
    service = FakePlaybookEvaluationService([])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_evaluation_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "evaluation",
            "add",
            "--run-id",
            str(run_id),
            "--effectiveness",
            effectiveness_value,
            "--finding",
            "The playbook isolated the issue",
            "--finding",
            "The rollback step was unclear",
            "--improvement",
            "Clarify rollback criteria",
            "--improvement",
            "Add verification evidence",
            "--evidence",
            "Incident log",
            "--evidence",
            "Reviewer note",
            "--notes",
            "Manual assessment",
            "--tag",
            "ops",
            "--tag",
            "review",
        ],
    )

    assert result.exit_code == 0
    assert service.add_calls == [
        (
            run_id,
            effectiveness,
            ["The playbook isolated the issue", "The rollback step was unclear"],
            ["Clarify rollback criteria", "Add verification evidence"],
            ["Incident log", "Reviewer note"],
            "Manual assessment",
            ["ops", "review"],
        )
    ]
    assert "Playbook evaluation stored." in result.output
    assert str(service.evaluations[0].id) in result.output


def test_evaluation_add_omitted_findings_returns_error_without_storing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = UUID("22222222-3333-4444-5555-666666666666")
    service = FakePlaybookEvaluationService([])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_evaluation_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "evaluation",
            "add",
            "--run-id",
            str(run_id),
            "--effectiveness",
            "ineffective",
        ],
    )

    assert result.exit_code == 1
    assert service.add_calls == [
        (
            run_id,
            PlaybookEffectiveness.INEFFECTIVE,
            [],
            None,
            None,
            None,
            None,
        )
    ]
    assert service.evaluations == []
    assert "Playbook evaluation requires at least one finding." in result.output


def test_evaluation_add_missing_run_returns_error_without_storing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_id = UUID("33333333-4444-5555-6666-777777777777")
    service = FakePlaybookEvaluationService([], missing_run_id=missing_id)
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_evaluation_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "evaluation",
            "add",
            "--run-id",
            str(missing_id),
            "--effectiveness",
            "partial",
            "--finding",
            "The run could not be assessed",
        ],
    )

    assert result.exit_code == 1
    assert len(service.add_calls) == 1
    assert service.evaluations == []
    assert f"Playbook run not found: {missing_id}" in result.output


def test_evaluation_list_displays_evaluation_summaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = UUID("44444444-5555-6666-7777-888888888888")
    evaluation = PlaybookEvaluation(
        run_id=run_id,
        effectiveness=PlaybookEffectiveness.EFFECTIVE,
        findings=["The playbook worked"],
    )
    service = FakePlaybookEvaluationService([evaluation])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_evaluation_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(cli.app, ["evaluation", "list"])

    assert result.exit_code == 0
    assert f"ID: {evaluation.id}" in result.output
    assert f"Timestamp: {evaluation.timestamp}" in result.output
    assert f"Run ID: {run_id}" in result.output
    assert "Effectiveness: effective" in result.output


def test_evaluation_list_handles_empty_repository(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakePlaybookEvaluationService([])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_evaluation_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(cli.app, ["evaluation", "list"])

    assert result.exit_code == 0
    assert "No playbook evaluations found." in result.output


def test_evaluation_proposals_delegates_positional_uuid_and_displays_linked_proposals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playbook_id = UUID("abababab-1111-2222-3333-444444444444")
    evaluation_id = UUID("bcbcbcbc-1111-2222-3333-444444444444")
    proposal = EvolutionProposal(
        playbook_id=playbook_id,
        evaluation_ids=[evaluation_id],
        summary="Referenced evaluation proposal",
        rationale="Manual relation lookup",
        proposed_changes=["Clarify finding"],
        expected_benefits=["Better manual review"],
        status=EvolutionProposalStatus.ACCEPTED,
    )
    service = FakeEvolutionProposalService([proposal])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(evolution_proposal_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(cli.app, ["evaluation", "proposals", str(evaluation_id)])

    assert result.exit_code == 0
    assert service.list_for_evaluation_calls == [evaluation_id]
    assert f"ID: {proposal.id}" in result.output
    assert f"Timestamp: {proposal.timestamp}" in result.output
    assert f"Playbook ID: {playbook_id}" in result.output
    assert "Summary: Referenced evaluation proposal" in result.output
    assert "Status: accepted" in result.output


def test_evaluation_proposals_empty_state_returns_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evaluation_id = UUID("cdcdcdcd-1111-2222-3333-444444444444")
    service = FakeEvolutionProposalService([])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(evolution_proposal_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(cli.app, ["evaluation", "proposals", str(evaluation_id)])

    assert result.exit_code == 0
    assert service.list_for_evaluation_calls == [evaluation_id]
    assert f"No proposals reference evaluation: {evaluation_id}" in result.output


def test_evaluation_proposals_missing_evaluation_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_id = UUID("dededede-1111-2222-3333-444444444444")
    service = FakeEvolutionProposalService([], missing_evaluation_id=missing_id)
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(evolution_proposal_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(cli.app, ["evaluation", "proposals", str(missing_id)])

    assert result.exit_code == 1
    assert service.list_for_evaluation_calls == [missing_id]
    assert f"Playbook evaluation not found: {missing_id}" in result.output


def test_evaluation_show_delegates_and_displays_all_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = UUID("55555555-6666-7777-8888-999999999999")
    evaluation = PlaybookEvaluation(
        run_id=run_id,
        effectiveness=PlaybookEffectiveness.PARTIAL,
        findings=["The first step helped", "The second step was unclear"],
        improvements=["Clarify step two", "Add evidence guidance"],
        evidence=["Incident report", "Reviewer note"],
        notes="External assessment",
        tags=["ops", "manual"],
    )
    service = FakePlaybookEvaluationService([evaluation])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_evaluation_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(cli.app, ["evaluation", "show", str(evaluation.id)])

    assert result.exit_code == 0
    assert service.requested_ids == [evaluation.id]
    assert f"ID: {evaluation.id}" in result.output
    assert f"Timestamp: {evaluation.timestamp}" in result.output
    assert f"Run ID: {run_id}" in result.output
    assert "Effectiveness: partial" in result.output
    assert "Findings:" in result.output
    assert "- The first step helped" in result.output
    assert "- The second step was unclear" in result.output
    assert "Improvements:" in result.output
    assert "- Clarify step two" in result.output
    assert "- Add evidence guidance" in result.output
    assert "Evidence:" in result.output
    assert "- Incident report" in result.output
    assert "- Reviewer note" in result.output
    assert "Notes: External assessment" in result.output
    assert "Tags: ops, manual" in result.output


def test_evaluation_show_displays_empty_optional_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evaluation = PlaybookEvaluation(
        run_id=UUID("66666666-7777-8888-9999-aaaaaaaaaaaa"),
        effectiveness=PlaybookEffectiveness.INEFFECTIVE,
        findings=["The playbook did not help"],
    )
    service = FakePlaybookEvaluationService([evaluation])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_evaluation_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(cli.app, ["evaluation", "show", str(evaluation.id)])

    assert result.exit_code == 0
    assert "Effectiveness: ineffective" in result.output
    assert "Improvements:\n-" in result.output
    assert "Evidence:\n-" in result.output
    assert "Notes: -" in result.output
    assert "Tags: -" in result.output


def test_evaluation_show_handles_missing_evaluation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_id = UUID("77777777-8888-9999-aaaa-bbbbbbbbbbbb")
    service = FakePlaybookEvaluationService([])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_evaluation_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(cli.app, ["evaluation", "show", str(missing_id)])

    assert result.exit_code == 1
    assert service.requested_ids == [missing_id]
    assert f"Playbook evaluation not found: {missing_id}" in result.output


def test_proposal_add_delegates_with_parsed_values_and_prints_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playbook_id = UUID("88888888-9999-aaaa-bbbb-cccccccccccc")
    first_evaluation_id = UUID("99999999-aaaa-bbbb-cccc-dddddddddddd")
    second_evaluation_id = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    service = FakeEvolutionProposalService([])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(evolution_proposal_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "proposal",
            "add",
            "--playbook-id",
            str(playbook_id),
            "--evaluation-id",
            str(first_evaluation_id),
            "--evaluation-id",
            str(second_evaluation_id),
            "--summary",
            "Clarify rollback",
            "--rationale",
            "Evaluations found unclear recovery steps",
            "--change",
            "Add rollback criteria",
            "--change",
            "Add verification step",
            "--benefit",
            "Faster recovery",
            "--benefit",
            "Clearer evidence",
            "--risk",
            "Longer checklist",
            "--notes",
            "Manual proposal",
            "--tag",
            "ops",
            "--tag",
            "manual",
        ],
    )

    assert result.exit_code == 0
    assert service.add_calls == [
        (
            playbook_id,
            [first_evaluation_id, second_evaluation_id],
            "Clarify rollback",
            "Evaluations found unclear recovery steps",
            ["Add rollback criteria", "Add verification step"],
            ["Faster recovery", "Clearer evidence"],
            ["Longer checklist"],
            EvolutionProposalStatus.DRAFT,
            "Manual proposal",
            ["ops", "manual"],
        )
    ]
    assert "Evolution proposal stored." in result.output
    assert str(service.proposals[0].id) in result.output


@pytest.mark.parametrize(
    ("status_value", "status"),
    [
        ("draft", EvolutionProposalStatus.DRAFT),
        ("accepted", EvolutionProposalStatus.ACCEPTED),
        ("rejected", EvolutionProposalStatus.REJECTED),
    ],
)
def test_proposal_add_parses_status_values(
    status_value: str,
    status: EvolutionProposalStatus,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playbook_id = UUID("bbbbbbbb-cccc-dddd-eeee-ffffffffffff")
    evaluation_id = UUID("cccccccc-dddd-eeee-ffff-111111111111")
    service = FakeEvolutionProposalService([])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(evolution_proposal_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "proposal",
            "add",
            "--playbook-id",
            str(playbook_id),
            "--evaluation-id",
            str(evaluation_id),
            "--summary",
            "Status proposal",
            "--rationale",
            "Check status parsing",
            "--change",
            "Change",
            "--benefit",
            "Benefit",
            "--status",
            status_value,
        ],
    )

    assert result.exit_code == 0
    assert service.add_calls[0][7] == status


def test_proposal_add_omitted_evaluations_returns_error_without_storing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playbook_id = UUID("dddddddd-eeee-ffff-1111-222222222222")
    service = FakeEvolutionProposalService([])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(evolution_proposal_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "proposal",
            "add",
            "--playbook-id",
            str(playbook_id),
            "--summary",
            "No evaluations",
            "--rationale",
            "Reject missing evaluations",
            "--change",
            "Change",
            "--benefit",
            "Benefit",
        ],
    )

    assert result.exit_code == 1
    assert service.add_calls[0][1] == []
    assert service.proposals == []
    assert "Evolution proposal requires at least one evaluation ID." in result.output


def test_proposal_add_omitted_changes_returns_error_without_storing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playbook_id = UUID("eeeeeeee-ffff-1111-2222-333333333333")
    evaluation_id = UUID("ffffffff-1111-2222-3333-444444444444")
    service = FakeEvolutionProposalService([])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(evolution_proposal_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "proposal",
            "add",
            "--playbook-id",
            str(playbook_id),
            "--evaluation-id",
            str(evaluation_id),
            "--summary",
            "No changes",
            "--rationale",
            "Reject missing changes",
            "--benefit",
            "Benefit",
        ],
    )

    assert result.exit_code == 1
    assert service.add_calls[0][4] == []
    assert service.proposals == []
    assert "Evolution proposal requires at least one proposed change." in result.output


def test_proposal_add_missing_playbook_returns_error_without_storing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_id = UUID("11111111-2222-3333-4444-555555555555")
    evaluation_id = UUID("22222222-3333-4444-5555-666666666666")
    service = FakeEvolutionProposalService([], missing_playbook_id=missing_id)
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(evolution_proposal_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "proposal",
            "add",
            "--playbook-id",
            str(missing_id),
            "--evaluation-id",
            str(evaluation_id),
            "--summary",
            "Missing playbook",
            "--rationale",
            "Reject missing playbook",
            "--change",
            "Change",
            "--benefit",
            "Benefit",
        ],
    )

    assert result.exit_code == 1
    assert service.proposals == []
    assert f"Playbook not found: {missing_id}" in result.output


def test_proposal_add_missing_evaluation_returns_error_without_storing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playbook_id = UUID("33333333-4444-5555-6666-777777777777")
    missing_id = UUID("44444444-5555-6666-7777-888888888888")
    service = FakeEvolutionProposalService([], missing_evaluation_id=missing_id)
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(evolution_proposal_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "proposal",
            "add",
            "--playbook-id",
            str(playbook_id),
            "--evaluation-id",
            str(missing_id),
            "--summary",
            "Missing evaluation",
            "--rationale",
            "Reject missing evaluation",
            "--change",
            "Change",
            "--benefit",
            "Benefit",
        ],
    )

    assert result.exit_code == 1
    assert service.proposals == []
    assert f"Playbook evaluation not found: {missing_id}" in result.output


def test_proposal_add_missing_run_returns_error_without_storing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playbook_id = UUID("55555555-6666-7777-8888-999999999999")
    evaluation_id = UUID("66666666-7777-8888-9999-aaaaaaaaaaaa")
    run_id = UUID("77777777-8888-9999-aaaa-bbbbbbbbbbbb")
    service = FakeEvolutionProposalService([], missing_run=(evaluation_id, run_id))
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(evolution_proposal_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "proposal",
            "add",
            "--playbook-id",
            str(playbook_id),
            "--evaluation-id",
            str(evaluation_id),
            "--summary",
            "Missing run",
            "--rationale",
            "Reject missing run",
            "--change",
            "Change",
            "--benefit",
            "Benefit",
        ],
    )

    assert result.exit_code == 1
    assert service.proposals == []
    assert str(evaluation_id) in result.output
    assert str(run_id) in result.output


def test_proposal_add_playbook_mismatch_returns_error_without_storing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evaluation_id = UUID("88888888-9999-aaaa-bbbb-cccccccccccc")
    expected_id = UUID("99999999-aaaa-bbbb-cccc-dddddddddddd")
    actual_id = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    service = FakeEvolutionProposalService(
        [],
        playbook_mismatch=(evaluation_id, expected_id, actual_id),
    )
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(evolution_proposal_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "proposal",
            "add",
            "--playbook-id",
            str(expected_id),
            "--evaluation-id",
            str(evaluation_id),
            "--summary",
            "Mismatch",
            "--rationale",
            "Reject mismatch",
            "--change",
            "Change",
            "--benefit",
            "Benefit",
        ],
    )

    assert result.exit_code == 1
    assert service.proposals == []
    assert str(evaluation_id) in result.output
    assert str(expected_id) in result.output
    assert str(actual_id) in result.output


def test_proposal_list_displays_proposal_summaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playbook_id = UUID("bbbbbbbb-cccc-dddd-eeee-ffffffffffff")
    proposal = EvolutionProposal(
        playbook_id=playbook_id,
        evaluation_ids=[UUID("cccccccc-dddd-eeee-ffff-111111111111")],
        summary="Listed proposal",
        rationale="List all proposals",
        proposed_changes=["Change"],
        expected_benefits=["Benefit"],
        status=EvolutionProposalStatus.ACCEPTED,
    )
    service = FakeEvolutionProposalService([proposal])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(evolution_proposal_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(cli.app, ["proposal", "list"])

    assert result.exit_code == 0
    assert f"ID: {proposal.id}" in result.output
    assert f"Timestamp: {proposal.timestamp}" in result.output
    assert f"Playbook ID: {playbook_id}" in result.output
    assert "Summary: Listed proposal" in result.output
    assert "Status: accepted" in result.output


def test_proposal_list_handles_empty_repository(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakeEvolutionProposalService([])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(evolution_proposal_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(cli.app, ["proposal", "list"])

    assert result.exit_code == 0
    assert "No evolution proposals found." in result.output


@pytest.mark.parametrize(
    ("status_value", "status"),
    [
        ("draft", EvolutionProposalStatus.DRAFT),
        ("accepted", EvolutionProposalStatus.ACCEPTED),
        ("rejected", EvolutionProposalStatus.REJECTED),
    ],
)
def test_proposal_status_delegates_parsed_status_and_prints_result(
    status_value: str,
    status: EvolutionProposalStatus,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal = EvolutionProposal(
        playbook_id=UUID("12121212-1212-1212-1212-121212121212"),
        evaluation_ids=[UUID("23232323-2323-2323-2323-232323232323")],
        summary="Status proposal",
        rationale="Manual status decision",
        proposed_changes=["Change"],
        expected_benefits=["Benefit"],
    )
    service = FakeEvolutionProposalService([proposal])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(evolution_proposal_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        ["proposal", "status", str(proposal.id), "--status", status_value],
    )

    assert result.exit_code == 0
    assert service.set_status_calls == [(proposal.id, status)]
    assert str(proposal.id) in result.output
    assert f"Status: {status.value}" in result.output


def test_proposal_status_missing_proposal_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_id = UUID("34343434-3434-3434-3434-343434343434")
    service = FakeEvolutionProposalService([])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(evolution_proposal_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        ["proposal", "status", str(missing_id), "--status", "accepted"],
    )

    assert result.exit_code == 1
    assert service.set_status_calls == [(missing_id, EvolutionProposalStatus.ACCEPTED)]
    assert f"Evolution proposal not found: {missing_id}" in result.output


def test_proposal_status_invalid_status_returns_usage_error_without_calling_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal = EvolutionProposal(
        playbook_id=UUID("45454545-4545-4545-4545-454545454545"),
        evaluation_ids=[UUID("56565656-5656-5656-5656-565656565656")],
        summary="Invalid status proposal",
        rationale="Typer should reject invalid status",
        proposed_changes=["Change"],
        expected_benefits=["Benefit"],
    )
    service = FakeEvolutionProposalService([proposal])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(evolution_proposal_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        ["proposal", "status", str(proposal.id), "--status", "unknown"],
    )

    assert result.exit_code != 0
    assert "Invalid value" in result.output
    assert service.set_status_calls == []


def test_proposal_show_delegates_and_displays_all_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playbook_id = UUID("dddddddd-eeee-ffff-1111-222222222222")
    first_evaluation_id = UUID("eeeeeeee-ffff-1111-2222-333333333333")
    second_evaluation_id = UUID("ffffffff-1111-2222-3333-444444444444")
    proposal = EvolutionProposal(
        playbook_id=playbook_id,
        evaluation_ids=[first_evaluation_id, second_evaluation_id],
        summary="Shown proposal",
        rationale="Show all fields",
        proposed_changes=["Clarify step", "Add verification"],
        expected_benefits=["Faster recovery", "Better audit trail"],
        risks=["Longer checklist", "More manual work"],
        status=EvolutionProposalStatus.REJECTED,
        notes="Manual review rejected this",
        tags=["ops", "review"],
    )
    service = FakeEvolutionProposalService([proposal])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(evolution_proposal_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(cli.app, ["proposal", "show", str(proposal.id)])

    assert result.exit_code == 0
    assert service.requested_ids == [proposal.id]
    assert f"ID: {proposal.id}" in result.output
    assert f"Timestamp: {proposal.timestamp}" in result.output
    assert f"Playbook ID: {playbook_id}" in result.output
    assert "Evaluation IDs:" in result.output
    assert f"- {first_evaluation_id}" in result.output
    assert f"- {second_evaluation_id}" in result.output
    assert "Summary: Shown proposal" in result.output
    assert "Rationale: Show all fields" in result.output
    assert "Proposed changes:" in result.output
    assert "- Clarify step" in result.output
    assert "- Add verification" in result.output
    assert "Expected benefits:" in result.output
    assert "- Faster recovery" in result.output
    assert "- Better audit trail" in result.output
    assert "Risks:" in result.output
    assert "- Longer checklist" in result.output
    assert "- More manual work" in result.output
    assert "Status: rejected" in result.output
    assert "Notes: Manual review rejected this" in result.output
    assert "Tags: ops, review" in result.output


def test_proposal_show_displays_empty_optional_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal = EvolutionProposal(
        playbook_id=UUID("11111111-2222-3333-4444-555555555555"),
        evaluation_ids=[UUID("22222222-3333-4444-5555-666666666666")],
        summary="No optional fields",
        rationale="Render empty optional values",
        proposed_changes=["Change"],
        expected_benefits=["Benefit"],
    )
    service = FakeEvolutionProposalService([proposal])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(evolution_proposal_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(cli.app, ["proposal", "show", str(proposal.id)])

    assert result.exit_code == 0
    assert "Status: draft" in result.output
    assert "Risks:\n-" in result.output
    assert "Notes: -" in result.output
    assert "Tags: -" in result.output


def test_proposal_show_handles_missing_proposal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_id = UUID("33333333-4444-5555-6666-777777777777")
    service = FakeEvolutionProposalService([])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(evolution_proposal_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(cli.app, ["proposal", "show", str(missing_id)])

    assert result.exit_code == 1
    assert service.requested_ids == [missing_id]
    assert f"Evolution proposal not found: {missing_id}" in result.output


def test_proposal_add_omitted_benefit_returns_usage_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playbook_id = UUID("aaaaaaaa-1111-2222-3333-444444444444")
    evaluation_id = UUID("bbbbbbbb-1111-2222-3333-444444444444")
    service = FakeEvolutionProposalService([])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(evolution_proposal_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "proposal",
            "add",
            "--playbook-id",
            str(playbook_id),
            "--evaluation-id",
            str(evaluation_id),
            "--summary",
            "No benefit",
            "--rationale",
            "Reject omitted benefit",
            "--change",
            "Change",
        ],
    )

    assert result.exit_code == 2
    assert "Error" in result.output
    assert service.add_calls == []


def test_proposal_add_one_benefit_is_delegated_correctly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playbook_id = UUID("cccccccc-2222-3333-4444-555555555555")
    evaluation_id = UUID("dddddddd-2222-3333-4444-555555555555")
    service = FakeEvolutionProposalService([])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(evolution_proposal_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "proposal",
            "add",
            "--playbook-id",
            str(playbook_id),
            "--evaluation-id",
            str(evaluation_id),
            "--summary",
            "One benefit",
            "--rationale",
            "Check single benefit",
            "--change",
            "Change",
            "--benefit",
            "Reduce downtime",
        ],
    )

    assert result.exit_code == 0
    assert service.add_calls[0][5] == ["Reduce downtime"]


def test_proposal_add_multiple_benefits_in_supplied_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playbook_id = UUID("eeeeeeee-3333-4444-5555-666666666666")
    evaluation_id = UUID("ffffffff-3333-4444-5555-666666666666")
    service = FakeEvolutionProposalService([])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(evolution_proposal_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "proposal",
            "add",
            "--playbook-id",
            str(playbook_id),
            "--evaluation-id",
            str(evaluation_id),
            "--summary",
            "Multiple benefits",
            "--rationale",
            "Check benefit order",
            "--change",
            "Change",
            "--benefit",
            "Faster recovery",
            "--benefit",
            "Clearer audit trail",
            "--benefit",
            "Less manual work",
        ],
    )

    assert result.exit_code == 0
    assert service.add_calls[0][5] == [
        "Faster recovery",
        "Clearer audit trail",
        "Less manual work",
    ]


def make_revision(
    title: str = "Revision title",
    playbook_id: UUID | None = None,
    proposal_id: UUID | None = None,
    knowledge_ids: list[UUID] | None = None,
) -> PlaybookRevision:
    return PlaybookRevision(
        playbook_id=playbook_id or UUID("11111111-aaaa-bbbb-cccc-111111111111"),
        proposal_id=proposal_id or UUID("22222222-aaaa-bbbb-cccc-222222222222"),
        title=title,
        situation="Revision situation",
        objective="Revision objective",
        steps=["First revised step", "Second revised step"],
        success_criteria=["First success criterion", "Second success criterion"],
        knowledge_ids=knowledge_ids
        or [
            UUID("33333333-aaaa-bbbb-cccc-333333333333"),
            UUID("44444444-aaaa-bbbb-cccc-444444444444"),
        ],
        notes="Revision notes",
        tags=["revision", "manual"],
    )


def make_activation(
    playbook_id: UUID,
    revision_id: UUID,
    proposal_id: UUID,
    decision: PlaybookRevisionActivationDecision = PlaybookRevisionActivationDecision.ACTIVE,
    previous_revision_id: UUID | None = None,
    reason: str = "Manual lifecycle decision",
    decided_by: str | None = None,
    notes: str | None = None,
    tags: list[str] | None = None,
) -> PlaybookRevisionActivation:
    return PlaybookRevisionActivation(
        playbook_id=playbook_id,
        revision_id=revision_id,
        proposal_id=proposal_id,
        decision=decision,
        reason=reason,
        previous_revision_id=previous_revision_id,
        decided_by=decided_by,
        notes=notes,
        tags=tags or [],
    )


def invoke_revision_activate(
    runner: CliRunner,
    revision_id: UUID,
    playbook_id: UUID,
    proposal_id: UUID,
    extra_args: list[str] | None = None,
) -> CliResult:
    return runner.invoke(
        cli.app,
        [
            "revision",
            "activate",
            str(revision_id),
            "--playbook",
            str(playbook_id),
            "--proposal",
            str(proposal_id),
            "--reason",
            "Manual activation decision",
            *(extra_args or []),
        ],
    )


def invoke_revision_supersede(
    runner: CliRunner,
    revision_id: UUID,
    playbook_id: UUID,
    proposal_id: UUID,
    previous_revision_id: UUID,
    extra_args: list[str] | None = None,
) -> CliResult:
    return runner.invoke(
        cli.app,
        [
            "revision",
            "supersede",
            str(revision_id),
            "--playbook",
            str(playbook_id),
            "--proposal",
            str(proposal_id),
            "--previous-revision",
            str(previous_revision_id),
            "--reason",
            "Manual supersession decision",
            *(extra_args or []),
        ],
    )


def invoke_revision_reject(
    runner: CliRunner,
    revision_id: UUID,
    playbook_id: UUID,
    proposal_id: UUID,
    extra_args: list[str] | None = None,
) -> CliResult:
    return runner.invoke(
        cli.app,
        [
            "revision",
            "reject",
            str(revision_id),
            "--playbook",
            str(playbook_id),
            "--proposal",
            str(proposal_id),
            "--reason",
            "Manual rejection decision",
            *(extra_args or []),
        ],
    )


def test_revision_activation_history_delegates_uuid_and_displays_records_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision_id = UUID("88888888-2222-3333-4444-bbbbbbbbbbbb")
    first = make_activation(
        UUID("99999999-2222-3333-4444-bbbbbbbbbbbb"),
        revision_id,
        UUID("aaaaaaaa-2222-3333-4444-bbbbbbbbbbbb"),
        reason="First revision decision",
    )
    second = make_activation(
        UUID("bbbbbbbb-2222-3333-4444-bbbbbbbbbbbb"),
        revision_id,
        UUID("cccccccc-2222-3333-4444-bbbbbbbbbbbb"),
        reason="Second revision decision",
    )
    service = FakePlaybookRevisionActivationService([first, second])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_activation_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(cli.app, ["revision", "activation-history", str(revision_id)])

    assert result.exit_code == 0
    assert service.list_for_revision_calls == [revision_id]
    assert f"ID: {first.id}" in result.output
    assert f"ID: {second.id}" in result.output
    assert result.output.index("Reason: First revision decision") < result.output.index(
        "Reason: Second revision decision"
    )
    assert service.add_calls == []
    assert service.list_for_playbook_calls == []
    assert service.list_for_proposal_calls == []
    assert service.get_active_revision_for_playbook_calls == []


def test_revision_activation_history_empty_state_returns_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision_id = UUID("dddddddd-2222-3333-4444-bbbbbbbbbbbb")
    service = FakePlaybookRevisionActivationService([])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_activation_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(cli.app, ["revision", "activation-history", str(revision_id)])

    assert result.exit_code == 0
    assert service.list_for_revision_calls == [revision_id]
    assert "No playbook revision activation records found for revision:" in result.output
    assert str(revision_id) in result.output
    assert service.add_calls == []


def test_revision_activation_history_missing_revision_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_revision_id = UUID("eeeeeeee-2222-3333-4444-bbbbbbbbbbbb")
    service = FakePlaybookRevisionActivationService([], missing_revision_id=missing_revision_id)
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_activation_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(cli.app, ["revision", "activation-history", str(missing_revision_id)])

    assert result.exit_code == 1
    assert service.list_for_revision_calls == [missing_revision_id]
    assert f"Playbook revision not found: {missing_revision_id}" in result.output
    assert service.add_calls == []


def test_revision_activation_history_invalid_uuid_returns_usage_error_without_calling_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakePlaybookRevisionActivationService([])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_activation_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(cli.app, ["revision", "activation-history", "not-a-uuid"])

    assert result.exit_code == 2
    assert "Invalid value" in result.output
    assert service.list_for_revision_calls == []
    assert service.add_calls == []


def test_revision_activate_delegates_default_active_decision_and_prints_activation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision_id = UUID("11111111-2222-3333-4444-000000000001")
    playbook_id = UUID("11111111-2222-3333-4444-000000000002")
    proposal_id = UUID("11111111-2222-3333-4444-000000000003")
    service = FakePlaybookRevisionActivationService([])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_activation_service=service),
    )
    runner = CliRunner()

    result = invoke_revision_activate(runner, revision_id, playbook_id, proposal_id)

    assert result.exit_code == 0
    assert service.add_calls == [
        (
            playbook_id,
            revision_id,
            proposal_id,
            PlaybookRevisionActivationDecision.ACTIVE,
            "Manual activation decision",
            None,
            None,
            None,
            None,
        )
    ]
    assert "Playbook revision activation recorded." in result.output
    assert f"ID: {service.activations[0].id}" in result.output
    assert "Decision: active" in result.output
    assert f"Revision ID: {revision_id}" in result.output
    assert service.list_for_playbook_calls == []
    assert service.get_active_revision_for_playbook_calls == []


def test_revision_activate_superseded_delegates_previous_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision_id = UUID("11111111-2222-3333-4444-000000000004")
    playbook_id = UUID("11111111-2222-3333-4444-000000000005")
    proposal_id = UUID("11111111-2222-3333-4444-000000000006")
    previous_revision_id = UUID("11111111-2222-3333-4444-000000000007")
    service = FakePlaybookRevisionActivationService([])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_activation_service=service),
    )
    runner = CliRunner()

    result = invoke_revision_activate(
        runner,
        revision_id,
        playbook_id,
        proposal_id,
        [
            "--decision",
            "superseded",
            "--previous-revision",
            str(previous_revision_id),
        ],
    )

    assert result.exit_code == 0
    assert service.add_calls[0][3] == PlaybookRevisionActivationDecision.SUPERSEDED
    assert service.add_calls[0][5] == previous_revision_id
    assert "Decision: superseded" in result.output
    assert f"Previous revision ID: {previous_revision_id}" in result.output


def test_revision_activate_rejected_delegates_rejected_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision_id = UUID("11111111-2222-3333-4444-000000000008")
    playbook_id = UUID("11111111-2222-3333-4444-000000000009")
    proposal_id = UUID("11111111-2222-3333-4444-00000000000a")
    service = FakePlaybookRevisionActivationService([])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_activation_service=service),
    )
    runner = CliRunner()

    result = invoke_revision_activate(
        runner,
        revision_id,
        playbook_id,
        proposal_id,
        ["--decision", "rejected"],
    )

    assert result.exit_code == 0
    assert service.add_calls[0][3] == PlaybookRevisionActivationDecision.REJECTED
    assert "Decision: rejected" in result.output


def test_revision_activate_delegates_optional_fields_and_displays_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision_id = UUID("11111111-2222-3333-4444-00000000000b")
    playbook_id = UUID("11111111-2222-3333-4444-00000000000c")
    proposal_id = UUID("11111111-2222-3333-4444-00000000000d")
    service = FakePlaybookRevisionActivationService([])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_activation_service=service),
    )
    runner = CliRunner()

    result = invoke_revision_activate(
        runner,
        revision_id,
        playbook_id,
        proposal_id,
        [
            "--decided-by",
            "reviewer",
            "--notes",
            "Activation note",
            "--tag",
            "manual",
            "--tag",
            "release",
        ],
    )

    assert result.exit_code == 0
    assert service.add_calls[0][6] == "reviewer"
    assert service.add_calls[0][7] == "Activation note"
    assert service.add_calls[0][8] == ["manual", "release"]
    assert "Decided by: reviewer" in result.output
    assert "Notes: Activation note" in result.output
    assert "Tags: manual, release" in result.output


def test_revision_activate_missing_reason_fails_before_service_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision_id = UUID("11111111-2222-3333-4444-00000000000e")
    playbook_id = UUID("11111111-2222-3333-4444-00000000000f")
    proposal_id = UUID("11111111-2222-3333-4444-000000000010")
    service = FakePlaybookRevisionActivationService([])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_activation_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "revision",
            "activate",
            str(revision_id),
            "--playbook",
            str(playbook_id),
            "--proposal",
            str(proposal_id),
        ],
    )

    assert result.exit_code == 2
    assert "Missing option" in result.output
    assert "--reason" in result.output
    assert service.add_calls == []


def test_revision_activate_invalid_decision_fails_before_service_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision_id = UUID("11111111-2222-3333-4444-000000000011")
    playbook_id = UUID("11111111-2222-3333-4444-000000000012")
    proposal_id = UUID("11111111-2222-3333-4444-000000000013")
    service = FakePlaybookRevisionActivationService([])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_activation_service=service),
    )
    runner = CliRunner()

    result = invoke_revision_activate(
        runner,
        revision_id,
        playbook_id,
        proposal_id,
        ["--decision", "unknown"],
    )

    assert result.exit_code != 0
    assert "Invalid value" in result.output
    assert service.add_calls == []


def test_revision_activate_missing_playbook_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision_id = UUID("11111111-2222-3333-4444-000000000014")
    missing_id = UUID("11111111-2222-3333-4444-000000000015")
    proposal_id = UUID("11111111-2222-3333-4444-000000000016")
    service = FakePlaybookRevisionActivationService([], missing_playbook_id=missing_id)
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_activation_service=service),
    )
    runner = CliRunner()

    result = invoke_revision_activate(runner, revision_id, missing_id, proposal_id)

    assert result.exit_code == 1
    assert f"Playbook not found: {missing_id}" in result.output


def test_revision_activate_missing_revision_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_revision_id = UUID("11111111-2222-3333-4444-000000000017")
    playbook_id = UUID("11111111-2222-3333-4444-000000000018")
    proposal_id = UUID("11111111-2222-3333-4444-000000000019")
    service = FakePlaybookRevisionActivationService([], missing_revision_id=missing_revision_id)
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_activation_service=service),
    )
    runner = CliRunner()

    result = invoke_revision_activate(runner, missing_revision_id, playbook_id, proposal_id)

    assert result.exit_code == 1
    assert f"Playbook revision not found: {missing_revision_id}" in result.output


def test_revision_activate_missing_proposal_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision_id = UUID("11111111-2222-3333-4444-00000000001a")
    playbook_id = UUID("11111111-2222-3333-4444-00000000001b")
    missing_proposal_id = UUID("11111111-2222-3333-4444-00000000001c")
    service = FakePlaybookRevisionActivationService([], missing_proposal_id=missing_proposal_id)
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_activation_service=service),
    )
    runner = CliRunner()

    result = invoke_revision_activate(runner, revision_id, playbook_id, missing_proposal_id)

    assert result.exit_code == 1
    assert f"Evolution proposal not found: {missing_proposal_id}" in result.output


def test_revision_activate_revision_playbook_mismatch_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision_id = UUID("11111111-2222-3333-4444-00000000001d")
    expected_playbook_id = UUID("11111111-2222-3333-4444-00000000001e")
    actual_playbook_id = UUID("11111111-2222-3333-4444-00000000001f")
    proposal_id = UUID("11111111-2222-3333-4444-000000000020")
    service = FakePlaybookRevisionActivationService(
        [],
        revision_mismatch=(revision_id, expected_playbook_id, actual_playbook_id),
    )
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_activation_service=service),
    )
    runner = CliRunner()

    result = invoke_revision_activate(runner, revision_id, expected_playbook_id, proposal_id)

    assert result.exit_code == 1
    assert str(revision_id) in result.output
    assert str(expected_playbook_id) in result.output
    assert str(actual_playbook_id) in result.output


def test_revision_activate_revision_proposal_mismatch_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision_id = UUID("11111111-2222-3333-4444-000000000021")
    playbook_id = UUID("11111111-2222-3333-4444-000000000022")
    expected_proposal_id = UUID("11111111-2222-3333-4444-000000000023")
    actual_proposal_id = UUID("11111111-2222-3333-4444-000000000024")
    service = FakePlaybookRevisionActivationService(
        [],
        proposal_mismatch=(revision_id, expected_proposal_id, actual_proposal_id),
    )
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_activation_service=service),
    )
    runner = CliRunner()

    result = invoke_revision_activate(runner, revision_id, playbook_id, expected_proposal_id)

    assert result.exit_code == 1
    assert str(revision_id) in result.output
    assert str(expected_proposal_id) in result.output
    assert str(actual_proposal_id) in result.output


def test_revision_activate_superseded_missing_previous_revision_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision_id = UUID("11111111-2222-3333-4444-000000000025")
    playbook_id = UUID("11111111-2222-3333-4444-000000000026")
    proposal_id = UUID("11111111-2222-3333-4444-000000000027")
    service = FakePlaybookRevisionActivationService([], previous_revision_required=True)
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_activation_service=service),
    )
    runner = CliRunner()

    result = invoke_revision_activate(
        runner,
        revision_id,
        playbook_id,
        proposal_id,
        ["--decision", "superseded"],
    )

    assert result.exit_code == 1
    assert "requires a previous revision ID" in result.output


def test_revision_activate_missing_previous_revision_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision_id = UUID("11111111-2222-3333-4444-000000000028")
    playbook_id = UUID("11111111-2222-3333-4444-000000000029")
    proposal_id = UUID("11111111-2222-3333-4444-00000000002a")
    missing_previous_revision_id = UUID("11111111-2222-3333-4444-00000000002b")
    service = FakePlaybookRevisionActivationService(
        [],
        missing_previous_revision_id=missing_previous_revision_id,
    )
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_activation_service=service),
    )
    runner = CliRunner()

    result = invoke_revision_activate(
        runner,
        revision_id,
        playbook_id,
        proposal_id,
        [
            "--decision",
            "superseded",
            "--previous-revision",
            str(missing_previous_revision_id),
        ],
    )

    assert result.exit_code == 1
    assert f"Previous playbook revision not found: {missing_previous_revision_id}" in result.output


def test_revision_activate_previous_revision_playbook_mismatch_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision_id = UUID("11111111-2222-3333-4444-00000000002c")
    playbook_id = UUID("11111111-2222-3333-4444-00000000002d")
    proposal_id = UUID("11111111-2222-3333-4444-00000000002e")
    previous_revision_id = UUID("11111111-2222-3333-4444-00000000002f")
    actual_playbook_id = UUID("11111111-2222-3333-4444-000000000030")
    service = FakePlaybookRevisionActivationService(
        [],
        previous_revision_mismatch=(previous_revision_id, playbook_id, actual_playbook_id),
    )
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_activation_service=service),
    )
    runner = CliRunner()

    result = invoke_revision_activate(
        runner,
        revision_id,
        playbook_id,
        proposal_id,
        [
            "--decision",
            "superseded",
            "--previous-revision",
            str(previous_revision_id),
        ],
    )

    assert result.exit_code == 1
    assert str(previous_revision_id) in result.output
    assert str(playbook_id) in result.output
    assert str(actual_playbook_id) in result.output


def test_revision_activate_rejected_with_previous_revision_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision_id = UUID("11111111-2222-3333-4444-000000000031")
    playbook_id = UUID("11111111-2222-3333-4444-000000000032")
    proposal_id = UUID("11111111-2222-3333-4444-000000000033")
    previous_revision_id = UUID("11111111-2222-3333-4444-000000000034")
    service = FakePlaybookRevisionActivationService(
        [],
        forbidden_previous_revision_id=previous_revision_id,
    )
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_activation_service=service),
    )
    runner = CliRunner()

    result = invoke_revision_activate(
        runner,
        revision_id,
        playbook_id,
        proposal_id,
        [
            "--decision",
            "rejected",
            "--previous-revision",
            str(previous_revision_id),
        ],
    )

    assert result.exit_code == 1
    assert "must not reference previous revision" in result.output
    assert str(previous_revision_id) in result.output


def test_revision_activate_domain_validation_error_returns_controlled_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision_id = UUID("11111111-2222-3333-4444-000000000035")
    playbook_id = UUID("11111111-2222-3333-4444-000000000036")
    proposal_id = UUID("11111111-2222-3333-4444-000000000037")
    service = FakePlaybookRevisionActivationService([])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_activation_service=service),
    )
    runner = CliRunner()

    result = invoke_revision_activate(
        runner,
        revision_id,
        playbook_id,
        proposal_id,
        ["--decided-by", " "],
    )

    assert result.exit_code == 1
    assert "Optional text fields must not be blank when supplied." in result.output
    assert service.list_for_playbook_calls == []
    assert service.get_active_revision_for_playbook_calls == []


def test_revision_supersede_delegates_fixed_superseded_decision_and_prints_activation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision_id = UUID("11111111-2222-3333-4444-000000000038")
    playbook_id = UUID("11111111-2222-3333-4444-000000000039")
    proposal_id = UUID("11111111-2222-3333-4444-00000000003a")
    previous_revision_id = UUID("11111111-2222-3333-4444-00000000003b")
    service = FakePlaybookRevisionActivationService([])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_activation_service=service),
    )
    runner = CliRunner()

    result = invoke_revision_supersede(
        runner,
        revision_id,
        playbook_id,
        proposal_id,
        previous_revision_id,
    )

    assert result.exit_code == 0
    assert service.add_calls == [
        (
            playbook_id,
            revision_id,
            proposal_id,
            PlaybookRevisionActivationDecision.SUPERSEDED,
            "Manual supersession decision",
            previous_revision_id,
            None,
            None,
            None,
        )
    ]
    assert "Playbook revision supersession recorded." in result.output
    assert f"ID: {service.activations[0].id}" in result.output
    assert "Decision: superseded" in result.output
    assert f"Revision ID: {revision_id}" in result.output
    assert f"Previous revision ID: {previous_revision_id}" in result.output
    assert service.list_for_playbook_calls == []
    assert service.get_active_revision_for_playbook_calls == []


def test_revision_supersede_delegates_optional_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision_id = UUID("11111111-2222-3333-4444-00000000003c")
    playbook_id = UUID("11111111-2222-3333-4444-00000000003d")
    proposal_id = UUID("11111111-2222-3333-4444-00000000003e")
    previous_revision_id = UUID("11111111-2222-3333-4444-00000000003f")
    service = FakePlaybookRevisionActivationService([])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_activation_service=service),
    )
    runner = CliRunner()

    result = invoke_revision_supersede(
        runner,
        revision_id,
        playbook_id,
        proposal_id,
        previous_revision_id,
        [
            "--decided-by",
            "reviewer",
            "--notes",
            "Supersession note",
            "--tag",
            "manual",
        ],
    )

    assert result.exit_code == 0
    assert service.add_calls[0][6] == "reviewer"
    assert service.add_calls[0][7] == "Supersession note"
    assert service.add_calls[0][8] == ["manual"]
    assert "Decided by: reviewer" in result.output
    assert "Notes: Supersession note" in result.output
    assert "Tags: manual" in result.output


def test_revision_supersede_missing_previous_revision_option_fails_before_service_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision_id = UUID("11111111-2222-3333-4444-000000000040")
    playbook_id = UUID("11111111-2222-3333-4444-000000000041")
    proposal_id = UUID("11111111-2222-3333-4444-000000000042")
    service = FakePlaybookRevisionActivationService([])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_activation_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "revision",
            "supersede",
            str(revision_id),
            "--playbook",
            str(playbook_id),
            "--proposal",
            str(proposal_id),
            "--reason",
            "Manual supersession decision",
        ],
    )

    assert result.exit_code == 2
    assert "Missing option" in result.output
    assert "--previous-revision" in result.output
    assert service.add_calls == []


def test_revision_supersede_missing_previous_revision_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision_id = UUID("11111111-2222-3333-4444-000000000043")
    playbook_id = UUID("11111111-2222-3333-4444-000000000044")
    proposal_id = UUID("11111111-2222-3333-4444-000000000045")
    missing_previous_revision_id = UUID("11111111-2222-3333-4444-000000000046")
    service = FakePlaybookRevisionActivationService(
        [],
        missing_previous_revision_id=missing_previous_revision_id,
    )
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_activation_service=service),
    )
    runner = CliRunner()

    result = invoke_revision_supersede(
        runner,
        revision_id,
        playbook_id,
        proposal_id,
        missing_previous_revision_id,
    )

    assert result.exit_code == 1
    assert f"Previous playbook revision not found: {missing_previous_revision_id}" in result.output


def test_revision_supersede_missing_playbook_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision_id = UUID("11111111-2222-3333-4444-000000000054")
    missing_playbook_id = UUID("11111111-2222-3333-4444-000000000055")
    proposal_id = UUID("11111111-2222-3333-4444-000000000056")
    previous_revision_id = UUID("11111111-2222-3333-4444-000000000057")
    service = FakePlaybookRevisionActivationService([], missing_playbook_id=missing_playbook_id)
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_activation_service=service),
    )
    runner = CliRunner()

    result = invoke_revision_supersede(
        runner,
        revision_id,
        missing_playbook_id,
        proposal_id,
        previous_revision_id,
    )

    assert result.exit_code == 1
    assert f"Playbook not found: {missing_playbook_id}" in result.output


def test_revision_supersede_missing_revision_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_revision_id = UUID("11111111-2222-3333-4444-000000000058")
    playbook_id = UUID("11111111-2222-3333-4444-000000000059")
    proposal_id = UUID("11111111-2222-3333-4444-00000000005a")
    previous_revision_id = UUID("11111111-2222-3333-4444-00000000005b")
    service = FakePlaybookRevisionActivationService([], missing_revision_id=missing_revision_id)
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_activation_service=service),
    )
    runner = CliRunner()

    result = invoke_revision_supersede(
        runner,
        missing_revision_id,
        playbook_id,
        proposal_id,
        previous_revision_id,
    )

    assert result.exit_code == 1
    assert f"Playbook revision not found: {missing_revision_id}" in result.output


def test_revision_supersede_missing_proposal_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision_id = UUID("11111111-2222-3333-4444-00000000005c")
    playbook_id = UUID("11111111-2222-3333-4444-00000000005d")
    missing_proposal_id = UUID("11111111-2222-3333-4444-00000000005e")
    previous_revision_id = UUID("11111111-2222-3333-4444-00000000005f")
    service = FakePlaybookRevisionActivationService([], missing_proposal_id=missing_proposal_id)
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_activation_service=service),
    )
    runner = CliRunner()

    result = invoke_revision_supersede(
        runner,
        revision_id,
        playbook_id,
        missing_proposal_id,
        previous_revision_id,
    )

    assert result.exit_code == 1
    assert f"Evolution proposal not found: {missing_proposal_id}" in result.output


def test_revision_supersede_revision_playbook_mismatch_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision_id = UUID("11111111-2222-3333-4444-000000000060")
    expected_playbook_id = UUID("11111111-2222-3333-4444-000000000061")
    actual_playbook_id = UUID("11111111-2222-3333-4444-000000000062")
    proposal_id = UUID("11111111-2222-3333-4444-000000000063")
    previous_revision_id = UUID("11111111-2222-3333-4444-000000000064")
    service = FakePlaybookRevisionActivationService(
        [],
        revision_mismatch=(revision_id, expected_playbook_id, actual_playbook_id),
    )
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_activation_service=service),
    )
    runner = CliRunner()

    result = invoke_revision_supersede(
        runner,
        revision_id,
        expected_playbook_id,
        proposal_id,
        previous_revision_id,
    )

    assert result.exit_code == 1
    assert str(revision_id) in result.output
    assert str(expected_playbook_id) in result.output
    assert str(actual_playbook_id) in result.output


def test_revision_supersede_revision_proposal_mismatch_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision_id = UUID("11111111-2222-3333-4444-000000000065")
    playbook_id = UUID("11111111-2222-3333-4444-000000000066")
    expected_proposal_id = UUID("11111111-2222-3333-4444-000000000067")
    actual_proposal_id = UUID("11111111-2222-3333-4444-000000000068")
    previous_revision_id = UUID("11111111-2222-3333-4444-000000000069")
    service = FakePlaybookRevisionActivationService(
        [],
        proposal_mismatch=(revision_id, expected_proposal_id, actual_proposal_id),
    )
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_activation_service=service),
    )
    runner = CliRunner()

    result = invoke_revision_supersede(
        runner,
        revision_id,
        playbook_id,
        expected_proposal_id,
        previous_revision_id,
    )

    assert result.exit_code == 1
    assert str(revision_id) in result.output
    assert str(expected_proposal_id) in result.output
    assert str(actual_proposal_id) in result.output


def test_revision_supersede_previous_revision_playbook_mismatch_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision_id = UUID("11111111-2222-3333-4444-00000000006a")
    playbook_id = UUID("11111111-2222-3333-4444-00000000006b")
    proposal_id = UUID("11111111-2222-3333-4444-00000000006c")
    previous_revision_id = UUID("11111111-2222-3333-4444-00000000006d")
    actual_playbook_id = UUID("11111111-2222-3333-4444-00000000006e")
    service = FakePlaybookRevisionActivationService(
        [],
        previous_revision_mismatch=(previous_revision_id, playbook_id, actual_playbook_id),
    )
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_activation_service=service),
    )
    runner = CliRunner()

    result = invoke_revision_supersede(
        runner,
        revision_id,
        playbook_id,
        proposal_id,
        previous_revision_id,
    )

    assert result.exit_code == 1
    assert str(previous_revision_id) in result.output
    assert str(playbook_id) in result.output
    assert str(actual_playbook_id) in result.output


def test_revision_supersede_domain_validation_error_returns_controlled_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision_id = UUID("11111111-2222-3333-4444-00000000006f")
    playbook_id = UUID("11111111-2222-3333-4444-000000000070")
    proposal_id = UUID("11111111-2222-3333-4444-000000000071")
    previous_revision_id = UUID("11111111-2222-3333-4444-000000000072")
    service = FakePlaybookRevisionActivationService([])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_activation_service=service),
    )
    runner = CliRunner()

    result = invoke_revision_supersede(
        runner,
        revision_id,
        playbook_id,
        proposal_id,
        previous_revision_id,
        ["--tag", " "],
    )

    assert result.exit_code == 1
    assert "Tags must not contain blank values." in result.output
    assert service.list_for_playbook_calls == []
    assert service.get_active_revision_for_playbook_calls == []


def test_revision_reject_delegates_fixed_rejected_decision_and_prints_activation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision_id = UUID("11111111-2222-3333-4444-000000000047")
    playbook_id = UUID("11111111-2222-3333-4444-000000000048")
    proposal_id = UUID("11111111-2222-3333-4444-000000000049")
    service = FakePlaybookRevisionActivationService([])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_activation_service=service),
    )
    runner = CliRunner()

    result = invoke_revision_reject(runner, revision_id, playbook_id, proposal_id)

    assert result.exit_code == 0
    assert service.add_calls == [
        (
            playbook_id,
            revision_id,
            proposal_id,
            PlaybookRevisionActivationDecision.REJECTED,
            "Manual rejection decision",
            None,
            None,
            None,
            None,
        )
    ]
    assert "Playbook revision rejection recorded." in result.output
    assert f"ID: {service.activations[0].id}" in result.output
    assert "Decision: rejected" in result.output
    assert f"Revision ID: {revision_id}" in result.output
    assert "Previous revision ID: -" in result.output
    assert service.list_for_playbook_calls == []
    assert service.get_active_revision_for_playbook_calls == []


def test_revision_reject_delegates_optional_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision_id = UUID("11111111-2222-3333-4444-00000000004a")
    playbook_id = UUID("11111111-2222-3333-4444-00000000004b")
    proposal_id = UUID("11111111-2222-3333-4444-00000000004c")
    service = FakePlaybookRevisionActivationService([])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_activation_service=service),
    )
    runner = CliRunner()

    result = invoke_revision_reject(
        runner,
        revision_id,
        playbook_id,
        proposal_id,
        [
            "--decided-by",
            "reviewer",
            "--notes",
            "Rejection note",
            "--tag",
            "manual",
        ],
    )

    assert result.exit_code == 0
    assert service.add_calls[0][6] == "reviewer"
    assert service.add_calls[0][7] == "Rejection note"
    assert service.add_calls[0][8] == ["manual"]
    assert "Decided by: reviewer" in result.output
    assert "Notes: Rejection note" in result.output
    assert "Tags: manual" in result.output


def test_revision_reject_does_not_expose_previous_revision_option(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision_id = UUID("11111111-2222-3333-4444-00000000004d")
    playbook_id = UUID("11111111-2222-3333-4444-00000000004e")
    proposal_id = UUID("11111111-2222-3333-4444-00000000004f")
    service = FakePlaybookRevisionActivationService([])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_activation_service=service),
    )
    runner = CliRunner()

    result = invoke_revision_reject(
        runner,
        revision_id,
        playbook_id,
        proposal_id,
        [
            "--previous-revision",
            "11111111-2222-3333-4444-000000000050",
        ],
    )

    assert result.exit_code == 2
    assert "No such option" in result.output
    assert "--previous-revision" in result.output
    assert service.add_calls == []


def test_revision_reject_missing_revision_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_revision_id = UUID("11111111-2222-3333-4444-000000000051")
    playbook_id = UUID("11111111-2222-3333-4444-000000000052")
    proposal_id = UUID("11111111-2222-3333-4444-000000000053")
    service = FakePlaybookRevisionActivationService([], missing_revision_id=missing_revision_id)
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_activation_service=service),
    )
    runner = CliRunner()

    result = invoke_revision_reject(runner, missing_revision_id, playbook_id, proposal_id)

    assert result.exit_code == 1
    assert f"Playbook revision not found: {missing_revision_id}" in result.output


def test_revision_reject_missing_playbook_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision_id = UUID("11111111-2222-3333-4444-000000000073")
    missing_playbook_id = UUID("11111111-2222-3333-4444-000000000074")
    proposal_id = UUID("11111111-2222-3333-4444-000000000075")
    service = FakePlaybookRevisionActivationService([], missing_playbook_id=missing_playbook_id)
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_activation_service=service),
    )
    runner = CliRunner()

    result = invoke_revision_reject(runner, revision_id, missing_playbook_id, proposal_id)

    assert result.exit_code == 1
    assert f"Playbook not found: {missing_playbook_id}" in result.output


def test_revision_reject_missing_proposal_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision_id = UUID("11111111-2222-3333-4444-000000000076")
    playbook_id = UUID("11111111-2222-3333-4444-000000000077")
    missing_proposal_id = UUID("11111111-2222-3333-4444-000000000078")
    service = FakePlaybookRevisionActivationService([], missing_proposal_id=missing_proposal_id)
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_activation_service=service),
    )
    runner = CliRunner()

    result = invoke_revision_reject(runner, revision_id, playbook_id, missing_proposal_id)

    assert result.exit_code == 1
    assert f"Evolution proposal not found: {missing_proposal_id}" in result.output


def test_revision_reject_revision_playbook_mismatch_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision_id = UUID("11111111-2222-3333-4444-000000000079")
    expected_playbook_id = UUID("11111111-2222-3333-4444-00000000007a")
    actual_playbook_id = UUID("11111111-2222-3333-4444-00000000007b")
    proposal_id = UUID("11111111-2222-3333-4444-00000000007c")
    service = FakePlaybookRevisionActivationService(
        [],
        revision_mismatch=(revision_id, expected_playbook_id, actual_playbook_id),
    )
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_activation_service=service),
    )
    runner = CliRunner()

    result = invoke_revision_reject(runner, revision_id, expected_playbook_id, proposal_id)

    assert result.exit_code == 1
    assert str(revision_id) in result.output
    assert str(expected_playbook_id) in result.output
    assert str(actual_playbook_id) in result.output


def test_revision_reject_revision_proposal_mismatch_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision_id = UUID("11111111-2222-3333-4444-00000000007d")
    playbook_id = UUID("11111111-2222-3333-4444-00000000007e")
    expected_proposal_id = UUID("11111111-2222-3333-4444-00000000007f")
    actual_proposal_id = UUID("11111111-2222-3333-4444-000000000080")
    service = FakePlaybookRevisionActivationService(
        [],
        proposal_mismatch=(revision_id, expected_proposal_id, actual_proposal_id),
    )
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_activation_service=service),
    )
    runner = CliRunner()

    result = invoke_revision_reject(runner, revision_id, playbook_id, expected_proposal_id)

    assert result.exit_code == 1
    assert str(revision_id) in result.output
    assert str(expected_proposal_id) in result.output
    assert str(actual_proposal_id) in result.output


def test_revision_reject_domain_validation_error_returns_controlled_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision_id = UUID("11111111-2222-3333-4444-000000000081")
    playbook_id = UUID("11111111-2222-3333-4444-000000000082")
    proposal_id = UUID("11111111-2222-3333-4444-000000000083")
    service = FakePlaybookRevisionActivationService([])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_activation_service=service),
    )
    runner = CliRunner()

    result = invoke_revision_reject(
        runner,
        revision_id,
        playbook_id,
        proposal_id,
        ["--reason", " "],
    )

    assert result.exit_code == 1
    assert "Playbook revision activation requires a reason." in result.output
    assert service.list_for_playbook_calls == []
    assert service.get_active_revision_for_playbook_calls == []


def test_revision_add_delegates_all_parsed_values_and_prints_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playbook_id = UUID("aaaaaaaa-1111-2222-3333-444444444444")
    proposal_id = UUID("bbbbbbbb-1111-2222-3333-444444444444")
    first_knowledge_id = UUID("cccccccc-1111-2222-3333-444444444444")
    second_knowledge_id = UUID("dddddddd-1111-2222-3333-444444444444")
    service = FakePlaybookRevisionService([])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "revision",
            "add",
            "--playbook-id",
            str(playbook_id),
            "--proposal-id",
            str(proposal_id),
            "--title",
            "Revised recovery playbook",
            "--situation",
            "A production recovery is unclear",
            "--objective",
            "Make recovery repeatable",
            "--step",
            "Collect recovery evidence",
            "--step",
            "Verify service health",
            "--success-criterion",
            "Evidence is recorded",
            "--success-criterion",
            "Service health is verified",
            "--knowledge-id",
            str(first_knowledge_id),
            "--knowledge-id",
            str(second_knowledge_id),
            "--notes",
            "Supplied by external reviewer",
            "--tag",
            "ops",
            "--tag",
            "candidate",
        ],
    )

    assert result.exit_code == 0
    assert service.add_calls == [
        (
            playbook_id,
            proposal_id,
            "Revised recovery playbook",
            "A production recovery is unclear",
            "Make recovery repeatable",
            ["Collect recovery evidence", "Verify service health"],
            ["Evidence is recorded", "Service health is verified"],
            [first_knowledge_id, second_knowledge_id],
            "Supplied by external reviewer",
            ["ops", "candidate"],
        )
    ]
    assert "Playbook revision stored." in result.output
    assert str(service.revisions[0].id) in result.output


@pytest.mark.parametrize(
    ("command", "integrity_error"),
    [
        (
            [
                "revision",
                "add",
                "--playbook-id",
                "aaaaaaaa-1111-2222-3333-444444444444",
                "--proposal-id",
                "bbbbbbbb-1111-2222-3333-444444444444",
                "--title",
                "Collision",
                "--situation",
                "A generated UUID already exists",
                "--objective",
                "Fail without replacement",
                "--step",
                "Persist once",
                "--success-criterion",
                "Existing bytes remain unchanged",
            ],
            PlaybookRevisionPersistenceConflictError(UUID("99999999-9999-9999-9999-999999999999")),
        ),
        (
            ["revision", "list"],
            PlaybookRevisionStoredDataError("not-a-uuid"),
        ),
        (
            [
                "revision",
                "show",
                "88888888-8888-8888-8888-888888888888",
            ],
            PlaybookRevisionIdentityMismatchError(
                UUID("88888888-8888-8888-8888-888888888888"),
                UUID("77777777-7777-7777-7777-777777777777"),
            ),
        ),
    ],
    ids=["add-conflict", "list-stored-data", "show-identity-mismatch"],
)
def test_revision_surfaces_render_controlled_repository_integrity_failures(
    monkeypatch: pytest.MonkeyPatch,
    command: list[str],
    integrity_error: PlaybookRevisionRepositoryError,
) -> None:
    service = FakePlaybookRevisionService([], integrity_error=integrity_error)
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(cli.app, command)

    assert result.exit_code == 1
    assert " ".join(str(integrity_error).split()) in " ".join(result.output.split())
    assert "Traceback" not in result.output
    assert service.revisions == []


def test_revision_add_invalid_uuid_returns_usage_error_without_calling_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakePlaybookRevisionService([])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "revision",
            "add",
            "--playbook-id",
            "not-a-uuid",
            "--proposal-id",
            "bbbbbbbb-1111-2222-3333-444444444444",
            "--title",
            "Invalid",
            "--situation",
            "Invalid input",
            "--objective",
            "Reject invalid UUID",
            "--step",
            "Step",
            "--success-criterion",
            "Criterion",
        ],
    )

    assert result.exit_code == 2
    assert "Invalid value" in result.output
    assert service.add_calls == []


def test_revision_add_missing_required_options_returns_typer_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakePlaybookRevisionService([])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(cli.app, ["revision", "add"])

    assert result.exit_code == 2
    assert "Missing option" in result.output
    assert service.add_calls == []


def test_revision_add_handles_empty_steps_without_storing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playbook_id = UUID("eeeeeeee-1111-2222-3333-444444444444")
    proposal_id = UUID("ffffffff-1111-2222-3333-444444444444")
    service = FakePlaybookRevisionService([])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "revision",
            "add",
            "--playbook-id",
            str(playbook_id),
            "--proposal-id",
            str(proposal_id),
            "--title",
            "No steps",
            "--situation",
            "No step was supplied",
            "--objective",
            "Reject incomplete revision",
            "--success-criterion",
            "Criterion",
        ],
    )

    assert result.exit_code == 2
    assert "--step" in result.output
    assert service.add_calls == []


def test_revision_add_handles_empty_success_criteria_without_storing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playbook_id = UUID("12121212-1111-2222-3333-444444444444")
    proposal_id = UUID("23232323-1111-2222-3333-444444444444")
    service = FakePlaybookRevisionService([])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "revision",
            "add",
            "--playbook-id",
            str(playbook_id),
            "--proposal-id",
            str(proposal_id),
            "--title",
            "No success criteria",
            "--situation",
            "No success criterion was supplied",
            "--objective",
            "Reject incomplete revision",
            "--step",
            "Step",
        ],
    )

    assert result.exit_code == 2
    assert "--success-criterion" in result.output
    assert service.add_calls == []


def test_revision_add_missing_proposal_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_id = UUID("34343434-1111-2222-3333-444444444444")
    service = FakePlaybookRevisionService([], missing_proposal_id=missing_id)
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "revision",
            "add",
            "--playbook-id",
            "45454545-1111-2222-3333-444444444444",
            "--proposal-id",
            str(missing_id),
            "--title",
            "Missing proposal",
            "--situation",
            "Proposal does not exist",
            "--objective",
            "Reject revision",
            "--step",
            "Step",
            "--success-criterion",
            "Criterion",
        ],
    )

    assert result.exit_code == 1
    assert f"Evolution proposal not found: {missing_id}" in result.output


def test_revision_add_not_accepted_proposal_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal_id = UUID("56565656-1111-2222-3333-444444444444")
    service = FakePlaybookRevisionService(
        [],
        not_accepted=(proposal_id, EvolutionProposalStatus.DRAFT),
    )
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "revision",
            "add",
            "--playbook-id",
            "67676767-1111-2222-3333-444444444444",
            "--proposal-id",
            str(proposal_id),
            "--title",
            "Draft proposal",
            "--situation",
            "Proposal is draft",
            "--objective",
            "Reject revision",
            "--step",
            "Step",
            "--success-criterion",
            "Criterion",
        ],
    )

    assert result.exit_code == 1
    assert str(proposal_id) in result.output
    assert "must be accepted" in result.output
    assert "draft" in result.output


def test_revision_add_proposal_mismatch_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal_id = UUID("78787878-1111-2222-3333-444444444444")
    expected_id = UUID("89898989-1111-2222-3333-444444444444")
    actual_id = UUID("90909090-1111-2222-3333-444444444444")
    service = FakePlaybookRevisionService(
        [],
        proposal_mismatch=(proposal_id, expected_id, actual_id),
    )
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "revision",
            "add",
            "--playbook-id",
            str(expected_id),
            "--proposal-id",
            str(proposal_id),
            "--title",
            "Mismatch",
            "--situation",
            "Proposal belongs elsewhere",
            "--objective",
            "Reject revision",
            "--step",
            "Step",
            "--success-criterion",
            "Criterion",
        ],
    )

    assert result.exit_code == 1
    assert str(proposal_id) in result.output
    assert str(expected_id) in result.output
    assert str(actual_id) in result.output


def test_revision_add_missing_playbook_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_id = UUID("abababab-1111-2222-3333-444444444444")
    service = FakePlaybookRevisionService([], missing_playbook_id=missing_id)
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "revision",
            "add",
            "--playbook-id",
            str(missing_id),
            "--proposal-id",
            "bcbcbcbc-1111-2222-3333-444444444444",
            "--title",
            "Missing playbook",
            "--situation",
            "Playbook does not exist",
            "--objective",
            "Reject revision",
            "--step",
            "Step",
            "--success-criterion",
            "Criterion",
        ],
    )

    assert result.exit_code == 1
    assert f"Playbook not found: {missing_id}" in result.output


def test_revision_add_missing_knowledge_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_id = UUID("cdcdcdcd-1111-2222-3333-444444444444")
    service = FakePlaybookRevisionService([], missing_knowledge_id=missing_id)
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "revision",
            "add",
            "--playbook-id",
            "dededede-1111-2222-3333-444444444444",
            "--proposal-id",
            "efefefef-1111-2222-3333-444444444444",
            "--title",
            "Missing knowledge",
            "--situation",
            "Knowledge does not exist",
            "--objective",
            "Reject revision",
            "--step",
            "Step",
            "--success-criterion",
            "Criterion",
            "--knowledge-id",
            str(missing_id),
        ],
    )

    assert result.exit_code == 1
    assert f"Knowledge not found: {missing_id}" in result.output


def test_revision_list_delegates_and_displays_one_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision = make_revision("Listed revision")
    service = FakePlaybookRevisionService([revision])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(cli.app, ["revision", "list"])

    assert result.exit_code == 0
    assert service.list_revisions_calls == 1
    assert f"ID: {revision.id}" in result.output
    assert f"Timestamp: {revision.timestamp}" in result.output
    assert f"Playbook ID: {revision.playbook_id}" in result.output
    assert f"Proposal ID: {revision.proposal_id}" in result.output
    assert "Title: Listed revision" in result.output


def test_revision_list_displays_multiple_revisions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = make_revision("First revision")
    second = make_revision("Second revision")
    service = FakePlaybookRevisionService([first, second])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(cli.app, ["revision", "list"])

    assert result.exit_code == 0
    assert "Title: First revision" in result.output
    assert "Title: Second revision" in result.output


def test_revision_list_empty_state_returns_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakePlaybookRevisionService([])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(cli.app, ["revision", "list"])

    assert result.exit_code == 0
    assert service.list_revisions_calls == 1
    assert "No playbook revisions found." in result.output


def test_revision_show_delegates_uuid_and_displays_all_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_knowledge_id = UUID("11111111-2222-3333-4444-555555555555")
    second_knowledge_id = UUID("22222222-3333-4444-5555-666666666666")
    revision = PlaybookRevision(
        playbook_id=UUID("33333333-4444-5555-6666-777777777777"),
        proposal_id=UUID("44444444-5555-6666-7777-888888888888"),
        title="Shown revision",
        situation="Detailed situation",
        objective="Detailed objective",
        steps=["First step", "Second step"],
        success_criteria=["First criterion", "Second criterion"],
        knowledge_ids=[first_knowledge_id, second_knowledge_id],
        notes="Detailed notes",
        tags=["detailed", "manual"],
    )
    service = FakePlaybookRevisionService([revision])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(cli.app, ["revision", "show", str(revision.id)])

    assert result.exit_code == 0
    assert service.requested_ids == [revision.id]
    assert f"ID: {revision.id}" in result.output
    assert f"Timestamp: {revision.timestamp}" in result.output
    assert f"Playbook ID: {revision.playbook_id}" in result.output
    assert f"Proposal ID: {revision.proposal_id}" in result.output
    assert "Title: Shown revision" in result.output
    assert "Situation: Detailed situation" in result.output
    assert "Objective: Detailed objective" in result.output
    assert "Steps:" in result.output
    assert "- First step" in result.output
    assert "- Second step" in result.output
    assert "Success criteria:" in result.output
    assert "- First criterion" in result.output
    assert "- Second criterion" in result.output
    assert "Knowledge IDs:" in result.output
    assert str(first_knowledge_id) in result.output
    assert str(second_knowledge_id) in result.output
    assert "Notes: Detailed notes" in result.output
    assert "Tags: detailed, manual" in result.output


def test_revision_show_handles_missing_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_id = UUID("55555555-6666-7777-8888-999999999999")
    service = FakePlaybookRevisionService([])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(cli.app, ["revision", "show", str(missing_id)])

    assert result.exit_code == 1
    assert service.requested_ids == [missing_id]
    assert f"Playbook revision not found: {missing_id}" in result.output


def test_revision_show_invalid_uuid_returns_usage_error_without_calling_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakePlaybookRevisionService([])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(playbook_revision_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(cli.app, ["revision", "show", "not-a-uuid"])

    assert result.exit_code == 2
    assert "Invalid value" in result.output
    assert service.requested_ids == []


def make_cli_decision(**updates: object) -> Decision:
    values: dict[str, object] = {
        "project_key": "NeuralEngine",
        "title": "Canonical decision ownership",
        "objective": "Record one bounded architecture choice",
        "context_summary": "A design requires an explicit durable Decision.",
        "alternatives": ("Implement Decision foundation", "Keep design-only state"),
        "proposed_option": "Implement Decision foundation",
        "rationale": "The foundation enables controlled dogfooding.",
        "proposed_by": "architecture-review",
        "idempotency_key": "decision-foundation-1",
    }
    values.update(updates)
    return Decision.model_validate(values)


def decision_add_args() -> list[str]:
    return [
        "decision",
        "add",
        "--project-key",
        "NeuralEngine",
        "--title",
        "Canonical decision ownership",
        "--objective",
        "Record one bounded architecture choice",
        "--context-summary",
        "A design requires an explicit durable Decision.",
        "--alternative",
        "Implement Decision foundation",
        "--alternative",
        "Keep design-only state",
        "--proposed-option",
        "Implement Decision foundation",
        "--rationale",
        "The foundation enables controlled dogfooding.",
        "--proposed-by",
        "architecture-review",
        "--idempotency-key",
        "decision-foundation-1",
    ]


def test_decision_help_exposes_outcome_and_review_slices() -> None:
    runner = CliRunner()

    result = runner.invoke(cli.app, ["decision", "--help"])

    assert result.exit_code == 0
    assert "add" in result.output
    assert "list" in result.output
    assert "show" in result.output
    assert "accept" in result.output
    assert "acceptance-history" in result.output
    assert "action" in result.output
    assert "action-history" in result.output
    assert "action-show" in result.output
    assert "state" in result.output
    assert "outcome" in result.output
    assert "review" in result.output


def test_decision_add_delegates_all_inputs_and_displays_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observation_id = UUID("66666666-6666-6666-6666-666666666666")
    superseded_id = UUID("77777777-7777-7777-7777-777777777777")
    evidence_json = (
        '{"kind":"agent_review","locator":".agent-work/reviews/review.md",'
        '"repository_or_project":"NeuralEngine","content_hash":"sha256:abc",'
        '"source":"reviewer","summary":"Architecture review"}'
    )
    service = FakeDecisionService()
    monkeypatch.setattr(cli, "container", FakeContainer(decision_service=service))
    runner = CliRunner()
    args = decision_add_args() + [
        "--observation-id",
        str(observation_id),
        "--evidence",
        evidence_json,
        "--supersedes-decision-id",
        str(superseded_id),
        "--tag",
        "architecture",
    ]

    result = runner.invoke(cli.app, args)

    assert result.exit_code == 0
    assert len(service.add_calls) == 1
    call = service.add_calls[0]
    assert call["alternatives"] == [
        "Implement Decision foundation",
        "Keep design-only state",
    ]
    assert call["observation_ids"] == [observation_id]
    assert call["supersedes_decision_id"] == superseded_id
    assert call["tags"] == ["architecture"]
    evidence = call["evidence_references"]
    assert isinstance(evidence, list)
    assert evidence[0].kind == "agent_review"
    assert evidence[0].locator == ".agent-work/reviews/review.md"
    assert "Decision stored." in result.output
    assert str(service.decisions[0].id) in result.output


def test_decision_list_delegates_project_filter_and_renders_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = make_cli_decision(title="First decision", idempotency_key="first")
    second = make_cli_decision(title="Second decision", idempotency_key="second")
    service = FakeDecisionService([first, second])
    monkeypatch.setattr(cli, "container", FakeContainer(decision_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["decision", "list", "--project", "NeuralEngine"])

    assert result.exit_code == 0
    assert service.list_calls == ["NeuralEngine"]
    assert "ID" in result.output
    assert "Created" in result.output
    assert "Project" in result.output
    assert "Title" in result.output
    assert "Proposed" in result.output
    assert "option" in result.output
    assert "by" in result.output
    assert "First" in result.output
    assert "Second" in result.output


def test_decision_show_renders_full_detail(monkeypatch: pytest.MonkeyPatch) -> None:
    observation_id = UUID("88888888-8888-8888-8888-888888888888")
    superseded_id = UUID("99999999-9999-9999-9999-999999999999")
    decision = make_cli_decision(
        observation_ids=(observation_id,),
        evidence_references=(
            EvidenceReference(
                kind="git_commit",
                locator="8829fd8",
                repository_or_project="NeuralEngine",
                content_hash="sha256:def",
                source="git",
                summary="Design sync",
            ),
        ),
        supersedes_decision_id=superseded_id,
        tags=("architecture", "decision"),
    )
    service = FakeDecisionService([decision])
    monkeypatch.setattr(cli, "container", FakeContainer(decision_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["decision", "show", str(decision.id)])

    assert result.exit_code == 0
    assert service.show_calls == [decision.id]
    assert "Title: Canonical decision ownership" in result.output
    assert "Objective: Record one bounded architecture choice" in result.output
    assert "Context summary: A design requires an explicit durable Decision." in result.output
    assert "- Implement Decision foundation" in result.output
    assert "Proposed option: Implement Decision foundation" in result.output
    assert "Rationale: The foundation enables controlled dogfooding." in result.output
    assert str(observation_id) in result.output
    assert "kind=git_commit; locator=8829fd8" in result.output
    assert f"Supersedes Decision ID: {superseded_id}" in result.output
    assert "Idempotency key: decision-foundation-1" in result.output
    assert "Tags: architecture, decision" in result.output


def test_decision_show_missing_returns_controlled_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    service = FakeDecisionService()
    monkeypatch.setattr(cli, "container", FakeContainer(decision_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["decision", "show", str(missing_id)])

    assert result.exit_code == 1
    assert service.show_calls == [missing_id]
    assert f"Decision not found: {missing_id}" in result.output


def test_decision_show_invalid_uuid_does_not_call_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakeDecisionService()
    monkeypatch.setattr(cli, "container", FakeContainer(decision_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["decision", "show", "not-a-uuid"])

    assert result.exit_code == 2
    assert "Invalid value" in result.output
    assert service.show_calls == []


def test_decision_add_missing_observation_returns_controlled_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_id = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    service = FakeDecisionService(missing_observation_id=missing_id)
    monkeypatch.setattr(cli, "container", FakeContainer(decision_service=service))
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        decision_add_args() + ["--observation-id", str(missing_id)],
    )

    assert result.exit_code == 1
    assert f"Observation not found: {missing_id}" in result.output


def test_decision_add_idempotent_replay_displays_existing_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = make_cli_decision()
    service = FakeDecisionService([existing])
    monkeypatch.setattr(cli, "container", FakeContainer(decision_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, decision_add_args())

    assert result.exit_code == 0
    assert len(service.add_calls) == 1
    assert str(existing.id) in result.output
    assert service.decisions == [existing]


def test_decision_add_conflicting_idempotency_key_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakeDecisionService(conflict=("NeuralEngine", "decision-foundation-1"))
    monkeypatch.setattr(cli, "container", FakeContainer(decision_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, decision_add_args())

    assert result.exit_code == 1
    assert "decision-foundation-1" in result.output
    assert "different payload" in result.output


def test_decision_add_rejects_invalid_evidence_without_calling_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakeDecisionService()
    monkeypatch.setattr(cli, "container", FakeContainer(decision_service=service))
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        decision_add_args() + ["--evidence", '{"kind":"agent_review"}'],
    )

    assert result.exit_code == 1
    assert "Field required" in result.output
    assert service.add_calls == []


def make_cli_acceptance(decision_id: UUID, **updates: object) -> DecisionAcceptance:
    values: dict[str, object] = {
        "decision_id": decision_id,
        "accepted_by": "architecture-owner",
        "reason": "Approved after architecture review.",
        "idempotency_key": "decision-acceptance-1",
    }
    values.update(updates)
    return DecisionAcceptance.model_validate(values)


def decision_accept_args(decision_id: UUID) -> list[str]:
    return [
        "decision",
        "accept",
        str(decision_id),
        "--accepted-by",
        "architecture-owner",
        "--reason",
        "Approved after architecture review.",
        "--idempotency-key",
        "decision-acceptance-1",
    ]


def test_decision_accept_delegates_inputs_and_displays_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    decision_id = UUID("11111111-2222-3333-4444-555555555555")
    evidence_json = (
        '{"kind":"manual_decision","locator":"approval:architecture-review",'
        '"summary":"Explicit approval"}'
    )
    service = FakeDecisionAcceptanceService()
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(decision_acceptance_service=service),
    )
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        decision_accept_args(decision_id) + ["--evidence", evidence_json, "--tag", "architecture"],
    )

    assert result.exit_code == 0
    assert len(service.accept_calls) == 1
    call = service.accept_calls[0]
    assert call["decision_id"] == decision_id
    assert call["accepted_by"] == "architecture-owner"
    assert call["reason"] == "Approved after architecture review."
    assert call["idempotency_key"] == "decision-acceptance-1"
    evidence = call["evidence_references"]
    assert isinstance(evidence, list)
    assert evidence[0].locator == "approval:architecture-review"
    assert call["tags"] == ["architecture"]
    assert "Decision acceptance stored." in result.output
    assert str(service.acceptances[0].id) in result.output


def test_decision_accept_missing_decision_returns_controlled_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_id = UUID("22222222-2222-2222-2222-222222222222")
    service = FakeDecisionAcceptanceService(missing_decision_id=missing_id)
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(decision_acceptance_service=service),
    )

    result = CliRunner().invoke(cli.app, decision_accept_args(missing_id))

    assert result.exit_code == 1
    assert f"Decision not found: {missing_id}" in result.output


def test_decision_accept_already_accepted_returns_controlled_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    decision_id = UUID("33333333-3333-3333-3333-333333333333")
    acceptance_id = UUID("44444444-4444-4444-4444-444444444444")
    service = FakeDecisionAcceptanceService(
        already_accepted=(decision_id, acceptance_id),
    )
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(decision_acceptance_service=service),
    )

    result = CliRunner().invoke(cli.app, decision_accept_args(decision_id))

    assert result.exit_code == 1
    assert f"Decision {decision_id} is already accepted" in result.output
    assert str(acceptance_id) in result.output


def test_decision_accept_idempotent_replay_displays_existing_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    decision_id = UUID("55555555-5555-5555-5555-555555555555")
    existing = make_cli_acceptance(decision_id)
    service = FakeDecisionAcceptanceService([existing])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(decision_acceptance_service=service),
    )

    result = CliRunner().invoke(cli.app, decision_accept_args(decision_id))

    assert result.exit_code == 0
    assert str(existing.id) in result.output
    assert service.acceptances == [existing]


def test_decision_accept_idempotency_conflict_returns_controlled_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    decision_id = UUID("66666666-6666-6666-6666-666666666666")
    service = FakeDecisionAcceptanceService(
        conflict=(decision_id, "decision-acceptance-1"),
    )
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(decision_acceptance_service=service),
    )

    result = CliRunner().invoke(cli.app, decision_accept_args(decision_id))

    assert result.exit_code == 1
    assert "decision-acceptance-1" in result.output
    assert "different payload" in result.output


def test_decision_accept_invalid_evidence_does_not_call_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    decision_id = UUID("77777777-7777-7777-7777-777777777777")
    service = FakeDecisionAcceptanceService()
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(decision_acceptance_service=service),
    )

    result = CliRunner().invoke(
        cli.app,
        decision_accept_args(decision_id) + ["--evidence", '{"kind":"manual"}'],
    )

    assert result.exit_code == 1
    assert "Field required" in result.output
    assert service.accept_calls == []


def test_decision_acceptance_history_renders_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    decision_id = UUID("88888888-8888-8888-8888-888888888888")
    acceptance = make_cli_acceptance(decision_id)
    service = FakeDecisionAcceptanceService([acceptance])
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(decision_acceptance_service=service),
    )

    result = CliRunner().invoke(
        cli.app,
        ["decision", "acceptance-history", str(decision_id)],
    )

    assert result.exit_code == 0
    assert service.list_calls == [decision_id]
    assert "ID" in result.output
    assert "Accepted" in result.output
    assert "Decision ID" in result.output
    assert "Accepted by" in result.output
    assert "Reason" in result.output
    assert str(acceptance.id)[:12] in result.output
    assert "architecture" in result.output


def test_decision_acceptance_history_renders_empty_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    decision_id = UUID("99999999-9999-9999-9999-999999999999")
    service = FakeDecisionAcceptanceService()
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(decision_acceptance_service=service),
    )

    result = CliRunner().invoke(
        cli.app,
        ["decision", "acceptance-history", str(decision_id)],
    )

    assert result.exit_code == 0
    assert f"No acceptance history found for Decision: {decision_id}" in result.output


def test_decision_acceptance_history_invalid_uuid_does_not_call_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakeDecisionAcceptanceService()
    monkeypatch.setattr(
        cli,
        "container",
        FakeContainer(decision_acceptance_service=service),
    )

    result = CliRunner().invoke(
        cli.app,
        ["decision", "acceptance-history", "not-a-uuid"],
    )

    assert result.exit_code == 2
    assert "Invalid value" in result.output
    assert service.list_calls == []


def make_cli_action(decision_id: UUID, acceptance_id: UUID, **updates: object) -> DecisionAction:
    values: dict[str, object] = {
        "decision_id": decision_id,
        "acceptance_id": acceptance_id,
        "action_type": "implementation",
        "summary": "Implemented the DecisionAction foundation.",
        "performed_by": "codex",
        "started_at": datetime(2026, 7, 17, 10, 0, tzinfo=UTC),
        "idempotency_key": "decision-action-1",
    }
    values.update(updates)
    return DecisionAction.model_validate(values)


def decision_action_add_args(decision_id: UUID, acceptance_id: UUID) -> list[str]:
    return [
        "decision",
        "action",
        "add",
        str(decision_id),
        "--acceptance-id",
        str(acceptance_id),
        "--action-type",
        "implementation",
        "--summary",
        "Implemented the DecisionAction foundation.",
        "--performed-by",
        "codex",
        "--started-at",
        "2026-07-17T10:00:00+00:00",
        "--idempotency-key",
        "decision-action-1",
    ]


def test_decision_action_add_delegates_inputs_and_displays_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    decision_id = UUID("11111111-1111-1111-1111-111111111111")
    acceptance_id = UUID("22222222-2222-2222-2222-222222222222")
    run_id = UUID("33333333-3333-3333-3333-333333333333")
    service = FakeDecisionActionService()
    monkeypatch.setattr(cli, "container", FakeContainer(decision_action_service=service))
    args = decision_action_add_args(decision_id, acceptance_id) + [
        "--completed-at",
        "2026-07-17T11:00:00+00:00",
        "--playbook-run-id",
        str(run_id),
        "--evidence",
        '{"kind":"review","locator":"review:action"}',
        "--tag",
        "implementation",
    ]

    result = CliRunner().invoke(cli.app, args)

    assert result.exit_code == 0
    call = service.add_calls[0]
    assert call["decision_id"] == decision_id
    assert call["acceptance_id"] == acceptance_id
    assert call["started_at"] == datetime(2026, 7, 17, 10, 0, tzinfo=UTC)
    assert call["completed_at"] == datetime(2026, 7, 17, 11, 0, tzinfo=UTC)
    assert call["playbook_run_id"] == run_id
    assert call["tags"] == ["implementation"]
    assert "Decision action stored." in result.output
    assert str(service.actions[0].id) in result.output


@pytest.mark.parametrize(
    "args",
    [
        ["decision", "action", "add", "not-a-uuid"],
        [
            "decision",
            "action",
            "add",
            "11111111-1111-1111-1111-111111111111",
            "--acceptance-id",
            "not-a-uuid",
        ],
    ],
)
def test_decision_action_add_rejects_invalid_uuids_before_service(
    monkeypatch: pytest.MonkeyPatch,
    args: list[str],
) -> None:
    service = FakeDecisionActionService()
    monkeypatch.setattr(cli, "container", FakeContainer(decision_action_service=service))

    result = CliRunner().invoke(cli.app, args)

    assert result.exit_code == 2
    assert service.add_calls == []


def test_decision_action_add_rejects_invalid_timestamp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    decision_id = UUID("11111111-1111-1111-1111-111111111111")
    acceptance_id = UUID("22222222-2222-2222-2222-222222222222")
    service = FakeDecisionActionService()
    monkeypatch.setattr(cli, "container", FakeContainer(decision_action_service=service))
    args = decision_action_add_args(decision_id, acceptance_id)
    args[args.index("2026-07-17T10:00:00+00:00")] = "not-a-timestamp"

    result = CliRunner().invoke(cli.app, args)

    assert result.exit_code == 1
    assert service.add_calls == []


def test_decision_action_add_rejects_invalid_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    decision_id = UUID("11111111-1111-1111-1111-111111111111")
    acceptance_id = UUID("22222222-2222-2222-2222-222222222222")
    service = FakeDecisionActionService()
    monkeypatch.setattr(cli, "container", FakeContainer(decision_action_service=service))

    result = CliRunner().invoke(
        cli.app,
        decision_action_add_args(decision_id, acceptance_id) + ["--evidence", '{"kind":"review"}'],
    )

    assert result.exit_code == 1
    assert service.add_calls == []


@pytest.mark.parametrize("error_kind", ["decision", "acceptance", "mismatch"])
def test_decision_action_add_renders_controlled_relation_errors(
    monkeypatch: pytest.MonkeyPatch,
    error_kind: str,
) -> None:
    decision_id = UUID("11111111-1111-1111-1111-111111111111")
    acceptance_id = UUID("22222222-2222-2222-2222-222222222222")
    other_decision_id = UUID("33333333-3333-3333-3333-333333333333")
    if error_kind == "decision":
        service = FakeDecisionActionService(missing_decision_id=decision_id)
        expected = f"Decision not found: {decision_id}"
    elif error_kind == "acceptance":
        service = FakeDecisionActionService(missing_acceptance_id=acceptance_id)
        expected = f"Decision acceptance not found: {acceptance_id}"
    else:
        service = FakeDecisionActionService(
            mismatch=(acceptance_id, decision_id, other_decision_id)
        )
        expected = str(other_decision_id)
    monkeypatch.setattr(cli, "container", FakeContainer(decision_action_service=service))

    result = CliRunner().invoke(cli.app, decision_action_add_args(decision_id, acceptance_id))

    assert result.exit_code == 1
    assert expected in result.output


def test_decision_action_add_idempotent_replay_displays_existing_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    decision_id = UUID("44444444-4444-4444-4444-444444444444")
    acceptance_id = UUID("55555555-5555-5555-5555-555555555555")
    action = make_cli_action(decision_id, acceptance_id)
    service = FakeDecisionActionService([action])
    monkeypatch.setattr(cli, "container", FakeContainer(decision_action_service=service))

    result = CliRunner().invoke(cli.app, decision_action_add_args(decision_id, acceptance_id))

    assert result.exit_code == 0
    assert str(action.id) in result.output
    assert service.actions == [action]


def test_decision_action_add_idempotency_conflict_is_visible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    decision_id = UUID("66666666-6666-6666-6666-666666666666")
    acceptance_id = UUID("77777777-7777-7777-7777-777777777777")
    service = FakeDecisionActionService(conflict=(decision_id, "decision-action-1"))
    monkeypatch.setattr(cli, "container", FakeContainer(decision_action_service=service))

    result = CliRunner().invoke(cli.app, decision_action_add_args(decision_id, acceptance_id))

    assert result.exit_code == 1
    assert "different payload" in result.output


def test_decision_action_history_renders_records_and_empty_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    decision_id = UUID("88888888-8888-8888-8888-888888888888")
    acceptance_id = UUID("99999999-9999-9999-9999-999999999999")
    action = make_cli_action(decision_id, acceptance_id)
    service = FakeDecisionActionService([action])
    monkeypatch.setattr(cli, "container", FakeContainer(decision_action_service=service))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["decision", "action-history", str(decision_id)])

    assert result.exit_code == 0
    assert service.list_calls == [decision_id]
    assert "Action" in result.output
    assert "type" in result.output
    assert "Performed" in result.output
    assert "implem" in result.output

    service.actions = []
    empty = runner.invoke(cli.app, ["decision", "action-history", str(decision_id)])
    assert empty.exit_code == 0
    assert f"No action history found for Decision: {decision_id}" in empty.output


def test_decision_action_show_renders_all_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    decision_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    acceptance_id = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    run_id = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
    action = make_cli_action(
        decision_id,
        acceptance_id,
        completed_at=datetime(2026, 7, 17, 11, 0, tzinfo=UTC),
        evidence_references=(EvidenceReference(kind="review", locator="review:1"),),
        playbook_run_id=run_id,
        tags=("implementation",),
    )
    service = FakeDecisionActionService([action])
    monkeypatch.setattr(cli, "container", FakeContainer(decision_action_service=service))

    result = CliRunner().invoke(cli.app, ["decision", "action-show", str(action.id)])

    assert result.exit_code == 0
    assert f"Decision ID: {decision_id}" in result.output
    assert f"Acceptance ID: {acceptance_id}" in result.output
    assert "Action type: implementation" in result.output
    assert "Summary: Implemented the DecisionAction foundation." in result.output
    assert "Performed by: codex" in result.output
    assert "kind=review; locator=review:1" in result.output
    assert f"Playbook run ID: {run_id}" in result.output
    assert "Idempotency key: decision-action-1" in result.output
    assert "Tags: implementation" in result.output


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (DecisionLifecycleState.PROPOSED, "proposed"),
        (DecisionLifecycleState.ACCEPTED, "accepted"),
        (DecisionLifecycleState.IN_PROGRESS, "in_progress"),
        (DecisionLifecycleState.SUCCEEDED, "succeeded"),
        (DecisionLifecycleState.FAILED, "failed"),
        (DecisionLifecycleState.PARTIAL, "partial"),
        (DecisionLifecycleState.OUTCOME_UNKNOWN, "outcome_unknown"),
    ],
)
def test_decision_state_renders_only_canonical_minimal_states(
    monkeypatch: pytest.MonkeyPatch,
    state: DecisionLifecycleState,
    expected: str,
) -> None:
    decision_id = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
    service = FakeDecisionLifecycleService(state)
    monkeypatch.setattr(cli, "container", FakeContainer(decision_lifecycle_service=service))

    result = CliRunner().invoke(cli.app, ["decision", "state", str(decision_id)])

    assert result.exit_code == 0
    assert result.output.strip() == expected
    assert service.state_calls == [decision_id]


class FakeDecisionOutcomeService:
    def __init__(self, outcomes: list[DecisionOutcome] | None = None) -> None:
        self.outcomes = outcomes or []
        self.add_calls: list[dict[str, object]] = []
        self.missing_decision_id: UUID | None = None
        self.conflict: tuple[UUID, str] | None = None

    def add(self, **values: object) -> DecisionOutcome:
        self.add_calls.append(values)
        if self.missing_decision_id is not None:
            raise DecisionOutcomeDecisionNotFoundError(self.missing_decision_id)
        if self.conflict is not None:
            raise DecisionOutcomeIdempotencyConflictError(*self.conflict)
        values["evidence_references"] = values.get("evidence_references") or []
        values["metrics"] = values.get("metrics") or {}
        values["tags"] = values.get("tags") or []
        outcome = DecisionOutcome.model_validate(values)
        self.outcomes.append(outcome)
        return outcome

    def list_for_decision(self, decision_id: UUID) -> list[DecisionOutcome]:
        if self.missing_decision_id is not None:
            raise DecisionOutcomeDecisionNotFoundError(self.missing_decision_id)
        return [outcome for outcome in self.outcomes if outcome.decision_id == decision_id]

    def show(self, outcome_id: UUID) -> DecisionOutcome:
        for outcome in self.outcomes:
            if outcome.id == outcome_id:
                return outcome
        raise DecisionOutcomeNotFoundError(outcome_id)

    def summary_for_decision(self, decision_id: UUID) -> DecisionOutcomeSummary:
        if self.missing_decision_id is not None:
            raise DecisionOutcomeDecisionNotFoundError(self.missing_decision_id)
        outcomes = [outcome for outcome in self.outcomes if outcome.decision_id == decision_id]
        latest = max(outcomes, key=lambda item: (item.validated_at, str(item.id)), default=None)
        return DecisionOutcomeSummary(
            decision_id=decision_id,
            outcome_count=len(outcomes),
            latest_result=latest.result if latest else None,
            latest_validated_at=latest.validated_at if latest else None,
            linked_action_count=len(
                {action_id for outcome in outcomes for action_id in outcome.action_ids}
            ),
            results_by_type={
                result.value: sum(outcome.result is result for outcome in outcomes)
                for result in DecisionOutcomeResult
            },
            has_success=any(
                outcome.result is DecisionOutcomeResult.SUCCEEDED for outcome in outcomes
            ),
            has_failure=any(outcome.result is DecisionOutcomeResult.FAILED for outcome in outcomes),
        )


class DecisionOutcomeContainer:
    def __init__(self, service: FakeDecisionOutcomeService) -> None:
        self.service = service

    def decision_outcome_service(self) -> FakeDecisionOutcomeService:
        return self.service


def make_cli_outcome() -> DecisionOutcome:
    return DecisionOutcome(
        id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        recorded_at=datetime(2026, 7, 18, 11, 30, tzinfo=UTC),
        decision_id=UUID("11111111-1111-1111-1111-111111111111"),
        acceptance_id=UUID("22222222-2222-2222-2222-222222222222"),
        action_ids=(
            UUID("33333333-3333-3333-3333-333333333333"),
            UUID("44444444-4444-4444-4444-444444444444"),
        ),
        result=DecisionOutcomeResult.SUCCEEDED,
        summary="All checks passed.",
        validated_by="pytest",
        validated_at=datetime(2026, 7, 18, 12, 0, tzinfo=UTC),
        evidence_references=(EvidenceReference(kind="test", locator="pytest:all"),),
        metrics={"passed": 681, "clean": True},
        idempotency_key="outcome-cli",
        tags=("validation",),
    )


def outcome_add_args() -> list[str]:
    outcome = make_cli_outcome()
    return [
        "decision",
        "outcome",
        "add",
        str(outcome.decision_id),
        "--acceptance-id",
        str(outcome.acceptance_id),
        "--action-id",
        str(outcome.action_ids[0]),
        "--action-id",
        str(outcome.action_ids[1]),
        "--result",
        "succeeded",
        "--summary",
        outcome.summary,
        "--validated-by",
        outcome.validated_by,
        "--validated-at",
        outcome.validated_at.isoformat(),
        "--idempotency-key",
        outcome.idempotency_key,
    ]


def test_decision_help_exposes_outcome_and_review_command_groups() -> None:
    runner = CliRunner()
    decision_help = runner.invoke(cli.app, ["decision", "--help"])
    outcome_help = runner.invoke(cli.app, ["decision", "outcome", "--help"])

    assert decision_help.exit_code == 0
    assert outcome_help.exit_code == 0
    assert "outcome-history" in decision_help.output
    assert "outcome-show" in decision_help.output
    assert "outcome-summary" in decision_help.output
    assert "add" in outcome_help.output
    assert "review" in decision_help.output.casefold()


def test_decision_outcome_add_parses_repeated_values_and_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakeDecisionOutcomeService()
    monkeypatch.setattr(cli, "container", DecisionOutcomeContainer(service))
    args = outcome_add_args() + [
        "--evidence",
        '{"kind":"test","locator":"pytest:all"}',
        "--metric",
        "passed=681",
        "--metric",
        "coverage=99.5",
        "--metric",
        "clean=true",
        "--metric",
        "suite=full",
        "--tag",
        "validation",
    ]

    result = CliRunner().invoke(cli.app, args)

    assert result.exit_code == 0
    call = service.add_calls[0]
    assert call["action_ids"] == list(make_cli_outcome().action_ids)
    assert call["metrics"] == {
        "passed": 681,
        "coverage": 99.5,
        "clean": True,
        "suite": "full",
    }
    assert "Decision outcome stored." in result.output


@pytest.mark.parametrize(
    ("option", "value", "expected_exit"),
    [
        ("--result", "invalid", 2),
        ("--validated-at", "invalid", 1),
        ("--metric", "malformed", 1),
        ("--metric", "Key=1", 0),
    ],
)
def test_decision_outcome_add_validates_cli_inputs(
    monkeypatch: pytest.MonkeyPatch, option: str, value: str, expected_exit: int
) -> None:
    service = FakeDecisionOutcomeService()
    monkeypatch.setattr(cli, "container", DecisionOutcomeContainer(service))
    args = outcome_add_args()
    if option in args:
        args[args.index(option) + 1] = value
    else:
        args.extend([option, value])

    result = CliRunner().invoke(cli.app, args)

    assert result.exit_code == expected_exit


def test_decision_outcome_add_rejects_invalid_evidence_and_duplicate_metric(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakeDecisionOutcomeService()
    monkeypatch.setattr(cli, "container", DecisionOutcomeContainer(service))
    runner = CliRunner()

    evidence = runner.invoke(cli.app, outcome_add_args() + ["--evidence", '{"kind":"test"}'])
    duplicate = runner.invoke(
        cli.app,
        outcome_add_args() + ["--metric", "Key=1", "--metric", "key=2"],
    )

    assert evidence.exit_code == 1
    assert duplicate.exit_code == 1
    assert "Duplicate metric key" in duplicate.output


def test_decision_outcome_service_errors_are_controlled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outcome = make_cli_outcome()
    missing_service = FakeDecisionOutcomeService()
    missing_service.missing_decision_id = outcome.decision_id
    monkeypatch.setattr(cli, "container", DecisionOutcomeContainer(missing_service))
    missing = CliRunner().invoke(cli.app, outcome_add_args())

    conflict_service = FakeDecisionOutcomeService()
    conflict_service.conflict = (outcome.decision_id, outcome.idempotency_key)
    monkeypatch.setattr(cli, "container", DecisionOutcomeContainer(conflict_service))
    conflict = CliRunner().invoke(cli.app, outcome_add_args())

    assert missing.exit_code == 1
    assert "Decision not found" in missing.output
    assert conflict.exit_code == 1
    assert "different payload" in conflict.output


def test_decision_outcome_history_show_and_summary_render_all_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outcome = make_cli_outcome()
    service = FakeDecisionOutcomeService([outcome])
    monkeypatch.setattr(cli, "container", DecisionOutcomeContainer(service))
    runner = CliRunner()

    history = runner.invoke(cli.app, ["decision", "outcome-history", str(outcome.decision_id)])
    show = runner.invoke(cli.app, ["decision", "outcome-show", str(outcome.id)])
    summary = runner.invoke(cli.app, ["decision", "outcome-summary", str(outcome.decision_id)])

    assert history.exit_code == show.exit_code == summary.exit_code == 0
    assert "Validated" in history.output
    assert "succeeded" in history.output
    assert f"Decision ID: {outcome.decision_id}" in show.output
    assert "Action IDs" in show.output
    assert "kind=test; locator=pytest:all" in show.output
    assert "passed=681" in show.output
    assert "Idempotency key: outcome-cli" in show.output
    assert "Outcome count: 1" in summary.output
    assert "Latest result: succeeded" in summary.output
    assert "Linked action count: 2" in summary.output
    assert "Has success: True" in summary.output


def test_decision_outcome_history_and_summary_have_controlled_empty_states(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    decision_id = make_cli_outcome().decision_id
    service = FakeDecisionOutcomeService()
    monkeypatch.setattr(cli, "container", DecisionOutcomeContainer(service))
    runner = CliRunner()

    history = runner.invoke(cli.app, ["decision", "outcome-history", str(decision_id)])
    summary = runner.invoke(cli.app, ["decision", "outcome-summary", str(decision_id)])

    assert history.exit_code == summary.exit_code == 0
    assert "No outcome history found" in history.output
    assert "Outcome count: 0" in summary.output
    assert "Latest result: -" in summary.output


class UnexpectedPathPreflightContainer:
    def __init__(self) -> None:
        self.calls = 0

    def observation_service(self) -> FakeObservationService:
        self.calls += 1
        raise AssertionError("service must not be resolved after path preflight failure")


def test_status_reports_absent_default_without_creating_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    isolated_home = tmp_path / "isolated"
    monkeypatch.setenv("HOME", str(isolated_home))
    monkeypatch.delenv("NEURAL_HOME", raising=False)

    result = CliRunner().invoke(cli.app, ["status"])

    assert result.exit_code == 0
    assert "Resolution source        : default" in result.output
    assert "Resolved Neural home" in result.output
    assert str(isolated_home / ".neural") in "".join(result.output.splitlines())
    assert "Brain state              : Not initialized" in result.output
    assert "Failure reason           : -" in result.output
    assert not isolated_home.exists()


def test_status_rejects_existing_default_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    isolated_home = tmp_path / "isolated"
    isolated_home.mkdir()
    selected_home = isolated_home / ".neural"
    selected_home.write_text("not a directory", encoding="utf-8")
    monkeypatch.setenv("HOME", str(isolated_home))
    monkeypatch.delenv("NEURAL_HOME", raising=False)

    result = CliRunner().invoke(cli.app, ["status"])

    assert result.exit_code == 1
    assert "Resolution source        : default" in result.output
    assert "Home is directory        : no" in result.output
    assert "home is not a directory" in result.output.lower()


def test_status_reports_valid_uninitialized_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured = tmp_path / "portable"
    configured.mkdir()
    monkeypatch.setenv("NEURAL_HOME", str(configured))

    result = CliRunner().invoke(cli.app, ["status"])

    assert result.exit_code == 0
    assert "Resolution source        : override (NEURAL_HOME)" in result.output
    assert "Configured Neural home" in result.output
    assert "Resolved Neural home" in result.output
    assert str(configured) in result.output
    assert "Configured root available: yes" in result.output
    assert "Brain state              : Not initialized" in result.output
    assert list(configured.iterdir()) == []


def test_status_and_no_command_fail_truthfully_for_unavailable_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured = tmp_path / "missing"
    monkeypatch.setenv("NEURAL_HOME", str(configured))
    runner = CliRunner()

    status_result = runner.invoke(cli.app, ["status"])
    root_result = runner.invoke(cli.app, [])

    assert status_result.exit_code == root_result.exit_code == 1
    for result in (status_result, root_result):
        assert "Brain state              : Unavailable" in result.output
        assert "Configured root available: no" in result.output
        assert "No fallback was used" in " ".join(result.output.split())
        assert "Ready" not in result.output
    assert not configured.exists()


def test_default_init_creates_default_home(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    isolated_home = tmp_path / "isolated"
    monkeypatch.setenv("HOME", str(isolated_home))
    monkeypatch.delenv("NEURAL_HOME", raising=False)

    result = CliRunner().invoke(cli.app, ["init"])

    assert result.exit_code == 0
    assert (isolated_home / ".neural" / "brain").is_dir()


def test_override_init_uses_only_preexisting_selected_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured = tmp_path / "portable"
    configured.mkdir()
    isolated_home = tmp_path / "isolated"
    monkeypatch.setenv("HOME", str(isolated_home))
    monkeypatch.setenv("NEURAL_HOME", str(configured))

    result = CliRunner().invoke(cli.app, ["init"])

    assert result.exit_code == 0
    assert (configured / "brain").is_dir()
    assert (configured / "brain" / "playbook-revision-activations").is_dir()
    assert (configured / "brain" / "playbook-revision-applications").is_dir()
    assert not isolated_home.exists()


def test_unavailable_override_blocks_read_and_write_before_service_use(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured = tmp_path / "missing"
    unexpected = UnexpectedPathPreflightContainer()
    monkeypatch.setenv("NEURAL_HOME", str(configured))
    monkeypatch.setattr(cli, "container", unexpected)
    runner = CliRunner()

    read_result = runner.invoke(cli.app, ["list"])
    write_result = runner.invoke(cli.app, ["observe", "must not persist"])

    assert read_result.exit_code == write_result.exit_code == 1
    assert "No fallback was used" in " ".join(read_result.output.split())
    assert "No fallback was used" in " ".join(write_result.output.split())
    assert unexpected.calls == 0
    assert not configured.exists()


def test_doctor_reports_ready_default_without_writes_or_payload_leakage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    isolated_home = tmp_path / "isolated"
    monkeypatch.setenv("HOME", str(isolated_home))
    monkeypatch.delenv("NEURAL_HOME", raising=False)
    paths = resolve_neural_paths()
    Brain(paths).initialize()
    observation = Observation(content="doctor-secret-payload")
    (paths.OBSERVATIONS / f"{observation.id}.json").write_text(
        observation.model_dump_json(),
        encoding="utf-8",
    )
    before = {
        path.relative_to(paths.HOME).as_posix(): (path.read_bytes() if path.is_file() else None)
        for path in paths.HOME.rglob("*")
    }

    result = CliRunner().invoke(cli.app, ["doctor"])

    after = {
        path.relative_to(paths.HOME).as_posix(): (path.read_bytes() if path.is_file() else None)
        for path in paths.HOME.rglob("*")
    }
    assert result.exit_code == 0
    assert "Selection" in result.output
    assert "Readiness" in result.output
    assert "READY" in result.output
    assert "sha256-relative-v1" in result.output
    assert "Fallback used   : no" in result.output
    assert "TOTAL" in result.output
    assert "Relative root   : Brain" in result.output
    assert "doctor-secret-payload" not in result.output
    assert str(observation.id) not in result.output
    assert before == after


def test_doctor_uses_override_and_reports_uninitialized_without_creating(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured = tmp_path / "portable"
    configured.mkdir()
    monkeypatch.setenv("NEURAL_HOME", str(configured))

    result = CliRunner().invoke(cli.app, ["doctor"])

    assert result.exit_code == 1
    assert "override (NEURAL_HOME)" in result.output
    assert "NOT READY" in result.output
    assert list(configured.iterdir()) == []


def test_doctor_invalid_invocation_and_internal_failure_exit_two(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invalid = CliRunner().invoke(cli.app, ["doctor", "--json"])

    class FailingService:
        def inspect(self) -> None:
            raise RuntimeError("private internal detail")

    class FailingContainer:
        def neural_doctor_service(self) -> FailingService:
            return FailingService()

    monkeypatch.setattr(cli, "container", FailingContainer())
    internal = CliRunner().invoke(cli.app, ["doctor"])

    assert invalid.exit_code == 2
    assert internal.exit_code == 2
    assert "failed unexpectedly" in internal.output
    assert "private internal detail" not in internal.output


def test_status_and_doctor_remain_separate_commands(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured = tmp_path / "portable"
    configured.mkdir()
    monkeypatch.setenv("NEURAL_HOME", str(configured))
    runner = CliRunner()

    status_result = runner.invoke(cli.app, ["status"])
    doctor_result = runner.invoke(cli.app, ["doctor"])

    assert "Brain state" in status_result.output
    assert "Readiness" not in status_result.output
    assert "Readiness" in doctor_result.output
    assert "Brain state" not in doctor_result.output

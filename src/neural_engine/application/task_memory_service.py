"""Policy-scoped task memory over the existing Brain read and write services."""

from collections.abc import Callable
from hashlib import sha256
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StringConstraints

from neural_engine.application.brain_context_service import (
    DEFAULT_CONTEXT_MAX_BYTES,
    MAX_CONTEXT_MAX_BYTES,
    MIN_CONTEXT_MAX_BYTES,
    BrainContextService,
)
from neural_engine.application.brain_trust_inspector import BrainTrustState
from neural_engine.application.decision_service import DecisionService
from neural_engine.application.experience_service import ExperienceService
from neural_engine.application.knowledge_service import KnowledgeService
from neural_engine.application.neural_doctor_service import DoctorState, NeuralDoctorReport
from neural_engine.domain import EvidenceReference, ExperienceResult, KnowledgeConfidence

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=400)]
Key = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")]
Digest = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ProviderDestination(Contract):
    """Exact Pi model destination from the operator's disclosure policy."""

    provider: Text
    model: Text
    api: Text
    base_url: Text


class TaskMemoryPolicy(Contract):
    workspace: str
    project: Key
    topic: Text | None = None
    brain_home: str
    max_bytes: int = Field(
        default=DEFAULT_CONTEXT_MAX_BYTES, ge=MIN_CONTEXT_MAX_BYTES, le=MAX_CONTEXT_MAX_BYTES
    )
    share_with: ProviderDestination | None = None
    default_verifier: Verifier | None = None
    verifiers: dict[Key, Verifier] = Field(default_factory=dict)


class Verifier(Contract):
    executable: str
    sha256: Digest


class DecisionLearning(Contract):
    kind: Literal["decision"]
    title: Text
    objective: Text
    alternatives: Annotated[tuple[Text, ...], Field(min_length=2, max_length=4)]
    proposed_option: Text
    rationale: Text


class KnowledgeLearning(Contract):
    kind: Literal["knowledge"]
    subject: Key
    statement: Text
    rationale: Text
    experience_id: UUID


Learning = Annotated[DecisionLearning | KnowledgeLearning, Field(discriminator="kind")]


class VerifiedTaskResult(Contract):
    """Output of an independently configured local verifier, never of the model."""

    passed: StrictBool
    evidence_path: Text | None = None
    evidence_sha256: Digest | None = None
    learning: Learning | None = None


class TaskMemoryError(Exception):
    """A task memory operation could not be admitted."""


class TaskMemoryIntegrityError(TaskMemoryError):
    """The selected Brain failed trust or integrity checks."""


class TaskMemoryService:
    def __init__(
        self,
        context: BrainContextService,
        doctor: Callable[[], NeuralDoctorReport],
        decisions: DecisionService,
        experiences: ExperienceService,
        knowledge: KnowledgeService,
    ) -> None:
        self._context = context
        self._doctor = doctor
        self._decisions = decisions
        self._experiences = experiences
        self._knowledge = knowledge

    def trusted_snapshot(self) -> tuple[UUID, int, str]:
        report = self._doctor()
        if report.resolved_home is None:
            raise TaskMemoryError("RETRIEVAL_ERROR")
        trust = report.brain_trust
        if (
            trust is None
            or trust.state != BrainTrustState.TRUSTED_CURRENT
            or trust.brain_id is None
            or trust.generation is None
            or any(store.state != DoctorState.PASS for store in report.stores)
            or any(check.state != DoctorState.PASS for check in report.integrity_checks)
            or report.manifest.aggregate_sha256 is None
            or not report.ready
        ):
            raise TaskMemoryIntegrityError("INTEGRITY_ERROR")
        return trust.brain_id, trust.generation, report.manifest.aggregate_sha256

    def context(self, policy: TaskMemoryPolicy) -> tuple[dict[str, object], str]:
        before = self.trusted_snapshot()
        topic = policy.topic
        selection = "PROJECT" if topic is None else "TOPIC"
        context, rendered = self._context.assemble_rendered(
            policy.project, topic=topic, max_bytes=policy.max_bytes
        )
        if topic is not None and not (context.decisions or context.knowledge or context.truncated):
            selection = "PROJECT_FALLBACK"
            context, rendered = self._context.assemble_rendered(
                policy.project, max_bytes=policy.max_bytes
            )
        if self.trusted_snapshot() != before:
            raise TaskMemoryIntegrityError("INTEGRITY_ERROR")
        state = "EMPTY"
        if context.truncated:
            state = "TRUNCATED"
        elif context.decisions or context.knowledge:
            state = "AVAILABLE"
        return {
            "state": state,
            "selection": selection,
            "requested_topic": topic,
            "effective_topic": context.topic,
            "brain_id": str(before[0]),
            "generation": before[1],
            "decision_ids": [item.id for item in context.decisions],
            "knowledge_ids": [item.id for item in context.knowledge],
            "omitted_decisions": context.omitted_decisions,
            "omitted_knowledge": context.omitted_knowledge,
            "sha256": sha256(rendered.encode()).hexdigest(),
        }, rendered

    def classify(self, project: str, learning: Learning) -> str:
        """Use explicit subject identity and exact normalized equivalence, never fuzzy merges."""
        if isinstance(learning, DecisionLearning):
            if learning.proposed_option not in learning.alternatives or len(
                set(learning.alternatives)
            ) != len(learning.alternatives):
                return "UNVERIFIED"
            related = [
                item
                for item in self._decisions.list_decisions(project)
                if _normalized(item.title) == _normalized(learning.title)
            ]
            comparisons = [
                _normalized(item.proposed_option) == _normalized(learning.proposed_option)
                and _normalized(item.objective) == _normalized(learning.objective)
                and _normalized(item.rationale) == _normalized(learning.rationale)
                and {_normalized(option) for option in item.alternatives}
                == {_normalized(option) for option in learning.alternatives}
                for item in related
            ]
        else:
            experience = self._experiences.get_by_id(learning.experience_id)
            if (
                experience is None
                or project not in experience.tags
                or experience.result != ExperienceResult.SUCCESS
            ):
                return "UNVERIFIED"
            subject = "memory-subject:" + learning.subject.casefold()
            items = [item for item in self._knowledge.list_knowledge() if project in item.tags]
            comparable = [
                item
                for item in items
                if subject in item.tags
                or learning.experience_id in item.experience_ids
                or _normalized(item.statement) == _normalized(learning.statement)
            ]
            comparisons = [
                _normalized(item.statement) == _normalized(learning.statement)
                and _normalized(item.rationale) == _normalized(learning.rationale)
                for item in comparable
            ]
        if comparisons:
            return "DUPLICATE" if all(comparisons) else "HOLD_CONFLICT"
        return "AWAITING_AUTHORIZATION"

    def apply(
        self,
        project: str,
        learning: Learning,
        evidence: EvidenceReference,
        brain_id: UUID,
        verified_artifact: EvidenceReference,
        *,
        authority_confirmed: bool,
    ) -> tuple[str, UUID | None]:
        if not authority_confirmed:
            raise TaskMemoryError("EXPLICIT_AUTHORIZATION_REQUIRED")
        if self.trusted_snapshot()[0] != brain_id:
            raise TaskMemoryIntegrityError("BRAIN_IDENTITY_CHANGED")
        status = self.classify(project, learning)
        if status != "AWAITING_AUTHORIZATION":
            return status, None
        if isinstance(learning, DecisionLearning):
            identity = f"{project}\0{_normalized(learning.title)}"
            decision = self._decisions.add(
                project_key=project,
                title=learning.title,
                objective=learning.objective,
                context_summary="Independently verified task result.",
                alternatives=list(learning.alternatives),
                proposed_option=learning.proposed_option,
                rationale=learning.rationale,
                proposed_by="task-memory verifier",
                idempotency_key="task-memory:" + sha256(identity.encode()).hexdigest(),
                evidence_references=[evidence, verified_artifact],
            )
            return "PROPOSED_DECISION_RECORDED", decision.id
        knowledge = self._knowledge.add_from_experience(
            experience_id=learning.experience_id,
            statement=learning.statement,
            rationale=learning.rationale,
            confidence=KnowledgeConfidence.MEDIUM,
            tags=[project, "memory-subject:" + learning.subject.casefold()],
        )
        return "KNOWLEDGE_RECORDED", knowledge.id


def _normalized(text: str) -> str:
    return " ".join(text.casefold().split())

from uuid import UUID

import pytest

from neural_engine.application.knowledge_service import (
    ExperienceNotFoundError,
    KnowledgeEvidenceRequiredError,
    KnowledgeService,
)
from neural_engine.domain import Experience, ExperienceResult, Knowledge, KnowledgeConfidence
from neural_engine.ports.experience_repository import ExperienceRepository
from neural_engine.ports.knowledge_repository import KnowledgeRepository


class FakeKnowledgeRepository(KnowledgeRepository):
    def __init__(self, experience_repository: FakeExperienceRepository) -> None:
        self.saved: list[Knowledge] = []
        self.load_all_calls = 0
        self.lookup_order_at_save: list[UUID] = []
        self._experience_repository = experience_repository

    def save(self, knowledge: Knowledge) -> None:
        self.lookup_order_at_save = list(self._experience_repository.requested_ids)
        self.saved.append(knowledge)

    def load_all(self) -> list[Knowledge]:
        self.load_all_calls += 1
        return self.saved

    def get_by_id(self, knowledge_id: UUID) -> Knowledge | None:
        for knowledge in self.saved:
            if knowledge.id == knowledge_id:
                return knowledge

        return None


class FakeExperienceRepository(ExperienceRepository):
    def __init__(self, experiences: list[Experience] | None = None) -> None:
        self.saved: list[Experience] = experiences or []
        self.requested_ids: list[UUID] = []

    def save(self, experience: Experience) -> None:
        self.saved.append(experience)

    def load_all(self) -> list[Experience]:
        return self.saved

    def get_by_id(self, experience_id: UUID) -> Experience | None:
        self.requested_ids.append(experience_id)

        for experience in self.saved:
            if experience.id == experience_id:
                return experience

        return None


def make_experience(title: str = "Existing experience") -> Experience:
    return Experience(
        title=title,
        context="Knowledge service test",
        action="Record an experience",
        outcome="Experience exists",
        result=ExperienceResult.SUCCESS,
    )


def test_add_knowledge_with_one_experience() -> None:
    experience = make_experience()
    experience_repo = FakeExperienceRepository([experience])
    knowledge_repo = FakeKnowledgeRepository(experience_repo)
    service = KnowledgeService(knowledge_repo, experience_repo)

    knowledge = service.add(
        statement="Use existing evidence",
        rationale="The referenced experience exists.",
        confidence=KnowledgeConfidence.MEDIUM,
        experience_ids=[experience.id],
    )

    assert knowledge_repo.saved == [knowledge]
    assert knowledge.experience_ids == [experience.id]


def test_add_knowledge_with_multiple_experiences() -> None:
    first = make_experience("First")
    second = make_experience("Second")
    experience_repo = FakeExperienceRepository([first, second])
    knowledge_repo = FakeKnowledgeRepository(experience_repo)
    service = KnowledgeService(knowledge_repo, experience_repo)

    knowledge = service.add(
        statement="Compare multiple outcomes",
        rationale="Both linked experiences point to the same lesson.",
        confidence=KnowledgeConfidence.HIGH,
        experience_ids=[first.id, second.id],
    )

    assert knowledge_repo.saved == [knowledge]
    assert knowledge.experience_ids == [first.id, second.id]


def test_add_knowledge_preserves_supplied_fields() -> None:
    experience = make_experience()
    experience_repo = FakeExperienceRepository([experience])
    knowledge_repo = FakeKnowledgeRepository(experience_repo)
    service = KnowledgeService(knowledge_repo, experience_repo)

    knowledge = service.add(
        statement="Explicit statements are preserved",
        rationale="The service must not infer rationale.",
        confidence=KnowledgeConfidence.LOW,
        experience_ids=[experience.id],
        tags=["manual", "lesson"],
    )

    assert knowledge.statement == "Explicit statements are preserved"
    assert knowledge.rationale == "The service must not infer rationale."
    assert knowledge.confidence == KnowledgeConfidence.LOW
    assert knowledge.tags == ["manual", "lesson"]


def test_add_knowledge_raises_when_evidence_is_empty() -> None:
    experience_repo = FakeExperienceRepository()
    knowledge_repo = FakeKnowledgeRepository(experience_repo)
    service = KnowledgeService(knowledge_repo, experience_repo)

    with pytest.raises(KnowledgeEvidenceRequiredError):
        service.add(
            statement="Missing evidence",
            rationale="No experience was linked.",
            confidence=KnowledgeConfidence.LOW,
            experience_ids=[],
        )

    assert experience_repo.requested_ids == []
    assert knowledge_repo.saved == []


def test_add_knowledge_raises_when_experience_is_missing() -> None:
    missing_id = UUID("11111111-1111-1111-1111-111111111111")
    experience_repo = FakeExperienceRepository()
    knowledge_repo = FakeKnowledgeRepository(experience_repo)
    service = KnowledgeService(knowledge_repo, experience_repo)

    with pytest.raises(ExperienceNotFoundError) as error:
        service.add(
            statement="Invalid evidence",
            rationale="The referenced experience is missing.",
            confidence=KnowledgeConfidence.LOW,
            experience_ids=[missing_id],
        )

    assert error.value.experience_id == missing_id
    assert knowledge_repo.saved == []


def test_add_knowledge_stops_on_first_missing_experience_without_saving() -> None:
    existing = make_experience()
    missing_id = UUID("22222222-2222-2222-2222-222222222222")
    later_id = UUID("33333333-3333-3333-3333-333333333333")
    experience_repo = FakeExperienceRepository([existing])
    knowledge_repo = FakeKnowledgeRepository(experience_repo)
    service = KnowledgeService(knowledge_repo, experience_repo)

    with pytest.raises(ExperienceNotFoundError) as error:
        service.add(
            statement="Partially invalid evidence",
            rationale="One referenced experience is missing.",
            confidence=KnowledgeConfidence.MEDIUM,
            experience_ids=[existing.id, missing_id, later_id],
        )

    assert error.value.experience_id == missing_id
    assert experience_repo.requested_ids == [existing.id, missing_id]
    assert knowledge_repo.saved == []


def test_add_knowledge_validates_all_experiences_before_saving() -> None:
    first = make_experience("First")
    second = make_experience("Second")
    experience_repo = FakeExperienceRepository([first, second])
    knowledge_repo = FakeKnowledgeRepository(experience_repo)
    service = KnowledgeService(knowledge_repo, experience_repo)

    service.add(
        statement="Validation precedes save",
        rationale="Repository save should see all experience lookups already completed.",
        confidence=KnowledgeConfidence.HIGH,
        experience_ids=[first.id, second.id],
    )

    assert knowledge_repo.lookup_order_at_save == [first.id, second.id]


def test_add_knowledge_from_experience_preserves_supplied_fields() -> None:
    experience = make_experience()
    experience_repo = FakeExperienceRepository([experience])
    knowledge_repo = FakeKnowledgeRepository(experience_repo)
    service = KnowledgeService(knowledge_repo, experience_repo)

    knowledge = service.add_from_experience(
        experience_id=experience.id,
        statement="Use narrow tests first",
        rationale="The source experience isolated the issue faster.",
        confidence=KnowledgeConfidence.HIGH,
        tags=["testing", "manual"],
    )

    assert knowledge_repo.saved == [knowledge]
    assert knowledge.statement == "Use narrow tests first"
    assert knowledge.rationale == "The source experience isolated the issue faster."
    assert knowledge.confidence == KnowledgeConfidence.HIGH
    assert knowledge.tags == ["testing", "manual"]
    assert knowledge.experience_ids == [experience.id]
    assert experience_repo.requested_ids == [experience.id]


def test_add_knowledge_from_experience_raises_when_experience_is_missing() -> None:
    missing_id = UUID("44444444-4444-4444-4444-444444444444")
    experience_repo = FakeExperienceRepository()
    knowledge_repo = FakeKnowledgeRepository(experience_repo)
    service = KnowledgeService(knowledge_repo, experience_repo)

    with pytest.raises(ExperienceNotFoundError) as error:
        service.add_from_experience(
            experience_id=missing_id,
            statement="Missing source",
            rationale="The source experience does not exist.",
            confidence=KnowledgeConfidence.LOW,
        )

    assert error.value.experience_id == missing_id
    assert knowledge_repo.saved == []
    assert experience_repo.requested_ids == [missing_id]


def test_list_knowledge_returns_repository_items() -> None:
    experience = make_experience()
    experience_repo = FakeExperienceRepository([experience])
    knowledge_repo = FakeKnowledgeRepository(experience_repo)
    service = KnowledgeService(knowledge_repo, experience_repo)
    knowledge = service.add(
        statement="List repository items",
        rationale="Saved knowledge should be listed.",
        confidence=KnowledgeConfidence.MEDIUM,
        experience_ids=[experience.id],
    )

    assert service.list_knowledge() == [knowledge]


def test_get_by_id_returns_matching_knowledge() -> None:
    experience = make_experience()
    experience_repo = FakeExperienceRepository([experience])
    knowledge_repo = FakeKnowledgeRepository(experience_repo)
    service = KnowledgeService(knowledge_repo, experience_repo)
    expected = service.add(
        statement="Find this",
        rationale="Lookup should delegate to the repository.",
        confidence=KnowledgeConfidence.HIGH,
        experience_ids=[experience.id],
    )

    assert service.get_by_id(expected.id) == expected


def test_get_by_id_returns_none_when_missing() -> None:
    experience_repo = FakeExperienceRepository()
    knowledge_repo = FakeKnowledgeRepository(experience_repo)
    service = KnowledgeService(knowledge_repo, experience_repo)

    assert service.get_by_id(UUID("00000000-0000-0000-0000-000000000000")) is None

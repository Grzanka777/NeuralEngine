import inspect
from collections.abc import Mapping
from uuid import UUID

import pytest

from neural_engine.application.experience_service import (
    DecisionReviewPromotionSourceIndexError,
)
from neural_engine.application.knowledge_service import (
    ExperienceNotFoundError,
    ExperienceReader,
    KnowledgeEvidenceRequiredError,
    KnowledgeService,
)
from neural_engine.domain import (
    DecisionReviewPromotionSourceKind,
    Experience,
    ExperienceResult,
    Knowledge,
    KnowledgeConfidence,
)
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


def test_list_knowledge_for_experience_returns_one_linked_item() -> None:
    experience = make_experience()
    linked = Knowledge(
        statement="Linked knowledge",
        rationale="It references the experience.",
        confidence=KnowledgeConfidence.MEDIUM,
        experience_ids=[experience.id],
    )
    experience_repo = FakeExperienceRepository([experience])
    knowledge_repo = FakeKnowledgeRepository(experience_repo)
    knowledge_repo.saved.append(linked)
    service = KnowledgeService(knowledge_repo, experience_repo)

    assert service.list_for_experience(experience.id) == [linked]
    assert knowledge_repo.load_all_calls == 1


def test_list_knowledge_for_experience_returns_multiple_linked_items() -> None:
    experience = make_experience()
    first = Knowledge(
        statement="First linked knowledge",
        rationale="It references the experience.",
        confidence=KnowledgeConfidence.HIGH,
        experience_ids=[experience.id],
    )
    second = Knowledge(
        statement="Second linked knowledge",
        rationale="It also references the experience.",
        confidence=KnowledgeConfidence.LOW,
        experience_ids=[experience.id],
    )
    experience_repo = FakeExperienceRepository([experience])
    knowledge_repo = FakeKnowledgeRepository(experience_repo)
    knowledge_repo.saved.extend([first, second])
    service = KnowledgeService(knowledge_repo, experience_repo)

    assert service.list_for_experience(experience.id) == [first, second]


def test_list_knowledge_for_experience_excludes_unrelated_items() -> None:
    experience = make_experience("Linked experience")
    other_experience = make_experience("Other experience")
    linked = Knowledge(
        statement="Linked knowledge",
        rationale="It references the requested experience.",
        confidence=KnowledgeConfidence.MEDIUM,
        experience_ids=[experience.id],
    )
    unrelated = Knowledge(
        statement="Unrelated knowledge",
        rationale="It references a different experience.",
        confidence=KnowledgeConfidence.HIGH,
        experience_ids=[other_experience.id],
    )
    experience_repo = FakeExperienceRepository([experience, other_experience])
    knowledge_repo = FakeKnowledgeRepository(experience_repo)
    knowledge_repo.saved.extend([linked, unrelated])
    service = KnowledgeService(knowledge_repo, experience_repo)

    assert service.list_for_experience(experience.id) == [linked]


def test_list_knowledge_for_experience_returns_empty_list_when_none_are_linked() -> None:
    experience = make_experience("Unlinked experience")
    other_experience = make_experience("Other experience")
    unrelated = Knowledge(
        statement="Unrelated knowledge",
        rationale="It references a different experience.",
        confidence=KnowledgeConfidence.LOW,
        experience_ids=[other_experience.id],
    )
    experience_repo = FakeExperienceRepository([experience, other_experience])
    knowledge_repo = FakeKnowledgeRepository(experience_repo)
    knowledge_repo.saved.append(unrelated)
    service = KnowledgeService(knowledge_repo, experience_repo)

    assert service.list_for_experience(experience.id) == []
    assert knowledge_repo.load_all_calls == 1


def test_list_knowledge_for_experience_raises_when_missing_without_loading_knowledge() -> None:
    missing_id = UUID("55555555-5555-5555-5555-555555555555")
    experience_repo = FakeExperienceRepository()
    knowledge_repo = FakeKnowledgeRepository(experience_repo)
    service = KnowledgeService(knowledge_repo, experience_repo)

    with pytest.raises(ExperienceNotFoundError) as error:
        service.list_for_experience(missing_id)

    assert error.value.experience_id == missing_id
    assert knowledge_repo.load_all_calls == 0


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


class ReaderOnly:
    """Structural reader test double with no repository write/list surface."""

    def __init__(
        self,
        experiences: list[Experience] | None = None,
        failures: Mapping[UUID, Exception] | None = None,
    ) -> None:
        self.experiences = list(experiences or [])
        self.failures = failures or {}
        self.requested_ids: list[UUID] = []

    def get_by_id(self, experience_id: UUID) -> Experience | None:
        self.requested_ids.append(experience_id)
        failure = self.failures.get(experience_id)
        if failure is not None:
            raise failure
        return next(
            (experience for experience in self.experiences if experience.id == experience_id),
            None,
        )


class ReaderKnowledgeRepository(KnowledgeRepository):
    def __init__(self, reader: ReaderOnly, items: list[Knowledge] | None = None) -> None:
        self.reader = reader
        self.items = list(items or [])
        self.saved: list[Knowledge] = []
        self.reads_at_save: list[UUID] = []
        self.load_all_calls = 0

    def save(self, knowledge: Knowledge) -> None:
        self.reads_at_save = list(self.reader.requested_ids)
        self.saved.append(knowledge)
        self.items.append(knowledge)

    def load_all(self) -> list[Knowledge]:
        self.load_all_calls += 1
        return list(self.items)

    def get_by_id(self, knowledge_id: UUID) -> Knowledge | None:
        return next((item for item in self.items if item.id == knowledge_id), None)


def make_knowledge(*experience_ids: UUID, statement: str = "Stored knowledge") -> Knowledge:
    return Knowledge(
        statement=statement,
        rationale="Knowledge relation validation test",
        confidence=KnowledgeConfidence.MEDIUM,
        experience_ids=list(experience_ids),
    )


def promotion_failure(experience_id: UUID) -> DecisionReviewPromotionSourceIndexError:
    return DecisionReviewPromotionSourceIndexError(
        UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        DecisionReviewPromotionSourceKind.FINDING,
        7,
    )


def test_service_depends_on_structural_experience_reader_not_repository() -> None:
    experience = make_experience()
    reader = ReaderOnly([experience])
    repository = ReaderKnowledgeRepository(reader)

    service = KnowledgeService(repository, reader)
    knowledge = service.add(
        statement="Narrow reads preserve ownership",
        rationale="Only get_by_id is needed.",
        confidence=KnowledgeConfidence.HIGH,
        experience_ids=[experience.id],
    )

    assert repository.saved == [knowledge]
    assert "ExperienceRepository" not in inspect.getsource(KnowledgeService)
    assert ExperienceReader.__name__ == "ExperienceReader"


def test_add_preserves_duplicate_ids_and_validates_them_in_caller_order() -> None:
    first = make_experience("First")
    second = make_experience("Second")
    reader = ReaderOnly([first, second])
    repository = ReaderKnowledgeRepository(reader)
    service = KnowledgeService(repository, reader)

    knowledge = service.add(
        statement="Duplicates remain caller-owned",
        rationale="This hardening does not normalize evidence.",
        confidence=KnowledgeConfidence.MEDIUM,
        experience_ids=[second.id, first.id, second.id],
    )

    assert reader.requested_ids == [second.id, first.id, second.id]
    assert repository.reads_at_save == [second.id, first.id, second.id]
    assert knowledge.experience_ids == [second.id, first.id, second.id]


def test_add_propagates_canonical_integrity_error_without_saving() -> None:
    valid = make_experience("Valid")
    corrupt = make_experience("Corrupt")
    failure = promotion_failure(corrupt.id)
    reader = ReaderOnly([valid, corrupt], {corrupt.id: failure})
    repository = ReaderKnowledgeRepository(reader)
    service = KnowledgeService(repository, reader)

    with pytest.raises(DecisionReviewPromotionSourceIndexError) as error:
        service.add(
            statement="Reject corrupt ancestry",
            rationale="The canonical reader fails closed.",
            confidence=KnowledgeConfidence.HIGH,
            experience_ids=[valid.id, corrupt.id],
        )

    assert error.value is failure
    assert reader.requested_ids == [valid.id, corrupt.id]
    assert repository.saved == []


def test_add_from_experience_propagates_integrity_error_without_saving() -> None:
    corrupt = make_experience("Corrupt")
    failure = promotion_failure(corrupt.id)
    reader = ReaderOnly([corrupt], {corrupt.id: failure})
    repository = ReaderKnowledgeRepository(reader)
    service = KnowledgeService(repository, reader)

    with pytest.raises(DecisionReviewPromotionSourceIndexError) as error:
        service.add_from_experience(
            corrupt.id,
            "Reject corrupt ancestry",
            "The canonical reader fails closed.",
            KnowledgeConfidence.HIGH,
        )

    assert error.value is failure
    assert repository.saved == []


def test_list_knowledge_validates_all_relations_in_record_order() -> None:
    first = make_experience("First")
    second = make_experience("Second")
    third = make_experience("Third")
    items = [make_knowledge(first.id, second.id), make_knowledge(third.id)]
    reader = ReaderOnly([first, second, third])
    repository = ReaderKnowledgeRepository(reader, items)
    service = KnowledgeService(repository, reader)

    assert service.list_knowledge() == items
    assert reader.requested_ids == [first.id, second.id, third.id]


def test_list_knowledge_fails_on_first_invalid_relation_without_skipping() -> None:
    valid = make_experience("Valid")
    corrupt = make_experience("Corrupt")
    later = make_experience("Later")
    failure = promotion_failure(corrupt.id)
    items = [make_knowledge(valid.id, corrupt.id), make_knowledge(later.id)]
    reader = ReaderOnly([valid, corrupt, later], {corrupt.id: failure})
    service = KnowledgeService(ReaderKnowledgeRepository(reader, items), reader)

    with pytest.raises(DecisionReviewPromotionSourceIndexError):
        service.list_knowledge()

    assert reader.requested_ids == [valid.id, corrupt.id]


def test_get_by_id_validates_all_relations_only_for_present_record() -> None:
    first = make_experience("First")
    second = make_experience("Second")
    knowledge = make_knowledge(first.id, second.id)
    reader = ReaderOnly([first, second])
    service = KnowledgeService(ReaderKnowledgeRepository(reader, [knowledge]), reader)

    assert service.get_by_id(knowledge.id) == knowledge
    assert reader.requested_ids == [first.id, second.id]

    reader.requested_ids.clear()
    assert service.get_by_id(UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")) is None
    assert reader.requested_ids == []


def test_get_by_id_raises_existing_error_for_missing_linked_experience() -> None:
    missing_id = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
    knowledge = make_knowledge(missing_id)
    reader = ReaderOnly()
    service = KnowledgeService(ReaderKnowledgeRepository(reader, [knowledge]), reader)

    with pytest.raises(ExperienceNotFoundError) as error:
        service.get_by_id(knowledge.id)

    assert error.value.experience_id == missing_id
    assert reader.requested_ids == [missing_id]


def test_list_for_experience_validates_target_and_all_returned_relations_only() -> None:
    requested = make_experience("Requested")
    other = make_experience("Other linked")
    unrelated_corrupt = make_experience("Unrelated corrupt")
    linked = make_knowledge(requested.id, other.id)
    unrelated = make_knowledge(unrelated_corrupt.id)
    unrelated_failure = promotion_failure(unrelated_corrupt.id)
    reader = ReaderOnly(
        [requested, other, unrelated_corrupt],
        {unrelated_corrupt.id: unrelated_failure},
    )
    repository = ReaderKnowledgeRepository(reader, [linked, unrelated])
    service = KnowledgeService(repository, reader)

    assert service.list_for_experience(requested.id) == [linked]
    assert reader.requested_ids == [requested.id, requested.id, other.id]


@pytest.mark.parametrize("failure_kind", ["missing", "corrupt"])
def test_list_for_experience_fails_on_invalid_non_requested_relation(
    failure_kind: str,
) -> None:
    requested = make_experience("Requested")
    other = make_experience("Other")
    linked = make_knowledge(requested.id, other.id)
    failures = {other.id: promotion_failure(other.id)} if failure_kind == "corrupt" else {}
    experiences = [requested, other] if failure_kind == "corrupt" else [requested]
    reader = ReaderOnly(experiences, failures)
    service = KnowledgeService(ReaderKnowledgeRepository(reader, [linked]), reader)

    expected = (
        DecisionReviewPromotionSourceIndexError
        if failure_kind == "corrupt"
        else ExperienceNotFoundError
    )
    with pytest.raises(expected):
        service.list_for_experience(requested.id)

    assert reader.requested_ids == [requested.id, requested.id, other.id]

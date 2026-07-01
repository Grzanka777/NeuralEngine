from uuid import UUID

import pytest

from neural_engine.application.playbook_service import (
    KnowledgeNotFoundError,
    PlaybookKnowledgeRequiredError,
    PlaybookService,
    PlaybookStepsRequiredError,
)
from neural_engine.domain import Knowledge, KnowledgeConfidence, Playbook
from neural_engine.ports.knowledge_repository import KnowledgeRepository
from neural_engine.ports.playbook_repository import PlaybookRepository


class FakeKnowledgeRepository(KnowledgeRepository):
    def __init__(self, knowledge_items: list[Knowledge] | None = None) -> None:
        self.saved: list[Knowledge] = knowledge_items or []
        self.requested_ids: list[UUID] = []

    def save(self, knowledge: Knowledge) -> None:
        self.saved.append(knowledge)

    def load_all(self) -> list[Knowledge]:
        return self.saved

    def get_by_id(self, knowledge_id: UUID) -> Knowledge | None:
        self.requested_ids.append(knowledge_id)

        for knowledge in self.saved:
            if knowledge.id == knowledge_id:
                return knowledge

        return None


class FakePlaybookRepository(PlaybookRepository):
    def __init__(self, knowledge_repository: FakeKnowledgeRepository) -> None:
        self.saved: list[Playbook] = []
        self.load_all_calls = 0
        self.lookup_order_at_save: list[UUID] = []
        self._knowledge_repository = knowledge_repository

    def save(self, playbook: Playbook) -> None:
        self.lookup_order_at_save = list(self._knowledge_repository.requested_ids)
        self.saved.append(playbook)

    def load_all(self) -> list[Playbook]:
        self.load_all_calls += 1
        return self.saved

    def get_by_id(self, playbook_id: UUID) -> Playbook | None:
        for playbook in self.saved:
            if playbook.id == playbook_id:
                return playbook

        return None


def make_knowledge(statement: str = "Use focused tests") -> Knowledge:
    return Knowledge(
        statement=statement,
        rationale="Knowledge service test",
        confidence=KnowledgeConfidence.MEDIUM,
        experience_ids=[UUID("11111111-1111-1111-1111-111111111111")],
    )


def test_add_playbook_with_one_knowledge_item() -> None:
    knowledge = make_knowledge()
    knowledge_repo = FakeKnowledgeRepository([knowledge])
    playbook_repo = FakePlaybookRepository(knowledge_repo)
    service = PlaybookService(playbook_repo, knowledge_repo)

    playbook = service.add(
        title="Debug flaky tests",
        situation="A test fails intermittently",
        objective="Find the source",
        steps=["Run the test repeatedly"],
        success_criteria=["Failure source is isolated"],
        knowledge_ids=[knowledge.id],
    )

    assert playbook_repo.saved == [playbook]
    assert playbook.knowledge_ids == [knowledge.id]


def test_add_playbook_with_multiple_knowledge_items() -> None:
    first = make_knowledge("First")
    second = make_knowledge("Second")
    knowledge_repo = FakeKnowledgeRepository([first, second])
    playbook_repo = FakePlaybookRepository(knowledge_repo)
    service = PlaybookService(playbook_repo, knowledge_repo)

    playbook = service.add(
        title="Apply several lessons",
        situation="A recurring engineering problem appears",
        objective="Use both lessons",
        steps=["Review first lesson", "Apply second lesson"],
        success_criteria=["Both lessons were considered"],
        knowledge_ids=[first.id, second.id],
    )

    assert playbook_repo.saved == [playbook]
    assert playbook.knowledge_ids == [first.id, second.id]


def test_add_playbook_preserves_supplied_fields() -> None:
    knowledge = make_knowledge()
    knowledge_repo = FakeKnowledgeRepository([knowledge])
    playbook_repo = FakePlaybookRepository(knowledge_repo)
    service = PlaybookService(playbook_repo, knowledge_repo)

    playbook = service.add(
        title="Preserve fields",
        situation="Fields are supplied explicitly",
        objective="Keep every field unchanged",
        steps=["Read input", "Store input"],
        success_criteria=["Stored fields match input"],
        knowledge_ids=[knowledge.id],
        constraints=["No inference"],
        tags=["manual", "procedure"],
    )

    assert playbook.title == "Preserve fields"
    assert playbook.situation == "Fields are supplied explicitly"
    assert playbook.objective == "Keep every field unchanged"
    assert playbook.steps == ["Read input", "Store input"]
    assert playbook.success_criteria == ["Stored fields match input"]
    assert playbook.constraints == ["No inference"]
    assert playbook.knowledge_ids == [knowledge.id]
    assert playbook.tags == ["manual", "procedure"]


def test_add_playbook_raises_when_knowledge_ids_are_empty() -> None:
    knowledge_repo = FakeKnowledgeRepository()
    playbook_repo = FakePlaybookRepository(knowledge_repo)
    service = PlaybookService(playbook_repo, knowledge_repo)

    with pytest.raises(PlaybookKnowledgeRequiredError):
        service.add(
            title="Missing knowledge",
            situation="No knowledge IDs were supplied",
            objective="Reject the playbook",
            steps=["Do one thing"],
            success_criteria=["Playbook is rejected"],
            knowledge_ids=[],
        )

    assert knowledge_repo.requested_ids == []
    assert playbook_repo.saved == []


def test_add_playbook_raises_when_steps_are_empty() -> None:
    knowledge = make_knowledge()
    knowledge_repo = FakeKnowledgeRepository([knowledge])
    playbook_repo = FakePlaybookRepository(knowledge_repo)
    service = PlaybookService(playbook_repo, knowledge_repo)

    with pytest.raises(PlaybookStepsRequiredError):
        service.add(
            title="Missing steps",
            situation="No steps were supplied",
            objective="Reject the playbook",
            steps=[],
            success_criteria=["Playbook is rejected"],
            knowledge_ids=[knowledge.id],
        )

    assert knowledge_repo.requested_ids == []
    assert playbook_repo.saved == []


def test_add_playbook_raises_when_knowledge_is_missing() -> None:
    missing_id = UUID("22222222-2222-2222-2222-222222222222")
    knowledge_repo = FakeKnowledgeRepository()
    playbook_repo = FakePlaybookRepository(knowledge_repo)
    service = PlaybookService(playbook_repo, knowledge_repo)

    with pytest.raises(KnowledgeNotFoundError) as error:
        service.add(
            title="Missing knowledge",
            situation="A linked knowledge item is missing",
            objective="Reject the playbook",
            steps=["Validate knowledge"],
            success_criteria=["Playbook is rejected"],
            knowledge_ids=[missing_id],
        )

    assert error.value.knowledge_id == missing_id
    assert playbook_repo.saved == []


def test_add_playbook_stops_on_first_missing_knowledge_without_saving() -> None:
    existing = make_knowledge()
    missing_id = UUID("33333333-3333-3333-3333-333333333333")
    later_id = UUID("44444444-4444-4444-4444-444444444444")
    knowledge_repo = FakeKnowledgeRepository([existing])
    playbook_repo = FakePlaybookRepository(knowledge_repo)
    service = PlaybookService(playbook_repo, knowledge_repo)

    with pytest.raises(KnowledgeNotFoundError) as error:
        service.add(
            title="Partially invalid",
            situation="One knowledge item is missing",
            objective="Stop on first missing item",
            steps=["Validate all knowledge"],
            success_criteria=["Playbook is rejected"],
            knowledge_ids=[existing.id, missing_id, later_id],
        )

    assert error.value.knowledge_id == missing_id
    assert knowledge_repo.requested_ids == [existing.id, missing_id]
    assert playbook_repo.saved == []


def test_add_playbook_validates_all_knowledge_before_saving() -> None:
    first = make_knowledge("First")
    second = make_knowledge("Second")
    knowledge_repo = FakeKnowledgeRepository([first, second])
    playbook_repo = FakePlaybookRepository(knowledge_repo)
    service = PlaybookService(playbook_repo, knowledge_repo)

    service.add(
        title="Validate before save",
        situation="All knowledge must exist",
        objective="Save only after validation",
        steps=["Validate first", "Validate second"],
        success_criteria=["Save happened after lookups"],
        knowledge_ids=[first.id, second.id],
    )

    assert playbook_repo.lookup_order_at_save == [first.id, second.id]


def test_list_playbooks_returns_repository_items() -> None:
    knowledge = make_knowledge()
    knowledge_repo = FakeKnowledgeRepository([knowledge])
    playbook_repo = FakePlaybookRepository(knowledge_repo)
    service = PlaybookService(playbook_repo, knowledge_repo)
    playbook = service.add(
        title="List me",
        situation="Repository contains a playbook",
        objective="Return repository items",
        steps=["List playbooks"],
        success_criteria=["Playbook is returned"],
        knowledge_ids=[knowledge.id],
    )

    assert service.list_playbooks() == [playbook]
    assert playbook_repo.load_all_calls == 1


def test_list_playbooks_for_knowledge_returns_one_linked_item() -> None:
    knowledge = make_knowledge()
    linked = Playbook(
        title="Linked playbook",
        situation="It references the knowledge",
        objective="Return linked playbook",
        steps=["Use the knowledge"],
        success_criteria=["Linked playbook is returned"],
        knowledge_ids=[knowledge.id],
    )
    knowledge_repo = FakeKnowledgeRepository([knowledge])
    playbook_repo = FakePlaybookRepository(knowledge_repo)
    playbook_repo.saved.append(linked)
    service = PlaybookService(playbook_repo, knowledge_repo)

    assert service.list_for_knowledge(knowledge.id) == [linked]
    assert playbook_repo.load_all_calls == 1


def test_list_playbooks_for_knowledge_returns_multiple_linked_items() -> None:
    knowledge = make_knowledge()
    first = Playbook(
        title="First linked playbook",
        situation="It references the knowledge",
        objective="Return first playbook",
        steps=["Use first procedure"],
        success_criteria=["First playbook is returned"],
        knowledge_ids=[knowledge.id],
    )
    second = Playbook(
        title="Second linked playbook",
        situation="It also references the knowledge",
        objective="Return second playbook",
        steps=["Use second procedure"],
        success_criteria=["Second playbook is returned"],
        knowledge_ids=[knowledge.id],
    )
    knowledge_repo = FakeKnowledgeRepository([knowledge])
    playbook_repo = FakePlaybookRepository(knowledge_repo)
    playbook_repo.saved.extend([first, second])
    service = PlaybookService(playbook_repo, knowledge_repo)

    assert service.list_for_knowledge(knowledge.id) == [first, second]


def test_list_playbooks_for_knowledge_excludes_unrelated_items() -> None:
    knowledge = make_knowledge("Linked knowledge")
    other_knowledge = make_knowledge("Other knowledge")
    linked = Playbook(
        title="Linked playbook",
        situation="It references the requested knowledge",
        objective="Return linked playbook",
        steps=["Use linked knowledge"],
        success_criteria=["Linked playbook is returned"],
        knowledge_ids=[knowledge.id],
    )
    unrelated = Playbook(
        title="Unrelated playbook",
        situation="It references different knowledge",
        objective="Do not return unrelated playbook",
        steps=["Use unrelated knowledge"],
        success_criteria=["Unrelated playbook is excluded"],
        knowledge_ids=[other_knowledge.id],
    )
    knowledge_repo = FakeKnowledgeRepository([knowledge, other_knowledge])
    playbook_repo = FakePlaybookRepository(knowledge_repo)
    playbook_repo.saved.extend([linked, unrelated])
    service = PlaybookService(playbook_repo, knowledge_repo)

    assert service.list_for_knowledge(knowledge.id) == [linked]


def test_list_playbooks_for_knowledge_returns_empty_list_when_none_are_linked() -> None:
    knowledge = make_knowledge("Unlinked knowledge")
    other_knowledge = make_knowledge("Other knowledge")
    unrelated = Playbook(
        title="Unrelated playbook",
        situation="It references different knowledge",
        objective="Return no playbooks",
        steps=["Use unrelated knowledge"],
        success_criteria=["No linked playbooks are returned"],
        knowledge_ids=[other_knowledge.id],
    )
    knowledge_repo = FakeKnowledgeRepository([knowledge, other_knowledge])
    playbook_repo = FakePlaybookRepository(knowledge_repo)
    playbook_repo.saved.append(unrelated)
    service = PlaybookService(playbook_repo, knowledge_repo)

    assert service.list_for_knowledge(knowledge.id) == []
    assert playbook_repo.load_all_calls == 1


def test_list_playbooks_for_knowledge_raises_when_missing_without_loading_playbooks() -> None:
    missing_id = UUID("55555555-5555-5555-5555-555555555555")
    knowledge_repo = FakeKnowledgeRepository()
    playbook_repo = FakePlaybookRepository(knowledge_repo)
    service = PlaybookService(playbook_repo, knowledge_repo)

    with pytest.raises(KnowledgeNotFoundError) as error:
        service.list_for_knowledge(missing_id)

    assert error.value.knowledge_id == missing_id
    assert playbook_repo.load_all_calls == 0


def test_get_by_id_returns_matching_playbook() -> None:
    knowledge = make_knowledge()
    knowledge_repo = FakeKnowledgeRepository([knowledge])
    playbook_repo = FakePlaybookRepository(knowledge_repo)
    service = PlaybookService(playbook_repo, knowledge_repo)
    expected = service.add(
        title="Find me",
        situation="Lookup by ID",
        objective="Return matching playbook",
        steps=["Ask repository"],
        success_criteria=["Matching playbook is returned"],
        knowledge_ids=[knowledge.id],
    )

    assert service.get_by_id(expected.id) == expected


def test_get_by_id_returns_none_when_missing() -> None:
    knowledge_repo = FakeKnowledgeRepository()
    playbook_repo = FakePlaybookRepository(knowledge_repo)
    service = PlaybookService(playbook_repo, knowledge_repo)

    assert service.get_by_id(UUID("00000000-0000-0000-0000-000000000000")) is None

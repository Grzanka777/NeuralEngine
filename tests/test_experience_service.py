from uuid import UUID

import pytest

from neural_engine.application.experience_service import (
    ExperienceService,
    ObservationNotFoundError,
)
from neural_engine.domain import Experience, ExperienceResult, Observation
from neural_engine.ports.experience_repository import ExperienceRepository
from neural_engine.ports.observation_repository import ObservationRepository


class FakeExperienceRepository(ExperienceRepository):
    def __init__(self) -> None:
        self.saved: list[Experience] = []
        self.load_all_calls = 0

    def save(self, experience: Experience) -> None:
        self.saved.append(experience)

    def load_all(self) -> list[Experience]:
        self.load_all_calls += 1
        return self.saved

    def get_by_id(self, experience_id: UUID) -> Experience | None:
        for experience in self.saved:
            if experience.id == experience_id:
                return experience

        return None


class FakeObservationRepository(ObservationRepository):
    def __init__(self, observations: list[Observation] | None = None) -> None:
        self.saved: list[Observation] = observations or []
        self.requested_ids: list[UUID] = []

    def save(self, observation: Observation) -> None:
        self.saved.append(observation)

    def load_all(self) -> list[Observation]:
        return self.saved

    def get_by_id(self, observation_id: UUID) -> Observation | None:
        self.requested_ids.append(observation_id)

        for observation in self.saved:
            if observation.id == observation_id:
                return observation

        return None


def test_add_experience() -> None:
    experience_repo = FakeExperienceRepository()
    observation_repo = FakeObservationRepository()
    service = ExperienceService(experience_repo, observation_repo)

    experience = service.add(
        title="Implement feature",
        context="Experience vertical slice",
        action="Added domain, service, port, and repository",
        outcome="Slice persisted locally",
        result=ExperienceResult.SUCCESS,
        tags=["experience"],
    )

    assert len(experience_repo.saved) == 1
    assert experience_repo.saved[0] == experience
    assert experience.title == "Implement feature"
    assert experience.result == ExperienceResult.SUCCESS
    assert experience.observation_ids == []
    assert experience.tags == ["experience"]


def test_add_experience_with_valid_observation_ids() -> None:
    observation = Observation(content="Existing observation")
    experience_repo = FakeExperienceRepository()
    observation_repo = FakeObservationRepository([observation])
    service = ExperienceService(experience_repo, observation_repo)

    experience = service.add(
        title="Link observation",
        context="Experience validation",
        action="Reference an existing observation",
        outcome="Experience is saved",
        result=ExperienceResult.SUCCESS,
        observation_ids=[observation.id],
    )

    assert experience_repo.saved == [experience]
    assert experience.observation_ids == [observation.id]


def test_add_experience_raises_when_observation_id_is_missing() -> None:
    missing_id = UUID("11111111-1111-1111-1111-111111111111")
    experience_repo = FakeExperienceRepository()
    observation_repo = FakeObservationRepository()
    service = ExperienceService(experience_repo, observation_repo)

    with pytest.raises(ObservationNotFoundError) as error:
        service.add(
            title="Invalid link",
            context="Experience validation",
            action="Reference a missing observation",
            outcome="Experience is rejected",
            result=ExperienceResult.FAILURE,
            observation_ids=[missing_id],
        )

    assert error.value.observation_id == missing_id
    assert experience_repo.saved == []


def test_add_experience_stops_validation_without_saving_when_any_observation_id_is_missing() -> (
    None
):
    existing_observation = Observation(content="Existing observation")
    missing_id = UUID("22222222-2222-2222-2222-222222222222")
    experience_repo = FakeExperienceRepository()
    observation_repo = FakeObservationRepository([existing_observation])
    service = ExperienceService(experience_repo, observation_repo)

    with pytest.raises(ObservationNotFoundError) as error:
        service.add(
            title="Partially invalid link",
            context="Experience validation",
            action="Reference mixed observations",
            outcome="Experience is rejected",
            result=ExperienceResult.MIXED,
            observation_ids=[existing_observation.id, missing_id],
        )

    assert error.value.observation_id == missing_id
    assert experience_repo.saved == []


def test_add_from_observation_creates_experience_from_existing_observation() -> None:
    observation = Observation(content="Exact observation content")
    experience_repo = FakeExperienceRepository()
    observation_repo = FakeObservationRepository([observation])
    service = ExperienceService(experience_repo, observation_repo)

    experience = service.add_from_observation(
        observation_id=observation.id,
        title="Derived experience",
        action="Used observation",
        outcome="Experience created",
        result=ExperienceResult.SUCCESS,
        tags=["derived", "manual"],
    )

    assert experience_repo.saved == [experience]
    assert experience.title == "Derived experience"
    assert experience.context == "Exact observation content"
    assert experience.action == "Used observation"
    assert experience.outcome == "Experience created"
    assert experience.result == ExperienceResult.SUCCESS
    assert experience.observation_ids == [observation.id]
    assert experience.tags == ["derived", "manual"]
    assert observation_repo.requested_ids == [observation.id]


def test_add_from_observation_raises_when_observation_is_missing_without_saving() -> None:
    missing_id = UUID("33333333-3333-3333-3333-333333333333")
    experience_repo = FakeExperienceRepository()
    observation_repo = FakeObservationRepository()
    service = ExperienceService(experience_repo, observation_repo)

    with pytest.raises(ObservationNotFoundError) as error:
        service.add_from_observation(
            observation_id=missing_id,
            title="Missing source",
            action="Use observation",
            outcome="Experience rejected",
            result=ExperienceResult.FAILURE,
        )

    assert error.value.observation_id == missing_id
    assert experience_repo.saved == []
    assert observation_repo.requested_ids == [missing_id]


def test_list_experiences_returns_repository_items() -> None:
    experience_repo = FakeExperienceRepository()
    observation_repo = FakeObservationRepository()
    service = ExperienceService(experience_repo, observation_repo)
    experience = service.add(
        title="Capture result",
        context="Manual validation",
        action="Recorded outcome",
        outcome="Outcome is available later",
        result=ExperienceResult.MIXED,
    )

    assert service.list_experiences() == [experience]


def test_list_for_observation_returns_one_linked_experience() -> None:
    observation = Observation(content="Linked observation")
    linked = Experience(
        title="Linked experience",
        context="Context",
        action="Action",
        outcome="Outcome",
        result=ExperienceResult.SUCCESS,
        observation_ids=[observation.id],
    )
    experience_repo = FakeExperienceRepository()
    experience_repo.saved.append(linked)
    observation_repo = FakeObservationRepository([observation])
    service = ExperienceService(experience_repo, observation_repo)

    assert service.list_for_observation(observation.id) == [linked]
    assert experience_repo.load_all_calls == 1


def test_list_for_observation_returns_multiple_linked_experiences() -> None:
    observation = Observation(content="Linked observation")
    first = Experience(
        title="First linked experience",
        context="Context",
        action="Action",
        outcome="Outcome",
        result=ExperienceResult.SUCCESS,
        observation_ids=[observation.id],
    )
    second = Experience(
        title="Second linked experience",
        context="Context",
        action="Action",
        outcome="Outcome",
        result=ExperienceResult.MIXED,
        observation_ids=[observation.id],
    )
    experience_repo = FakeExperienceRepository()
    experience_repo.saved.extend([first, second])
    observation_repo = FakeObservationRepository([observation])
    service = ExperienceService(experience_repo, observation_repo)

    assert service.list_for_observation(observation.id) == [first, second]


def test_list_for_observation_excludes_unrelated_experiences() -> None:
    observation = Observation(content="Linked observation")
    other_observation = Observation(content="Other observation")
    linked = Experience(
        title="Linked experience",
        context="Context",
        action="Action",
        outcome="Outcome",
        result=ExperienceResult.SUCCESS,
        observation_ids=[observation.id],
    )
    unrelated = Experience(
        title="Unrelated experience",
        context="Context",
        action="Action",
        outcome="Outcome",
        result=ExperienceResult.FAILURE,
        observation_ids=[other_observation.id],
    )
    experience_repo = FakeExperienceRepository()
    experience_repo.saved.extend([linked, unrelated])
    observation_repo = FakeObservationRepository([observation, other_observation])
    service = ExperienceService(experience_repo, observation_repo)

    assert service.list_for_observation(observation.id) == [linked]


def test_list_for_observation_returns_empty_list_when_no_experiences_are_linked() -> None:
    observation = Observation(content="Unlinked observation")
    unrelated = Experience(
        title="Unrelated experience",
        context="Context",
        action="Action",
        outcome="Outcome",
        result=ExperienceResult.FAILURE,
    )
    experience_repo = FakeExperienceRepository()
    experience_repo.saved.append(unrelated)
    observation_repo = FakeObservationRepository([observation])
    service = ExperienceService(experience_repo, observation_repo)

    assert service.list_for_observation(observation.id) == []


def test_list_for_observation_raises_when_observation_is_missing_without_loading_experiences() -> (
    None
):
    missing_id = UUID("44444444-4444-4444-4444-444444444444")
    experience_repo = FakeExperienceRepository()
    observation_repo = FakeObservationRepository()
    service = ExperienceService(experience_repo, observation_repo)

    with pytest.raises(ObservationNotFoundError) as error:
        service.list_for_observation(missing_id)

    assert error.value.observation_id == missing_id
    assert experience_repo.load_all_calls == 0


def test_get_by_id_returns_matching_experience() -> None:
    experience_repo = FakeExperienceRepository()
    observation_repo = FakeObservationRepository()
    service = ExperienceService(experience_repo, observation_repo)
    expected = service.add(
        title="Find this",
        context="Lookup",
        action="Use repository id lookup",
        outcome="The matching item is returned",
        result=ExperienceResult.UNKNOWN,
    )

    assert service.get_by_id(expected.id) == expected


def test_get_by_id_returns_none_when_missing() -> None:
    experience_repo = FakeExperienceRepository()
    observation_repo = FakeObservationRepository()
    service = ExperienceService(experience_repo, observation_repo)

    assert service.get_by_id(UUID("00000000-0000-0000-0000-000000000000")) is None

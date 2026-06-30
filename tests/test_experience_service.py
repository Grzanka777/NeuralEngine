from uuid import UUID

from neural_engine.application.experience_service import ExperienceService
from neural_engine.domain import Experience, ExperienceResult
from neural_engine.ports.experience_repository import ExperienceRepository


class FakeExperienceRepository(ExperienceRepository):
    def __init__(self) -> None:
        self.saved: list[Experience] = []

    def save(self, experience: Experience) -> None:
        self.saved.append(experience)

    def load_all(self) -> list[Experience]:
        return self.saved

    def get_by_id(self, experience_id: UUID) -> Experience | None:
        for experience in self.saved:
            if experience.id == experience_id:
                return experience

        return None


def test_add_experience() -> None:
    repo = FakeExperienceRepository()
    service = ExperienceService(repo)

    experience = service.add(
        title="Implement feature",
        context="Experience vertical slice",
        action="Added domain, service, port, and repository",
        outcome="Slice persisted locally",
        result=ExperienceResult.SUCCESS,
        tags=["experience"],
    )

    assert len(repo.saved) == 1
    assert repo.saved[0] == experience
    assert experience.title == "Implement feature"
    assert experience.result == ExperienceResult.SUCCESS
    assert experience.tags == ["experience"]


def test_list_experiences_returns_repository_items() -> None:
    repo = FakeExperienceRepository()
    service = ExperienceService(repo)
    experience = service.add(
        title="Capture result",
        context="Manual validation",
        action="Recorded outcome",
        outcome="Outcome is available later",
        result=ExperienceResult.MIXED,
    )

    assert service.list_experiences() == [experience]


def test_get_by_id_returns_matching_experience() -> None:
    repo = FakeExperienceRepository()
    service = ExperienceService(repo)
    expected = service.add(
        title="Find this",
        context="Lookup",
        action="Use repository id lookup",
        outcome="The matching item is returned",
        result=ExperienceResult.UNKNOWN,
    )

    assert service.get_by_id(expected.id) == expected


def test_get_by_id_returns_none_when_missing() -> None:
    repo = FakeExperienceRepository()
    service = ExperienceService(repo)

    assert service.get_by_id(UUID("00000000-0000-0000-0000-000000000000")) is None

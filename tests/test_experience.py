from datetime import UTC

from neural_engine.domain import Experience, ExperienceResult


def test_experience_has_domain_defaults() -> None:
    experience = Experience(
        title="A useful outcome",
        context="A problem was investigated",
        action="Ran focused tests",
        outcome="The failing behavior was isolated",
        result=ExperienceResult.SUCCESS,
    )

    assert experience.title == "A useful outcome"
    assert experience.context == "A problem was investigated"
    assert experience.action == "Ran focused tests"
    assert experience.outcome == "The failing behavior was isolated"
    assert experience.result == ExperienceResult.SUCCESS
    assert experience.observation_ids == []
    assert experience.tags == []
    assert experience.timestamp.tzinfo == UTC


def test_experience_result_values() -> None:
    assert ExperienceResult.SUCCESS.value == "success"
    assert ExperienceResult.FAILURE.value == "failure"
    assert ExperienceResult.MIXED.value == "mixed"
    assert ExperienceResult.UNKNOWN.value == "unknown"

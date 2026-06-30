from datetime import UTC

from neural_engine.domain import Observation


def test_observation_has_domain_defaults() -> None:
    observation = Observation(content="A useful signal")

    assert observation.content == "A useful signal"
    assert observation.source == "user"
    assert observation.tags == []
    assert observation.timestamp.tzinfo == UTC

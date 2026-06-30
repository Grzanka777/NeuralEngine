from neural_engine.core.brain import Brain


def test_brain_exists() -> None:
    brain = Brain()
    brain.initialize()

    assert brain.exists()

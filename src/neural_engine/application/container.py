from neural_engine.application.experience_service import ExperienceService
from neural_engine.application.observation_service import ObservationService
from neural_engine.infrastructure.json_experience_repository import (
    JsonExperienceRepository,
)
from neural_engine.infrastructure.json_observation_repository import (
    JsonObservationRepository,
)


class Container:
    """Application dependency container."""

    def observation_service(self) -> ObservationService:
        return ObservationService(
            JsonObservationRepository(),
        )

    def experience_service(self) -> ExperienceService:
        return ExperienceService(
            JsonExperienceRepository(),
            JsonObservationRepository(),
        )

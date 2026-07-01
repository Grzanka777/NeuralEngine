from neural_engine.application.experience_service import ExperienceService
from neural_engine.application.knowledge_service import KnowledgeService
from neural_engine.application.observation_service import ObservationService
from neural_engine.application.playbook_run_service import PlaybookRunService
from neural_engine.application.playbook_service import PlaybookService
from neural_engine.infrastructure.json_experience_repository import (
    JsonExperienceRepository,
)
from neural_engine.infrastructure.json_knowledge_repository import (
    JsonKnowledgeRepository,
)
from neural_engine.infrastructure.json_observation_repository import (
    JsonObservationRepository,
)
from neural_engine.infrastructure.json_playbook_repository import (
    JsonPlaybookRepository,
)
from neural_engine.infrastructure.json_playbook_run_repository import (
    JsonPlaybookRunRepository,
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

    def knowledge_service(self) -> KnowledgeService:
        return KnowledgeService(
            JsonKnowledgeRepository(),
            JsonExperienceRepository(),
        )

    def playbook_service(self) -> PlaybookService:
        return PlaybookService(
            JsonPlaybookRepository(),
            JsonKnowledgeRepository(),
        )

    def playbook_run_service(self) -> PlaybookRunService:
        return PlaybookRunService(
            JsonPlaybookRunRepository(),
            JsonPlaybookRepository(),
        )

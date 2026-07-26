from uuid import UUID

from neural_engine.application.playbook_run_service import PlaybookRunReader
from neural_engine.domain import PlaybookEffectiveness, PlaybookEvaluation
from neural_engine.ports.playbook_evaluation_repository import (
    PlaybookEvaluationRepository,
)


class PlaybookEvaluationFindingsRequiredError(Exception):
    """Raised when a playbook evaluation is created without findings."""

    def __init__(self) -> None:
        super().__init__("Playbook evaluation requires at least one finding.")


class PlaybookRunNotFoundError(Exception):
    """Raised when a playbook evaluation references an unknown playbook run."""

    def __init__(self, run_id: UUID) -> None:
        self.run_id = run_id
        super().__init__(f"Playbook run not found: {run_id}")


class PlaybookEvaluationService:
    """Application service for playbook evaluations."""

    def __init__(
        self,
        evaluation_repository: PlaybookEvaluationRepository,
        run_repository: PlaybookRunReader,
    ) -> None:
        self._evaluation_repository = evaluation_repository
        self._run_repository = run_repository

    def add(
        self,
        run_id: UUID,
        effectiveness: PlaybookEffectiveness,
        findings: list[str],
        improvements: list[str] | None = None,
        evidence: list[str] | None = None,
        notes: str | None = None,
        tags: list[str] | None = None,
    ) -> PlaybookEvaluation:
        self._validate(run_id, findings)

        evaluation = PlaybookEvaluation(
            run_id=run_id,
            effectiveness=effectiveness,
            findings=findings,
            improvements=improvements or [],
            evidence=evidence or [],
            notes=notes,
            tags=tags or [],
        )

        self._evaluation_repository.save(evaluation)

        return evaluation

    def list_evaluations(self) -> list[PlaybookEvaluation]:
        return self._evaluation_repository.load_all()

    def list_for_run(self, run_id: UUID) -> list[PlaybookEvaluation]:
        if self._run_repository.get_by_id(run_id) is None:
            raise PlaybookRunNotFoundError(run_id)

        evaluations = self._evaluation_repository.load_all()

        return [evaluation for evaluation in evaluations if evaluation.run_id == run_id]

    def get_by_id(self, evaluation_id: UUID) -> PlaybookEvaluation | None:
        return self._evaluation_repository.get_by_id(evaluation_id)

    def _validate(self, run_id: UUID, findings: list[str]) -> None:
        if not findings:
            raise PlaybookEvaluationFindingsRequiredError()

        if self._run_repository.get_by_id(run_id) is None:
            raise PlaybookRunNotFoundError(run_id)

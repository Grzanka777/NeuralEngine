from __future__ import annotations

from uuid import UUID

from neural_engine.domain import PlaybookRun
from neural_engine.ports.playbook_repository import PlaybookRepository
from neural_engine.ports.playbook_run_repository import PlaybookRunRepository


class PlaybookRunActionsRequiredError(Exception):
    """Raised when a playbook run is created without recorded actions."""

    def __init__(self) -> None:
        super().__init__("Playbook run requires at least one action taken.")


class PlaybookNotFoundError(Exception):
    """Raised when a playbook run references an unknown playbook."""

    def __init__(self, playbook_id: UUID) -> None:
        self.playbook_id = playbook_id
        super().__init__(f"Playbook not found: {playbook_id}")


class PlaybookRunService:
    """Application service for playbook runs."""

    def __init__(
        self,
        run_repository: PlaybookRunRepository,
        playbook_repository: PlaybookRepository,
    ) -> None:
        self._run_repository = run_repository
        self._playbook_repository = playbook_repository

    def add(
        self,
        playbook_id: UUID,
        situation: str,
        actions_taken: list[str],
        outcome: str,
        success: bool,
        evidence: list[str] | None = None,
        notes: str | None = None,
        tags: list[str] | None = None,
    ) -> PlaybookRun:
        self._validate(playbook_id, actions_taken)

        run = PlaybookRun(
            playbook_id=playbook_id,
            situation=situation,
            actions_taken=actions_taken,
            outcome=outcome,
            success=success,
            evidence=evidence or [],
            notes=notes,
            tags=tags or [],
        )

        self._run_repository.save(run)

        return run

    def list_runs(self) -> list[PlaybookRun]:
        return self._run_repository.load_all()

    def get_by_id(self, run_id: UUID) -> PlaybookRun | None:
        return self._run_repository.get_by_id(run_id)

    def _validate(self, playbook_id: UUID, actions_taken: list[str]) -> None:
        if not actions_taken:
            raise PlaybookRunActionsRequiredError()

        if self._playbook_repository.get_by_id(playbook_id) is None:
            raise PlaybookNotFoundError(playbook_id)

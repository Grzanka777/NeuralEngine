from __future__ import annotations

from typing import Protocol
from uuid import UUID

from neural_engine.domain import PlaybookRun
from neural_engine.ports.playbook_repository import PlaybookRepository
from neural_engine.ports.playbook_revision_repository import PlaybookRevisionRepository
from neural_engine.ports.playbook_run_repository import PlaybookRunRepository


class PlaybookRunReader(Protocol):
    """Narrow validated read boundary for downstream Run consumers."""

    def get_by_id(self, run_id: UUID) -> PlaybookRun | None: ...


class PlaybookRunActionsRequiredError(Exception):
    """Raised when a playbook run is created without recorded actions."""

    def __init__(self) -> None:
        super().__init__("Playbook run requires at least one action taken.")


class PlaybookNotFoundError(Exception):
    """Raised when a playbook run references an unknown playbook."""

    def __init__(self, playbook_id: UUID) -> None:
        self.playbook_id = playbook_id
        super().__init__(f"Playbook not found: {playbook_id}")


class PlaybookRevisionNotFoundError(Exception):
    """Raised when a playbook run references an unknown revision."""

    def __init__(self, revision_id: UUID) -> None:
        self.revision_id = revision_id
        super().__init__(f"Playbook revision not found: {revision_id}")


class PlaybookRunRevisionPlaybookMismatchError(Exception):
    """Raised when a run revision belongs to another playbook."""

    def __init__(
        self,
        revision_id: UUID,
        expected_playbook_id: UUID,
        actual_playbook_id: UUID,
    ) -> None:
        self.revision_id = revision_id
        self.expected_playbook_id = expected_playbook_id
        self.actual_playbook_id = actual_playbook_id
        super().__init__(
            f"Playbook revision {revision_id} belongs to playbook {actual_playbook_id}, "
            f"expected {expected_playbook_id}."
        )


class PlaybookRunService:
    """Application service for playbook runs."""

    def __init__(
        self,
        run_repository: PlaybookRunRepository,
        playbook_repository: PlaybookRepository,
        revision_repository: PlaybookRevisionRepository,
    ) -> None:
        self._run_repository = run_repository
        self._playbook_repository = playbook_repository
        self._revision_repository = revision_repository

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
        revision_id: UUID | None = None,
    ) -> PlaybookRun:
        self._validate_write(playbook_id, actions_taken, revision_id)

        run = PlaybookRun(
            playbook_id=playbook_id,
            revision_id=revision_id,
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
        runs = self._run_repository.load_all()
        self._validate_runs(runs)
        return runs

    def list_for_playbook(self, playbook_id: UUID) -> list[PlaybookRun]:
        if self._playbook_repository.get_by_id(playbook_id) is None:
            raise PlaybookNotFoundError(playbook_id)

        runs = self._run_repository.load_all()
        matching = [run for run in runs if run.playbook_id == playbook_id]
        self._validate_runs(matching)
        return matching

    def list_for_revision(self, revision_id: UUID) -> list[PlaybookRun]:
        revision = self._revision_repository.get_by_id(revision_id)
        if revision is None:
            raise PlaybookRevisionNotFoundError(revision_id)

        runs = [run for run in self._run_repository.load_all() if run.revision_id == revision_id]
        self._validate_runs(runs)
        return runs

    def get_by_id(self, run_id: UUID) -> PlaybookRun | None:
        run = self._run_repository.get_by_id(run_id)
        if run is not None:
            self._validate_revision_relation(run)
        return run

    def _validate_write(
        self,
        playbook_id: UUID,
        actions_taken: list[str],
        revision_id: UUID | None,
    ) -> None:
        if not actions_taken:
            raise PlaybookRunActionsRequiredError()

        if self._playbook_repository.get_by_id(playbook_id) is None:
            raise PlaybookNotFoundError(playbook_id)

        if revision_id is not None:
            self._validate_revision(revision_id, playbook_id)

    def _validate_runs(self, runs: list[PlaybookRun]) -> None:
        for run in runs:
            self._validate_revision_relation(run)

    def _validate_revision_relation(self, run: PlaybookRun) -> None:
        if run.revision_id is not None:
            self._validate_revision(run.revision_id, run.playbook_id)

    def _validate_revision(self, revision_id: UUID, playbook_id: UUID) -> None:
        revision = self._revision_repository.get_by_id(revision_id)
        if revision is None:
            raise PlaybookRevisionNotFoundError(revision_id)

        if revision.playbook_id != playbook_id:
            raise PlaybookRunRevisionPlaybookMismatchError(
                revision_id=revision_id,
                expected_playbook_id=playbook_id,
                actual_playbook_id=revision.playbook_id,
            )

import re
from datetime import datetime
from math import isfinite
from typing import Annotated, cast
from uuid import UUID

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from neural_engine import APP_NAME, __version__
from neural_engine.application.container import Container
from neural_engine.application.decision_acceptance_service import (
    DecisionAcceptanceDecisionNotFoundError,
    DecisionAcceptanceIdempotencyConflictError,
    DecisionAlreadyAcceptedError,
)
from neural_engine.application.decision_action_service import (
    DecisionActionAcceptanceMismatchError,
    DecisionActionAcceptanceNotFoundError,
    DecisionActionDecisionNotFoundError,
    DecisionActionIdempotencyConflictError,
    DecisionActionNotFoundError,
    DecisionActionPlaybookRunNotFoundError,
)
from neural_engine.application.decision_lifecycle_service import (
    DecisionLifecycleActionAcceptanceMismatchError,
    DecisionLifecycleDecisionNotFoundError,
    DecisionLifecycleError,
    DecisionLifecycleMultipleAcceptancesError,
)
from neural_engine.application.decision_outcome_service import DecisionOutcomeError
from neural_engine.application.decision_review_service import DecisionReviewError
from neural_engine.application.decision_service import (
    DecisionIdempotencyConflictError,
    DecisionNotFoundError,
    DecisionObservationNotFoundError,
    DecisionProjectKeyRequiredError,
    DecisionSupersededNotFoundError,
    DecisionSupersededProjectMismatchError,
)
from neural_engine.application.development_evidence_service import (
    DevelopmentEvidenceCandidate,
    DevelopmentEvidenceError,
    DevelopmentEvidenceRecordInput,
    DevelopmentEvidenceRequest,
)
from neural_engine.application.evolution_proposal_service import (
    EvolutionProposalChangesRequiredError,
    EvolutionProposalEvaluationPlaybookMismatchError,
    EvolutionProposalEvaluationRunNotFoundError,
    EvolutionProposalEvaluationsRequiredError,
    EvolutionProposalNotFoundError,
    PlaybookEvaluationNotFoundError,
)
from neural_engine.application.evolution_proposal_service import (
    PlaybookNotFoundError as ProposalPlaybookNotFoundError,
)
from neural_engine.application.experience_service import (
    DecisionReviewPromotionError,
    DecisionReviewPromotionSelector,
    ObservationNotFoundError,
)
from neural_engine.application.knowledge_service import (
    ExperienceNotFoundError,
    KnowledgeEvidenceRequiredError,
)
from neural_engine.application.neural_doctor_service import (
    DoctorCheck,
    DoctorState,
    NeuralDoctorReport,
)
from neural_engine.application.playbook_evaluation_service import (
    PlaybookEvaluationFindingsRequiredError,
    PlaybookRunNotFoundError,
)
from neural_engine.application.playbook_revision_activation_service import (
    PlaybookRevisionActivationPlaybookNotFoundError,
    PlaybookRevisionActivationPreviousRevisionForbiddenError,
    PlaybookRevisionActivationPreviousRevisionNotFoundError,
    PlaybookRevisionActivationPreviousRevisionPlaybookMismatchError,
    PlaybookRevisionActivationPreviousRevisionRequiredError,
    PlaybookRevisionActivationProposalNotFoundError,
    PlaybookRevisionActivationRevisionNotFoundError,
    PlaybookRevisionActivationRevisionPlaybookMismatchError,
    PlaybookRevisionActivationRevisionProposalMismatchError,
)
from neural_engine.application.playbook_revision_service import (
    KnowledgeNotFoundError as RevisionKnowledgeNotFoundError,
)
from neural_engine.application.playbook_revision_service import (
    PlaybookNotFoundError as RevisionPlaybookNotFoundError,
)
from neural_engine.application.playbook_revision_service import (
    PlaybookRevisionProposalMismatchError,
    PlaybookRevisionProposalNotAcceptedError,
    PlaybookRevisionStepsRequiredError,
    PlaybookRevisionSuccessCriteriaRequiredError,
)
from neural_engine.application.playbook_run_service import (
    PlaybookNotFoundError,
    PlaybookRevisionNotFoundError,
    PlaybookRunActionsRequiredError,
    PlaybookRunRevisionPlaybookMismatchError,
)
from neural_engine.application.playbook_service import (
    KnowledgeNotFoundError,
    PlaybookKnowledgeRequiredError,
    PlaybookStepsRequiredError,
)
from neural_engine.core.brain import Brain
from neural_engine.core.paths import NeuralHomeError, resolve_neural_paths
from neural_engine.domain import (
    Decision,
    DecisionAction,
    DecisionOutcome,
    DecisionOutcomeResult,
    DecisionReview,
    DecisionReviewAssessment,
    DecisionReviewConfidence,
    DecisionReviewPromotionSourceKind,
    EvidenceReference,
    EvolutionProposal,
    EvolutionProposalStatus,
    Experience,
    ExperienceResult,
    Knowledge,
    KnowledgeConfidence,
    Observation,
    Playbook,
    PlaybookEffectiveness,
    PlaybookEvaluation,
    PlaybookRevision,
    PlaybookRevisionActivation,
    PlaybookRevisionActivationDecision,
    PlaybookRun,
)
from neural_engine.domain.decision_outcome import DecisionOutcomeMetricValue
from neural_engine.infrastructure.local_development_evidence_source import (
    LocalDevelopmentEvidenceSourceError,
)
from neural_engine.ports.knowledge_repository import KnowledgeRepositoryError
from neural_engine.ports.playbook_revision_repository import (
    PlaybookRevisionRepositoryError,
)

app = typer.Typer(
    add_completion=False,
    help="Neural Engine CLI",
)
decision_app = typer.Typer(
    help="Record and inspect proposed decisions.",
)
decision_action_app = typer.Typer(
    help="Record Decision actions.",
)
decision_outcome_app = typer.Typer(
    help="Record factual Decision outcomes.",
)
decision_review_app = typer.Typer(
    help="Record authorized interpretations of Decision outcomes.",
)
experience_app = typer.Typer(
    help="Manage experiences.",
)
evaluation_app = typer.Typer(
    help="Record and inspect playbook evaluations.",
)
proposal_app = typer.Typer(
    help="Record and inspect evolution proposals.",
)
revision_app = typer.Typer(
    help="Record and inspect playbook revisions.",
)
knowledge_app = typer.Typer(
    help="Manage knowledge.",
)
observation_app = typer.Typer(
    help="Inspect observations.",
)
playbook_app = typer.Typer(
    help="Manage playbooks.",
)
run_app = typer.Typer(
    help="Record and inspect playbook runs.",
)
development_evidence_app = typer.Typer(
    help="Preview or explicitly apply one local development evidence bundle.",
)
app.add_typer(decision_app, name="decision")
decision_app.add_typer(decision_action_app, name="action")
decision_app.add_typer(decision_outcome_app, name="outcome")
decision_app.add_typer(decision_review_app, name="review")
app.add_typer(experience_app, name="experience")
app.add_typer(evaluation_app, name="evaluation")
app.add_typer(knowledge_app, name="knowledge")
app.add_typer(observation_app, name="observation")
app.add_typer(playbook_app, name="playbook")
app.add_typer(proposal_app, name="proposal")
app.add_typer(revision_app, name="revision")
app.add_typer(run_app, name="run")
app.add_typer(development_evidence_app, name="development-evidence")

console = Console()
container = Container()


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """Neural Engine entry point."""

    if ctx.invoked_subcommand in {"doctor", "init", "status"}:
        return

    if ctx.invoked_subcommand is None:
        if not _render_neural_status():
            raise typer.Exit(code=1)
        return

    try:
        paths = resolve_neural_paths()
        paths.require_available(operation=ctx.invoked_subcommand)
        if paths.is_override:
            Brain(paths).require_initialized(operation=ctx.invoked_subcommand)
    except NeuralHomeError as error:
        _exit_neural_home_error(error)


@app.command()
def init() -> None:
    """Initialize the local Neural Engine brain."""

    try:
        paths = resolve_neural_paths()
        Brain(paths).initialize()
    except NeuralHomeError as error:
        _exit_neural_home_error(error)
    except OSError as error:
        console.print(f"[red]Neural home initialization failed: {error}[/red]")
        raise typer.Exit(code=1) from error

    console.print("[green]🧠 Neural Engine initialized successfully![/green]")


@app.command()
def status() -> None:
    """Show Neural Engine status."""

    if not _render_neural_status():
        raise typer.Exit(code=1)


@app.command()
def doctor() -> None:
    """Assess local Neural Engine operational readiness without writing."""

    try:
        report = container.neural_doctor_service().inspect()
    except Exception as error:
        console.print("[red]Neural Doctor failed unexpectedly.[/red]")
        raise typer.Exit(code=2) from error

    _render_neural_doctor(report)
    if not report.ready:
        raise typer.Exit(code=1)


def _render_neural_doctor(report: NeuralDoctorReport) -> None:
    console.print(f"[bold cyan]{APP_NAME} Doctor[/bold cyan]")
    _render_doctor_section("Selection", report.selection_checks)
    console.print(f"Source          : {report.source}")
    console.print(f"Configured home : {_doctor_value(report.configured_value)}")
    console.print(f"Resolved home   : {_doctor_value(report.resolved_home)}")
    console.print(f"Resolved Brain  : {_doctor_value(report.resolved_brain)}")
    console.print("Fallback used   : no")
    _render_doctor_section("Home", report.home_checks)
    _render_doctor_section("Brain", report.brain_checks)

    console.print("\n[bold]Stores[/bold]")
    stores = Table(show_header=True, box=None)
    stores.add_column("Store")
    stores.add_column("State")
    stores.add_column("Records", justify="right")
    stores.add_column("Detail")
    for store in report.stores:
        stores.add_row(
            store.name,
            _doctor_state(store.state),
            str(store.record_count),
            store.detail,
        )
    total_state = (
        DoctorState.FAIL
        if any(store.state == DoctorState.FAIL for store in report.stores)
        else DoctorState.SKIP
        if any(store.state == DoctorState.SKIP for store in report.stores)
        else DoctorState.PASS
    )
    stores.add_row(
        "TOTAL",
        _doctor_state(total_state),
        str(sum(store.record_count for store in report.stores)),
        f"{len(report.stores)} stores",
    )
    console.print(stores)

    _render_doctor_section("Integrity", report.integrity_checks)
    console.print("\n[bold]Manifest[/bold]")
    console.print(f"State           : {_doctor_state(report.manifest.state)}")
    console.print(f"Algorithm       : {report.manifest.algorithm}")
    console.print("Relative root   : Brain")
    console.print(f"JSON files      : {report.manifest.file_count}")
    console.print(f"Aggregate SHA-256: {_doctor_value(report.manifest.aggregate_sha256)}")
    console.print(f"Detail          : {report.manifest.detail}")

    console.print("\n[bold]Readiness[/bold]")
    readiness = "[green]READY[/green]" if report.ready else "[red]NOT READY[/red]"
    console.print(f"State           : {readiness}")
    console.print(f"Failed checks   : {report.failed_check_count}")


def _render_doctor_section(name: str, checks: tuple[DoctorCheck, ...]) -> None:
    console.print(f"\n[bold]{name}[/bold]")
    for check in checks:
        console.print(f"{_doctor_state(check.state):20} {check.label}: {check.detail}")


def _doctor_state(state: DoctorState) -> str:
    colors = {
        DoctorState.PASS: "green",
        DoctorState.WARN: "yellow",
        DoctorState.FAIL: "red",
        DoctorState.SKIP: "dim",
    }
    return f"[{colors[state]}]{state.value}[/{colors[state]}]"


def _doctor_value(value: str | None) -> str:
    if value == "":
        return "(blank)"
    return value if value is not None else "-"


def _render_neural_status() -> bool:
    try:
        paths = resolve_neural_paths()
        paths.require_available(operation="status")
    except NeuralHomeError as error:
        _render_unavailable_neural_status(error)
        return False

    brain_status = Brain(paths).status()
    configured = paths.configured_value if paths.configured_value is not None else "-"
    state = (
        "Initialized"
        if brain_status.initialized
        else "Unavailable"
        if brain_status.brain_exists
        else "Not initialized"
    )
    failure_reason = (
        f"Neural Brain is unavailable at {paths.BRAIN}." if state == "Unavailable" else "-"
    )
    _render_status_fields(
        source="override (NEURAL_HOME)" if paths.is_override else "default",
        configured=configured,
        resolved_home=str(paths.HOME),
        resolved_brain=str(paths.BRAIN),
        home_exists=brain_status.home_exists,
        home_is_directory=brain_status.home_is_directory,
        home_accessible=brain_status.home_accessible,
        brain_exists=brain_status.brain_exists,
        brain_accessible=brain_status.brain_accessible,
        configured_root_available=brain_status.home_accessible,
        brain_state=state,
        failure_reason=failure_reason,
    )
    return state != "Unavailable"


def _render_unavailable_neural_status(error: NeuralHomeError) -> None:
    configured = error.configured_value
    if configured == "":
        configured = "(blank)"
    resolved_home = error.resolved_path
    home_exists = resolved_home is not None and resolved_home.exists()
    home_is_directory = resolved_home is not None and resolved_home.is_dir()
    _render_status_fields(
        source="override (NEURAL_HOME)" if error.source == "override" else "default",
        configured=configured or "-",
        resolved_home=str(resolved_home) if resolved_home is not None else "-",
        resolved_brain=(str(resolved_home / "brain") if resolved_home is not None else "-"),
        home_exists=home_exists,
        home_is_directory=home_is_directory,
        home_accessible=False,
        brain_exists=False,
        brain_accessible=False,
        configured_root_available=False,
        brain_state="Unavailable",
        failure_reason=str(error),
    )


def _render_status_fields(
    *,
    source: str,
    configured: str,
    resolved_home: str,
    resolved_brain: str,
    home_exists: bool,
    home_is_directory: bool,
    home_accessible: bool,
    brain_exists: bool,
    brain_accessible: bool,
    configured_root_available: bool,
    brain_state: str,
    failure_reason: str,
) -> None:
    console.print(f"[bold cyan]{APP_NAME}[/bold cyan]")
    console.print(f"Version                  : {__version__}")
    console.print(f"Resolution source        : {source}")
    console.print(f"Configured Neural home   : {configured}")
    console.print(f"Resolved Neural home     : {resolved_home}")
    console.print(f"Resolved Brain path      : {resolved_brain}")
    console.print(f"Home exists              : {_yes_no(home_exists)}")
    console.print(f"Home is directory        : {_yes_no(home_is_directory)}")
    console.print(f"Home accessible          : {_yes_no(home_accessible)}")
    console.print(f"Brain exists             : {_yes_no(brain_exists)}")
    console.print(f"Brain accessible         : {_yes_no(brain_accessible)}")
    console.print(f"Configured root available: {_yes_no(configured_root_available)}")
    console.print(f"Brain state              : {brain_state}")
    console.print(f"Failure reason           : {failure_reason}")


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _exit_neural_home_error(error: NeuralHomeError) -> None:
    console.print(f"[red]{error}[/red]")
    raise typer.Exit(code=1) from error


@development_evidence_app.command("preview")
def preview_development_evidence(
    repository_root: Annotated[str, typer.Option("--repository-root")],
    prompt_path: Annotated[str, typer.Option("--prompt-path")],
    review_path: Annotated[str, typer.Option("--review-path")],
    commit_sha: Annotated[str, typer.Option("--commit-sha")],
    records_json: Annotated[str, typer.Option("--records-json")],
) -> None:
    """Render a side-effect-free candidate from explicitly selected local evidence."""

    candidate = _development_evidence_candidate(
        repository_root, prompt_path, review_path, commit_sha, records_json
    )
    console.print_json(candidate.model_dump_json())


@development_evidence_app.command("apply")
def apply_development_evidence(
    repository_root: Annotated[str, typer.Option("--repository-root")],
    prompt_path: Annotated[str, typer.Option("--prompt-path")],
    review_path: Annotated[str, typer.Option("--review-path")],
    commit_sha: Annotated[str, typer.Option("--commit-sha")],
    records_json: Annotated[str, typer.Option("--records-json")],
    authority_confirmed: Annotated[
        bool,
        typer.Option(
            "--confirm-authority",
            help="Confirm explicit authority for all supplied semantic actor fields.",
        ),
    ] = False,
) -> None:
    """Render, revalidate, and explicitly apply a candidate."""

    service = container.development_evidence_service()
    candidate = _development_evidence_candidate(
        repository_root, prompt_path, review_path, commit_sha, records_json
    )
    console.print_json(candidate.model_dump_json())
    try:
        result = service.apply(candidate, authority_confirmed=authority_confirmed)
    except (DevelopmentEvidenceError, LocalDevelopmentEvidenceSourceError) as error:
        _exit_development_evidence_error(error)
    console.print_json(result.model_dump_json())


@decision_app.command("add")
def add_decision(
    project_key: Annotated[str, typer.Option("--project-key")],
    title: Annotated[str, typer.Option("--title")],
    objective: Annotated[str, typer.Option("--objective")],
    context_summary: Annotated[str, typer.Option("--context-summary")],
    alternatives: Annotated[list[str], typer.Option("--alternative")],
    proposed_option: Annotated[str, typer.Option("--proposed-option")],
    rationale: Annotated[str, typer.Option("--rationale")],
    proposed_by: Annotated[str, typer.Option("--proposed-by")],
    idempotency_key: Annotated[str, typer.Option("--idempotency-key")],
    observation_ids: Annotated[list[UUID] | None, typer.Option("--observation-id")] = None,
    evidence_values: Annotated[list[str] | None, typer.Option("--evidence")] = None,
    supersedes_decision_id: Annotated[
        UUID | None,
        typer.Option("--supersedes-decision-id"),
    ] = None,
    tags: Annotated[list[str] | None, typer.Option("--tag")] = None,
) -> None:
    """Record one proposed Decision."""

    try:
        evidence_references = [
            EvidenceReference.model_validate_json(value) for value in evidence_values or []
        ]
        decision = container.decision_service().add(
            project_key=project_key,
            title=title,
            objective=objective,
            context_summary=context_summary,
            alternatives=alternatives,
            proposed_option=proposed_option,
            rationale=rationale,
            proposed_by=proposed_by,
            idempotency_key=idempotency_key,
            observation_ids=observation_ids,
            evidence_references=evidence_references,
            supersedes_decision_id=supersedes_decision_id,
            tags=tags,
        )
    except ValidationError as error:
        console.print(f"[red]{error.errors()[0]['msg']}[/red]")
        raise typer.Exit(code=1) from error
    except DecisionObservationNotFoundError as error:
        console.print(f"[red]Observation not found: {error.observation_id}[/red]")
        raise typer.Exit(code=1) from error
    except DecisionSupersededNotFoundError as error:
        console.print(f"[red]Superseded Decision not found: {error.decision_id}[/red]")
        raise typer.Exit(code=1) from error
    except DecisionSupersededProjectMismatchError as error:
        console.print(
            f"[red]Superseded Decision {error.decision_id} belongs to project "
            f"{error.actual_project_key}, expected {error.expected_project_key}[/red]"
        )
        raise typer.Exit(code=1) from error
    except DecisionIdempotencyConflictError as error:
        console.print(
            f"[red]Decision idempotency key {error.idempotency_key!r} already exists for "
            f"project {error.project_key!r} with a different payload.[/red]"
        )
        raise typer.Exit(code=1) from error

    console.print(f"[green]Decision stored.[/green] ID: [cyan]{decision.id}[/cyan]")


@decision_app.command("list")
def list_decisions(
    project_key: Annotated[str | None, typer.Option("--project")] = None,
) -> None:
    """List proposed Decisions."""

    try:
        decisions = container.decision_service().list_decisions(project_key)
    except DecisionProjectKeyRequiredError as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(code=1) from error

    if not decisions:
        message = (
            f"No Decisions found for project: {project_key}"
            if project_key is not None
            else "No Decisions found."
        )
        console.print(f"[yellow]{message}[/yellow]")
        return

    table = Table()
    table.add_column("ID")
    table.add_column("Created")
    table.add_column("Project")
    table.add_column("Title")
    table.add_column("Proposed option")
    table.add_column("Proposed by")
    for decision in decisions:
        table.add_row(
            str(decision.id),
            decision.created_at.isoformat(),
            decision.project_key,
            decision.title,
            decision.proposed_option,
            decision.proposed_by,
        )

    console.print(table)


@decision_app.command("show")
def show_decision(decision_id: UUID) -> None:
    """Show one proposed Decision."""

    try:
        decision = container.decision_service().show(decision_id)
    except DecisionNotFoundError as error:
        console.print(f"[red]Decision not found: {error.decision_id}[/red]")
        raise typer.Exit(code=1) from error

    _print_decision(decision)


@decision_app.command("accept")
def accept_decision(
    decision_id: UUID,
    accepted_by: Annotated[str, typer.Option("--accepted-by")],
    reason: Annotated[str, typer.Option("--reason")],
    idempotency_key: Annotated[str, typer.Option("--idempotency-key")],
    evidence_values: Annotated[list[str] | None, typer.Option("--evidence")] = None,
    tags: Annotated[list[str] | None, typer.Option("--tag")] = None,
) -> None:
    """Explicitly authorize one proposed Decision for future execution."""

    try:
        evidence_references = [
            EvidenceReference.model_validate_json(value) for value in evidence_values or []
        ]
        acceptance = container.decision_acceptance_service().accept(
            decision_id=decision_id,
            accepted_by=accepted_by,
            reason=reason,
            idempotency_key=idempotency_key,
            evidence_references=evidence_references,
            tags=tags,
        )
    except ValidationError as error:
        console.print(f"[red]{error.errors()[0]['msg']}[/red]")
        raise typer.Exit(code=1) from error
    except DecisionAcceptanceDecisionNotFoundError as error:
        console.print(f"[red]Decision not found: {error.decision_id}[/red]")
        raise typer.Exit(code=1) from error
    except DecisionAlreadyAcceptedError as error:
        console.print(
            f"[red]Decision {error.decision_id} is already accepted by acceptance "
            f"{error.acceptance_id}.[/red]"
        )
        raise typer.Exit(code=1) from error
    except DecisionAcceptanceIdempotencyConflictError as error:
        console.print(
            f"[red]Decision acceptance idempotency key {error.idempotency_key!r} already "
            f"exists for Decision {error.decision_id} with a different payload.[/red]"
        )
        raise typer.Exit(code=1) from error

    console.print(f"[green]Decision acceptance stored.[/green] ID: [cyan]{acceptance.id}[/cyan]")


@decision_app.command("acceptance-history")
def decision_acceptance_history(decision_id: UUID) -> None:
    """Show the acceptance history for one Decision."""

    try:
        acceptances = container.decision_acceptance_service().list_for_decision(decision_id)
    except DecisionAcceptanceDecisionNotFoundError as error:
        console.print(f"[red]Decision not found: {error.decision_id}[/red]")
        raise typer.Exit(code=1) from error

    if not acceptances:
        console.print(f"[yellow]No acceptance history found for Decision: {decision_id}[/yellow]")
        return

    table = Table()
    table.add_column("ID")
    table.add_column("Accepted")
    table.add_column("Decision ID")
    table.add_column("Accepted by")
    table.add_column("Reason")
    for acceptance in acceptances:
        table.add_row(
            str(acceptance.id),
            acceptance.accepted_at.isoformat(),
            str(acceptance.decision_id),
            acceptance.accepted_by,
            acceptance.reason,
        )

    console.print(table)


@decision_action_app.command("add")
def add_decision_action(
    decision_id: UUID,
    acceptance_id: Annotated[UUID, typer.Option("--acceptance-id")],
    action_type: Annotated[str, typer.Option("--action-type")],
    summary: Annotated[str, typer.Option("--summary")],
    performed_by: Annotated[str, typer.Option("--performed-by")],
    started_at_value: Annotated[str, typer.Option("--started-at")],
    idempotency_key: Annotated[str, typer.Option("--idempotency-key")],
    completed_at_value: Annotated[str | None, typer.Option("--completed-at")] = None,
    playbook_run_id: Annotated[UUID | None, typer.Option("--playbook-run-id")] = None,
    evidence_values: Annotated[list[str] | None, typer.Option("--evidence")] = None,
    tags: Annotated[list[str] | None, typer.Option("--tag")] = None,
) -> None:
    """Record work performed under an accepted Decision."""

    try:
        started_at = _parse_iso_datetime(started_at_value, "--started-at")
        completed_at = (
            _parse_iso_datetime(completed_at_value, "--completed-at")
            if completed_at_value is not None
            else None
        )
        evidence_references = [
            EvidenceReference.model_validate_json(value) for value in evidence_values or []
        ]
        action = container.decision_action_service().add(
            decision_id=decision_id,
            acceptance_id=acceptance_id,
            action_type=action_type,
            summary=summary,
            performed_by=performed_by,
            started_at=started_at,
            idempotency_key=idempotency_key,
            completed_at=completed_at,
            evidence_references=evidence_references,
            playbook_run_id=playbook_run_id,
            tags=tags,
        )
    except ValidationError as error:
        console.print(f"[red]{error.errors()[0]['msg']}[/red]")
        raise typer.Exit(code=1) from error
    except ValueError as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(code=1) from error
    except DecisionActionDecisionNotFoundError as error:
        console.print(f"[red]Decision not found: {error.decision_id}[/red]")
        raise typer.Exit(code=1) from error
    except DecisionActionAcceptanceNotFoundError as error:
        console.print(f"[red]Decision acceptance not found: {error.acceptance_id}[/red]")
        raise typer.Exit(code=1) from error
    except DecisionActionAcceptanceMismatchError as error:
        console.print(
            f"[red]Decision acceptance {error.acceptance_id} belongs to Decision "
            f"{error.actual_decision_id}, expected {error.expected_decision_id}.[/red]"
        )
        raise typer.Exit(code=1) from error
    except DecisionActionPlaybookRunNotFoundError as error:
        console.print(f"[red]Playbook run not found: {error.playbook_run_id}[/red]")
        raise typer.Exit(code=1) from error
    except (PlaybookRevisionNotFoundError, PlaybookRunRevisionPlaybookMismatchError) as error:
        _exit_playbook_run_revision_error(error)
    except PlaybookRevisionRepositoryError as error:
        _exit_playbook_revision_repository_error(error)
    except DecisionActionIdempotencyConflictError as error:
        console.print(
            f"[red]Decision action idempotency key {error.idempotency_key!r} already "
            f"exists for Decision {error.decision_id} with a different payload.[/red]"
        )
        raise typer.Exit(code=1) from error

    console.print(f"[green]Decision action stored.[/green] ID: [cyan]{action.id}[/cyan]")


@decision_app.command("action-history")
def decision_action_history(decision_id: UUID) -> None:
    """Show recorded actions for one Decision."""

    try:
        actions = container.decision_action_service().list_for_decision(decision_id)
    except DecisionActionDecisionNotFoundError as error:
        console.print(f"[red]Decision not found: {error.decision_id}[/red]")
        raise typer.Exit(code=1) from error

    if not actions:
        console.print(f"[yellow]No action history found for Decision: {decision_id}[/yellow]")
        return

    table = Table()
    table.add_column("ID")
    table.add_column("Recorded")
    table.add_column("Action type")
    table.add_column("Performed by")
    table.add_column("Started")
    table.add_column("Completed")
    table.add_column("Summary")
    for action in actions:
        table.add_row(
            str(action.id),
            action.recorded_at.isoformat(),
            action.action_type,
            action.performed_by,
            action.started_at.isoformat(),
            action.completed_at.isoformat() if action.completed_at is not None else "-",
            action.summary,
        )

    console.print(table)


@decision_app.command("action-show")
def show_decision_action(action_id: UUID) -> None:
    """Show one recorded Decision action."""

    try:
        action = container.decision_action_service().show(action_id)
    except DecisionActionNotFoundError as error:
        console.print(f"[red]Decision action not found: {error.action_id}[/red]")
        raise typer.Exit(code=1) from error

    _print_decision_action(action)


@decision_outcome_app.command("add")
def add_decision_outcome(
    decision_id: UUID,
    acceptance_id: Annotated[UUID, typer.Option("--acceptance-id")],
    action_ids: Annotated[list[UUID], typer.Option("--action-id")],
    result: Annotated[DecisionOutcomeResult, typer.Option("--result")],
    summary: Annotated[str, typer.Option("--summary")],
    validated_by: Annotated[str, typer.Option("--validated-by")],
    validated_at_value: Annotated[str, typer.Option("--validated-at")],
    idempotency_key: Annotated[str, typer.Option("--idempotency-key")],
    evidence_values: Annotated[list[str] | None, typer.Option("--evidence")] = None,
    metric_values: Annotated[list[str] | None, typer.Option("--metric")] = None,
    tags: Annotated[list[str] | None, typer.Option("--tag")] = None,
) -> None:
    """Record a factual result for one or more Decision actions."""

    try:
        validated_at = _parse_iso_datetime(validated_at_value, "--validated-at")
        evidence_references = [
            EvidenceReference.model_validate_json(value) for value in evidence_values or []
        ]
        metrics = _parse_metrics(metric_values or [])
        outcome = container.decision_outcome_service().add(
            decision_id=decision_id,
            acceptance_id=acceptance_id,
            action_ids=action_ids,
            result=result,
            summary=summary,
            validated_by=validated_by,
            validated_at=validated_at,
            idempotency_key=idempotency_key,
            evidence_references=evidence_references,
            metrics=metrics,
            tags=tags,
        )
    except ValidationError as error:
        console.print(f"[red]{error.errors()[0]['msg']}[/red]")
        raise typer.Exit(code=1) from error
    except (ValueError, DecisionOutcomeError) as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(code=1) from error

    console.print(f"[green]Decision outcome stored.[/green] ID: [cyan]{outcome.id}[/cyan]")


@decision_app.command("outcome-history")
def decision_outcome_history(decision_id: UUID) -> None:
    """Show recorded outcomes for one Decision."""

    try:
        outcomes = container.decision_outcome_service().list_for_decision(decision_id)
    except DecisionOutcomeError as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(code=1) from error

    if not outcomes:
        console.print(f"[yellow]No outcome history found for Decision: {decision_id}[/yellow]")
        return

    table = Table()
    table.add_column("ID")
    table.add_column("Validated")
    table.add_column("Result")
    table.add_column("Actions")
    table.add_column("Validated by")
    table.add_column("Summary")
    for outcome in outcomes:
        table.add_row(
            str(outcome.id),
            outcome.validated_at.isoformat(),
            outcome.result.value,
            ", ".join(str(action_id) for action_id in outcome.action_ids),
            outcome.validated_by,
            outcome.summary,
        )
    console.print(table)


@decision_app.command("outcome-show")
def show_decision_outcome(outcome_id: UUID) -> None:
    """Show one recorded Decision outcome."""

    try:
        outcome = container.decision_outcome_service().show(outcome_id)
    except DecisionOutcomeError as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(code=1) from error
    _print_decision_outcome(outcome)


@decision_app.command("outcome-summary")
def show_decision_outcome_summary(decision_id: UUID) -> None:
    """Show the non-persisted outcome summary for one Decision."""

    try:
        summary = container.decision_outcome_service().summary_for_decision(decision_id)
    except DecisionOutcomeError as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(code=1) from error

    console.print(f"Outcome count: {summary.outcome_count}")
    console.print(f"Latest result: {summary.latest_result.value if summary.latest_result else '-'}")
    console.print(
        "Latest validated: "
        f"{summary.latest_validated_at.isoformat() if summary.latest_validated_at else '-'}"
    )
    console.print(f"Linked action count: {summary.linked_action_count}")
    console.print(
        "Results by type: "
        + ", ".join(f"{key}={value}" for key, value in summary.results_by_type.items())
    )
    console.print(f"Has success: {summary.has_success}")
    console.print(f"Has failure: {summary.has_failure}")


@decision_app.command("state")
def show_decision_state(decision_id: UUID) -> None:
    """Show the canonical minimal lifecycle state for one Decision."""

    try:
        state = container.decision_lifecycle_service().state(decision_id)
    except DecisionLifecycleDecisionNotFoundError as error:
        console.print(f"[red]Decision not found: {error.decision_id}[/red]")
        raise typer.Exit(code=1) from error
    except DecisionLifecycleMultipleAcceptancesError as error:
        console.print(f"[red]Decision has multiple acceptance records: {error.decision_id}[/red]")
        raise typer.Exit(code=1) from error
    except DecisionLifecycleActionAcceptanceMismatchError as error:
        expected = (
            str(error.expected_acceptance_id)
            if error.expected_acceptance_id is not None
            else "none"
        )
        console.print(
            f"[red]Decision action {error.action_id} references acceptance "
            f"{error.actual_acceptance_id}, expected {expected}.[/red]"
        )
        raise typer.Exit(code=1) from error
    except DecisionLifecycleError as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(code=1) from error

    console.print(state.value)


@decision_review_app.command("add")
def add_decision_review(
    decision_id: UUID,
    acceptance_id: Annotated[UUID, typer.Option("--acceptance-id")],
    outcome_ids: Annotated[list[UUID], typer.Option("--outcome-id")],
    reviewed_by: Annotated[str, typer.Option("--reviewed-by")],
    reviewed_at_value: Annotated[str, typer.Option("--reviewed-at")],
    assessment: Annotated[DecisionReviewAssessment, typer.Option("--assessment")],
    summary: Annotated[str, typer.Option("--summary")],
    findings: Annotated[list[str], typer.Option("--finding")],
    confidence: Annotated[DecisionReviewConfidence, typer.Option("--confidence")],
    idempotency_key: Annotated[str, typer.Option("--idempotency-key")],
    candidate_lessons: Annotated[list[str] | None, typer.Option("--candidate-lesson")] = None,
    evidence_values: Annotated[list[str] | None, typer.Option("--evidence")] = None,
    tags: Annotated[list[str] | None, typer.Option("--tag")] = None,
) -> None:
    """Record an authorized interpretation of explicit Decision outcomes."""

    try:
        reviewed_at = _parse_iso_datetime(reviewed_at_value, "--reviewed-at")
        evidence_references = [
            EvidenceReference.model_validate_json(value) for value in evidence_values or []
        ]
        review = container.decision_review_service().add(
            decision_id=decision_id,
            acceptance_id=acceptance_id,
            outcome_ids=outcome_ids,
            reviewed_by=reviewed_by,
            reviewed_at=reviewed_at,
            assessment=assessment,
            summary=summary,
            findings=findings,
            confidence=confidence,
            idempotency_key=idempotency_key,
            candidate_lessons=candidate_lessons,
            evidence_references=evidence_references,
            tags=tags,
        )
    except ValidationError as error:
        console.print(f"[red]{error.errors()[0]['msg']}[/red]")
        raise typer.Exit(code=1) from error
    except (ValueError, DecisionReviewError) as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(code=1) from error

    console.print(f"[green]Decision review stored.[/green] ID: [cyan]{review.id}[/cyan]")
    _print_decision_review(review)


@decision_review_app.command("history")
def decision_review_history(decision_id: UUID) -> None:
    """Show authorized review history for one Decision."""

    try:
        reviews = container.decision_review_service().list_for_decision(decision_id)
    except DecisionReviewError as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(code=1) from error

    if not reviews:
        console.print(f"[yellow]No review history found for Decision: {decision_id}[/yellow]")
        return

    table = Table()
    table.add_column("ID")
    table.add_column("Reviewed")
    table.add_column("Reviewed by")
    table.add_column("Assessment")
    table.add_column("Confidence")
    table.add_column("Outcome IDs")
    table.add_column("Summary")
    for review in reviews:
        table.add_row(
            str(review.id),
            review.reviewed_at.isoformat(),
            review.reviewed_by,
            review.assessment.value,
            review.confidence.value,
            ", ".join(str(outcome_id) for outcome_id in review.outcome_ids),
            review.summary,
        )
    console.print(table)


@decision_review_app.command("show")
def show_decision_review(review_id: UUID) -> None:
    """Show one authorized Decision review."""

    try:
        review = container.decision_review_service().show(review_id)
    except DecisionReviewError as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(code=1) from error
    _print_decision_review(review)


@app.command()
def observe(
    content: str,
    tags: Annotated[list[str] | None, typer.Option()] = None,
) -> None:
    """Store a new observation."""

    service = container.observation_service()
    result = service.add(content, tags)

    console.print("[green]Observation stored.[/green]")

    if result.duplicate_ids:
        console.print("[yellow]Warning: exact duplicate observations already exist:[/yellow]")
        for duplicate_id in result.duplicate_ids:
            console.print(f"- {duplicate_id}")


@app.command("list")
def observations() -> None:
    """List all observations."""

    service = container.observation_service()
    observations = service.list_observations()

    if not observations:
        console.print("[yellow]No observations found.[/yellow]")
        return

    for observation in observations:
        _print_observation_summary(observation)
        console.print()


@app.command()
def show(observation_id: UUID) -> None:
    """Show one observation."""

    service = container.observation_service()
    observation = service.get_by_id(observation_id)

    if observation is None:
        console.print(f"[red]Observation not found: {observation_id}[/red]")
        raise typer.Exit(code=1)

    _print_observation(observation)


@app.command()
def search(query: str) -> None:
    """Search observations by content."""

    service = container.observation_service()
    observations = service.search(query)

    if not observations:
        console.print("[yellow]No matching observations found.[/yellow]")
        return

    for observation in observations:
        console.print(f"[cyan]{observation.timestamp}[/cyan]")
        console.print(observation.content)

        if observation.tags:
            console.print(f"[dim]Tags: {', '.join(observation.tags)}[/dim]")

        console.print()


@experience_app.command("add")
def add_experience(
    title: Annotated[str, typer.Option("--title")],
    context: Annotated[str, typer.Option("--context")],
    action: Annotated[str, typer.Option("--action")],
    outcome: Annotated[str, typer.Option("--outcome")],
    result: Annotated[ExperienceResult, typer.Option("--result")],
    observation_ids: Annotated[list[UUID] | None, typer.Option("--observation-id")] = None,
    tags: Annotated[list[str] | None, typer.Option("--tag")] = None,
) -> None:
    """Store a new experience."""

    service = container.experience_service()
    try:
        experience = service.add(
            title=title,
            context=context,
            action=action,
            outcome=outcome,
            result=result,
            observation_ids=observation_ids,
            tags=tags,
        )
    except ObservationNotFoundError as error:
        _exit_observation_not_found(error)

    console.print(f"[green]Experience stored.[/green] ID: [cyan]{experience.id}[/cyan]")


@experience_app.command("from-observation")
def add_experience_from_observation(
    observation_id: UUID,
    title: Annotated[str, typer.Option("--title")],
    action: Annotated[str, typer.Option("--action")],
    outcome: Annotated[str, typer.Option("--outcome")],
    result: Annotated[ExperienceResult, typer.Option("--result")],
    tags: Annotated[list[str] | None, typer.Option("--tag")] = None,
) -> None:
    """Store a new experience from an existing observation."""

    service = container.experience_service()
    try:
        experience = service.add_from_observation(
            observation_id=observation_id,
            title=title,
            action=action,
            outcome=outcome,
            result=result,
            tags=tags,
        )
    except ObservationNotFoundError as error:
        _exit_observation_not_found(error)

    console.print(
        f"[green]Experience stored from observation.[/green] ID: [cyan]{experience.id}[/cyan]"
    )


@experience_app.command("from-review")
def add_experience_from_review(
    review_id: UUID,
    sources: Annotated[
        list[str],
        typer.Option(
            "--source",
            help=(
                "Ordered KIND:ORDINAL selector; KIND is finding or candidate_lesson and "
                "ORDINAL is 1-based."
            ),
        ),
    ],
    promoted_by: Annotated[str, typer.Option("--promoted-by")],
    promotion_reason: Annotated[str, typer.Option("--promotion-reason")],
    idempotency_key: Annotated[str, typer.Option("--idempotency-key")],
    title: Annotated[str, typer.Option("--title")],
    context: Annotated[str, typer.Option("--context")],
    action: Annotated[str, typer.Option("--action")],
    outcome: Annotated[str, typer.Option("--outcome")],
    result: Annotated[ExperienceResult, typer.Option("--result")],
    observation_ids: Annotated[list[UUID] | None, typer.Option("--observation-id")] = None,
    tags: Annotated[list[str] | None, typer.Option("--tag")] = None,
) -> None:
    """Explicitly promote ordered DecisionReview statements into one Experience."""

    try:
        selectors = [_parse_review_promotion_selector(value) for value in sources]
        experience = container.experience_service().add_from_decision_review(
            decision_review_id=review_id,
            source_selectors=selectors,
            promoted_by=promoted_by,
            promotion_reason=promotion_reason,
            idempotency_key=idempotency_key,
            title=title,
            context=context,
            action=action,
            outcome=outcome,
            result=result,
            observation_ids=observation_ids,
            tags=tags,
        )
    except ValidationError as error:
        console.print(f"[red]{error.errors()[0]['msg']}[/red]")
        raise typer.Exit(code=1) from error
    except (ValueError, DecisionReviewError, DecisionReviewPromotionError) as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(code=1) from error
    except ObservationNotFoundError as error:
        _exit_observation_not_found(error)

    console.print(
        f"[green]Experience stored from Decision review.[/green] ID: [cyan]{experience.id}[/cyan]"
    )
    _print_experience(experience)


@experience_app.command("list")
def list_experiences() -> None:
    """List all experiences."""

    service = container.experience_service()
    try:
        experiences = service.list_experiences()
    except (DecisionReviewError, DecisionReviewPromotionError) as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(code=1) from error

    if not experiences:
        console.print("[yellow]No experiences found.[/yellow]")
        return

    for experience in experiences:
        _print_experience_summary(experience)
        console.print()


@observation_app.command("experiences")
def list_observation_experiences(observation_id: UUID) -> None:
    """List experiences linked to one observation."""

    service = container.experience_service()
    try:
        experiences = service.list_for_observation(observation_id)
    except ObservationNotFoundError as error:
        _exit_observation_not_found(error)
    except (DecisionReviewError, DecisionReviewPromotionError) as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(code=1) from error

    if not experiences:
        console.print(f"[yellow]No experiences linked to observation: {observation_id}[/yellow]")
        return

    for experience in experiences:
        _print_experience_summary(experience)
        console.print()


@experience_app.command("knowledge")
def list_experience_knowledge(experience_id: UUID) -> None:
    """List knowledge linked to one experience."""

    service = container.knowledge_service()
    try:
        knowledge_items = service.list_for_experience(experience_id)
    except ExperienceNotFoundError as error:
        _exit_experience_not_found(error)
    except (DecisionReviewError, DecisionReviewPromotionError) as error:
        _exit_decision_review_integrity_error(error)
    except KnowledgeRepositoryError as error:
        _exit_knowledge_repository_error(error)

    if not knowledge_items:
        console.print(f"[yellow]No knowledge linked to experience: {experience_id}[/yellow]")
        return

    for knowledge in knowledge_items:
        _print_knowledge_summary(knowledge)
        console.print()


@experience_app.command("show")
def show_experience(experience_id: UUID) -> None:
    """Show one experience."""

    service = container.experience_service()
    try:
        experience = service.get_by_id(experience_id)
    except (DecisionReviewError, DecisionReviewPromotionError) as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(code=1) from error

    if experience is None:
        console.print(f"[red]Experience not found: {experience_id}[/red]")
        raise typer.Exit(code=1)

    _print_experience(experience)


@knowledge_app.command("add")
def add_knowledge(
    statement: Annotated[str, typer.Option("--statement")],
    rationale: Annotated[str, typer.Option("--rationale")],
    confidence: Annotated[KnowledgeConfidence, typer.Option("--confidence")],
    experience_ids: Annotated[list[UUID] | None, typer.Option("--experience-id")] = None,
    tags: Annotated[list[str] | None, typer.Option("--tag")] = None,
) -> None:
    """Store a new knowledge item."""

    service = container.knowledge_service()
    try:
        knowledge = service.add(
            statement=statement,
            rationale=rationale,
            confidence=confidence,
            experience_ids=experience_ids or [],
            tags=tags,
        )
    except KnowledgeEvidenceRequiredError as error:
        console.print("[red]Knowledge requires at least one experience ID.[/red]")
        raise typer.Exit(code=1) from error
    except ExperienceNotFoundError as error:
        _exit_experience_not_found(error)
    except (DecisionReviewError, DecisionReviewPromotionError) as error:
        _exit_decision_review_integrity_error(error)
    except KnowledgeRepositoryError as error:
        _exit_knowledge_repository_error(error)

    console.print(f"[green]Knowledge stored.[/green] ID: [cyan]{knowledge.id}[/cyan]")


@knowledge_app.command("from-experience")
def add_knowledge_from_experience(
    experience_id: UUID,
    statement: Annotated[str, typer.Option("--statement")],
    rationale: Annotated[str, typer.Option("--rationale")],
    confidence: Annotated[KnowledgeConfidence, typer.Option("--confidence")],
    tags: Annotated[list[str] | None, typer.Option("--tag")] = None,
) -> None:
    """Store a new knowledge item from an existing experience."""

    service = container.knowledge_service()
    try:
        knowledge = service.add_from_experience(
            experience_id=experience_id,
            statement=statement,
            rationale=rationale,
            confidence=confidence,
            tags=tags,
        )
    except ExperienceNotFoundError as error:
        _exit_experience_not_found(error)
    except (DecisionReviewError, DecisionReviewPromotionError) as error:
        _exit_decision_review_integrity_error(error)
    except KnowledgeRepositoryError as error:
        _exit_knowledge_repository_error(error)

    console.print(
        f"[green]Knowledge stored from experience.[/green] ID: [cyan]{knowledge.id}[/cyan]"
    )


@knowledge_app.command("list")
def list_knowledge() -> None:
    """List all knowledge."""

    service = container.knowledge_service()
    try:
        knowledge_items = service.list_knowledge()
    except ExperienceNotFoundError as error:
        _exit_experience_not_found(error)
    except (DecisionReviewError, DecisionReviewPromotionError) as error:
        _exit_decision_review_integrity_error(error)
    except KnowledgeRepositoryError as error:
        _exit_knowledge_repository_error(error)

    if not knowledge_items:
        console.print("[yellow]No knowledge found.[/yellow]")
        return

    for knowledge in knowledge_items:
        _print_knowledge_summary(knowledge)
        console.print()


@knowledge_app.command("playbooks")
def list_knowledge_playbooks(knowledge_id: UUID) -> None:
    """List playbooks linked to one knowledge item."""

    service = container.playbook_service()
    try:
        playbooks = service.list_for_knowledge(knowledge_id)
    except KnowledgeNotFoundError as error:
        _exit_knowledge_not_found(error)
    except KnowledgeRepositoryError as error:
        _exit_knowledge_repository_error(error)

    if not playbooks:
        console.print(f"[yellow]No playbooks linked to knowledge: {knowledge_id}[/yellow]")
        return

    for playbook in playbooks:
        _print_playbook_summary(playbook)
        console.print()


@knowledge_app.command("revisions")
def list_knowledge_revisions(knowledge_id: UUID) -> None:
    """List playbook revisions linked to one knowledge item."""

    service = container.playbook_revision_service()
    try:
        revisions = service.list_for_knowledge(knowledge_id)
    except RevisionKnowledgeNotFoundError as error:
        console.print(f"[red]Knowledge not found: {error.knowledge_id}[/red]")
        raise typer.Exit(code=1) from error
    except KnowledgeRepositoryError as error:
        _exit_knowledge_repository_error(error)
    except PlaybookRevisionRepositoryError as error:
        _exit_playbook_revision_repository_error(error)

    if not revisions:
        console.print(f"[yellow]No playbook revisions linked to knowledge: {knowledge_id}[/yellow]")
        return

    for revision in revisions:
        _print_playbook_revision_summary(revision)
        console.print()


@knowledge_app.command("show")
def show_knowledge(knowledge_id: UUID) -> None:
    """Show one knowledge item."""

    service = container.knowledge_service()
    try:
        knowledge = service.get_by_id(knowledge_id)
    except ExperienceNotFoundError as error:
        _exit_experience_not_found(error)
    except (DecisionReviewError, DecisionReviewPromotionError) as error:
        _exit_decision_review_integrity_error(error)
    except KnowledgeRepositoryError as error:
        _exit_knowledge_repository_error(error)

    if knowledge is None:
        console.print(f"[red]Knowledge not found: {knowledge_id}[/red]")
        raise typer.Exit(code=1)

    _print_knowledge(knowledge)


@evaluation_app.command("add")
def add_evaluation(
    run_id: Annotated[UUID, typer.Option("--run-id")],
    effectiveness: Annotated[PlaybookEffectiveness, typer.Option("--effectiveness")],
    findings: Annotated[list[str] | None, typer.Option("--finding")] = None,
    improvements: Annotated[list[str] | None, typer.Option("--improvement")] = None,
    evidence: Annotated[list[str] | None, typer.Option("--evidence")] = None,
    notes: Annotated[str | None, typer.Option("--notes")] = None,
    tags: Annotated[list[str] | None, typer.Option("--tag")] = None,
) -> None:
    """Record a manual or external playbook evaluation."""

    service = container.playbook_evaluation_service()
    try:
        evaluation = service.add(
            run_id=run_id,
            effectiveness=effectiveness,
            findings=findings or [],
            improvements=improvements,
            evidence=evidence,
            notes=notes,
            tags=tags,
        )
    except PlaybookEvaluationFindingsRequiredError as error:
        console.print("[red]Playbook evaluation requires at least one finding.[/red]")
        raise typer.Exit(code=1) from error
    except PlaybookRunNotFoundError as error:
        _exit_playbook_run_not_found(error)
    except (PlaybookRevisionNotFoundError, PlaybookRunRevisionPlaybookMismatchError) as error:
        _exit_playbook_run_revision_error(error)
    except PlaybookRevisionRepositoryError as error:
        _exit_playbook_revision_repository_error(error)

    console.print(f"[green]Playbook evaluation stored.[/green] ID: [cyan]{evaluation.id}[/cyan]")


@evaluation_app.command("list")
def list_evaluations() -> None:
    """List all playbook evaluations."""

    service = container.playbook_evaluation_service()
    evaluations = service.list_evaluations()

    if not evaluations:
        console.print("[yellow]No playbook evaluations found.[/yellow]")
        return

    for evaluation in evaluations:
        _print_playbook_evaluation_summary(evaluation)
        console.print()


@evaluation_app.command("proposals")
def list_evaluation_proposals(evaluation_id: UUID) -> None:
    """List evolution proposals that reference one playbook evaluation."""

    service = container.evolution_proposal_service()
    try:
        proposals = service.list_for_evaluation(evaluation_id)
    except PlaybookEvaluationNotFoundError as error:
        console.print(f"[red]Playbook evaluation not found: {error.evaluation_id}[/red]")
        raise typer.Exit(code=1) from error

    if not proposals:
        console.print(f"[yellow]No proposals reference evaluation: {evaluation_id}[/yellow]")
        return

    for proposal in proposals:
        _print_evolution_proposal_summary(proposal)
        console.print()


@evaluation_app.command("show")
def show_evaluation(evaluation_id: UUID) -> None:
    """Show one playbook evaluation."""

    service = container.playbook_evaluation_service()
    evaluation = service.get_by_id(evaluation_id)

    if evaluation is None:
        console.print(f"[red]Playbook evaluation not found: {evaluation_id}[/red]")
        raise typer.Exit(code=1)

    _print_playbook_evaluation(evaluation)


@proposal_app.command("add")
def add_proposal(
    playbook_id: Annotated[UUID, typer.Option("--playbook-id")],
    summary: Annotated[str, typer.Option("--summary")],
    rationale: Annotated[str, typer.Option("--rationale")],
    expected_benefits: Annotated[list[str], typer.Option("--benefit")],
    evaluation_ids: Annotated[list[UUID] | None, typer.Option("--evaluation-id")] = None,
    proposed_changes: Annotated[list[str] | None, typer.Option("--change")] = None,
    risks: Annotated[list[str] | None, typer.Option("--risk")] = None,
    status: Annotated[
        EvolutionProposalStatus,
        typer.Option("--status"),
    ] = EvolutionProposalStatus.DRAFT,
    notes: Annotated[str | None, typer.Option("--notes")] = None,
    tags: Annotated[list[str] | None, typer.Option("--tag")] = None,
) -> None:
    """Record a manual or external evolution proposal."""

    service = container.evolution_proposal_service()
    try:
        proposal = service.add(
            playbook_id=playbook_id,
            evaluation_ids=evaluation_ids or [],
            summary=summary,
            rationale=rationale,
            proposed_changes=proposed_changes or [],
            expected_benefits=expected_benefits,
            risks=risks,
            status=status,
            notes=notes,
            tags=tags,
        )
    except EvolutionProposalEvaluationsRequiredError as error:
        console.print("[red]Evolution proposal requires at least one evaluation ID.[/red]")
        raise typer.Exit(code=1) from error
    except EvolutionProposalChangesRequiredError as error:
        console.print("[red]Evolution proposal requires at least one proposed change.[/red]")
        raise typer.Exit(code=1) from error
    except ProposalPlaybookNotFoundError as error:
        console.print(f"[red]Playbook not found: {error.playbook_id}[/red]")
        raise typer.Exit(code=1) from error
    except PlaybookEvaluationNotFoundError as error:
        console.print(f"[red]Playbook evaluation not found: {error.evaluation_id}[/red]")
        raise typer.Exit(code=1) from error
    except EvolutionProposalEvaluationRunNotFoundError as error:
        console.print(
            "[red]Playbook run not found: "
            f"{error.run_id} referenced by evaluation {error.evaluation_id}[/red]"
        )
        raise typer.Exit(code=1) from error
    except EvolutionProposalEvaluationPlaybookMismatchError as error:
        console.print(
            "[red]Playbook evaluation "
            f"{error.evaluation_id} belongs to playbook {error.actual_playbook_id}, "
            f"expected {error.expected_playbook_id}[/red]"
        )
        raise typer.Exit(code=1) from error
    except (PlaybookRevisionNotFoundError, PlaybookRunRevisionPlaybookMismatchError) as error:
        _exit_playbook_run_revision_error(error)
    except PlaybookRevisionRepositoryError as error:
        _exit_playbook_revision_repository_error(error)

    console.print(f"[green]Evolution proposal stored.[/green] ID: [cyan]{proposal.id}[/cyan]")


@proposal_app.command("list")
def list_proposals() -> None:
    """List all evolution proposals."""

    service = container.evolution_proposal_service()
    proposals = service.list_proposals()

    if not proposals:
        console.print("[yellow]No evolution proposals found.[/yellow]")
        return

    for proposal in proposals:
        _print_evolution_proposal_summary(proposal)
        console.print()


@proposal_app.command("status")
def set_proposal_status(
    proposal_id: UUID,
    status: Annotated[EvolutionProposalStatus, typer.Option("--status")],
) -> None:
    """Record a manual or external evolution proposal status decision."""

    service = container.evolution_proposal_service()
    try:
        proposal = service.set_status(proposal_id, status)
    except EvolutionProposalNotFoundError as error:
        console.print(f"[red]Evolution proposal not found: {error.proposal_id}[/red]")
        raise typer.Exit(code=1) from error

    console.print(
        "[green]Evolution proposal status updated.[/green] "
        f"ID: [cyan]{proposal.id}[/cyan] Status: [cyan]{proposal.status.value}[/cyan]"
    )


@proposal_app.command("revisions")
def list_proposal_revisions(proposal_id: UUID) -> None:
    """List playbook revisions linked to one evolution proposal."""

    service = container.playbook_revision_service()
    try:
        revisions = service.list_for_proposal(proposal_id)
    except EvolutionProposalNotFoundError as error:
        console.print(f"[red]Evolution proposal not found: {error.proposal_id}[/red]")
        raise typer.Exit(code=1) from error
    except PlaybookRevisionRepositoryError as error:
        _exit_playbook_revision_repository_error(error)

    if not revisions:
        console.print(f"[yellow]No playbook revisions linked to proposal: {proposal_id}[/yellow]")
        return

    for revision in revisions:
        _print_playbook_revision_summary(revision)
        console.print()


@proposal_app.command("activation-history")
def list_proposal_activation_history(proposal_id: UUID) -> None:
    """List playbook revision lifecycle decisions linked to one evolution proposal."""

    service = container.playbook_revision_activation_service()
    try:
        activations = service.list_for_proposal(proposal_id)
    except PlaybookRevisionActivationProposalNotFoundError as error:
        console.print(f"[red]Evolution proposal not found: {error.proposal_id}[/red]")
        raise typer.Exit(code=1) from error
    except PlaybookRevisionRepositoryError as error:
        _exit_playbook_revision_repository_error(error)

    if not activations:
        console.print(
            f"[yellow]No playbook revision activation records found for proposal: "
            f"{proposal_id}[/yellow]"
        )
        return

    for activation in activations:
        _print_playbook_revision_activation(activation)
        console.print()


@proposal_app.command("show")
def show_proposal(proposal_id: UUID) -> None:
    """Show one evolution proposal."""

    service = container.evolution_proposal_service()
    proposal = service.get_by_id(proposal_id)

    if proposal is None:
        console.print(f"[red]Evolution proposal not found: {proposal_id}[/red]")
        raise typer.Exit(code=1)

    _print_evolution_proposal(proposal)


@revision_app.command("add")
def add_revision(
    playbook_id: Annotated[UUID, typer.Option("--playbook-id")],
    proposal_id: Annotated[UUID, typer.Option("--proposal-id")],
    title: Annotated[str, typer.Option("--title")],
    situation: Annotated[str, typer.Option("--situation")],
    objective: Annotated[str, typer.Option("--objective")],
    steps: Annotated[list[str], typer.Option("--step")],
    success_criteria: Annotated[list[str], typer.Option("--success-criterion")],
    knowledge_ids: Annotated[list[UUID] | None, typer.Option("--knowledge-id")] = None,
    notes: Annotated[str | None, typer.Option("--notes")] = None,
    tags: Annotated[list[str] | None, typer.Option("--tag")] = None,
) -> None:
    """Record a manual or external playbook revision candidate."""

    service = container.playbook_revision_service()
    try:
        revision = service.add(
            playbook_id=playbook_id,
            proposal_id=proposal_id,
            title=title,
            situation=situation,
            objective=objective,
            steps=steps,
            success_criteria=success_criteria,
            knowledge_ids=knowledge_ids or [],
            notes=notes,
            tags=tags,
        )
    except PlaybookRevisionStepsRequiredError as error:
        console.print("[red]Playbook revision requires at least one step.[/red]")
        raise typer.Exit(code=1) from error
    except PlaybookRevisionSuccessCriteriaRequiredError as error:
        console.print("[red]Playbook revision requires at least one success criterion.[/red]")
        raise typer.Exit(code=1) from error
    except EvolutionProposalNotFoundError as error:
        console.print(f"[red]Evolution proposal not found: {error.proposal_id}[/red]")
        raise typer.Exit(code=1) from error
    except PlaybookRevisionProposalNotAcceptedError as error:
        console.print(
            "[red]Evolution proposal "
            f"{error.proposal_id} must be accepted, got {error.actual_status.value}[/red]"
        )
        raise typer.Exit(code=1) from error
    except PlaybookRevisionProposalMismatchError as error:
        console.print(
            "[red]Evolution proposal "
            f"{error.proposal_id} belongs to playbook {error.actual_playbook_id}, "
            f"expected {error.expected_playbook_id}[/red]"
        )
        raise typer.Exit(code=1) from error
    except RevisionPlaybookNotFoundError as error:
        console.print(f"[red]Playbook not found: {error.playbook_id}[/red]")
        raise typer.Exit(code=1) from error
    except RevisionKnowledgeNotFoundError as error:
        console.print(f"[red]Knowledge not found: {error.knowledge_id}[/red]")
        raise typer.Exit(code=1) from error
    except PlaybookRevisionRepositoryError as error:
        _exit_playbook_revision_repository_error(error)

    console.print(f"[green]Playbook revision stored.[/green] ID: [cyan]{revision.id}[/cyan]")


@revision_app.command("list")
def list_revisions() -> None:
    """List all playbook revisions."""

    service = container.playbook_revision_service()
    try:
        revisions = service.list_revisions()
    except PlaybookRevisionRepositoryError as error:
        _exit_playbook_revision_repository_error(error)

    if not revisions:
        console.print("[yellow]No playbook revisions found.[/yellow]")
        return

    for revision in revisions:
        _print_playbook_revision_summary(revision)
        console.print()


@revision_app.command("show")
def show_revision(revision_id: UUID) -> None:
    """Show one playbook revision."""

    service = container.playbook_revision_service()
    try:
        revision = service.get_by_id(revision_id)
    except PlaybookRevisionRepositoryError as error:
        _exit_playbook_revision_repository_error(error)

    if revision is None:
        console.print(f"[red]Playbook revision not found: {revision_id}[/red]")
        raise typer.Exit(code=1)

    _print_playbook_revision(revision)


@revision_app.command("activation-history")
def list_revision_activation_history(revision_id: UUID) -> None:
    """List playbook revision lifecycle decisions linked to one revision."""

    service = container.playbook_revision_activation_service()
    try:
        activations = service.list_for_revision(revision_id)
    except PlaybookRevisionActivationRevisionNotFoundError as error:
        console.print(f"[red]Playbook revision not found: {error.revision_id}[/red]")
        raise typer.Exit(code=1) from error
    except PlaybookRevisionRepositoryError as error:
        _exit_playbook_revision_repository_error(error)

    if not activations:
        console.print(
            f"[yellow]No playbook revision activation records found for revision: "
            f"{revision_id}[/yellow]"
        )
        return

    for activation in activations:
        _print_playbook_revision_activation(activation)
        console.print()


@revision_app.command("runs")
def list_revision_runs(revision_id: UUID) -> None:
    """List runs that explicitly declare one playbook revision."""

    service = container.playbook_run_service()
    try:
        runs = service.list_for_revision(revision_id)
    except (PlaybookRevisionNotFoundError, PlaybookRunRevisionPlaybookMismatchError) as error:
        _exit_playbook_run_revision_error(error)
    except PlaybookRevisionRepositoryError as error:
        _exit_playbook_revision_repository_error(error)

    if not runs:
        console.print(f"[yellow]No playbook runs linked to revision: {revision_id}[/yellow]")
        return

    for run in runs:
        _print_playbook_run_summary(run)
        console.print()


@revision_app.command("activate")
def activate_revision(
    revision_id: UUID,
    playbook_id: Annotated[UUID, typer.Option("--playbook")],
    proposal_id: Annotated[UUID, typer.Option("--proposal")],
    reason: Annotated[str, typer.Option("--reason")],
    decision: Annotated[
        PlaybookRevisionActivationDecision,
        typer.Option("--decision"),
    ] = PlaybookRevisionActivationDecision.ACTIVE,
    previous_revision_id: Annotated[UUID | None, typer.Option("--previous-revision")] = None,
    decided_by: Annotated[str | None, typer.Option("--decided-by")] = None,
    notes: Annotated[str | None, typer.Option("--notes")] = None,
    tags: Annotated[list[str] | None, typer.Option("--tag")] = None,
) -> None:
    """Record an explicit playbook revision lifecycle decision."""

    activation = _record_playbook_revision_activation(
        playbook_id=playbook_id,
        revision_id=revision_id,
        proposal_id=proposal_id,
        decision=decision,
        reason=reason,
        previous_revision_id=previous_revision_id,
        decided_by=decided_by,
        notes=notes,
        tags=tags,
    )

    console.print("[green]Playbook revision activation recorded.[/green]")
    _print_playbook_revision_activation(activation)


@revision_app.command("supersede")
def supersede_revision(
    revision_id: UUID,
    playbook_id: Annotated[UUID, typer.Option("--playbook")],
    proposal_id: Annotated[UUID, typer.Option("--proposal")],
    previous_revision_id: Annotated[UUID, typer.Option("--previous-revision")],
    reason: Annotated[str, typer.Option("--reason")],
    decided_by: Annotated[str | None, typer.Option("--decided-by")] = None,
    notes: Annotated[str | None, typer.Option("--notes")] = None,
    tags: Annotated[list[str] | None, typer.Option("--tag")] = None,
) -> None:
    """Record a supersession lifecycle decision for a playbook revision."""

    activation = _record_playbook_revision_activation(
        playbook_id=playbook_id,
        revision_id=revision_id,
        proposal_id=proposal_id,
        decision=PlaybookRevisionActivationDecision.SUPERSEDED,
        reason=reason,
        previous_revision_id=previous_revision_id,
        decided_by=decided_by,
        notes=notes,
        tags=tags,
    )

    console.print("[green]Playbook revision supersession recorded.[/green]")
    _print_playbook_revision_activation(activation)


@revision_app.command("reject")
def reject_revision(
    revision_id: UUID,
    playbook_id: Annotated[UUID, typer.Option("--playbook")],
    proposal_id: Annotated[UUID, typer.Option("--proposal")],
    reason: Annotated[str, typer.Option("--reason")],
    decided_by: Annotated[str | None, typer.Option("--decided-by")] = None,
    notes: Annotated[str | None, typer.Option("--notes")] = None,
    tags: Annotated[list[str] | None, typer.Option("--tag")] = None,
) -> None:
    """Record a rejection lifecycle decision for a playbook revision."""

    activation = _record_playbook_revision_activation(
        playbook_id=playbook_id,
        revision_id=revision_id,
        proposal_id=proposal_id,
        decision=PlaybookRevisionActivationDecision.REJECTED,
        reason=reason,
        previous_revision_id=None,
        decided_by=decided_by,
        notes=notes,
        tags=tags,
    )

    console.print("[green]Playbook revision rejection recorded.[/green]")
    _print_playbook_revision_activation(activation)


@playbook_app.command("add")
def add_playbook(
    title: Annotated[str, typer.Option("--title")],
    situation: Annotated[str, typer.Option("--situation")],
    objective: Annotated[str, typer.Option("--objective")],
    success_criteria: Annotated[list[str], typer.Option("--success-criterion")],
    steps: Annotated[list[str] | None, typer.Option("--step")] = None,
    knowledge_ids: Annotated[list[UUID] | None, typer.Option("--knowledge-id")] = None,
    constraints: Annotated[list[str] | None, typer.Option("--constraint")] = None,
    tags: Annotated[list[str] | None, typer.Option("--tag")] = None,
) -> None:
    """Store a new playbook."""

    service = container.playbook_service()
    try:
        playbook = service.add(
            title=title,
            situation=situation,
            objective=objective,
            steps=steps or [],
            success_criteria=success_criteria,
            knowledge_ids=knowledge_ids or [],
            constraints=constraints,
            tags=tags,
        )
    except PlaybookKnowledgeRequiredError as error:
        console.print("[red]Playbook requires at least one knowledge ID.[/red]")
        raise typer.Exit(code=1) from error
    except PlaybookStepsRequiredError as error:
        console.print("[red]Playbook requires at least one step.[/red]")
        raise typer.Exit(code=1) from error
    except KnowledgeNotFoundError as error:
        _exit_knowledge_not_found(error)

    console.print(f"[green]Playbook stored.[/green] ID: [cyan]{playbook.id}[/cyan]")


@playbook_app.command("list")
def list_playbooks() -> None:
    """List all playbooks."""

    service = container.playbook_service()
    playbooks = service.list_playbooks()

    if not playbooks:
        console.print("[yellow]No playbooks found.[/yellow]")
        return

    for playbook in playbooks:
        _print_playbook_summary(playbook)
        console.print()


@playbook_app.command("runs")
def list_playbook_runs(playbook_id: UUID) -> None:
    """List playbook runs linked to one playbook."""

    service = container.playbook_run_service()
    try:
        runs = service.list_for_playbook(playbook_id)
    except PlaybookNotFoundError as error:
        _exit_playbook_not_found(error)
    except (PlaybookRevisionNotFoundError, PlaybookRunRevisionPlaybookMismatchError) as error:
        _exit_playbook_run_revision_error(error)
    except PlaybookRevisionRepositoryError as error:
        _exit_playbook_revision_repository_error(error)

    if not runs:
        console.print(f"[yellow]No playbook runs linked to playbook: {playbook_id}[/yellow]")
        return

    for run in runs:
        _print_playbook_run_summary(run)
        console.print()


@playbook_app.command("proposals")
def list_playbook_proposals(playbook_id: UUID) -> None:
    """List evolution proposals linked to one playbook."""

    service = container.evolution_proposal_service()
    try:
        proposals = service.list_for_playbook(playbook_id)
    except ProposalPlaybookNotFoundError as error:
        console.print(f"[red]Playbook not found: {error.playbook_id}[/red]")
        raise typer.Exit(code=1) from error

    if not proposals:
        console.print(f"[yellow]No evolution proposals linked to playbook: {playbook_id}[/yellow]")
        return

    for proposal in proposals:
        _print_evolution_proposal_summary(proposal)
        console.print()


@playbook_app.command("revisions")
def list_playbook_revisions(playbook_id: UUID) -> None:
    """List playbook revisions linked to one playbook."""

    service = container.playbook_revision_service()
    try:
        revisions = service.list_for_playbook(playbook_id)
    except RevisionPlaybookNotFoundError as error:
        console.print(f"[red]Playbook not found: {error.playbook_id}[/red]")
        raise typer.Exit(code=1) from error
    except PlaybookRevisionRepositoryError as error:
        _exit_playbook_revision_repository_error(error)

    if not revisions:
        console.print(f"[yellow]No playbook revisions linked to playbook: {playbook_id}[/yellow]")
        return

    for revision in revisions:
        _print_playbook_revision_summary(revision)
        console.print()


@playbook_app.command("revision-history")
def list_playbook_revision_history(playbook_id: UUID) -> None:
    """List playbook revision lifecycle decisions for one playbook."""

    service = container.playbook_revision_activation_service()
    try:
        activations = service.list_for_playbook(playbook_id)
    except PlaybookRevisionActivationPlaybookNotFoundError as error:
        _exit_revision_activation_playbook_not_found(error)
    except PlaybookRevisionRepositoryError as error:
        _exit_playbook_revision_repository_error(error)

    if not activations:
        console.print(
            f"[yellow]No playbook revision lifecycle records linked to playbook: "
            f"{playbook_id}[/yellow]"
        )
        return

    for activation in activations:
        _print_playbook_revision_activation(activation)
        console.print()


@playbook_app.command("active-revision")
def show_playbook_active_revision(playbook_id: UUID) -> None:
    """Show the current active playbook revision for one playbook."""

    service = container.playbook_revision_activation_service()
    try:
        revision = service.get_active_revision_for_playbook(playbook_id)
    except PlaybookRevisionActivationPlaybookNotFoundError as error:
        _exit_revision_activation_playbook_not_found(error)
    except PlaybookRevisionActivationRevisionNotFoundError as error:
        console.print(f"[red]Playbook revision not found: {error.revision_id}[/red]")
        raise typer.Exit(code=1) from error
    except PlaybookRevisionActivationRevisionPlaybookMismatchError as error:
        console.print(
            "[red]Playbook revision "
            f"{error.revision_id} belongs to playbook {error.actual_playbook_id}, "
            f"expected {error.expected_playbook_id}[/red]"
        )
        raise typer.Exit(code=1) from error
    except PlaybookRevisionRepositoryError as error:
        _exit_playbook_revision_repository_error(error)

    if revision is None:
        console.print(f"[yellow]No active playbook revision for playbook: {playbook_id}[/yellow]")
        return

    _print_playbook_revision(revision)


@playbook_app.command("show")
def show_playbook(playbook_id: UUID) -> None:
    """Show one playbook."""

    service = container.playbook_service()
    playbook = service.get_by_id(playbook_id)

    if playbook is None:
        console.print(f"[red]Playbook not found: {playbook_id}[/red]")
        raise typer.Exit(code=1)

    _print_playbook(playbook)


def _parse_bool_option(value: str) -> bool:
    normalized = value.lower()

    if normalized == "true":
        return True

    if normalized == "false":
        return False

    raise typer.BadParameter("Expected true or false.")


@run_app.command("add")
def add_run(
    playbook_id: Annotated[UUID, typer.Option("--playbook-id")],
    situation: Annotated[str, typer.Option("--situation")],
    outcome: Annotated[str, typer.Option("--outcome")],
    success: Annotated[object, typer.Option("--success", parser=_parse_bool_option)],
    actions_taken: Annotated[list[str] | None, typer.Option("--action")] = None,
    evidence: Annotated[list[str] | None, typer.Option("--evidence")] = None,
    notes: Annotated[str | None, typer.Option("--notes")] = None,
    tags: Annotated[list[str] | None, typer.Option("--tag")] = None,
    revision_id: Annotated[UUID | None, typer.Option("--revision-id")] = None,
) -> None:
    """Record a manually or externally applied playbook run."""

    service = container.playbook_run_service()
    try:
        run = service.add(
            playbook_id=playbook_id,
            situation=situation,
            actions_taken=actions_taken or [],
            outcome=outcome,
            success=cast(bool, success),
            evidence=evidence,
            notes=notes,
            tags=tags,
            revision_id=revision_id,
        )
    except PlaybookRunActionsRequiredError as error:
        console.print("[red]Playbook run requires at least one action taken.[/red]")
        raise typer.Exit(code=1) from error
    except PlaybookNotFoundError as error:
        _exit_playbook_not_found(error)
    except (PlaybookRevisionNotFoundError, PlaybookRunRevisionPlaybookMismatchError) as error:
        _exit_playbook_run_revision_error(error)
    except PlaybookRevisionRepositoryError as error:
        _exit_playbook_revision_repository_error(error)

    console.print(f"[green]Playbook run stored.[/green] ID: [cyan]{run.id}[/cyan]")


@run_app.command("list")
def list_runs() -> None:
    """List all playbook runs."""

    service = container.playbook_run_service()
    try:
        runs = service.list_runs()
    except (PlaybookRevisionNotFoundError, PlaybookRunRevisionPlaybookMismatchError) as error:
        _exit_playbook_run_revision_error(error)
    except PlaybookRevisionRepositoryError as error:
        _exit_playbook_revision_repository_error(error)

    if not runs:
        console.print("[yellow]No playbook runs found.[/yellow]")
        return

    for run in runs:
        _print_playbook_run_summary(run)
        console.print()


@run_app.command("evaluations")
def list_run_evaluations(run_id: UUID) -> None:
    """List playbook evaluations linked to one playbook run."""

    service = container.playbook_evaluation_service()
    try:
        evaluations = service.list_for_run(run_id)
    except PlaybookRunNotFoundError as error:
        _exit_playbook_run_not_found(error)
    except (PlaybookRevisionNotFoundError, PlaybookRunRevisionPlaybookMismatchError) as error:
        _exit_playbook_run_revision_error(error)
    except PlaybookRevisionRepositoryError as error:
        _exit_playbook_revision_repository_error(error)

    if not evaluations:
        console.print(f"[yellow]No playbook evaluations linked to run: {run_id}[/yellow]")
        return

    for evaluation in evaluations:
        _print_playbook_evaluation_summary(evaluation)
        console.print()


@run_app.command("show")
def show_run(run_id: UUID) -> None:
    """Show one playbook run."""

    service = container.playbook_run_service()
    try:
        run = service.get_by_id(run_id)
    except (PlaybookRevisionNotFoundError, PlaybookRunRevisionPlaybookMismatchError) as error:
        _exit_playbook_run_revision_error(error)
    except PlaybookRevisionRepositoryError as error:
        _exit_playbook_revision_repository_error(error)

    if run is None:
        console.print(f"[red]Playbook run not found: {run_id}[/red]")
        raise typer.Exit(code=1)

    _print_playbook_run(run)


def _print_experience(experience: Experience) -> None:
    console.print(f"ID: {experience.id}")
    console.print(f"Timestamp: {experience.timestamp}")
    console.print(f"Title: {experience.title}")
    console.print(f"Context: {experience.context}")
    console.print(f"Action: {experience.action}")
    console.print(f"Outcome: {experience.outcome}")
    console.print(f"Result: {experience.result.value}")
    console.print(
        "Observation IDs: "
        + (
            ", ".join(str(observation_id) for observation_id in experience.observation_ids)
            if experience.observation_ids
            else "-"
        )
    )
    console.print(f"Tags: {', '.join(experience.tags) if experience.tags else '-'}")
    _print_decision_review_promotion(experience)


def _print_decision(decision: Decision) -> None:
    console.print(f"ID: {decision.id}")
    console.print(f"Created: {decision.created_at}")
    console.print(f"Project: {decision.project_key}")
    console.print(f"Title: {decision.title}")
    console.print(f"Objective: {decision.objective}")
    console.print(f"Context summary: {decision.context_summary}")
    _print_repeated_field("Alternatives", list(decision.alternatives))
    console.print(f"Proposed option: {decision.proposed_option}")
    console.print(f"Rationale: {decision.rationale}")
    _print_repeated_field(
        "Observation IDs",
        [str(observation_id) for observation_id in decision.observation_ids],
    )
    _print_repeated_field(
        "Evidence references",
        [_format_evidence_reference(evidence) for evidence in decision.evidence_references],
    )
    console.print(f"Proposed by: {decision.proposed_by}")
    console.print(
        "Supersedes Decision ID: "
        f"{decision.supersedes_decision_id if decision.supersedes_decision_id is not None else '-'}"
    )
    console.print(f"Idempotency key: {decision.idempotency_key}")
    console.print(f"Tags: {', '.join(decision.tags) if decision.tags else '-'}")


def _print_decision_action(action: DecisionAction) -> None:
    console.print(f"ID: {action.id}")
    console.print(f"Recorded: {action.recorded_at}")
    console.print(f"Decision ID: {action.decision_id}")
    console.print(f"Acceptance ID: {action.acceptance_id}")
    console.print(f"Action type: {action.action_type}")
    console.print(f"Summary: {action.summary}")
    console.print(f"Performed by: {action.performed_by}")
    console.print(f"Started: {action.started_at}")
    console.print(f"Completed: {action.completed_at if action.completed_at is not None else '-'}")
    _print_repeated_field(
        "Evidence references",
        [_format_evidence_reference(evidence) for evidence in action.evidence_references],
    )
    console.print(
        f"Playbook run ID: {action.playbook_run_id if action.playbook_run_id is not None else '-'}"
    )
    console.print(f"Idempotency key: {action.idempotency_key}")
    console.print(f"Tags: {', '.join(action.tags) if action.tags else '-'}")


def _print_decision_outcome(outcome: DecisionOutcome) -> None:
    console.print(f"ID: {outcome.id}")
    console.print(f"Recorded: {outcome.recorded_at}")
    console.print(f"Decision ID: {outcome.decision_id}")
    console.print(f"Acceptance ID: {outcome.acceptance_id}")
    _print_repeated_field("Action IDs", [str(action_id) for action_id in outcome.action_ids])
    console.print(f"Result: {outcome.result.value}")
    console.print(f"Summary: {outcome.summary}")
    console.print(f"Validated by: {outcome.validated_by}")
    console.print(f"Validated at: {outcome.validated_at}")
    _print_repeated_field(
        "Evidence references",
        [_format_evidence_reference(evidence) for evidence in outcome.evidence_references],
    )
    console.print(
        "Metrics: "
        + (
            ", ".join(f"{key}={value!r}" for key, value in outcome.metrics.items())
            if outcome.metrics
            else "-"
        )
    )
    console.print(f"Idempotency key: {outcome.idempotency_key}")
    console.print(f"Tags: {', '.join(outcome.tags) if outcome.tags else '-'}")


def _print_decision_review(review: DecisionReview) -> None:
    console.print(f"ID: {review.id}")
    console.print(f"Recorded: {review.recorded_at}")
    console.print(f"Decision ID: {review.decision_id}")
    console.print(f"Acceptance ID: {review.acceptance_id}")
    _print_repeated_field("Outcome IDs", [str(outcome_id) for outcome_id in review.outcome_ids])
    console.print(f"Reviewed by: {review.reviewed_by}")
    console.print(f"Reviewed at: {review.reviewed_at}")
    console.print(f"Assessment: {review.assessment.value}")
    console.print(f"Summary: {review.summary}")
    _print_repeated_field("Findings", list(review.findings))
    _print_repeated_field("Candidate lessons", list(review.candidate_lessons))
    _print_repeated_field(
        "Evidence references",
        [_format_evidence_reference(evidence) for evidence in review.evidence_references],
    )
    console.print(f"Confidence: {review.confidence.value}")
    console.print(f"Idempotency key: {review.idempotency_key}")
    console.print(f"Tags: {', '.join(review.tags) if review.tags else '-'}")


def _format_evidence_reference(evidence: EvidenceReference) -> str:
    return (
        f"kind={evidence.kind}; locator={evidence.locator}; "
        f"repository/project={evidence.repository_or_project or '-'}; "
        f"hash={evidence.content_hash or '-'}; captured={evidence.captured_at.isoformat()}; "
        f"source={evidence.source or '-'}; summary={evidence.summary or '-'}"
    )


def _parse_iso_datetime(value: str, option_name: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"Invalid ISO-8601 value for {option_name}: {value!r}.") from error


def _parse_review_promotion_selector(value: str) -> DecisionReviewPromotionSelector:
    kind_value, separator, ordinal_value = value.partition(":")
    if not separator:
        raise ValueError(
            f"Invalid source selector {value!r}; expected KIND:ORDINAL with a 1-based ordinal."
        )
    try:
        kind = DecisionReviewPromotionSourceKind(kind_value)
    except ValueError as error:
        raise ValueError(
            f"Invalid source selector kind {kind_value!r}; expected finding or candidate_lesson."
        ) from error
    try:
        ordinal = int(ordinal_value)
    except ValueError as error:
        raise ValueError(
            f"Invalid source selector ordinal {ordinal_value!r}; expected a positive integer."
        ) from error
    if ordinal < 1:
        raise ValueError(
            "Decision review source selector ordinals are 1-based and must be positive."
        )
    return DecisionReviewPromotionSelector(kind=kind, index=ordinal - 1)


def _parse_metrics(values: list[str]) -> dict[str, DecisionOutcomeMetricValue]:
    metrics: dict[str, DecisionOutcomeMetricValue] = {}
    semantic_keys: set[str] = set()
    for entry in values:
        if "=" not in entry:
            raise ValueError(f"Invalid metric {entry!r}; expected KEY=VALUE.")
        key, raw_value = entry.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"Invalid metric {entry!r}; key must not be blank.")
        semantic_key = key.casefold()
        if semantic_key in semantic_keys:
            raise ValueError(f"Duplicate metric key: {key}")
        semantic_keys.add(semantic_key)
        metrics[key] = _parse_metric_value(raw_value.strip())
    return metrics


def _parse_metric_value(value: str) -> DecisionOutcomeMetricValue:
    lowered = value.casefold()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if re.fullmatch(r"[+-]?\d+", value):
        return int(value)
    if "." in value or "e" in lowered:
        try:
            number = float(value)
        except ValueError:
            pass
        else:
            if isfinite(number):
                return number
    return value


def _print_experience_summary(experience: Experience) -> None:
    console.print(f"ID: {experience.id}")
    console.print(f"Timestamp: {experience.timestamp}")
    console.print(f"Title: {experience.title}")
    console.print(f"Result: {experience.result.value}")
    promotion = experience.decision_review_promotion
    if promotion is not None:
        console.print(f"Decision review promotion: {promotion.decision_review_id}")


def _print_decision_review_promotion(experience: Experience) -> None:
    promotion = experience.decision_review_promotion
    if promotion is None:
        console.print("Decision review promotion: -")
        return
    console.print(f"Decision review promotion: {promotion.decision_review_id}")
    console.print(f"Promoted by: {promotion.promoted_by}")
    console.print(f"Promotion reason: {promotion.promotion_reason}")
    console.print(f"Promotion idempotency key: {promotion.idempotency_key}")
    _print_repeated_field(
        "Promotion source statements",
        [
            f"{statement.kind.value}:{statement.index + 1} (stored index {statement.index}) "
            f"{statement.text}"
            for statement in promotion.source_statements
        ],
    )


def _print_knowledge(knowledge: Knowledge) -> None:
    console.print(f"ID: {knowledge.id}")
    console.print(f"Timestamp: {knowledge.timestamp}")
    console.print(f"Statement: {knowledge.statement}")
    console.print(f"Rationale: {knowledge.rationale}")
    console.print(f"Confidence: {knowledge.confidence.value}")
    console.print(
        "Experience IDs: "
        + (
            ", ".join(str(experience_id) for experience_id in knowledge.experience_ids)
            if knowledge.experience_ids
            else "-"
        )
    )
    console.print(f"Tags: {', '.join(knowledge.tags) if knowledge.tags else '-'}")


def _print_knowledge_summary(knowledge: Knowledge) -> None:
    console.print(f"ID: {knowledge.id}")
    console.print(f"Timestamp: {knowledge.timestamp}")
    console.print(f"Statement: {knowledge.statement}")
    console.print(f"Confidence: {knowledge.confidence.value}")


def _print_playbook(playbook: Playbook) -> None:
    console.print(f"ID: {playbook.id}")
    console.print(f"Timestamp: {playbook.timestamp}")
    console.print(f"Title: {playbook.title}")
    console.print(f"Situation: {playbook.situation}")
    console.print(f"Objective: {playbook.objective}")
    _print_repeated_field("Steps", playbook.steps)
    _print_repeated_field("Success criteria", playbook.success_criteria)
    _print_repeated_field("Constraints", playbook.constraints)
    _print_repeated_field(
        "Knowledge IDs",
        [str(knowledge_id) for knowledge_id in playbook.knowledge_ids],
    )
    console.print(f"Tags: {', '.join(playbook.tags) if playbook.tags else '-'}")


def _print_playbook_summary(playbook: Playbook) -> None:
    console.print(f"ID: {playbook.id}")
    console.print(f"Timestamp: {playbook.timestamp}")
    console.print(f"Title: {playbook.title}")
    console.print(f"Objective: {playbook.objective}")


def _print_playbook_run(run: PlaybookRun) -> None:
    console.print(f"ID: {run.id}")
    console.print(f"Timestamp: {run.timestamp}")
    console.print(f"Playbook ID: {run.playbook_id}")
    console.print(f"Revision ID: {run.revision_id if run.revision_id is not None else '-'}")
    console.print(f"Situation: {run.situation}")
    _print_repeated_field("Actions taken", run.actions_taken)
    console.print(f"Outcome: {run.outcome}")
    console.print(f"Success: {str(run.success).lower()}")
    _print_repeated_field("Evidence", run.evidence)
    console.print(f"Notes: {run.notes if run.notes is not None else '-'}")
    console.print(f"Tags: {', '.join(run.tags) if run.tags else '-'}")


def _print_playbook_run_summary(run: PlaybookRun) -> None:
    console.print(f"ID: {run.id}")
    console.print(f"Timestamp: {run.timestamp}")
    console.print(f"Playbook ID: {run.playbook_id}")
    console.print(f"Revision ID: {run.revision_id if run.revision_id is not None else '-'}")
    console.print(f"Situation: {run.situation}")
    console.print(f"Success: {str(run.success).lower()}")


def _print_playbook_evaluation(evaluation: PlaybookEvaluation) -> None:
    console.print(f"ID: {evaluation.id}")
    console.print(f"Timestamp: {evaluation.timestamp}")
    console.print(f"Run ID: {evaluation.run_id}")
    console.print(f"Effectiveness: {evaluation.effectiveness.value}")
    _print_repeated_field("Findings", evaluation.findings)
    _print_repeated_field("Improvements", evaluation.improvements)
    _print_repeated_field("Evidence", evaluation.evidence)
    console.print(f"Notes: {evaluation.notes if evaluation.notes is not None else '-'}")
    console.print(f"Tags: {', '.join(evaluation.tags) if evaluation.tags else '-'}")


def _print_playbook_evaluation_summary(evaluation: PlaybookEvaluation) -> None:
    console.print(f"ID: {evaluation.id}")
    console.print(f"Timestamp: {evaluation.timestamp}")
    console.print(f"Run ID: {evaluation.run_id}")
    console.print(f"Effectiveness: {evaluation.effectiveness.value}")


def _print_playbook_revision(revision: PlaybookRevision) -> None:
    console.print(f"ID: {revision.id}")
    console.print(f"Timestamp: {revision.timestamp}")
    console.print(f"Playbook ID: {revision.playbook_id}")
    console.print(f"Proposal ID: {revision.proposal_id}")
    console.print(f"Title: {revision.title}")
    console.print(f"Situation: {revision.situation}")
    console.print(f"Objective: {revision.objective}")
    _print_repeated_field("Steps", revision.steps)
    _print_repeated_field("Success criteria", revision.success_criteria)
    _print_repeated_field(
        "Knowledge IDs",
        [str(knowledge_id) for knowledge_id in revision.knowledge_ids],
    )
    console.print(f"Notes: {revision.notes if revision.notes is not None else '-'}")
    console.print(f"Tags: {', '.join(revision.tags) if revision.tags else '-'}")


def _print_playbook_revision_summary(revision: PlaybookRevision) -> None:
    console.print(f"ID: {revision.id}")
    console.print(f"Timestamp: {revision.timestamp}")
    console.print(f"Playbook ID: {revision.playbook_id}")
    console.print(f"Proposal ID: {revision.proposal_id}")
    console.print(f"Title: {revision.title}")


def _print_playbook_revision_activation(activation: PlaybookRevisionActivation) -> None:
    console.print(f"ID: {activation.id}")
    console.print(f"Timestamp: {activation.timestamp}")
    console.print(f"Playbook ID: {activation.playbook_id}")
    console.print(f"Revision ID: {activation.revision_id}")
    console.print(f"Proposal ID: {activation.proposal_id}")
    console.print(f"Decision: {activation.decision.value}")
    console.print(
        "Previous revision ID: "
        f"{activation.previous_revision_id if activation.previous_revision_id is not None else '-'}"
    )
    console.print(f"Reason: {activation.reason}")
    console.print(
        f"Decided by: {activation.decided_by if activation.decided_by is not None else '-'}"
    )
    console.print(f"Notes: {activation.notes if activation.notes is not None else '-'}")
    console.print(f"Tags: {', '.join(activation.tags) if activation.tags else '-'}")


def _record_playbook_revision_activation(
    playbook_id: UUID,
    revision_id: UUID,
    proposal_id: UUID,
    decision: PlaybookRevisionActivationDecision,
    reason: str,
    previous_revision_id: UUID | None = None,
    decided_by: str | None = None,
    notes: str | None = None,
    tags: list[str] | None = None,
) -> PlaybookRevisionActivation:
    service = container.playbook_revision_activation_service()
    try:
        return service.add(
            playbook_id=playbook_id,
            revision_id=revision_id,
            proposal_id=proposal_id,
            decision=decision,
            reason=reason,
            previous_revision_id=previous_revision_id,
            decided_by=decided_by,
            notes=notes,
            tags=tags,
        )
    except PlaybookRevisionActivationPlaybookNotFoundError as error:
        _exit_revision_activation_playbook_not_found(error)
    except PlaybookRevisionActivationRevisionNotFoundError as error:
        console.print(f"[red]Playbook revision not found: {error.revision_id}[/red]")
        raise typer.Exit(code=1) from error
    except PlaybookRevisionActivationProposalNotFoundError as error:
        console.print(f"[red]Evolution proposal not found: {error.proposal_id}[/red]")
        raise typer.Exit(code=1) from error
    except PlaybookRevisionActivationRevisionPlaybookMismatchError as error:
        console.print(
            "[red]Playbook revision "
            f"{error.revision_id} belongs to playbook {error.actual_playbook_id}, "
            f"expected {error.expected_playbook_id}[/red]"
        )
        raise typer.Exit(code=1) from error
    except PlaybookRevisionActivationRevisionProposalMismatchError as error:
        console.print(
            "[red]Playbook revision "
            f"{error.revision_id} belongs to proposal {error.actual_proposal_id}, "
            f"expected {error.expected_proposal_id}[/red]"
        )
        raise typer.Exit(code=1) from error
    except PlaybookRevisionActivationPreviousRevisionRequiredError as error:
        console.print("[red]Superseded revision activation requires a previous revision ID.[/red]")
        raise typer.Exit(code=1) from error
    except PlaybookRevisionActivationPreviousRevisionNotFoundError as error:
        console.print(
            f"[red]Previous playbook revision not found: {error.previous_revision_id}[/red]"
        )
        raise typer.Exit(code=1) from error
    except PlaybookRevisionActivationPreviousRevisionPlaybookMismatchError as error:
        console.print(
            "[red]Previous playbook revision "
            f"{error.previous_revision_id} belongs to playbook {error.actual_playbook_id}, "
            f"expected {error.expected_playbook_id}[/red]"
        )
        raise typer.Exit(code=1) from error
    except PlaybookRevisionActivationPreviousRevisionForbiddenError as error:
        console.print(
            "[red]Rejected revision activation must not reference previous revision "
            f"{error.previous_revision_id}.[/red]"
        )
        raise typer.Exit(code=1) from error
    except ValidationError as error:
        console.print(f"[red]{error.errors()[0]['msg']}[/red]")
        raise typer.Exit(code=1) from error
    except PlaybookRevisionRepositoryError as error:
        _exit_playbook_revision_repository_error(error)

    raise AssertionError("Unreachable playbook revision activation error path")


def _print_evolution_proposal(proposal: EvolutionProposal) -> None:
    console.print(f"ID: {proposal.id}")
    console.print(f"Timestamp: {proposal.timestamp}")
    console.print(f"Playbook ID: {proposal.playbook_id}")
    _print_repeated_field(
        "Evaluation IDs",
        [str(evaluation_id) for evaluation_id in proposal.evaluation_ids],
    )
    console.print(f"Summary: {proposal.summary}")
    console.print(f"Rationale: {proposal.rationale}")
    _print_repeated_field("Proposed changes", proposal.proposed_changes)
    _print_repeated_field("Expected benefits", proposal.expected_benefits)
    _print_repeated_field("Risks", proposal.risks)
    console.print(f"Status: {proposal.status.value}")
    console.print(f"Notes: {proposal.notes if proposal.notes is not None else '-'}")
    console.print(f"Tags: {', '.join(proposal.tags) if proposal.tags else '-'}")


def _print_evolution_proposal_summary(proposal: EvolutionProposal) -> None:
    console.print(f"ID: {proposal.id}")
    console.print(f"Timestamp: {proposal.timestamp}")
    console.print(f"Playbook ID: {proposal.playbook_id}")
    console.print(f"Summary: {proposal.summary}")
    console.print(f"Status: {proposal.status.value}")


def _print_observation_summary(observation: Observation) -> None:
    console.print(f"ID: {observation.id}")
    console.print(f"Timestamp: {observation.timestamp}")
    console.print(f"Content: {observation.content}")
    console.print(f"Tags: {', '.join(observation.tags) if observation.tags else '-'}")


def _print_observation(observation: Observation) -> None:
    console.print(f"ID: {observation.id}")
    console.print(f"Timestamp: {observation.timestamp}")
    console.print(f"Source: {observation.source}")
    console.print(f"Content: {observation.content}")
    console.print(f"Tags: {', '.join(observation.tags) if observation.tags else '-'}")


def _exit_observation_not_found(error: ObservationNotFoundError) -> None:
    console.print(f"[red]Observation not found: {error.observation_id}[/red]")
    raise typer.Exit(code=1) from error


def _exit_experience_not_found(error: ExperienceNotFoundError) -> None:
    console.print(f"[red]Experience not found: {error.experience_id}[/red]")
    raise typer.Exit(code=1) from error


def _exit_knowledge_not_found(error: KnowledgeNotFoundError) -> None:
    console.print(f"[red]Knowledge not found: {error.knowledge_id}[/red]")
    raise typer.Exit(code=1) from error


def _exit_knowledge_repository_error(error: KnowledgeRepositoryError) -> None:
    console.print(f"[red]{error}[/red]")
    raise typer.Exit(code=1) from error


def _exit_playbook_revision_repository_error(
    error: PlaybookRevisionRepositoryError,
) -> None:
    console.print(f"[red]{error}[/red]")
    raise typer.Exit(code=1) from error


def _exit_decision_review_integrity_error(
    error: DecisionReviewError | DecisionReviewPromotionError,
) -> None:
    console.print(f"[red]{error}[/red]")
    raise typer.Exit(code=1) from error


def _exit_playbook_not_found(error: PlaybookNotFoundError) -> None:
    console.print(f"[red]Playbook not found: {error.playbook_id}[/red]")
    raise typer.Exit(code=1) from error


def _exit_playbook_run_not_found(error: PlaybookRunNotFoundError) -> None:
    console.print(f"[red]Playbook run not found: {error.run_id}[/red]")
    raise typer.Exit(code=1) from error


def _exit_playbook_run_revision_error(
    error: PlaybookRevisionNotFoundError | PlaybookRunRevisionPlaybookMismatchError,
) -> None:
    console.print(f"[red]{error}[/red]")
    raise typer.Exit(code=1) from error


def _exit_revision_activation_playbook_not_found(
    error: PlaybookRevisionActivationPlaybookNotFoundError,
) -> None:
    console.print(f"[red]Playbook not found: {error.playbook_id}[/red]")
    raise typer.Exit(code=1) from error


def _development_evidence_candidate(
    repository_root: str,
    prompt_path: str,
    review_path: str,
    commit_sha: str,
    records_json: str,
) -> DevelopmentEvidenceCandidate:
    try:
        records = DevelopmentEvidenceRecordInput.model_validate_json(records_json)
        return container.development_evidence_service().preview(
            DevelopmentEvidenceRequest(
                repository_root=repository_root,
                prompt_path=prompt_path,
                review_path=review_path,
                commit_sha=commit_sha,
            ),
            records,
        )
    except ValidationError as error:
        console.print(f"[red]{error.errors()[0]['msg']}[/red]")
        raise typer.Exit(code=1) from error
    except (DevelopmentEvidenceError, LocalDevelopmentEvidenceSourceError) as error:
        _exit_development_evidence_error(error)

    raise AssertionError("Unreachable development evidence error path")


def _exit_development_evidence_error(
    error: DevelopmentEvidenceError | LocalDevelopmentEvidenceSourceError,
) -> None:
    console.print(f"[red]{error}[/red]")
    raise typer.Exit(code=1) from error


def _print_repeated_field(label: str, values: list[str]) -> None:
    console.print(f"{label}:")

    if not values:
        console.print("-")
        return

    for value in values:
        console.print(f"- {value}")

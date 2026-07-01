from typing import Annotated, cast
from uuid import UUID

import typer
from rich.console import Console
from rich.panel import Panel

from neural_engine import APP_NAME, MISSION, __version__
from neural_engine.application.container import Container
from neural_engine.application.evolution_proposal_service import (
    EvolutionProposalChangesRequiredError,
    EvolutionProposalEvaluationPlaybookMismatchError,
    EvolutionProposalEvaluationRunNotFoundError,
    EvolutionProposalEvaluationsRequiredError,
    PlaybookEvaluationNotFoundError,
)
from neural_engine.application.evolution_proposal_service import (
    PlaybookNotFoundError as ProposalPlaybookNotFoundError,
)
from neural_engine.application.experience_service import ObservationNotFoundError
from neural_engine.application.knowledge_service import (
    ExperienceNotFoundError,
    KnowledgeEvidenceRequiredError,
)
from neural_engine.application.playbook_evaluation_service import (
    PlaybookEvaluationFindingsRequiredError,
    PlaybookRunNotFoundError,
)
from neural_engine.application.playbook_run_service import (
    PlaybookNotFoundError,
    PlaybookRunActionsRequiredError,
)
from neural_engine.application.playbook_service import (
    KnowledgeNotFoundError,
    PlaybookKnowledgeRequiredError,
    PlaybookStepsRequiredError,
)
from neural_engine.core.brain import Brain
from neural_engine.domain import (
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
    PlaybookRun,
)

app = typer.Typer(
    add_completion=False,
    help="Neural Engine CLI",
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
app.add_typer(experience_app, name="experience")
app.add_typer(evaluation_app, name="evaluation")
app.add_typer(knowledge_app, name="knowledge")
app.add_typer(observation_app, name="observation")
app.add_typer(playbook_app, name="playbook")
app.add_typer(proposal_app, name="proposal")
app.add_typer(run_app, name="run")

console = Console()
container = Container()


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """Neural Engine entry point."""

    if ctx.invoked_subcommand is not None:
        return

    brain = Brain()
    brain_status = (
        "[green]Initialized[/green]" if brain.exists() else "[yellow]Not initialized[/yellow]"
    )

    console.print(
        Panel.fit(
            f"""[bold cyan]{APP_NAME}[/bold cyan]

Version: {__version__}

Mission:
  {MISSION}

Status:
  Ready

Brain:
  {brain_status}

Run:
  neural init
""",
            title="🧠 Neural Engine",
        )
    )


@app.command()
def init() -> None:
    """Initialize the local Neural Engine brain."""

    brain = Brain()
    brain.initialize()

    console.print("[green]🧠 Neural Engine initialized successfully![/green]")


@app.command()
def status() -> None:
    """Show Neural Engine status."""

    brain = Brain()

    state = "Initialized" if brain.exists() else "Not initialized"

    console.print(f"[bold cyan]{APP_NAME}[/bold cyan]")
    console.print(f"Version : {__version__}")
    console.print(f"Brain   : {state}")


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


@experience_app.command("list")
def list_experiences() -> None:
    """List all experiences."""

    service = container.experience_service()
    experiences = service.list_experiences()

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
    experience = service.get_by_id(experience_id)

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

    console.print(
        f"[green]Knowledge stored from experience.[/green] ID: [cyan]{knowledge.id}[/cyan]"
    )


@knowledge_app.command("list")
def list_knowledge() -> None:
    """List all knowledge."""

    service = container.knowledge_service()
    knowledge_items = service.list_knowledge()

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

    if not playbooks:
        console.print(f"[yellow]No playbooks linked to knowledge: {knowledge_id}[/yellow]")
        return

    for playbook in playbooks:
        _print_playbook_summary(playbook)
        console.print()


@knowledge_app.command("show")
def show_knowledge(knowledge_id: UUID) -> None:
    """Show one knowledge item."""

    service = container.knowledge_service()
    knowledge = service.get_by_id(knowledge_id)

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


@proposal_app.command("show")
def show_proposal(proposal_id: UUID) -> None:
    """Show one evolution proposal."""

    service = container.evolution_proposal_service()
    proposal = service.get_by_id(proposal_id)

    if proposal is None:
        console.print(f"[red]Evolution proposal not found: {proposal_id}[/red]")
        raise typer.Exit(code=1)

    _print_evolution_proposal(proposal)


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

    if not runs:
        console.print(f"[yellow]No playbook runs linked to playbook: {playbook_id}[/yellow]")
        return

    for run in runs:
        _print_playbook_run_summary(run)
        console.print()


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
        )
    except PlaybookRunActionsRequiredError as error:
        console.print("[red]Playbook run requires at least one action taken.[/red]")
        raise typer.Exit(code=1) from error
    except PlaybookNotFoundError as error:
        _exit_playbook_not_found(error)

    console.print(f"[green]Playbook run stored.[/green] ID: [cyan]{run.id}[/cyan]")


@run_app.command("list")
def list_runs() -> None:
    """List all playbook runs."""

    service = container.playbook_run_service()
    runs = service.list_runs()

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
    run = service.get_by_id(run_id)

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


def _print_experience_summary(experience: Experience) -> None:
    console.print(f"ID: {experience.id}")
    console.print(f"Timestamp: {experience.timestamp}")
    console.print(f"Title: {experience.title}")
    console.print(f"Result: {experience.result.value}")


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


def _exit_playbook_not_found(error: PlaybookNotFoundError) -> None:
    console.print(f"[red]Playbook not found: {error.playbook_id}[/red]")
    raise typer.Exit(code=1) from error


def _exit_playbook_run_not_found(error: PlaybookRunNotFoundError) -> None:
    console.print(f"[red]Playbook run not found: {error.run_id}[/red]")
    raise typer.Exit(code=1) from error


def _print_repeated_field(label: str, values: list[str]) -> None:
    console.print(f"{label}:")

    if not values:
        console.print("-")
        return

    for value in values:
        console.print(f"- {value}")

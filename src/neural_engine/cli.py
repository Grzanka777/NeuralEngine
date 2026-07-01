from typing import Annotated
from uuid import UUID

import typer
from rich.console import Console
from rich.panel import Panel

from neural_engine import APP_NAME, MISSION, __version__
from neural_engine.application.container import Container
from neural_engine.application.experience_service import ObservationNotFoundError
from neural_engine.application.knowledge_service import (
    ExperienceNotFoundError,
    KnowledgeEvidenceRequiredError,
)
from neural_engine.core.brain import Brain
from neural_engine.domain import (
    Experience,
    ExperienceResult,
    Knowledge,
    KnowledgeConfidence,
    Observation,
)

app = typer.Typer(
    add_completion=False,
    help="Neural Engine CLI",
)
experience_app = typer.Typer(
    help="Manage experiences.",
)
knowledge_app = typer.Typer(
    help="Manage knowledge.",
)
observation_app = typer.Typer(
    help="Inspect observations.",
)
app.add_typer(experience_app, name="experience")
app.add_typer(knowledge_app, name="knowledge")
app.add_typer(observation_app, name="observation")

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


@knowledge_app.command("show")
def show_knowledge(knowledge_id: UUID) -> None:
    """Show one knowledge item."""

    service = container.knowledge_service()
    knowledge = service.get_by_id(knowledge_id)

    if knowledge is None:
        console.print(f"[red]Knowledge not found: {knowledge_id}[/red]")
        raise typer.Exit(code=1)

    _print_knowledge(knowledge)


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

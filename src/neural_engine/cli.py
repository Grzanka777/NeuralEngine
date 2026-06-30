from typing import Annotated
from uuid import UUID

import typer
from rich.console import Console
from rich.panel import Panel

from neural_engine import APP_NAME, MISSION, __version__
from neural_engine.application.container import Container
from neural_engine.core.brain import Brain
from neural_engine.domain import Experience, ExperienceResult

app = typer.Typer(
    add_completion=False,
    help="Neural Engine CLI",
)
experience_app = typer.Typer(
    help="Manage experiences.",
)
app.add_typer(experience_app, name="experience")

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
    service.add(content, tags)

    console.print("[green]Observation stored.[/green]")


@app.command("list")
def observations() -> None:
    """List all observations."""

    service = container.observation_service()
    observations = service.list_observations()

    if not observations:
        console.print("[yellow]No observations found.[/yellow]")
        return

    for observation in observations:
        console.print(f"[cyan]{observation.timestamp}[/cyan]")
        console.print(observation.content)

        if observation.tags:
            console.print(f"[dim]Tags: {', '.join(observation.tags)}[/dim]")

        console.print()


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
    experience = service.add(
        title=title,
        context=context,
        action=action,
        outcome=outcome,
        result=result,
        observation_ids=observation_ids,
        tags=tags,
    )

    console.print(f"[green]Experience stored.[/green] ID: [cyan]{experience.id}[/cyan]")


@experience_app.command("list")
def list_experiences() -> None:
    """List all experiences."""

    service = container.experience_service()
    experiences = service.list_experiences()

    if not experiences:
        console.print("[yellow]No experiences found.[/yellow]")
        return

    for experience in experiences:
        console.print(f"[cyan]{experience.id}[/cyan]")
        console.print(f"Timestamp: {experience.timestamp}")
        console.print(f"Title: {experience.title}")
        console.print(f"Result: {experience.result.value}")
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

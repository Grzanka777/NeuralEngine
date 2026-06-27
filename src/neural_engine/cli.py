import typer
from rich.console import Console
from rich.panel import Panel


from neural_engine import APP_NAME, MISSION, __version__
from neural_engine.core.brain import Brain

app = typer.Typer(
    add_completion=False,
    help="Neural Engine CLI",
)

console = Console()


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """Neural Engine entry point."""

    if ctx.invoked_subcommand is not None:
        return

    brain = Brain()
    brain_status = (
      "[green]Initialized[/green]"
      if brain.exists()
      else "[yellow]Not initialized[/yellow]"
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

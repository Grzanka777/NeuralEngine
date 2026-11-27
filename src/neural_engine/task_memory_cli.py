"""CLI adapters for native runtime hooks and operator authorization."""

import json
import shlex
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated
from uuid import UUID

import typer

from neural_engine.application.container import Container
from neural_engine.application.task_memory_service import TaskMemoryError, TaskMemoryService
from neural_engine.core.paths import resolve_neural_paths
from neural_engine.infrastructure.task_memory_runtime import (
    TaskFinish,
    TaskMemoryRuntime,
    TaskStart,
)

app = typer.Typer(help="Inspect and authorize memory prepared by a task runtime.")
Policy = Annotated[Path, typer.Option("--policy", help="Absolute operator policy path.")]


@contextmanager
def _controlled_errors() -> Iterator[None]:
    try:
        yield
    except TaskMemoryError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from None
    except typer.Exit:
        raise
    except Exception:
        # Runtime failures may mention local paths or record text. Keep the bridge redacted.
        typer.echo("TASK_MEMORY_OPERATION_FAILED", err=True)
        raise typer.Exit(1) from None


def _service(runtime: TaskMemoryRuntime) -> TaskMemoryService:
    paths = resolve_neural_paths(environ={"NEURAL_HOME": runtime.policy.brain_home})
    return Container(paths).task_memory_service()


@app.command(hidden=True)
def start(policy: Policy) -> None:
    with _controlled_errors():
        runtime = TaskMemoryRuntime(policy)
        request = TaskStart.model_validate_json(sys.stdin.buffer.read(32_769))
        typer.echo(json.dumps(runtime.start(request, lambda: _service(runtime))))


@app.command(hidden=True)
def finish(policy: Policy) -> None:
    with _controlled_errors():
        runtime = TaskMemoryRuntime(policy)
        request = TaskFinish.model_validate_json(sys.stdin.buffer.read(32_769))
        result, digest = runtime.finish(request, lambda: _service(runtime))
        learning = (
            result.learning.model_dump(mode="json")
            if result.learning and result.status in {"AWAITING_AUTHORIZATION", "HOLD_CONFLICT"}
            else None
        )
        typer.echo(
            json.dumps({"status": result.status, "confirmation": digest, "learning": learning})
        )


@app.command()
def show(session: UUID, policy: Policy) -> None:
    """Show the exact candidate and its content-bound authorization digest."""
    with _controlled_errors():
        runtime = TaskMemoryRuntime(policy)
        result, digest = runtime.result(session)
        typer.echo(result.model_dump_json(indent=2))
        typer.echo(f"Confirmation SHA-256 {digest}")
        if result.status == "AWAITING_AUTHORIZATION":
            command = [
                "uv",
                "run",
                "--no-sync",
                "neural",
                "memory",
                "apply",
                str(session),
                "--policy",
                str(policy),
                "--confirm-authority",
                digest,
            ]
            typer.echo(shlex.join(command))


@app.command()
def apply(
    session: UUID,
    policy: Policy,
    confirmation: Annotated[str, typer.Option("--confirm-authority")] = "",
) -> None:
    """Explicitly authorize this exact receipt for persistence through Brain Trust."""
    with _controlled_errors():
        runtime = TaskMemoryRuntime(policy)
        status, record = runtime.authorise(session, confirmation, lambda: _service(runtime))
        typer.echo(json.dumps({"status": status, "record": str(record) if record else None}))
        if status not in {"DUPLICATE", "KNOWLEDGE_RECORDED", "PROPOSED_DECISION_RECORDED"}:
            raise typer.Exit(code=1)

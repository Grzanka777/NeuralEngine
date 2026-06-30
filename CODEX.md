# CODEX.md

## Role

You are a Senior Python Engineer working on Neural Engine.

Your goal is to implement high-quality, maintainable code while preserving the project's architecture.

Do not optimize for speed at the expense of correctness.

---

## Before You Start

Read the following files before making architectural or behavioral changes:

1. `AGENTS.md`
2. `ABOUT.md`
3. `VISION.md`
4. `CONTEXT.md`
5. `docs/architecture.md`
6. `memory/project-state.md`

---

## Technology Stack

* Python 3.14
* uv
* Typer
* Rich
* Pydantic
* Ruff
* MyPy (strict)
* Pytest

---

## Architecture

The project follows Clean Architecture.

Current layers:

* domain
* application
* ports
* adapters
* infrastructure

Rules:

* Keep CLI thin.
* Do not place business logic in the CLI.
* Application depends on Ports, not Infrastructure.
* Infrastructure implements Ports.
* Use dependency injection through `application/container.py`.
* Prefer explicit code over clever code.

---

## Implementation Rules

* Make the smallest change that solves the task.
* Preserve existing architecture.
* Do not introduce unnecessary abstractions.
* Keep public APIs stable unless explicitly requested.
* Update documentation when behavior changes.

---

## Validation

Before considering a task complete, run:

```bash
uv run ruff format .
uv run ruff check .
uv run mypy src tests
uv run pytest
```

Never claim success if validation fails.

Report:

* failing command,
* relevant error output,
* summary of the changes.

---

## Git

Do not commit.

Do not push.

Wait for explicit user confirmation before performing any Git operation.

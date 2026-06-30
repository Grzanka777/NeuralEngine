# Neural Engine — Agent Instructions

## Mission

Neural Engine is a model-agnostic cognitive evolution engine.

The primary goal is to build a modular, maintainable and AI-native system that can evolve through collaboration between humans and multiple AI agents.

Every change should improve long-term maintainability rather than only solving the immediate task.

---

# Project Architecture

The project follows Clean Architecture principles.

Current layers:

* domain
* application
* ports
* adapters
* infrastructure

Rules:

* Domain must not depend on infrastructure.
* Business logic belongs in the domain or application layer.
* Infrastructure implements ports.
* Avoid introducing tight coupling between layers.
* Preserve the existing architecture unless explicitly instructed otherwise.
* CLI must remain thin and must not contain business logic.
* Dependency creation belongs in `application/container.py`.
* Application services should depend on ports, not infrastructure implementations.

---

# Development Principles

* Prefer small, focused changes.
* Keep functions simple.
* Avoid premature optimization.
* Avoid unnecessary dependencies.
* Document architectural decisions.
* Never remove tests to make the suite pass.
* Update documentation whenever behavior changes.
* Prefer dependency injection over hard-coded implementations.
* Do not introduce new architectural layers without justification.

---

# Validation Requirements

Before considering any task complete, every AI agent **must** perform:

```bash
uv run ruff format .
uv run ruff check .
uv run mypy src tests
uv run pytest
```

Rules:

* Never claim success if any validation command fails.
* Report the exact command that failed.
* Include relevant error output.
* Never hide failures.
* Explain if validation could not be executed.
* Keep the repository in a buildable state.

---

# Definition of Done

A task is complete only if:

* Requested functionality is implemented.
* Code is formatted.
* Ruff passes.
* MyPy passes.
* Pytest passes.
* Documentation is updated if necessary.
* No unrelated files were modified.
* A concise summary of the changes is provided.

---

# Repository Workflow

Before starting work:

1. Read `VISION.md`.
2. Read `CONTEXT.md`.
3. Read `memory/project-state.md`.

When finishing work:

1. Update documentation if needed.
2. Run validation.
3. Summarize completed work.
4. Suggest the next logical step.

---

# Communication

* Be explicit about assumptions.
* Do not invent missing information.
* Explain architectural trade-offs.
* Prefer correctness over speed.
* If uncertain, state the uncertainty clearly.

---

## AI Context

Before architectural changes, agents should also read:

1. `ABOUT.md`
2. `docs/architecture.md`
3. `docs/conventions.md`

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

# Repository Authority and Scope Safety

Every AI agent must:

* Read repository instructions and required project context before editing.
* Work only within the authorized task scope.
* Preserve explicitly stated non-goals.
* Treat the verified live checkout as repository authority.
* Use `/run/media/grzanka/777/projekty/NeuralEngine` for NeuralEngine work.
* Never substitute stale checkouts under `/run/media/grzanka/Big_Shit/`.
* Treat the live NeuralEngine Brain as read-only by default.
* Never write to Brain, create lifecycle records, or mutate durable state without separate explicit authorization.

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
* No unrelated changes exist in the worktree.
* A concise summary of the changes is provided.

---

# Repository Workflow

Before starting work:

1. Read `VISION.md`.
2. Read `CONTEXT.md`.
3. Read `memory/project-state.md`.
4. Verify the live checkout required by the task.
5. Confirm the worktree is clean unless the task explicitly allows working with existing changes.

When finishing work:

1. Update documentation if needed.
2. Run validation.
3. Create the exact task-specific review artifact under `.agent-work/reviews/`.
4. Summarize completed work.
5. Suggest the next logical step.

Review artifacts must include:

* Verified checkpoint.
* Context read.
* Changed files.
* Validation output.
* Diff stat.
* `git diff --check`.
* `git status --short`.
* Full diff.
* Scope and non-goal audit.

---

# Git Operation Boundaries

AI agents must never stage files or run:

```bash
git add
git add -N
git apply --cached
git rm --cached
```

AI agents must never commit, amend, tag, merge, or push.

Staging, commit, amend, tag, merge, and push are separate user-authorized operations outside the agent task.

Never claim completion when validation fails or unrelated changes exist.

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

---
name: NeuralEngine Development
description: Apply this skill to every engineering task inside the NeuralEngine repository.
---

# NeuralEngine Development

## Mandatory first actions

1. Read `AGENTS.md`.
2. Read `.agent-work/project-state.md` when present.
3. Run baseline validation before changes.
4. Inspect relevant code and tests.
5. Keep scope minimal.

## Core rules

# NeuralEngine Constitution

## Mission

Build an engine that transforms observations into reusable knowledge, executable playbooks, evaluated outcomes, and controlled evolution.

## Core principles

1. Correctness before speed.
2. Domain before persistence.
3. Explicit dependencies before convenience.
4. Architecture before implementation shortcuts.
5. Deterministic behavior where practical.
6. Validation before persistence.
7. Small coherent changes.
8. Tests as executable specifications.
9. Review evidence before success claims.
10. No commits or pushes by agents.

## Forbidden

- Business logic in CLI handlers.
- Business logic in infrastructure adapters.
- Hidden dependencies.
- Global mutable state.
- Silent validation failure.
- Scope expansion.
- Unrelated refactoring.
- Repository interfaces used as service APIs.
- Manual edits to generated handbook outputs.

## Architecture

# Architecture

NeuralEngine follows a hexagonal architecture.

## Layers

- Domain
- Application
- Ports
- Infrastructure
- CLI

## Dependency rules

- Domain depends on no outer layer.
- Application depends on domain and ports.
- Infrastructure implements ports.
- CLI invokes application services.
- Dependency construction belongs in the container.
- Infrastructure must never depend on CLI.

## Responsibility rules

- Entities and value objects own domain invariants.
- Application services own use cases.
- Repository ports define persistence contracts.
- Adapters implement persistence contracts.
- CLI translates input and renders output.
- Relationship navigation should be composed in services when it does not belong in persistence.

## Domain chain

# Domain Chain

The confirmed NeuralEngine chain is:

`Observation`
→ `Experience`
→ `Knowledge`
→ `Playbook`
→ `PlaybookRun`
→ `PlaybookEvaluation`
→ `EvolutionProposal`
→ `PlaybookRevision`

## Relationship ownership

Relationship navigation belongs in application services unless persistence itself owns the concern.

Confirmed example:

- `PlaybookRevisionService.list_for_playbook(UUID)` owns playbook revision navigation.
- Repository interfaces remain persistence-focused.
- `PlaybookService` should not gain unrelated persistence dependencies.

## Workflow

# Development Workflow

## Before work

1. Read `AGENTS.md`.
2. Read `.agent-work/project-state.md` when present.
3. Run `./scripts/validate.sh`.
4. Inspect affected code and tests.
5. Define the smallest complete scope.
6. Create a task prompt under `.agent-work/prompts/`.

## During work

- Implement a coherent vertical slice.
- Follow current patterns.
- Add tests with implementation.
- Preserve public behavior unless explicitly changing it.
- Preserve persisted schemas unless explicitly changing them.
- Avoid unrelated cleanup.

## After work

1. Run `./scripts/validate.sh`.
2. Create a review file under `.agent-work/reviews/`.
3. Include validation output, diff stat, diff check, git status, and full diff.
4. Stop without committing or pushing.

## Agent assignment

# Agent Assignment Policy

## Codex GPT-5.5 medium

Use for:

- new features,
- domain models,
- vertical slices,
- ports and adapters,
- repositories and services,
- dependency injection,
- CLI additions,
- persisted schema changes,
- public behavior changes,
- validation-order changes,
- provenance decisions,
- architectural documentation.

## DeepSeek

Use only for small controlled post-review fixes, normally one to three files:

- one concrete bug,
- targeted regression tests,
- Ruff or MyPy corrections,
- small message, type, validation, or CLI-option fixes,
- minor refactors without behavior change.

Every DeepSeek prompt must begin with reading `AGENTS.md`.

Required scope guard:

> Do not add features. Do not broaden scope. Do not change architecture, persisted schemas, public behavior, validation order, or provenance rules. Modify only the files required for the specified fix.

## Validation

# Validation Policy

Preferred command:

```bash
./scripts/validate.sh
```

Required checks:

```bash
ruff format --check .
ruff check .
mypy src tests
pytest
```

Never claim success unless all required checks pass.

When validation fails:

- show the failing command,
- include relevant output,
- identify whether the failure is pre-existing,
- do not bypass or suppress the failure.

## Definition of Done

# Definition of Done

A task is complete only when:

- requested behavior is implemented,
- scope has not expanded,
- architectural boundaries are preserved,
- tests cover the change,
- all required validation passes,
- prompt and review artifacts exist,
- review includes complete evidence,
- no commit or push was performed.

## Review checklist

# Review Checklist

- Is the requested scope complete?
- Were unrelated changes avoided?
- Are layer responsibilities preserved?
- Is business logic in the correct layer?
- Are repository interfaces persistence-focused?
- Are tests sufficient?
- Did validation pass?
- Does the review include diff stat, diff check, git status, and full diff?
- Were persisted schemas or public behavior changed?
- Was any commit or push performed?

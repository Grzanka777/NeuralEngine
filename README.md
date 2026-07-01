# Neural Engine

Neural Engine is a model-agnostic cognitive evolution engine.

The project is organized around Clean Architecture boundaries so domain concepts,
application services, ports, and infrastructure can evolve independently.

## Current Capabilities

The first implemented slice is Observation capture:

```bash
neural observe "Pytest is useful" --tags python --tags testing
neural list
neural show 11111111-1111-1111-1111-111111111111
neural observation experiences 11111111-1111-1111-1111-111111111111
neural search pytest
```

`neural observe` always stores the new observation. If exact duplicate content
already exists, it prints a warning with the existing observation IDs.

Experience capture is exposed through a nested CLI group:

```bash
neural experience add \
  --title "Fixed flaky test" \
  --context "CI failed on timing-sensitive assertion" \
  --action "Replaced sleep with explicit condition" \
  --outcome "Test is deterministic" \
  --result success \
  --observation-id 11111111-1111-1111-1111-111111111111 \
  --tag testing

neural experience list
neural experience show 11111111-1111-1111-1111-111111111111
neural experience knowledge 11111111-1111-1111-1111-111111111111
```

Create an experience directly from one existing observation:

```bash
neural experience from-observation 11111111-1111-1111-1111-111111111111 \
  --title "Fixed flaky test" \
  --action "Replaced sleep with explicit condition" \
  --outcome "Test is deterministic" \
  --result success \
  --tag testing
```

When `--observation-id` is supplied, every referenced observation must already
exist.

Knowledge capture is exposed through a nested CLI group and requires explicit
human-supplied content:

```bash
neural knowledge add \
  --statement "Focused tests reduce debugging time" \
  --rationale "Linked experiences showed faster isolation with narrow test runs" \
  --confidence high \
  --experience-id 11111111-1111-1111-1111-111111111111 \
  --tag testing

neural knowledge from-experience 11111111-1111-1111-1111-111111111111 \
  --statement "Focused tests reduce debugging time" \
  --rationale "The linked experience showed faster isolation with narrow test runs" \
  --confidence high \
  --tag testing

neural knowledge list
neural knowledge show 11111111-1111-1111-1111-111111111111
```

Every referenced experience must already exist. The CLI stores only the
statement, rationale, confidence, experience IDs, and tags provided by the user.

Observations are stored locally as JSON files under the Neural Engine brain
directory. Experiences are stored locally as JSON files under the experience
directory. Knowledge is stored locally as JSON files under the knowledge
directory. The CLI delegates behavior to application services and does not own
business logic.

## Validation

Run the full validation suite before considering a change complete:

```bash
uv run ruff format .
uv run ruff check .
uv run mypy src tests
uv run pytest
```

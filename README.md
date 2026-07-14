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
neural knowledge playbooks 11111111-1111-1111-1111-111111111111
neural knowledge revisions 11111111-1111-1111-1111-111111111111
```

Every referenced experience must already exist. The CLI stores only the
statement, rationale, confidence, experience IDs, and tags provided by the user.

Playbook capture is exposed through a nested CLI group and stores explicit
operational procedures:

```bash
neural playbook add \
  --title "Debug flaky test" \
  --situation "A test fails intermittently" \
  --objective "Find the unstable dependency" \
  --step "Run the failing test repeatedly" \
  --success-criterion "Failure source is isolated" \
  --knowledge-id 11111111-1111-1111-1111-111111111111 \
  --constraint "Do not skip the test" \
  --tag testing

neural playbook list
neural playbook show 11111111-1111-1111-1111-111111111111
neural playbook runs 11111111-1111-1111-1111-111111111111
neural playbook revisions 11111111-1111-1111-1111-111111111111
neural playbook revision-history 11111111-1111-1111-1111-111111111111
neural playbook active-revision 11111111-1111-1111-1111-111111111111
```

Every referenced knowledge item must already exist. Playbooks are stored
procedures; the CLI does not execute or generate them. `neural playbook
revisions` is read-only navigation that lists candidate revisions assigned to
one Playbook. It does not activate a revision, select a current version, modify
the Playbook, apply a proposal, or perform automatic evolution.
`neural playbook revision-history` and `neural playbook active-revision` are
read-only lifecycle inspection commands backed by activation records. They do
not create activation decisions, mutate Playbooks or revisions, change proposal
status, apply proposals, or perform automatic evolution.

Playbook runs record manual or external application of one existing Playbook to
a concrete situation. They store the actions taken, outcome, success flag,
evidence, notes, and tags; Neural Engine does not execute Playbooks.

```bash
neural run add \
  --playbook-id 11111111-1111-1111-1111-111111111111 \
  --situation "A test failed intermittently in CI" \
  --action "Applied the flaky-test playbook manually" \
  --outcome "The unstable dependency was isolated" \
  --success true \
  --evidence "CI log excerpt" \
  --notes "Follow-up issue created" \
  --tag testing

neural run list
neural run show 11111111-1111-1111-1111-111111111111
```

Playbook evaluations are explicit human or external-system assessments of one
existing PlaybookRun. They record effectiveness, findings, possible
improvements, evidence, notes, and tags; Neural Engine does not evaluate runs
automatically or create evolution proposals.

```bash
neural evaluation add \
  --run-id 11111111-1111-1111-1111-111111111111 \
  --effectiveness partial \
  --finding "The playbook isolated the likely cause" \
  --improvement "Clarify the verification step" \
  --evidence "Manual review note" \
  --notes "Assessment supplied after the run" \
  --tag testing

neural evaluation list
neural evaluation show 11111111-1111-1111-1111-111111111111
neural run evaluations 11111111-1111-1111-1111-111111111111
```

Evolution proposals are explicit manual or external-system proposals to improve
one existing Playbook based on one or more existing PlaybookEvaluation records.
They record proposed changes only; Neural Engine does not apply proposals,
modify Playbooks, or perform automatic evolution.

```bash
neural proposal add \
  --playbook-id 11111111-1111-1111-1111-111111111111 \
  --evaluation-id 22222222-2222-2222-2222-222222222222 \
  --summary "Clarify verification step" \
  --rationale "Manual evaluations found unclear success checks" \
  --change "Add explicit verification criteria" \
  --benefit "More consistent manual application" \
  --risk "Longer checklist" \
  --tag testing

neural proposal list
neural proposal show 11111111-1111-1111-1111-111111111111
neural proposal status 11111111-1111-1111-1111-111111111111 --status accepted
neural proposal revisions 11111111-1111-1111-1111-111111111111
neural playbook proposals 11111111-1111-1111-1111-111111111111
neural evaluation proposals 22222222-2222-2222-2222-222222222222
```

Proposal status is supplied manually or by an external system. Setting a
proposal to `accepted` records the decision only; it does not apply changes to a
Playbook.

Playbook revisions are immutable candidate snapshots of revised Playbook
content supplied manually or by an external system. They must reference one
accepted EvolutionProposal and do not replace or modify the original Playbook.
Creating a revision is a separate explicit action; it does not activate the
revision, apply the proposal, or perform automatic evolution.

```bash
neural revision add \
  --playbook-id 11111111-1111-1111-1111-111111111111 \
  --proposal-id 33333333-3333-3333-3333-333333333333 \
  --title "Debug flaky test v2" \
  --situation "A test fails intermittently" \
  --objective "Find and verify the unstable dependency" \
  --step "Collect recent failure evidence" \
  --step "Run the failing test repeatedly" \
  --success-criterion "Failure source is isolated" \
  --success-criterion "Verification evidence is recorded" \
  --knowledge-id 44444444-4444-4444-4444-444444444444 \
  --notes "Candidate revision supplied after manual review" \
  --tag testing

neural revision list
neural revision show 55555555-5555-5555-5555-555555555555
neural revision activate 55555555-5555-5555-5555-555555555555 \
  --playbook 11111111-1111-1111-1111-111111111111 \
  --proposal 33333333-3333-3333-3333-333333333333 \
  --reason "Manual reviewer selected this revision"
```

`neural revision activate` records an explicit lifecycle decision only. It does
not copy or materialize revision content into the Playbook, mutate the Playbook
or revision, change proposal status, apply proposals, or perform automatic
evolution.

Observations are stored locally as JSON files under the Neural Engine brain
directory. Experiences are stored locally as JSON files under the experience
directory. Knowledge is stored locally as JSON files under the knowledge
directory. Playbooks, playbook runs, playbook evaluations, evolution proposals,
and playbook revisions are stored locally as JSON files under their brain
directories. The CLI delegates behavior to application services and does not own
business logic.

## Validation

Run the full validation suite before considering a change complete:

```bash
uv run ruff format .
uv run ruff check .
uv run mypy src tests
uv run pytest
```

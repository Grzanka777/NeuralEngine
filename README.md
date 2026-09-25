# Neural Engine

Neural Engine is a model-agnostic cognitive evolution engine.

The project is organized around Clean Architecture boundaries so domain concepts,
application services, ports, and infrastructure can evolve independently.

## Neural Home Selection

By default, Neural Engine stores its complete local operational home at:

```text
Path.home() / ".neural"
```

One explicit alternate home can be selected for a process through
`NEURAL_HOME`:

```bash
NEURAL_HOME=/absolute/existing/directory neural status
```

The variable selects the complete Neural home, including `brain/`, `projects/`,
`logs/`, `config.toml`, and `VERSION`. A supplied value must be non-blank,
absolute, free of `~`, and resolve strictly to an existing accessible
directory. Valid symlinked roots are supported when their target is available.
A blank, relative, missing, dangling, non-directory, or inaccessible override
fails without falling back to `~/.neural`.

`neural status` is read-only and reports the selection source, configured and
resolved home, resolved Brain path, availability, initialization state, and a
controlled failure reason. `neural init` may create the default `~/.neural`
root. With `NEURAL_HOME`, the selected root itself must already exist; init
creates only approved children inside it.

`neural doctor` is a deeper, intrinsically read-only readiness inspection. It
checks the selected home and Brain access, the persisted Brain format in
`VERSION`, `config.toml`, the exact 15-store topology, every JSON record's
readability, UTF-8, domain schema and filename/payload identity, per-store
duplicate IDs, and a deterministic relative-path SHA-256 manifest. The package
release version and Brain format version are independent: upgrading the package
does not require rewriting `VERSION` unless the persisted Brain format changes.
Doctor prints compact evidence without record payloads, config contents,
individual IDs, or per-file hashes. Exit status is `0` for `READY`, `1` for
`NOT READY`, and `2` for invalid invocation or an unexpected internal failure.
Doctor does not initialize, repair, migrate, copy, or write any state.

Path selection does not discover or mount devices, migrate or copy Brain data,
create backups, synchronize hosts, add locking, or coordinate multiple
writers. If a configured removable root becomes unavailable, normal commands
fail rather than treating it as an empty Brain or recreating a local fallback.
When `NEURAL_HOME` points to a directory on portable storage, a user-managed
portable Neural home is supported provided the same path is available and
accessible. Storage lifecycle, device management, and deployment remain user
and operator responsibilities.

The complete repository-owned reconstruction contract for the current
NeuralEngine/OpenCode workflow is in
[`docs/reproducible-baseline.md`](docs/reproducible-baseline.md). It separates
development and non-editable production installation, documents external
OpenCode/llama/model prerequisites, and defines the read-only health sequence.

## Current Capabilities

### Frozen local LLM launcher

The repository includes a small terminal-first launcher for the frozen local
Qwen3.6 GENERAL, Qwen3-Coder CODE, and Gemma 4 VISION profiles. It performs
prerequisite, port, health, and verified process checks without enabling a
service or starting anything during login or boot. To make the command
available as `llm`, install the executable into a user-local bin directory:

```bash
install -m 0755 scripts/llm ~/.local/bin/llm
```

Use it from fish or another shell:

```text
llm code
llm general
llm vision
llm switch general
llm switch code
llm switch vision
llm status
llm state
llm identity
llm stop
```

`llm state` is a machine-readable ownership check and prints exactly one of
`STOPPED`, `GENERAL`, `CODE`, `VISION`, or `UNKNOWN`. It reports a profile only
when its listener, process command line, and health endpoint are all verified.
`llm switch <profile>` serializes state inspection, verified shutdown, target
startup, and target verification with a user-level lifecycle lock. It refuses
unknown, foreign, or conflicting state and does not perform automatic rollback.
`llm identity` is a read-only machine-readable check that prints `PROFILE PID`,
`STOPPED`, or `UNKNOWN`.

The launcher reports these OpenAI-compatible endpoints after `/health` becomes
ready:

```text
CODE:    http://127.0.0.1:18080/v1
GENERAL: http://127.0.0.1:18081/v1
VISION:  http://127.0.0.1:18082/v1
```

CODE uses the frozen Vulkan profile without speculative decoding, MTP, or
EAGLE3 flags. VISION uses the verified Gemma 4 projector and draft-MTP n2
profile. Only one supported profile may run at a time.

### Manual OpenCode fresh-session handoff

`neural handoff opencode` renders a compact, copy/paste-ready checkpoint for a
new OpenCode session. It never calls OpenCode compaction or summarize APIs,
does not start a session, and does not read or write Brain state. The caller
must explicitly provide the current task goal and next action; optional facts
are included only when supplied as concise reviewed values.

```bash
neural handoff opencode \
  --task-goal "Implement a bounded handoff helper" \
  --next-action "Review the checkpoint before starting a fresh session" \
  --verified-decision "Keep the workflow manual" \
  --file src/neural_engine/cli.py \
  --validated-evidence "Focused tests passed" \
  --uncertainty "Automatic triggering is not approved"
```

The command writes only to stdout, validates supplied working-set files as
repository-relative existing files, deduplicates facts, rejects oversized raw
logs and likely secrets, and records live Git branch, HEAD, and a bounded
worktree state. Redirect stdout when a reviewable file is wanted.

### OpenCode context-pressure watcher

`neural handoff watch` is a foreground, read-only assistant for deciding when
to create the manual checkpoint. It does not compact, summarize, rewrite,
close, replace, or start an OpenCode session; it does not modify OpenCode
configuration or Brain state.

```bash
# One non-interactive status check for a script.
neural handoff watch --check --session ses_example

# Interactively offer the existing manual handoff only at HANDOFF pressure.
neural handoff watch --session ses_example

# Foreground-only monitoring; transitions and changes of at least 1,000 tokens.
neural handoff watch --follow --session ses_example --interval 60
```

The frozen production context limit is `32768` tokens. Levels are `HEALTHY`
below `22000`, `NOTICE` from `22000`, `HANDOFF` from `25000`, and `CRITICAL`
from `29000`. `--check` exits `0` for HEALTHY/NOTICE, `10` for HANDOFF, `20`
for CRITICAL, and `30` if session selection or context observation is
unavailable or ambiguous.

OpenCode v2.0.3 stores sessions in `session_v2` and completed response token
components in `session_message`; older installations use `session` and
`part`. The adapter reads both layouts and reports the latest completed
response as `ESTIMATED` (prefixed with `~`), not as a live active-prompt
total. It fails closed when the current directory maps to more than one
unarchived session; use `--session` to select a specific session. A persisted
session is considered observable only while a live local OpenCode process
exists; after OpenCode exits, `--check` returns `UNKNOWN` with exit `30` rather
than presenting stale session state. An estimated value never alone produces
`CRITICAL`.

### Daily OpenCode wrapper

Install the wrapper as `opencode-watch` (the existing fish `ow` function may
continue to resolve it):

```bash
install -m 0755 scripts/opencode-watch ~/.local/bin/opencode-watch
```

The wrapper records `llm state`, launches OpenCode directly with its original
arguments and terminal streams, and leaves context management, compaction, and
tools to OpenCode. It does not resolve sessions, read the OpenCode SQLite
database, or start a background NeuralEngine watcher. When the initial state is
`STOPPED`, it records exact verified profile/PID observations and uses signal-safe,
idempotent cleanup. It invokes `llm stop` only when the same exact identity is
still verified; pre-existing, conflicting, unknown, or changed ownership is
preserved.

### OpenCode rolling compatibility

NeuralEngine follows OpenCode as a rolling external platform. After an OpenCode
update, run the read-only capability preflight:

```bash
neural opencode doctor
```

The preflight records the installed OpenCode version for diagnostics and checks
the executable, resolved user config, selected agent, GENERAL/CODE/VISION
provider and model identifiers, `llm` lifecycle integration, executable
`opencode-watch` wrapper, and the explicit NeuralEngine/Brain safety boundary.
It does not compare against an exact version, start a model, open the OpenCode
database/service, or write Brain state.

Interpret the result as follows:

```text
Compatibility: PASS       continue normal work
Compatibility: DEGRADED   continue; the output names the optional capability
Compatibility: BLOCKED    stop and repair the named required capability
Compatibility: UNKNOWN    stop and run the smallest named diagnostic
```

When stronger evidence is needed, request one bounded marker smoke explicitly:

```bash
neural opencode doctor --live-smoke --lane code
```

Use `--lane general` when validating the GENERAL path. The live smoke reuses
the existing wrapper and exact LLM ownership cleanup; it requires `STOPPED`
before launch and must finish with `llm state` reported as `STOPPED`. Do not
pin or downgrade OpenCode, rebaseline prompts, or run token benchmarks merely
because its version changed.

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

Decision learning is an explicit immutable chain from proposal through factual
outcome and authorized interpretation. Review does not change the factual
lifecycle state and does not create learning artifacts automatically:

```bash
neural decision add [OPTIONS]
neural decision accept DECISION_UUID [OPTIONS]
neural decision action add DECISION_UUID [OPTIONS]
neural decision outcome add DECISION_UUID [OPTIONS]
neural decision review add DECISION_UUID \
  --acceptance-id ACCEPTANCE_UUID \
  --outcome-id OUTCOME_UUID \
  --reviewed-by OWNER \
  --reviewed-at 2026-07-18T12:00:00+00:00 \
  --assessment sound \
  --summary "The decision remains defensible" \
  --finding "The implementation preserved its boundaries" \
  --confidence high \
  --idempotency-key review-1

neural decision review history DECISION_UUID
neural decision review show REVIEW_UUID
neural decision state DECISION_UUID
```

Completed local NeuralEngine development work can be previewed and explicitly
applied to that existing chain through `neural development-evidence`. The
supported one-repository/one-prompt/one-review/one-commit contract and its
authority, provenance, replay, and non-behavior boundaries are documented in
[`docs/development-evidence-ingestion.md`](docs/development-evidence-ingestion.md).

Review assessment is exactly `sound`, `flawed`, `mixed`, or `inconclusive`;
confidence is `low`, `medium`, or `high`. Findings and candidate lessons are
interpretive statements only. They do not constitute Experience, Knowledge,
Playbook, evaluation, revision, or proposal creation until a separate explicit
use case succeeds.

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

Explicitly promote ordered Review statements with 1-based CLI ordinals:

```bash
neural experience from-review REVIEW_UUID \
  --source finding:1 \
  --source candidate_lesson:2 \
  --promoted-by learning-owner \
  --promotion-reason "The reviewed statements are operationally reusable" \
  --idempotency-key review-experience-1 \
  --title "Preserve explicit learning authority" \
  --context "Decision review follow-up" \
  --action "Promoted selected reviewed statements" \
  --outcome "Experience stored with immutable Review provenance" \
  --result mixed \
  --tag decision-learning
```

The command copies statement text from the immutable Review; callers do not
retype it. Reviewer and promoter are separate authorities. A promoted
Experience is still not Knowledge, changes no Decision lifecycle state, and
triggers no later learning artifact.

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
neural knowledge search focused
neural knowledge playbooks 11111111-1111-1111-1111-111111111111
neural knowledge revisions 11111111-1111-1111-1111-111111111111
```

Every referenced experience must already exist. The CLI stores only the
statement, rationale, confidence, experience IDs, and tags provided by the user.
Knowledge creation and reads validate every linked Experience through
`ExperienceService`, so corrupt DecisionReview-derived promotion provenance
fails closed with its canonical error. `neural experience knowledge UUID` is
read-only navigation; explicit creation uses the existing generic `neural
knowledge add` or `neural knowledge from-experience` command. No Knowledge
schema, authority, idempotency, or automatic creation behavior is implied, and
storing Knowledge does not prove that it improved a later decision.

`neural knowledge search QUERY` is read-only. It performs case-insensitive
substring matching against each Knowledge item's statement or rationale and
returns matches in repository load order. It does not rank results, perform
semantic or cross-record retrieval, add CLI options, or change persistence.

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
a concrete situation. A caller may optionally declare the exact immutable
PlaybookRevision whose content was used. Omission makes no revision-specific
claim and remains compatible with base and legacy Runs. The service validates
revision existence and same-Playbook ownership but never infers from active
revision or application-intent state.

```bash
neural run add \
  --playbook-id 11111111-1111-1111-1111-111111111111 \
  --revision-id 22222222-2222-2222-2222-222222222222 \
  --situation "A test failed intermittently in CI" \
  --action "Applied the flaky-test playbook manually" \
  --outcome "The unstable dependency was isolated" \
  --success true \
  --evidence "CI log excerpt" \
  --notes "Follow-up issue created" \
  --tag testing

neural run list
neural run show 11111111-1111-1111-1111-111111111111
neural revision runs 22222222-2222-2222-2222-222222222222
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
neural proposal activation-history 11111111-1111-1111-1111-111111111111
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
neural revision activation-history 55555555-5555-5555-5555-555555555555
neural revision activate 55555555-5555-5555-5555-555555555555 \
  --playbook 11111111-1111-1111-1111-111111111111 \
  --proposal 33333333-3333-3333-3333-333333333333 \
  --reason "Manual reviewer selected this revision"
neural revision supersede 66666666-6666-6666-6666-666666666666 \
  --playbook 11111111-1111-1111-1111-111111111111 \
  --proposal 77777777-7777-7777-7777-777777777777 \
  --previous-revision 55555555-5555-5555-5555-555555555555 \
  --reason "Manual reviewer selected the newer revision"
neural revision reject 88888888-8888-8888-8888-888888888888 \
  --playbook 11111111-1111-1111-1111-111111111111 \
  --proposal 99999999-9999-9999-9999-999999999999 \
  --reason "Manual reviewer rejected this candidate"
```

`neural revision activate`, `neural revision supersede`, and
`neural revision reject` record explicit lifecycle decisions only. They do not
copy or materialize revision content into the Playbook, mutate the Playbook or
revision, change proposal status, apply proposals, or perform automatic
evolution.
`neural revision activation-history` and `neural proposal activation-history`
are read-only lifecycle inspection commands. They list activation records linked
to an existing revision or proposal without adding repository query methods,
creating lifecycle decisions, mutating records, changing proposal status,
applying proposals, or performing automatic evolution.

Observations are stored locally as JSON files under the Neural Engine brain
directory. Experiences are stored locally as JSON files under the experience
directory. Knowledge is stored locally as JSON files under the knowledge
directory. Playbooks, playbook runs, playbook evaluations, evolution proposals,
and playbook revisions are stored locally as JSON files under their brain
directories. The CLI delegates behavior to application services and does not own
business logic.

## Durable operational Knowledge use and feedback

Neural Engine distinguishes durable Knowledge from its later operational use:

```text
Knowledge exists
-> Knowledge was selected into Playbook.knowledge_ids
-> the Playbook was manually or externally applied as a PlaybookRun
-> the Run was evaluated through PlaybookEvaluation.run_id
-> the Evaluation supported an EvolutionProposal
```

The exact persisted feedback path is:

```text
PlaybookEvaluation.run_id
-> PlaybookRun.playbook_id
-> Playbook.knowledge_ids
-> Knowledge.id
```

An EvolutionProposal stores the target `playbook_id` and exact
`evaluation_ids`; the application service verifies that every Evaluation's Run
belongs to that Playbook. A DecisionAction may also point to the exact Run. A
DecisionOutcome points to exact DecisionActions, so the optional decision path
is:

```text
DecisionOutcome.action_ids
-> DecisionAction.playbook_run_id?
-> PlaybookRun.playbook_id
-> Playbook.knowledge_ids
```

The second path is optional because `playbook_run_id` is optional. These
relations provide durable feedback at Playbook and declared Knowledge-set
scope. They do not prove that one Knowledge item caused an outcome, attribute
individual contributions in a multi-Knowledge Playbook, or demonstrate causal
or comparative improvement. Neural Engine does not record durable Knowledge
retrieval history or recommendation events and never infers use from
co-existence, timestamps, tags, text similarity, or repository order.

`PlaybookRun` may identify one exact PlaybookRevision explicitly; otherwise it
makes no revision-specific claim. `PlaybookRevisionApplication` still records
application intent/audit with unchanged content and is not execution. Revision
provenance is never inferred from lifecycle or application records. Knowledge
selection, Run recording, Evaluation, Proposal creation, and decision linkage
remain explicit caller actions and do not trigger automatic learning or mutation.

## Validation

Run the full validation suite before considering a change complete:

```bash
uv run ruff format .
uv run ruff check .
uv run mypy src tests
uv run pytest
```

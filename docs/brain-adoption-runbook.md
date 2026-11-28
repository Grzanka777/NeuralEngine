# Daily Brain Adoption Runbook

This runbook defines the minimal, read-first daily workflow for supplying
project-scoped NeuralEngine Brain context to existing coding and review agents
without expanding schemas, Planner enrichment, or Governor rules.

## Automatic task memory in Pi

Pi supports one ephemeral print task per invocation; the qualified Z13 host runs
Pi 1.7.0. Configure the
workspace and project once, then send the same two-line ticket invocation.
The Pi extension reads the ticket and supplies eligible Brain evidence before
inference. It reports a receipt ID and the result on stderr. The provider
receives the ticket and a separate, untrusted evidence message.

Create a directory outside the workspace with mode `0700` for the operator
policy and receipts. Create `policy.json` in it with mode `0600`. Use exact,
canonical absolute paths for the workspace, Brain home and verifier. The
selected Brain must already be adopted and healthy. Use an existing runtime
catalog and set `share_with` to the exact provider, model, API and base URL
approved for project evidence. The default `null` denies automatic disclosure
and skips pre-task Brain retrieval. The policy applies to both topic matches
and bounded project fallback.

For an authorized local review, derive the exact `share_with` object from
the current manifest. This command only reads the manifest.

```bash
scripts/llm project-profile current-qwen36
```

Use its `destination` as `share_with` in the private policy alongside the
absolute `workspace` and `brain_home`, `project: "NeuralEngine"`,
`topic: "brain"` and `max_bytes: 4096`. The deployed route uses
`neuralengine-local/qwen3.6-35b-a3b-q6` at `http://127.0.0.1:18086/v1`.

From the configured project root, create one reusable `0600` policy per supported
model route inside a `0700` directory outside the workspace (for example
`~/.local/state/neuralengine/qwen-policy.json` and
`~/.local/state/neuralengine/deepseek-policy.json`). Set `"topic": null` (or a
default subsystem topic) and optional `"default_verifier"` once so daily tasks
reuse the same policy without per-task edits.

Run the manifest-backed GENERAL launcher for local Qwen 3.6 Q6_K. It explicitly
loads the repository provider projection, Guard, and memory extension when the
policy is present. The projection starts or borrows the exact runtime and cleans
up only its owned process on Pi shutdown:

```bash
export NEURAL_TASK_MEMORY_POLICY=/absolute/path/to/operator-directory/qwen-policy.json
scripts/pi-local general -- --offline --print --no-session --no-tools -- \
  $'Read and execute:\n.agent-work/prompts/TASK.md'
```

For explicit cloud escalation to DeepSeek, use `scripts/pi-local deepseek` with
a separate policy whose `share_with` is `null` (to deny Brain disclosure) or
explicitly matches `deepseek` / `deepseek-flash` / `openai-completions` /
`https://api.deepseek.com` (Pi's built-in catalog model ID; `deepseek-v4-pro` is
also available via native `pi --provider deepseek --model deepseek-v4-pro`).
`scripts/pi-local` never falls back from `general` to `deepseek` automatically:

```bash
export NEURAL_TASK_MEMORY_POLICY=/absolute/path/to/operator-directory/deepseek-policy.json
scripts/pi-local deepseek -- --offline --print --no-session --no-tools -- \
  $'Read and execute:\n.agent-work/prompts/TASK.md'
```

`--offline` disables Pi startup network operations; only an explicit `deepseek`
invocation with provider credentials sends inference requests to DeepSeek.

For tool-enabled Pi runs, load the existing project Guard explicitly, set
`NEURAL_PI_POLICY_FILE` to the bounded Governor policy, and replace
`--no-tools` with `--extension "$PWD/.pi/extensions/neuralengine-guard.ts"`
before the task-memory extension. Use the native Pi CLI with exact provider and
model arguments for this mode. Keep Brain, operator files, and Brain-reading
commands outside the Governor allowlists. The Guard remains a process-level
control. The runtime trusts the operator's model catalog, authorized files,
verification programs and transport configuration. A shared host process or
provider proxy with broader access needs its own authorization before use.

## Codex and Antigravity headless task memory

Use the same task file and shared verifier, receipt and authorization commands.
The supported entrypoints are a new `codex exec --ephemeral --json` task and
one task sent over the headless Antigravity CLI JSON stream. The launcher
pins the workspace and sends the admitted task bytes with an explicit model
selector. It admits success only with exit zero, a native session ID and a
successful terminal event. The receipt records the requested model and native
session ID. A requested selector does not attest the effective provider, model,
endpoint or final provider payload.

Use `share_with: null` and omit `trust_native` for the default
`DISCLOSURE_DENIED` workflow. The verifier can still prepare a candidate
locally after a successful settlement.

The policy document is a strict contract: unknown keys are rejected, so a
`_note` or comment field makes the whole file unusable. Keep the active
policy free of annotations. Inactive client-trust drafts belong in a
separate `templates/` directory and must never be passed to `--policy`.

For an explicitly authorized project and signed-in native client, create
one private policy per engine. Add `trust_native` alongside the existing
workspace, project, Brain home, context limits and optional verifier.
Keep `share_with: null`.

```json
{
  "trust_native": {
    "engine": "codex",
    "model": "gpt-6.2-sol",
    "executable": "/canonical/path/to/codex",
    "sha256": "REPLACE_WITH_THE_64_LOWERCASE_HEX_DIGEST"
  }
}
```

For AGY use `"engine": "antigravity"`, the `gemini-3.8-flash-medium` selector
and the resolved `agy` executable. Obtain the canonical path with
`readlink -f (command -s codex)` or `readlink -f (command -s agy)` in fish.
Use `sha256sum` on the resolved executable. Review a client update and update
the pin before using it to disclose context.

The pin must describe the executable the launcher actually resolves on
`PATH`, not another installation of the same version. Two builds of one
version, for example a distribution package and a standalone self-managed
build, have different digests; pinning the wrong one fails admission with
`NATIVE_CLIENT_IDENTITY_MISMATCH`. Prefer one installation per client.

`trust_native` authorizes the launcher to hand bounded Brain context to the
pinned native client. The operator trusts the client, its subscription
account, configuration, tools and routing. The launcher checks the engine,
requested model, resolved executable and SHA-256. It rejects recognized
alternate API routes and mixed policy modes. Trusted Codex launches select
the built-in OpenAI provider and ChatGPT login, ignore user config and
disable hooks. AGY uses its existing Google account settings with direct
Gemini API and ADC settings refused. A local preflight does not establish
the final provider request, recipient, fallback behavior or retention.

The receipt records `OPERATOR_TRUSTED_NATIVE` and the client digest. With
that label, `context_supplied` records that the launcher attached context
to native input and observed a session ID. A missing session ID does not
prove that context stayed local. Pi’s separate `share_with` mode keeps its
request-payload and destination checks.

The launcher requires Linux bubblewrap with working mount and PID namespaces.
It binds `/` read-write, supplies a private `/dev` and `/proc`, and hides the
selected Brain, inherited Neural home, default Neural home and
private policy/receipt directory from the CLI subprocess and removes both
Neural environment variables from its environment. Use trusted client
configuration, tools and integrations. A pre-existing external process or
MCP server runs outside this filesystem boundary. Task files and other
workspace documents are ordinary agent input, so keep private Brain exports
outside the workspace and out of provider-bound tasks. Invalid policy or
workspace fails admission before launching a CLI.

From the project root, define the task once in fish. The model selectors
below are explicit examples. Select available models for your account during
one-time setup. Run one of the four commands for each task.

```fish
set task (printf 'Read and execute:\n.agent-work/prompts/TASK.md' | string collect)
set policies ~/.local/state/neuralengine
set codex_model gpt-6.2-sol
set antigravity_model gemini-3.8-flash-medium

uv run --no-sync neural memory run codex --model "$codex_model" \
  --policy "$policies/codex-policy.json" "$task"

uv run --no-sync neural memory run antigravity --model "$antigravity_model" \
  --policy "$policies/antigravity-policy.json" "$task"

env NEURAL_TASK_MEMORY_POLICY="$policies/deepseek-policy.json" \
  scripts/pi-local deepseek -- --offline --print --no-session --no-tools -- "$task"

env NEURAL_TASK_MEMORY_POLICY="$policies/qwen-policy.json" \
  scripts/pi-local general -- --offline --print --no-session --no-tools -- "$task"
```

Codex and Antigravity print a `neural memory show` command on completion.
Inspect the receipt and run its exact authorization command only when you
approve that candidate for persistence. A Decision record is a proposal.
Its acceptance remains a separate operation. Native Antigravity may retain
conversation data according to its client settings. The memory receipt
stores settlement and verifier provenance only.

T3 Code uses its own Codex and Antigravity drivers. A T3 chat turn bypasses
this launcher, its private policy preflight and its completion receipt.
From a terminal at the T3 project's Git root, run the CLI workflow for
tasks that need automatic memory. T3 chat, desktop and resumed sessions
remain outside this qualification.

## Completion and authorization

The extension records safe metadata outside Brain, including task hash, context
hash and record IDs, fallback selection, omissions, and whether the provider
request was assembled with evidence. It distinguishes `AVAILABLE`, `EMPTY`,
`TRUNCATED`, `DISCLOSURE_DENIED`, `RETRIEVAL_ERROR` and `INTEGRITY_ERROR`.
The last two stop the task before inference. The evidence contains no new
acceptance object and Planner enrichment stays off. A started receipt without
a result means completion could not be established. Graceful interruption
produces an `INTERRUPTED` result. Receipt files contain no full prompts,
transcripts, model responses or logs.

For repeatable tasks, register an existing independently maintained verifier
under the task basename in the policy's optional `verifiers` map:

```json
{
  "verifiers": {
    "TASK": {
      "executable": "/absolute/path/to/operator-owned-verifier",
      "sha256": "REPLACE_WITH_THE_64_LOWERCASE_HEX_DIGEST"
    }
  }
}
```

A project can use `default_verifier` with the same executable and hash fields
to cover multiple tasks. Per-task entries override the default. The verifier
runs after a successful Pi completion, with the workspace as its
working directory. It receives the admission receipt on stdin with only
bounded metadata, and emits one JSON result on stdout. Use
`{"passed": true}` on verified tasks with no durable lesson. For a candidate,
also emit `evidence_path` and `evidence_sha256` for a checked workspace artifact
and one `learning` object:

- Proposed Decision fields are `kind` set to `decision`, `title`, `objective`,
  `alternatives`, `proposed_option`, and `rationale`.
- Knowledge fields are `kind` set to `knowledge`, `subject`, `statement`,
  `rationale`, and `experience_id` for an existing successful Experience tagged
  with the same project.

The verifier establishes the task outcome and any stated finding from the
actual evidence. Its executable and stdout are bounded and checked. A missing
verifier produces `NO_VERIFIER`. Failed checks, invalid evidence, and missing
Experience provenance suppress write candidates. Keep secrets and full
reports out of verifier results. Generic semantic extraction from agent prose
requires an independent fact source and is outside this lane.

For `AWAITING_AUTHORIZATION`, Pi displays the compact candidate and prints the
complete authorization command. Execute that exact command only if you
authorize the candidate. The digest binds authorization to the private receipt.
Use `neural memory show SESSION --policy PATH` to inspect its full provenance. Apply requires the same
Brain identity, rechecks conflicts, and calls existing services through the
Brain Trust coordinator. Exact replay leaves the existing record in place.
`HOLD_CONFLICT` requires operator resolution. Equivalence and conflict checks
use normalized Decision titles and payloads, Knowledge statement/rationale,
subject and Experience references. Cross-title semantic conflict detection
requires human judgment. Proposal authorization does not accept or supersede a
Decision. Use the separate existing Decision authority workflow for those
operations. If a write returned a pending transition, inspect the Brain and
use the existing separately authorized recovery procedure before retrying.

| Engine | Pre-task retrieval and injection | Result collection | Candidate and authorized apply | Runtime evidence |
| --- | --- | --- | --- | --- |
| Pi with DeepSeek | Automatic for a matching policy | Automatic | Automatic preparation with an eligible verifier. Explicit apply. | Native CLI and serialized request tested offline with mocked transport. |
| Local Qwen 3.6 via Pi | Automatic for a matching policy | Automatic | Same Pi contract | Native CLI with the configured GENERAL provider/model tested offline with mocked transport. |
| Codex | Automatic for a matching policy through `neural memory run codex`. Default is `DISCLOSURE_DENIED`; `trust_native` is required for disclosure. | Automatic: native JSONL session ID and terminal event | Shared operator CLI prepares the candidate and applies it after exact-digest authorization | Live headless subscription turn qualified; denied and streamed routes tested with a controlled transport. |
| Antigravity | Automatic for a matching policy through `neural memory run antigravity`. Default is `DISCLOSURE_DENIED`; `trust_native` is required for disclosure. | Automatic: native NDJSON settlement | Same shared operator CLI | Live headless subscription turn qualified; native workspace and conversation identity matched. |

### First production task proposal

Use `NeuralEngine` with topic `brain` on the candidate in the local Qwen 3.6
GENERAL lane. With separately authorized read-only production Brain access,
ask the agent to identify from the supplied context which lifecycle decisions
are currently accepted and whether any evidence establishes permission to
persist new records. Use the exact loopback destination above, `--no-tools`,
no verifier, no external provider permission, and no production write
authorization. Expect a scoped context receipt and `NO_VERIFIER` on normal
completion. Inspect only the context status, IDs and omitted counts to judge
retrieval. This proposal does not activate production.

## Manual workflow for engines without runtime integration

## Scope and Rules

- **Read-only retrieval**: `neural context`, `neural status`, `neural doctor`,
  `neural decision list/show/acceptance-history/state`, and
  `neural knowledge search` never write to the Brain.
- **No inferred approval**: Only a Decision with status `accepted` (backed by a
  `DecisionAcceptance` record) grants prior approval. `proposed` and `rejected`
  Decisions, superseded Decisions, and standalone `Knowledge` items do **not**
  authorize action.
- **Planner enrichment off by default**: The initial daily workflow uses raw
  project-scoped Decision, Acceptance presence, and Knowledge records only
  (`planner_enrichment=false`).
- **Separate write authorization**: Never mutate production Brain state or
  commit/push changes automatically. Every durable write requires separate
  explicit operator approval.

---

## 1. Check Neural Home and Brain Readiness

Verify which `NEURAL_HOME` is selected and that the Brain is readable before
starting work:

```bash
neural status
neural doctor
```

Routine read-only inspection does not require manual write checkpoints. Stop if
`neural status` or `neural doctor` reports an unavailable home or failing store.

---

## 2. Choose Project Scope and Retrieve Context

Use an exact `--project` key matching `Decision.project_key` and
`Knowledge.tags`. Add `--topic` when the task targets a specific subsystem or
topic; omit `--topic` to retrieve all decisions and tagged knowledge for that
project up to `--max-bytes` (default `4096`, range `512`–`16384`).

```bash
# Compact JSON (canonical reusable contract)
uv run neural context --project my-project --topic registry --max-bytes 4096

# Human-readable Markdown for direct prompt pasting
uv run neural context --project my-project --topic registry --format markdown
```

---

## 3. Inspect Retrieved Evidence

Before sending context to an agent, inspect the returned fields:

- `decisions[].status`:
  - `accepted` — an explicit `DecisionAcceptance` record exists.
  - `rejected` — unaccepted and tagged `rejected`; avoid repeating this pattern.
  - `proposed` — no `DecisionAcceptance` exists; insufficient for execution.
- `decisions[].supersedes` / `decisions[].superseded_by`:
  - Follow `superseded_by` to the active replacement Decision. Do not execute a
    superseded Decision when a newer Decision exists.
- `truncated`, `omitted_decisions`, `omitted_knowledge`:
  - If `truncated` is `true`, narrow `--topic` or raise `--max-bytes` so
    relevant records are not omitted. Omitted records make authority context
    incomplete. Supersession- and title-linked decisions are packed atomically
    and are never clipped mid-record.
- `warnings`:
  - Check for truncation notices and for
    `"potential credential pattern withheld by best-effort secret filter"`.
    Credential filtering is a **best-effort pattern check only, not a
    confidentiality guarantee**—never store secrets in Brain records, and
    always inspect context before sending it to an agent.

To inspect one Decision's full details or lifecycle state:

```bash
uv run neural decision show <DECISION_UUID>
uv run neural decision acceptance-history <DECISION_UUID>
uv run neural decision state <DECISION_UUID>
```

---

## 4. Supply Context and Run the Chosen Agent

Use the **same** compact `neural context` output across engines. Do not build
engine-specific memory adapters or pass credentials in prompts.

| Engine | How to supply context | Evidence & runtime boundary |
| --- | --- | --- |
| **DeepSeek (via Pi)** (`deepseek/deepseek-flash`, `deepseek/deepseek-v4-pro`) | Preload the `neural context` JSON/Markdown block into the task prompt. | **Qualified** on synthetic Brain-assisted tasks (`NE-EVAL-MEMORY-UTILITY-01`, `NE-BRAIN-PRACTICAL-UTILITY-01`). Cloud escalation requires explicit operator selection. In bounded Pi (`NEURAL_PI_BOUNDED_CODE=1`), preloading is mandatory because `bash` and `read` are scope-locked. |
| **Codex** | Preload `neural context` into the task prompt (or authorize read-only `neural context` execution inside the session). | Prompt/instruction contract via `CODEX.md` and `AGENTS.md`. `CODEX_RUNTIME_ENFORCEMENT=UNPROVEN` (`docs/control-plane-governor.md`). |
| **Antigravity** | Preload `neural context` into the task prompt (or authorize read-only `neural context` execution when Brain access is enabled). | Instruction-level contract via `.agents/skills/command-protocol/SKILL.md`; no runtime Governor hook or Brain-write enforcement. |
| **Local Qwen 3.6** via `scripts/pi-local general` | Use the automatic Pi workflow above for the supported local route. | Offline native Pi and provider transport verified. Live production use requires separate authorization. |

Include an explicit instruction in the agent prompt:

> Use only the supplied ticket and scoped Brain context. A `proposed`,
> `rejected`, or superseded decision does not authorize action. If required
> approval is missing or evidence conflicts, do not modify files and end with
> `HOLD`.

---

## 5. Handle Missing or Conflicting Approval

- If the task requires prior approval and retrieved Decisions are only
  `proposed`, `rejected`, missing, or from another project: leave files
  unchanged and stop at `HOLD`.
- If two active Decisions or Knowledge statements conflict without a clear
  supersession link: inspect the full records (`neural decision show`) and
  resolve the conflict with the operator before acting.

---

## 6. Verify the Outcome

After the agent finishes, run the repository verification commands independently:

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
uv run pytest
```

Confirm no unintended files or Brain state changed.

---

## 7. Review Candidate Knowledge and Record Only With Approval

Review any new architectural choice, rejected alternative, or lesson discovered
during the task. Persist records **only after separate explicit operator
approval**:

```bash
# Record a proposed Decision (does not accept it)
uv run neural decision add \
  --project-key <PROJECT> \
  --title "<TITLE>" \
  --objective "<OBJECTIVE>" \
  --context-summary "<SUMMARY>" \
  --alternative "<OPT_A>" --alternative "<OPT_B>" \
  --proposed-option "<OPT_A>" \
  --rationale "<RATIONALE>" \
  --proposed-by "<ACTOR>" \
  --idempotency-key "<UNIQUE_KEY>"

# Explicitly accept a Decision after separate authorization
uv run neural decision accept <DECISION_UUID> \
  --accepted-by "<APPROVER>" \
  --reason "<REASON>" \
  --idempotency-key "<ACCEPT_KEY>"

# Or capture an Observation / Experience / Knowledge item when justified
uv run neural observe "<OBSERVATION_TEXT>" --tags <PROJECT>
```

---

## 8. Lightweight Observation Record (Manual Checklist)

After real development tasks, capture a brief plain-text note (for example in
your task notes or review log) to evaluate practical Brain utility without
adding automated analytics or new schemas:

```markdown
- **Date / Task**:
- **Project (`--project`)**:
- **Engine / Model**:
- **Brain evidence useful?**: yes / partial / no / none available
- **Prior decisions respected?**: yes / no (Decision IDs: ...)
- **Missing or irrelevant evidence**:
- **Unnecessary tool activity observed?**:
- **Outcome & operator corrections**:
```

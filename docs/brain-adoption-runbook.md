# Daily Brain Adoption Runbook

This runbook defines the minimal, read-first daily workflow for supplying
project-scoped NeuralEngine Brain context to existing coding and review agents
without expanding schemas, Planner enrichment, or Governor rules.

## Automatic task memory in Pi

Pi 1.6.1 supports one ephemeral print task per invocation. Configure the
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

### Completion and authorization

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
| Codex | Existing instruction-level retrieval only | Unsupported in this integration | Shared operator CLI applies existing Pi receipts | Native lifecycle enforcement unverified. |
| Antigravity | Existing instruction-level retrieval only | Unsupported in this integration | Shared operator CLI applies existing Pi receipts | No runtime lifecycle hook established. |

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

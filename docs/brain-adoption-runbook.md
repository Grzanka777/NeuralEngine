# Daily Brain Adoption Runbook

This runbook defines the minimal, read-first daily workflow for supplying
project-scoped NeuralEngine Brain context to existing coding and review agents
without expanding schemas, Planner enrichment, or Governor rules.

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
| **Local Qwen 3.6** (`neural-general` via `scripts/pi-local general` / `scripts/llm general`) | Preload `neural context` into the task prompt before starting `GENERAL` / `REVIEW` / `SEEK`. | **Unqualified on live Brain benchmarks**; contingent on local `llama-server` (`127.0.0.1:18081`) and GGUF model availability. `GENERAL` runs without a bounded Governor policy (`scripts/pi-local code` uses Nemotron Q5). |

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

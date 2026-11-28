# Operator Deployment and Daily Workflow

This document is the supported deployment contract for the stable NeuralEngine
release. It covers the canonical workspace, one-time private policy setup, the
daily task invocation for every supported engine, the trust and disclosure
boundaries, troubleshooting, backup and rollback, and portable Brain use.

Companion documents:

- [`docs/brain-adoption-runbook.md`](brain-adoption-runbook.md) — the detailed
  Brain adoption and receipt workflow.
- [`docs/stable-release-notes.md`](stable-release-notes.md) — release contents,
  supported engine matrix and known limitations.
- [`docs/architecture.md`](architecture.md) and
  [`docs/conventions.md`](conventions.md) — architecture and editing rules.

Nothing here introduces a new runtime, harness or configuration framework. Every
command reuses the existing `neural` CLI, `scripts/llm`, `scripts/pi-local` and
the existing task-memory services.

## 1. Supported operating environment

| Component | Qualified value | Notes |
| --- | --- | --- |
| Package | `neural-engine` `1.1.0` | Version lives in `pyproject.toml`. |
| Python | `3.14` via `uv` and the project `.venv` | `UV_NO_SYNC=1` keeps a validated environment reproducible. |
| Sandbox | `bubblewrap 0.13.1` | Required by the native Codex/Antigravity launcher. |
| Pi | `1.7.0` at `~/.local/bin/pi` | `scripts/pi-local` resolves this path explicitly and fails loudly when absent. |
| Codex | `codex-cli 0.172.0` | Resolved from `PATH`; see the client identity rule in §4. |
| Antigravity | `agy 1.5.18` at `~/.local/bin/agy` | Same identity rule. |
| Local Qwen | Qwen 3.6 35B A3B Q6_K on `127.0.0.1:18086` | Declared only in `llm-manifest.json`; started or borrowed by `scripts/llm`. |
| Production Brain | `/home/grzanka/Work/NeuralEngine-State` | Selected through `NEURAL_HOME`; never written by this documentation. |

`VISION.md`, `CONTEXT.md`, `memory/project-state.md` and `AGENTS.md` remain the
authoritative repository instructions. This document does not grant any
permission that those files withhold.

## 2. Canonical workspace

### 2.1 Current state

| Checkout | Path | Role |
| --- | --- | --- |
| Original source | `/home/grzanka/Work/NeuralEngine` | Dirty working checkout on the historical `ship/llm-context-ubatch-harness` branch. Preserved untouched, including a large uncommitted overlay and unpushed local commits. |
| Stable release candidate | `.agent-work/worktrees/ne-stable-release-01/candidate` | Isolated checkout of authoritative `main` plus the release patch. Review artifact only. |
| Historical candidates | `.agent-work/worktrees/ne-*` | Earlier milestone evidence. Retained, never a permanent workspace. |
| Production Brain | `/home/grzanka/Work/NeuralEngine-State` | Durable operator state. Read-only unless a separate write is authorized. |

The candidate directory is a staging area. Permanent operator policies must
never bind to it, because a later cleanup would break them.

### 2.2 Recommended destination

The canonical daily workspace is an ordinary clean Git checkout at the release
commit. The operator policy files already bind
`"workspace": "/home/grzanka/Work/NeuralEngine"`, and
`integrations/pi/extensions/neuralengine-model-lifecycle.ts` uses the same path
as its single documented install-time constant. Keeping that path avoids
editing private policy files and avoids a second configuration surface.

Therefore the transition is: bring `/home/grzanka/Work/NeuralEngine` to the
release commit, instead of introducing a new root. That operation is
destructive for the current dirty checkout and requires explicit authorization.
The exact commands, the preservation evidence and the rollback plan are in
§9.2. Nothing in this document performs it.

### 2.3 If the operator prefers a separate root

A separate clean checkout is supported by the application, because the
application reads `NEURAL_HOME`, the workspace and the project from the policy
rather than from hardcoded paths. It requires three explicit edits, taken
deliberately rather than automatically:

1. `workspace` in each of the four policy files,
2. `NEURALENGINE_PI_PROJECT_ROOT` (or the `CANONICAL_ROOT` override) for the
   Pi model-lifecycle extension,
3. the operator directory used in the daily commands.

`scripts/pi-local` and the native launcher both operate on their own checkout
root, so a second root is workable but must be chosen once and documented.

### 2.4 Local exclude

`.agent-work/` is ignored through `.git/info/exclude`, which is local
repository metadata and is not versioned. A fresh checkout shows
`.agent-work/` as untracked until the same line is added. Add it once per
checkout; do not add it to the tracked `.gitignore`, because it is operator
scratch space rather than project content.

## 3. One-time private policy setup

Create the operator directory outside the workspace, once:

```fish
mkdir -p ~/.local/state/neuralengine/templates
chmod 700 ~/.local/state/neuralengine ~/.local/state/neuralengine/templates
```

Each active policy is a strict document: unknown keys are rejected and the file
becomes unusable. Never keep a `_note`, comment field or placeholder inside an
active policy. Inactive client-trust drafts live in `templates/` and are never
passed to `--policy`.

One active policy per engine route, each with mode `0600`:

```json
{
  "workspace": "/home/grzanka/Work/NeuralEngine",
  "project": "NeuralEngine",
  "brain_home": "/home/grzanka/Work/NeuralEngine-State",
  "topic": "brain",
  "max_bytes": 4096,
  "share_with": null
}
```

| File | Disclosure | Purpose |
| --- | --- | --- |
| `codex-policy.json` | `share_with: null`, no `trust_native` | Deny Brain disclosure to Codex. |
| `antigravity-policy.json` | `share_with: null`, no `trust_native` | Deny Brain disclosure to Antigravity. |
| `deepseek-policy.json` | `share_with: null` | Deny Brain disclosure to DeepSeek. |
| `qwen-policy.json` | `share_with` = exact manifest destination | Permit Brain context for the loopback Qwen runtime only. |

The Qwen destination is derived from the authoritative manifest, never typed
from memory:

```fish
scripts/llm project-profile current-qwen36
```

Use its `destination` object verbatim:

```json
{
  "provider": "neuralengine-local",
  "model": "qwen3.6-35b-a3b-q6",
  "api": "openai-completions",
  "base_url": "http://127.0.0.1:18086/v1"
}
```

`share_with` and `trust_native` are mutually exclusive; a policy that sets both
is rejected. An optional `default_verifier` or `verifiers` entry enables the
independent-verifier lane described in §6.

Cloud disclosure stays disabled by default. Enabling
`trust_native` for Codex or Antigravity requires a separate, explicit,
per-session operator authorization, and the pin must be the binary the
launcher actually resolves.

## 4. Client identity pins

The native launcher resolves the client with `PATH` lookup and refuses any
configuration where the resolved executable is not byte-identical to the pin.
Two legitimate installations of one version therefore produce two different
pins.

```fish
readlink -f (command -s codex)
readlink -f (command -s agy)
sha256sum (readlink -f (command -s codex))
sha256sum (readlink -f (command -s agy))
```

On the Z13 host this resolves to:

| Client | Resolved executable | SHA-256 |
| --- | --- | --- |
| Codex | `~/.codex/packages/standalone/releases/0.172.0-x86_64-unknown-linux-musl/bin/codex` (via `~/.local/bin/codex`) | `ad83b94c093f0cdd8176a6bc8005a461bdf23a759863e157d40f562b8a9d664d` |
| Antigravity | `~/.local/bin/agy` | `7c96ad8c944c1a8d195ca34d2041a3d74d5166c96662b52183b748a3c455d52f` |

The distribution package `openai-codex 0.172.0-1.1` installs a second, separate
Codex build at `/usr/lib/openai-codex/bin/codex` with SHA-256
`4e5ef54fa95546646e965200cb6dd138fb76334de6776abb286b8dc5eb70b819`. It is a
different distribution of the same version, not a tampered binary. Pinning it
while `PATH` resolves the standalone build fails admission with
`NATIVE_CLIENT_IDENTITY_MISMATCH`.

Prefer one installation per client. The standalone build ships a self-updater;
after any update the digest changes and admission fails closed until the pin is
reviewed and updated deliberately.

## 5. Daily task invocation

The daily contract is one ticket file and one command per task. The ticket
content is the same for every engine:

```text
Read and execute:
.agent-work/prompts/TASK.md
```

Create that file once per task and keep it in the workspace. Then, from the
canonical workspace root in `fish`:

```fish
set task (printf 'Read and execute:\n.agent-work/prompts/TASK.md' | string collect)
set policies ~/.local/state/neuralengine
```

Codex, denial mode (default):

```fish
uv run --no-sync neural memory run codex --model gpt-6.2-sol \
  --policy $policies/codex-policy.json "$task"
```

Antigravity, denial mode (default):

```fish
uv run --no-sync neural memory run antigravity --model gemini-3.8-flash-medium \
  --policy $policies/antigravity-policy.json "$task"
```

Pi with DeepSeek:

```fish
env NEURAL_TASK_MEMORY_POLICY=$policies/deepseek-policy.json \
  scripts/pi-local deepseek -- --offline --print --no-session --no-tools -- "$task"
```

Pi with local Qwen 3.6:

```fish
env NEURAL_TASK_MEMORY_POLICY=$policies/qwen-policy.json \
  scripts/pi-local general -- --offline --print --no-session --no-tools -- "$task"
```

Use the literal `"$task"` form shown above. Fish does not support Bash
`$'...'` ANSI-C quoting, and a multi-line argument must be passed as one
collected value.

The operator does not copy Brain context, author per-task policies, manage
local model ownership or collect receipts. Each launcher attaches eligible
evidence, records its own receipt and prints the inspection command.

## 6. Receipts, verification and persistence

Every run produces an inspectable receipt outside the Brain:

```fish
neural memory show <SESSION-ID> --policy $policies/qwen-policy.json
```

| Outcome | Meaning |
| --- | --- |
| `AVAILABLE` | Eligible Brain evidence was attached. |
| `EMPTY` / `TRUNCATED` | No eligible evidence, or evidence capped by `max_bytes`. |
| `DISCLOSURE_DENIED` | The policy denies disclosure; inference proceeds without Brain context. |
| `RETRIEVAL_ERROR` / `INTEGRITY_ERROR` | The task stops before inference. |
| `NO_VERIFIER` | The task completed; no independent verifier is configured. |
| `INTERRUPTED` | The task was cancelled and settled as interrupted. |

Learning preparation requires an independently maintained verifier configured
in the policy and pinned by digest. Without one, a completed task yields
`NO_VERIFIER` and no candidate: NeuralEngine does not claim automatic learning
when no independent verifier is configured.

Persistence is separate and explicit:

1. The verifier emits a candidate.
2. The receipt shows `AWAITING_AUTHORIZATION` with the complete authorization
   command.
3. The operator runs that exact command. The digest binds the authorization to
   that private receipt.
4. Apply rechecks Brain identity and conflicts through the existing Brain Trust
   coordinator.
5. Accepting a Decision remains a separate authority operation.

The operator workflow therefore distinguishes ordinary task execution,
authorized Brain context retrieval, cloud disclosure, learning-candidate
preparation, authorized persistence and acceptance of proposed Decisions.
None of these imply the next.

## 7. Trust and disclosure boundaries

| Boundary | Enforced behaviour |
| --- | --- |
| Cloud Brain disclosure | Denied by default for Codex, Antigravity and DeepSeek through `share_with: null`. |
| Trusted native disclosure | Requires `trust_native` in the active policy, matching engine, model, executable and digest, plus operator authorization for that session. |
| Local Qwen disclosure | Permitted only for the exact loopback destination from the manifest. |
| Production Brain writes | Never implied by retrieval, completion or a receipt. Require exact-digest authorization plus Brain Trust. |
| Decision acceptance | Separate from proposal and from persistence. |
| Brain masking | The native launcher mounts a temporary filesystem over the selected Brain, the receipts directory, the inherited and default Neural homes before starting the client. |
| Route overrides | Recognized API-key and base-URL overrides are rejected for a trusted native launch. |

Filesystem scope is the launcher and its descendants. A host process, an
external MCP server or an editor integration keeps its own access unless it is
started through the launcher.

## 8. Troubleshooting

### The launcher refuses to start the native client

| Symptom | Cause and fix |
| --- | --- |
| `NATIVE_CLIENT_IDENTITY_MISMATCH` | The pinned executable is not the one `PATH` resolves, or the digest changed after a client update. Re-run §4 and update the pin deliberately. |
| `NATIVE_ROUTE_OVERRIDE` | A recognized API-key or base-URL variable is set in the environment. Unset it; a trusted launch must use the client's own sign-in. |
| `NATIVE_BRAIN_HOME_INVALID` | `brain_home` is not an absolute, resolved, existing directory. |
| `NATIVE_PROTECTED_PATH_OVERLAP` | The workspace overlaps the Brain, the receipts directory or a Neural home. Choose a workspace outside them. |
| Launcher exits before the client starts | `bubblewrap` is missing or cannot create its namespaces. `bwrap --version` must report `0.13.1`. |

### A tool call inside the client fails with `Permission denied (os error 13)`

This was a real defect and is fixed in this release. `bwrap --bind / /` exposes
host device nodes that a capability-free child cannot open, so any tool that
redirects stdio to `/dev/null` failed with `EACCES`. The launcher now supplies a
private `--dev /dev`. If the symptom returns, check that the installed launcher
still passes `--dev`, and confirm with:

```fish
bwrap --die-with-parent --unshare-pid --bind / / --dev /dev --proc /proc \
  --chdir /tmp -- python3 -c 'open("/dev/null","w").write("")'
```

### The task completes but no learning candidate appears

`NO_VERIFIER` is expected when the policy has no `default_verifier` or
`verifiers` entry. Add an independently maintained verifier and pin its digest;
do not treat model prose as verification.

### The receipt says `DISCLOSURE_DENIED`

That is the default for Codex, Antigravity and DeepSeek. It is not an error.
Enabling disclosure requires the §7 authorization.

### `neural doctor` reports `NOT READY`

Read the `Home`, `Brain`, `Integrity` and `Manifest` sections in order. A
fingerprint mismatch means a record changed outside the supported write path.
Do not edit records by hand; use the existing separately authorized recovery
procedure.

### The local Qwen runtime does not start

`scripts/llm` owns the runtime lifecycle. Check the manifest endpoint and the
owned-state record, then let the script start or borrow the runtime. Do not
start a second `llama-server` by hand; a second process on the same port breaks
the STARTED/BORROWED ownership accounting.

### A T3 Code chat turn produces no receipt

Expected. T3 Code is supported as an operator interface, not as a receipt
producer. A T3 chat turn is host-managed and never enters this launcher, so it
cannot be policy-checked or settled. Use the terminal invocation from §5 for any
task that must produce a receipt. Hooks, interactive, resumed and desktop
sessions were assessed and remain unqualified; no desktop application or
additional orchestration layer is introduced to change that.

## 9. Backup, rollback and preservation

### 9.1 Backups

| Artifact | Location | Verified |
| --- | --- | --- |
| Original source checkout | `/run/media/grzanka/g7c/Backups/NeuralEngine/NeuralEngine-20261127-101750.tar` (`766` MB) | SHA-256 sidecar verification passed. |
| Production Brain | No separate archive exists. The repository backup does not cover it. | Tree fingerprint and manifest aggregate recorded read-only. |

A source-repository backup is not a Brain backup. Before any authorized Brain
write, take a separate copy of `/home/grzanka/Work/NeuralEngine-State` and verify
it; this release does not do that on the operator's behalf.

### 9.2 Reversible transition to the canonical workspace

Presented for authorization, not executed. The dirty checkout contains
unpushed commits and a large uncommitted overlay, so step 1 is mandatory.

```fish
# 1. Preserve the current checkout exactly (new archive, never overwrite).
set stamp (date -u +%Y%m%dT%H%M%SZ)
tar -C /home/grzanka/Work -cf /run/media/grzanka/g7c/Backups/NeuralEngine/NeuralEngine-overlay-$stamp.tar NeuralEngine
sha256sum /run/media/grzanka/g7c/Backups/NeuralEngine/NeuralEngine-overlay-$stamp.tar

# 2. Record the current fingerprints for comparison.
git -C /home/grzanka/Work/NeuralEngine status --short | sha256sum
git -C /home/grzanka/Work/NeuralEngine diff --binary | sha256sum

# 3. Archive the historical branch locally; never delete it.
git -C /home/grzanka/Work/NeuralEngine branch archive/source-overlay-$stamp

# 4. Install the release tree into the canonical root and keep one clean state.
```

Rollback plan:

1. Verify the archive from step 1.
2. Restore `/home/grzanka/Work/NeuralEngine` from that archive.
3. Re-check `HEAD`, the `status --short` fingerprint and the `diff --binary`
   fingerprint against the recorded values.
4. Confirm `neural doctor` still reports `TRUSTED_CURRENT` for the production
   Brain, which no step above writes.

### 9.3 What this release never does

It does not reset, stash, clean, remove or overwrite the original checkout, and
it does not delete historical branches, worktrees, reviews, artifacts or
backups. Any destructive cleanup requires a separate, bounded authorization.

## 10. Portable Brain

The application never hardcodes a Brain path. `NEURAL_HOME` is resolved in one
place (`src/neural_engine/core/paths.py`) with these rules:

- an unset variable means `~/.neural`,
- an override must be absolute,
- `~` is neither expanded nor accepted,
- a missing, non-directory or unreadable path raises an explicit error,
- there is no silent fallback.

That contract is what makes the portable workflow possible: the same code, the
same trust and integrity validation and the same identity checks run against a
store on a portable medium or on a second host.

Verified for this release:

1. A relative, `~`-prefixed, blank or missing `NEURAL_HOME` is rejected with an
explicit error and no fallback.
2. `neural init` creates a Neural home at an arbitrary absolute path and
   `neural doctor` runs there. A fresh binding without trust metadata reports
   `RECOVERY_REQUIRED` and refuses controlled mutation until the existing
   separately authorized adoption or recovery step runs. This release does not
   perform that step.
3. The complete production store was copied read-only, relocated twice to
   different absolute paths (a Z13-style layout and a work-style layout), and
   reported `TRUSTED_CURRENT` with an identical manifest aggregate each time.
4. Editing one record in the relocated copy outside the supported write path
   changed the aggregate and failed `Filename/payload identity`; restoring the
   record restored the aggregate and the `TRUSTED_CURRENT` state.
5. The production store itself still reports the accepted manifest aggregate
   afterwards, so none of the above wrote to it.

Documented limits:

- This release adds no synchronization, replication, store merging or migration.
  Copy the directory; do not merge two stores.
- Two hosts using two copies diverge immediately. Treat one as authoritative
  and copy in one direction only.
- The production portable Brain is not accessed or mutated by this release.
- Host-specific values that remain are deployment data, not application logic:
  the `llm-manifest.json` model paths and runtime binary, the optional
  `scripts/challenger` PATCH server path, and the `CANONICAL_ROOT` install
  constant with its environment override.

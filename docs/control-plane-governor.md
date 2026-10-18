# Governor v1 control plane

`control-plane/governor.ts` owns policy parsing, SHA-256 identity, capabilities,
mode decisions, budgets, scope requests, and verdict state. It has no Pi import.
`.pi/extensions/neuralengine-guard.ts` is the sole live adapter. It maps Pi
session, prompt, tool, compaction, and agent-end hooks to neutral events.

Bounded Pi activation is unchanged: set `NEURAL_PI_BOUNDED_CODE=1` and
`NEURAL_PI_POLICY_FILE`. A policy path alone also activates it. Missing or invalid
policy stops before prompt admission. Plain interactive Pi stays unbounded.

For named v1 runs, set `RUN_ID` and absolute `WORKSPACE_ROOT`. The latter must
realpath to the launcher's project root. `POLICY_REVISION` defaults to 1;
`MODE` defaults to `BOUNDED_EXECUTE`; `ROLE` defaults to `CODE`. Legacy policies
without `RUN_ID` retain their v0 default and status behavior. Policy identity is
SHA-256 of recursively key-sorted JSON of the parsed, default-filled policy.
`legacy-v0` is compatibility-only and is not valid for controlled benchmark
qualification. M4 qualification must use `parseQualificationPolicy()` with a
non-legacy `RUN_ID`, an absolute authoritative `WORKSPACE_ROOT`,
`POLICY_REVISION` at least 1, and `MODE=BOUNDED_EXECUTE` (or an approved
`EXPANDED_EXECUTE` revision). Controlled qualification policies must explicitly
provide both `MAX_REPEATED_FAILURES` and `MAX_TOTAL_CORRECTIONS`. The parser
does not fill either field for qualification: their values are part of the
immutable canonical policy and its SHA-256 execution identity. Ordinary and
legacy policies may still use the compatibility fallbacks. Set `WORKSPACE_ROOT`
to the absolute root of the current checkout, referred to as `$REPO_ROOT` in
operator examples. Do not use a plain legacy policy for M4.
The Pi session snapshot records the hash, revision, run ID, counters, tool
decisions, validation results, scope requests, model claim, and verdict inputs.
`auditRecord()` exposes the deterministic logical run artifact. Pi persists
snapshots in its existing non-model-visible session entries; no Brain record is
written.

Modes are `OBSERVE` (listed evidence reads), `DISCOVER` (workspace reads and
searches), `BOUNDED_EXECUTE` (scoped edits), `PATCH` (at most one touched file
and 30 deleted lines), and `EXPANDED_EXECUTE` (scoped edits with an approved
predecessor). `REVIEW` and `VISION` roles deny mutation. `CODE` and `PATCH`
roles may mutate only when mode and policy permit. `ROLE=PATCH` requires the
explicit narrow `MODE=PATCH`, and `MODE=PATCH` is invalid for every other role.
Model selection stays outside the Governor.

An out-of-scope read or edit returns `REQUEST_SCOPE_EXPANSION`, never an allow.
The request records path, capability, reason, evidence reference, and run ID.
Absent evidence is marked `UNKNOWN` and must be supplied before approval.
A trusted control-plane operator reviews evidence,
creates a new policy with the same `RUN_ID`, incremented `POLICY_REVISION`,
`MODE=EXPANDED_EXECUTE`, and `PREVIOUS_POLICY_SHA256` equal to the old hash,
with `EVIDENCE_PACK_REF` pointing to the reviewed workspace evidence pack and
`EVIDENCE_PACK_SHA256` binding its exact bytes,
then resumes the Pi session with that policy. State restoration accepts this
exact predecessor chain and retains counters. A model cannot grant its own
request through a tool result or final text. The active policy file cannot be
edited through Pi's file tools.

Shell classification uses a deliberately small grammar. Exact configured
validation commands, simple Git inspection commands, and path-checked `cat`,
`find`, or `rg` reads are allowed. Ambiguous shell expressions, Git mutations,
network commands, and system mutations are denied in bounded modes. This is a
tool boundary, not a sandbox for an uncontrolled process.

## Git authority

The canonical policy is the same for every provider or host:

```text
GIT_READ=ALLOW
GIT_STAGE=BOUNDED
GIT_COMMIT=EXPLICIT_AUTHORIZATION
GIT_PUSH=SEPARATE_EXPLICIT_AUTHORIZATION
GIT_FORCE_PUSH=DENY
GIT_REMOTE_CHANGE=DENY
GIT_AUTH_MUTATION=DENY

GPT_DESKTOP_POLICY=SAME_GOVERNOR_POLICY
CODEX_POLICY=SAME_GOVERNOR_POLICY
GPT_DESKTOP_RUNTIME_ENFORCEMENT=UNPROVEN
CODEX_RUNTIME_ENFORCEMENT=UNPROVEN
```

Policy definition does not prove a host routes its tools through Governor:
`POLICY_DEFINED != RUNTIME_ENFORCEMENT_PROVEN`. No GPT Desktop or Codex runtime
adapter is implemented here. The current Pi adapter also retains its separate
stricter Git mutation guard. Host identity does not grant extra Git authority.

Git policy is additive to execution-mode and role checks. `OBSERVE` continues
to accept file evidence only; Git shell reads do not bypass that rule. Outside
`OBSERVE`, read operations include status, diff, log, show, current branch,
`rev-parse`, `remote -v`, `rev-list`, and guarded fetch. Fetch is rejected if a
configured refspec could update a local branch or worktree ref.

Exact staging paths must be changed paths listed in
`AUTHORIZED_GIT_STAGE_PATHS`. Broad staging (`git add .`, `git add -A`, or
`git add --all`) needs a separately reviewed changed-path snapshot and explicit
operator approval. Git policy evaluates authority; it does not execute staging,
commit, or push commands.

`EDIT != STAGE`, `STAGE != COMMIT`, `COMMIT != PUSH`, and `PUSH != PR`. Each is a
separate authority transition; approval for one never authorizes the next.

Commit preflight records repository, branch, `HEAD`, staged paths and diff
digest, unstaged paths, and the exact message. Push preflight records repository,
branch, `HEAD`, matching upstream, one configured push URL identity, and
ahead/behind counts. The push URL itself is never included in the review; its
opaque comparison digest is internal and must not be rendered. A mismatch
invalidates the preflight and stops the run.
Commit and push each require their own explicit operator approval; neither
approval grants authority for the other operation. Push preflight is limited
to the reviewed `HEAD` and matching upstream with exactly one outgoing commit
and none incoming. Tags and pull requests are outside this permission.

The authorization snapshot is an in-process preflight value, not an execution
lock. `AUTHORIZATION_PREFLIGHT=PROVEN`; `ATOMIC_EXECUTION_GUARANTEE=NO`;
`HOST_MUST_RECHECK_IMMEDIATELY_BEFORE_EXECUTION=YES`. Git state can change
after any preflight and before the separate process runs; this policy makes no
race-free or cross-process serialization claim. An invalidated review returns
`AUTHORIZATION_INVALIDATED=YES` and `STOP`.

Force push (including `--force-with-lease`), remote configuration changes,
and recognized credential/authentication changes are denied. File tools
protect `.git` metadata paths and files named exactly `.gitmodules`; ordinary
project paths containing `.ssh` text are not protected on that basis. Git
configuration and SSH files outside the repository are outside file-tool
scope. These path checks and command classification are not a shell sandbox;
hosts must stop on interactive authentication and must not work around it.

Final assistant text is stored as `model_claim`; it never sets GREEN. GREEN
requires successful configured validation tool results after the latest source
edit. Different failed validation output digests count as new evidence for
correction progress. Consecutive identical failures consume
`MAX_REPEATED_FAILURES` (default 2); every failed validation consumes the
independent `MAX_TOTAL_CORRECTIONS` budget (default 6), even with new evidence.
At one repeat or at the sixth total failure, Governor requests a replan; a
second repeat or seventh total failure stops the run. A new digest clears
repeat pressure but preserves the total count and the distinct evidence count.
Successful validation clears repeat pressure and permits GREEN while preserving
total correction history. `MAX_CORRECTION_CYCLES` remains accepted as the
repeated-failure limit when `MAX_REPEATED_FAILURES` is absent, preserving old
policy hashes; old snapshots reconstruct total history from validation results.
Compaction, tool/read counters, and elapsed run time remain visible. The Evidence Compiler
is deterministic and labels hypotheses as `INFERRED` by default.

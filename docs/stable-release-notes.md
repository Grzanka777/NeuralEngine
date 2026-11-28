# Stable Release Notes — post-`v1.1.0` consolidation

These notes cover the `NE-STABLE-RELEASE-01` consolidation: a stable-release
candidate for daily operator deployment across the four supported engines.

## Proposed version

`1.1.1` — proposed, **not applied**.

Derivation from the repository's actual contract:

- The package version is declared once, in `pyproject.toml`, and is `1.1.0`.
- `CONTEXT.md` records annotated release tags `v1.0.0` and `v1.1.0`, with
  `v1.1.0` at release commit `f9b74c652b2000e1d5eedf16fc1e3427a6ff3b2b`.
- The release base `41ffda2b12634e99cd033936b075c6e5f467421c` is **after**
  `v1.1.0`, so this candidate is a post-release change.
- The change set is a defect fix plus documentation. It adds no capability
  removal, no schema change and no incompatible behaviour. That is a patch
  release under the observed `v1.x` sequence.

The version bump and the tag are release-owner operations. They are not applied
here, because `CONTEXT.md` binds the package version to the release commit and
because creating a release requires explicit authorization.

If the release owner prefers to hold the version until more post-`v1.1.0` work
accumulates, the candidate is still correct as it stands: no code depends on a
new version string.

## Base and candidate

| Item | Value |
| --- | --- |
| Authoritative base | `41ffda2b12634e99cd033936b075c6e5f467421c` (merge of `f9e10bc291322b95da4c9ab6f91f810ad61f48f6` and `28c2de0f1cade55b802b5701579b144bf7b7d8be`) |
| Base tree | `abef47bc62b6a7f13741e44fb187ef8e2f3b0b8d` |
| Candidate | `.agent-work/worktrees/ne-stable-release-01/candidate` |
| Candidate scope | 7 paths: 5 modified, 2 added |

The authoritative base is not reachable from this checkout's `origin/main`
reference, which is stale at `3af8eb84d666a6eaeef9721446db460fb8f4b5b8`
(2026-10-17). The base commit object is present in the preserved isolated clone
at `.agent-work/worktrees/ne-multi-engine-adoption-01/candidate`, and the
candidate was built from it there. Remote re-verification requires network
egress, which needs operator approval in this environment.

## What changed

### 1. Native tool execution inside the launcher namespace (defect fix)

`src/neural_engine/infrastructure/task_memory_native.py` now passes `--dev /dev`
to `bwrap`.

Reproduced cause: the launcher binds `/` read-write, which exposes host device
nodes. A capability-free child cannot open them, so `/dev/null` failed with
`EACCES` and any tool call that redirected stdio to `os.devnull` failed with
`Permission denied (os error 13)`. The previous review attributed that failure
to the PID namespace; the PID namespace is not the cause, and nested process
spawn works there. The device node was the cause.

Effect: a private devtmpfs restores `/dev/null`, `/dev/full`, `/dev/random` and
`/dev/tty` without exposing host devices (`btrfs-control`, `console`, raw block
and character devices are no longer visible). Isolation improves rather than
weakens.

`tests/test_task_memory.py` asserts the regression: a tool that opens
`os.devnull` inside the masked namespace must succeed.

### 2. Operator documentation

- `docs/operator-deployment.md` (new) — supported environment, canonical
  workspace and its relationship to the preserved source checkout, one-time
  private policy setup, client identity pins, fish daily commands for all four
  engines, receipts and authorization chain, trust and disclosure boundaries,
  troubleshooting, backup and rollback, portable Brain.
- `docs/brain-adoption-runbook.md` — obsolete capability rows replaced. Codex
  and Antigravity are no longer described as "instruction-level retrieval only"
  with unsupported result collection; they have a native `neural memory run`
  lane with settlement. The Pi version statement no longer names a version the
  host does not run.
- `README.md`, `CONTEXT.md` — pointers to the two new documents and one
  current-state entry for the consolidation.

No Planner, Governor, Command Protocol, Brain schema, acceptance object,
orchestrator, harness, database or desktop application was added or changed.

## Supported engine matrix

| Engine | Route | Entry point | Brain disclosure default | Runtime ownership |
| --- | --- | --- | --- | --- |
| Codex (native CLI) | `neural memory run codex` | `codex-cli 0.172.0` via bubblewrap | Denied (`DISCLOSURE_DENIED`) | External client |
| Antigravity (native CLI) | `neural memory run antigravity` | `agy 1.5.18` via bubblewrap | Denied (`DISCLOSURE_DENIED`) | External client |
| DeepSeek (via Pi) | `scripts/pi-local deepseek` | Pi `1.7.0`, `deepseek-flash` | Denied (`share_with: null`) | Pi |
| Local Qwen 3.6 Q6_K (via Pi) | `scripts/pi-local general` | Pi `1.7.0`, manifest profile `current-qwen36` | Permitted for the exact loopback destination | `scripts/llm`, STARTED/BORROWED |
| T3 Code | Operator interface | T3 drivers | Not applicable | Host-managed |

Claude Code compatibility is preserved at the architecture level. Claude Code
implementation and activation are outside this release.

## Known limitations

1. **T3 Code chat turns produce no receipt.** A host-managed T3 session cannot be
   policy-checked, cannot enter this launcher and cannot be settled. Use the
   terminal invocation for any task that must produce a receipt. Hooks,
   interactive, resumed and desktop sessions are unqualified. No desktop
   application or extra orchestration layer is introduced to change that.
2. **No automatic learning without an independent verifier.** Without a
   digest-pinned verifier in the policy, a completed task yields `NO_VERIFIER`
   and no candidate. Model prose is never treated as verification.
3. **Trusted native disclosure remains a client-trust boundary.** The launcher
   attests the executable, its digest, the requested model, route-override
   absence and the native session ID. It cannot attest the effective account,
   provider forwarding, upstream model, provider payload or retention. The
   templates in `~/.local/state/neuralengine/templates/` are inactive, carry a
   deliberate unknown key and are rejected by the loader.
4. **Two legitimate Codex installations produce two digests.** The pin must
   match the executable `PATH` resolves. The standalone build ships a
   self-updater, so a client update breaks admission closed until the pin is
   reviewed.
5. **Sensitive to a stale `origin/main`.** The source checkout's remote
   tracking reference is behind the authoritative base; remote verification
   needs network egress.
6. **`.agent-work/` exclusion is local metadata.** `.git/info/exclude` is not
   versioned, so a fresh checkout shows it as untracked until the same line is
   added.
7. **Host-specific deployment data remains.** `llm-manifest.json` model paths
   and runtime binary, the optional `scripts/challenger` PATCH server path
   (no environment override) and the `CANONICAL_ROOT` install constant. The
   application layer (`src/`) contains no host-specific absolute path.
8. **No synchronization, replication, store merging or migration.** Portability
   is directory relocation, verified. Two hosts using two copies diverge.
9. **Native live qualification boundaries.** The recorded live evidence is one
   disclosure-denied headless turn per cloud engine plus one
   operator-trust turn each against a synthetic Brain. No paid or
   subscription-backed inference was made in this consolidation.

## Verification summary

| Check | Result |
| --- | --- |
| `ruff format --check` (219 files) | PASS |
| `ruff check` | PASS |
| `mypy src tests` (213 files) | PASS |
| `pytest tests/test_task_memory.py` | 56 passed |
| Full regression, isolated environment | see below |
| `git diff --check` | PASS |
| Credential-pattern scan of added lines | 0 matches, 12 patterns |
| Production Brain read-only doctor | `TRUSTED_CURRENT`, integrity `PASS`, manifest `PASS`, `READY`, 22 records in 15 stores, aggregate `10c90630…` |

The complete diff, per-file hunk summary, patch identity and the exact
validation transcript are in
`.agent-work/reviews/NE-STABLE-RELEASE-01.md`.

## Authorization boundaries

None of the following is performed by this release:

1. Commit, push, merge, tag or publish.
2. The `1.1.1` version bump.
3. Replacing the dirty canonical checkout with the release tree (§9.2 of
   `docs/operator-deployment.md`), including its archive step.
4. Any production Brain write, persistence or Decision acceptance.
5. Any production cloud disclosure, including activating `trust_native`.
6. Any Codex or Antigravity client pin update.
7. Any further paid or subscription-backed live qualification.
8. Any destructive cleanup of the historical overlay, branches or worktrees.

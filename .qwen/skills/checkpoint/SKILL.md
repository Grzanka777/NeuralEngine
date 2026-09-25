---
name: checkpoint
description: Capture review evidence tied to the exact current repository or system state during critical work.
---

# CHECKPOINT adapter

Use this skill at a critical phase boundary. Follow the canonical [CHECKPOINT contract](../../../docs/command-protocol/COMMAND_PROTOCOL_v1.2.md) and [Engineering Workflow](../../../docs/command-protocol/ENGINEERING_WORKFLOW_v1.1.md).

Bind the checkpoint to the user's explicitly requested scope root. For a file
or directory scope, record that root, the relevant file inventory, SHA-256
hashes, and target-specific validation. Use branch/HEAD and repository-wide
diff or status only when the scope root is the repository. Do not substitute
unrelated repository, worktree, or Brain state for target identity. Mark
unavailable evidence `UNVERIFIED` instead of inferring it.

When hashes are required, run an available SHA-256 tool on the exact in-scope
files and copy each returned hash and path verbatim. Never invent, reconstruct,
or pattern-generate a hash. If the tool output is unavailable, mark that hash
`UNVERIFIED` and do not claim the checkpoint is valid. Record validation state
only from directly observed target-specific evidence.

Record the verdict, state identity, changed paths, validation, change summary,
scope audit, blockers, deviations, and remaining risks. Material changes within
the scope root make an earlier checkpoint stale.

---
name: verify
description: Run the applicable declared checks and report fresh, exact verification evidence.
---

# VERIFY adapter

Use this skill when behavior or a claim needs verification. Follow the repository's validation requirements and the [VERIFY contract](../../../docs/command-protocol/COMMAND_PROTOCOL_v1.2.md).

Resolve the exact claim and user-requested target before checking. The target is
the scope root; verify only that claim using direct in-scope evidence such as
exact paths, contents, hashes, and target-specific command output. Do not
broaden verification or substitute branch/HEAD, repository-wide Git state,
unrelated worktree state, or Brain state for target evidence. If required
evidence is unavailable in scope, report `UNVERIFIED`; request authorization
before expanding scope.

When the claim requires a hash, obtain it by running a hash tool on the exact
in-scope file and copy the returned value verbatim. Never invent or reconstruct
hashes. If the tool result or a required before-state hash is unavailable, mark
the affected comparison `UNVERIFIED` rather than claiming a change or no
change.

Prefer focused checks before broader checks. Run only relevant, authorized
commands; preserve test specifications. If a runner or dependency is missing,
do not install packages or rewrite tests to adapt the environment. Report each
exact command, observed result, failure, and unverified item.

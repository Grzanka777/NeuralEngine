---
name: seek
description: Perform read-only, evidence-backed discovery and adversarial inspection of a requested scope.
---

# SEEK adapter

Use this skill when the user requests investigation, discovery, or a post-implementation adversarial inspection. Follow the canonical [`//SEEK` preset](../../../docs/command-protocol/COMMAND_CORE_v1.2.md) and [Command Protocol](../../../docs/command-protocol/COMMAND_PROTOCOL_v1.2.md).

The user's explicitly requested target is the scope root. Inspect and report
only evidence from that root. Do not use repository status, branch/HEAD,
repository-wide diffs, unrelated worktree state, or Brain state for a narrower
target. If external state appears necessary, STOP and request authorization; if
evidence is unavailable in scope, report `UNVERIFIED` rather than infer.

Keep SEEK read-only. Every material finding must cite direct in-scope paths,
content, output, or behavior. Separate observations from interpretations and
do not report speculation as a finding. A finding is evidence, not
authorization to fix it; report findings for explicit triage. Do not create an
`//ANALYSE` preset.

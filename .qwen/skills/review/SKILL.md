---
name: review
description: Review a requested change against its scope, contracts, compatibility, data safety, and evidence.
---

# REVIEW adapter

Use this skill when the user asks for a change review or when the canonical workflow requires a review phase. Follow the [Command Protocol](../../../docs/command-protocol/COMMAND_PROTOCOL_v1.2.md), [Engineering Workflow](../../../docs/command-protocol/ENGINEERING_WORKFLOW_v1.1.md), and repository instructions.

The user's explicitly requested target is the scope root. Review only that
target and evidence directly required to understand it. Do not inspect or
report unrelated repository status, branch/HEAD, worktree dirt, or Brain state
for a narrower target. If external state appears necessary, STOP and request
authorization. Findings must cite direct in-scope evidence; report
`UNVERIFIED` when evidence is absent instead of inferring.

Prioritize material correctness, data loss, security, compatibility,
concurrency, migration safety, and missing evidence. Report findings with
in-scope locations and severity; do not modify files as part of a review.
When the request specifies verdict, evidence, scope, blockers, and unverified
items, return only those fields with those labels. Base the verdict on the
observed in-scope evidence; mark unsupported items `UNVERIFIED` rather than
filling gaps with inference.

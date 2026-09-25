---
name: review
description: Review a requested change against its scope, contracts, compatibility, data safety, and evidence.
---

# REVIEW adapter

Use this skill when the user asks for a change review or when the canonical workflow requires a review phase. Follow the [Command Protocol](../../../docs/command-protocol/COMMAND_PROTOCOL_v1.2.md), [Engineering Workflow](../../../docs/command-protocol/ENGINEERING_WORKFLOW_v1.1.md), and repository instructions. Inspect the actual diff and relevant surrounding code. Prioritize material correctness, data loss, security, compatibility, concurrency, migration safety, and missing evidence. Report findings with locations and severity; do not modify files as part of a review.

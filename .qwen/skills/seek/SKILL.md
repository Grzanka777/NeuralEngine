---
name: seek
description: Perform read-only, evidence-backed discovery and adversarial inspection of a requested scope.
---

# SEEK adapter

Use this skill when the user requests investigation, discovery, or a post-implementation adversarial inspection. Follow the canonical [`//SEEK` preset](../../../docs/command-protocol/COMMAND_CORE_v1.2.md) and [Command Protocol](../../../docs/command-protocol/COMMAND_PROTOCOL_v1.2.md).

Keep SEEK read-only. Cite the exact source, path, output, or behavior supporting each material finding. Record uncertainty and scope limits. A finding is evidence, not authorization to fix it; report findings for explicit triage. Do not create an `//ANALYSE` preset.

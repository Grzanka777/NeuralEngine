---
name: recheck
description: Revalidate whether the proposed next critical phase still fits the latest checkpoint and current evidence.
---

# RECHECK adapter

Use this skill before continuing a multi-phase critical task. Apply the canonical [RECHECK contract](../../../docs/command-protocol/COMMAND_PROTOCOL_v1.2.md): compare the latest checkpoint with current state, requirements, scope, exclusions, dependencies, blockers, and planned validation. Return exactly `PROCEED`, `REVISE`, or `STOP`, with the required scope correction or blocking reason. `PROCEED` authorizes the plan, not execution; the next phase still needs an explicit launch.

---
name: recheck
description: Revalidate whether the proposed next critical phase still fits the latest checkpoint and current evidence.
---

# RECHECK adapter

Use this skill before continuing a multi-phase critical task. Apply the canonical [RECHECK contract](../../../docs/command-protocol/COMMAND_PROTOCOL_v1.2.md): compare the latest checkpoint and current evidence within the user's explicitly requested scope root against requirements, exclusions, dependencies, blockers, and planned validation. Do not use unrelated repository, worktree, or Brain state to decide a narrower task. If external state is necessary, return `STOP` and request authorization. Return exactly `PROCEED`, `REVISE`, or `STOP`, with the required scope correction or blocking reason. `PROCEED` authorizes the plan, not execution; the next phase still needs an explicit launch.

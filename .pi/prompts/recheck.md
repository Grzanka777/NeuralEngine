---
description: Decide a Command Protocol recheck
argument-hint: "[checkpoint]"
---
Use the `command-protocol` skill. Interpret this as `RECHECK $ARGUMENTS` under `AGENTS.md`. Compare the proposed next phase with the latest checkpoint, current state, requirements, blockers, scope, exclusions, and validation needs. Output exactly one verdict token on the first line: `PROCEED`, `REVISE`, or `STOP`. Do not repeat the verdict token. Then give brief evidence; for a required revision, give the corrected scope or prompt; for a stop, name the blocker. A proceed verdict authorizes the plan only. Never launch the next phase automatically.

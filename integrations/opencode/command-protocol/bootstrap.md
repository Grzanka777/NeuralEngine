# NeuralEngine Command Protocol bootstrap

This small bootstrap recognizes the canonical Command Protocol tokens and
loads the `command-protocol` skill when their semantics are needed. Direct
canonical syntax remains primary; native slash commands are convenience
adapters only.

Recognized tokens include `//SEEK`, `//FIX`, `//ARCH`, `//SHIP`, `//RESEARCH`,
`//OPTIMIZE`, `//KILL`, `CHECKPOINT`, `RECHECK`, and `NEXT`.

Preserve the nearest project `AGENTS.md` as the authority for repository
rules. Preserve the NeuralEngine/Brain boundary and all data-safety rules.
Do not invent unknown commands. `PROCEED` is a review verdict and never
starts the next phase automatically. This bootstrap never authorizes commit,
push, delete, deploy, or other irreversible work.

The full Protocol/Core/Workflow documents are references for the skill, not
embedded bootstrap content.

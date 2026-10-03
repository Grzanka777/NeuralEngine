# NeuralEngine Pi adapter

`AGENTS.md` is the repository authority discovered by Pi. Load the project
context through `neuralengine-development` and the canonical skill at
`.claude/skills/neuralengine/SKILL.md` before engineering work.

Pi integration baseline: 1.0.0; verify the installed version separately.
GENERAL is local Qwen3.6, CODE is local Nemotron Q5, and PATCH is local GPT-OSS.
VISION is UNFILLED and refused. REVIEW and SEEK are workflow overlays on
GENERAL, not separate model capabilities. CODE and PATCH require the bounded
Governor policy through `scripts/pi-local`; confirmation cannot bypass it.

Cloud escalation is explicit operator selection only. DeepSeek FLASH
(`deepseek/deepseek-flash`) and PRO (`deepseek/deepseek-v4-pro`) are optional
cloud choices. There is no automatic cloud fallback. Credentials belong in
Pi's private authentication store or environment, never this repository.

GLOBAL resources are installed from `integrations/pi/manifest.json` through
`scripts/sync-pi-resources` into `~/.pi/agent/`: Command Protocol and lifecycle
extension each load once. Project-local `.pi/` owns Guard, skills, prompts,
and settings. Model selection triggers lifecycle acquisition; shutdown stops
only the exact session-owned runtime, preserving borrowed and replaced PIDs.

Command Protocol meaning remains owned by `docs/command-protocol/`; packaged
references match those canonical sources. Adapters do not redefine semantics.
Brain writes, durable-state mutation, and Git mutation require separate
explicit authorization. Guard preserves protected-command confirmation outside
bounded execution and fails closed without interactive confirmation. It is
defense in depth, not a shell sandbox.

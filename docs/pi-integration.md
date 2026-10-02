# Pi integration

Pi 1.0.0 (project baseline) is configured as a thin, DeepSeek-only
NeuralEngine client through the project `.pi/` configuration. Verify the
running version with `pi --version`; the integration uses only stable
mechanisms (project settings, skills, prompt templates, and the `tool_call`
extension hook) and does not depend on version-specific behavior.

## Launch

From this repository:

```bash
pi
```

On the first run, approve this project when Pi asks to load project settings,
skills, prompts, and the guard extension. `pi --approve` is the verified
one-run alternative. Pi discovers the nearest `AGENTS.md` automatically; the
project `APPEND_SYSTEM.md` only points Pi at the additional NeuralEngine
context and canonical authorities.

The reusable NeuralEngine Development adapter loads the canonical
`.claude/skills/neuralengine/SKILL.md`. The Command Protocol adapter and its
prompt templates are referenced directly from
`integrations/opencode/command-protocol/`; no Pi semantic copy is maintained.

## DeepSeek-only project policy

The project `enabledModels` scope is exactly:

```json
["deepseek/*"]
```

Only the DeepSeek provider is enabled for the project. The project does not
enable `openai`, `openai-codex`, `google`, or any other native Pi provider.
This matches the authenticated account used for this worktree: DeepSeek only.

| Model reference | Role | Notes |
| --- | --- | --- |
| `deepseek/deepseek-flash` | FLASH (default) | Default execution model |
| `deepseek/deepseek-v4-pro` | PRO (escalation) | Architecture, persistence, security, critical reasoning |

Pi matches each `enabledModels` pattern with `minimatch` against
`provider/model`; `*` does not span `/`, so `deepseek/*` covers every model on
the DeepSeek provider without enabling any other provider.

### Authentication

Use Pi's `/login` flow or its documented private `auth.json` store, or set
`DEEPSEEK_API_KEY` in the environment. Never print, copy, commit, or place
credentials in `.pi/`, repository files, shell configuration, or tracked
configuration. A non-secret readiness check is:

```bash
pi auth check --provider deepseek --json --no-refresh
```

The DeepSeek API key remains private user configuration; the project does not
store it.

### Model store and provider policy

Pi's cached model catalog (`models-store.json`) records the models Pi knows
about; it does not define the project's active provider policy. The project
policy is the `enabledModels` scope in `.pi/settings.json`. A model appearing
in the cache does not make its provider part of this project.

## Roles

Roles are execution guidance underneath the Command Protocol; they do not
redefine any command, preset, gate, or lifecycle semantic. The full contract
lives in the `neuralengine-roles` skill
(`.pi/skills/neuralengine-roles/SKILL.md`).

- FLASH (`deepseek/deepseek-flash`) is the default role for `//SEEK`,
  `//ANALYSE`, standard `//FIX`, implementation, tests, documentation, and
  mechanical or repetitive work.
- PRO (`deepseek/deepseek-v4-pro`) is the escalation role for architecture,
  Brain-related reasoning, persistence, migrations, security, public API or
  persisted schema changes, critical review, and difficult root-cause
  analysis.

FLASH escalates to PRO when the task crosses a PRO boundary, stating the
reason. Pi does not bind a model to a skill or role declaration, and this
project does not enable an automatic model router or silently switch models
during a task. Select the role's model explicitly with `/model`,
`pi --provider deepseek --model <id>`, or a saved default. Pi's virtual-model
extension mechanism exists, but no automatic role switching is configured in
this worktree.

## Command Protocol controls

The existing thin prompt adapters are available as:

`/arch`, `/checkpoint`, `/fix`, `/kill`, `/next`, `/optimize`, `/recheck`,
`/research`, `/seek`, and `/ship`.

They load the `command-protocol` skill and forward to the canonical protocol
documents in `docs/command-protocol/`. `REVIEW` and `VERIFY` remain workflow
semantics and skills rather than invented standalone Pi commands. Unknown
commands remain unknown. Use `/skill:command-protocol` when the adapter must be
loaded explicitly.

The canonical controls retain their gates: `//SEEK` is read-only,
`//FIX` requires diagnosis/root cause/minimal correction/verification,
`CHECKPOINT` binds evidence to exact state, `RECHECK` returns only
`PROCEED | REVISE | STOP`, and critical `//AGENT` work still requires
`review -> CHECKPOINT -> RECHECK -> explicit launch`.

## Local models

Local Qwen, llama.cpp, Ollama, LM Studio, localhost endpoints, and the
NeuralEngine `scripts/llm` integration are not part of this project
configuration. No local model integration is included in this worktree.

## Safety boundary

Pi's `tool_call` extension blocks recognized Git mutations, selected durable
`neural` writes, `sudo`, and recursive removal in non-interactive runs. In an
interactive run it asks for one-command authorization. This is a narrow
defense-in-depth guard, not a shell parser or operating-system sandbox; nested,
aliased, or otherwise obfuscated commands require normal review and remain
outside its coverage. Brain writes remain separately authorized by the
canonical repository contract, and Pi does not automatically create records,
mutate Playbooks, persist learning, stage, commit, or push.

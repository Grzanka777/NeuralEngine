# Qwen Code project adapter

`AGENTS.md` and the NeuralEngine Development skill remain the repository
authority. Load the relevant project context before engineering work:
`VISION.md`, `CONTEXT.md`, `memory/project-state.md`, `docs/architecture.md`,
and `docs/conventions.md`. This adapter only supplies Qwen-specific bindings;
it does not repeat repository policy.

## Command Protocol

Protocol meaning comes only from the canonical sources:

- [Command Core v1.2](docs/command-protocol/COMMAND_CORE_v1.2.md)
- [Command Protocol v1.2](docs/command-protocol/COMMAND_PROTOCOL_v1.2.md)
- [Engineering Workflow v1.1](docs/command-protocol/ENGINEERING_WORKFLOW_v1.1.md)

Use the Qwen command/skill adapters for `SEEK`, `REVIEW`, `CHECKPOINT`,
`RECHECK`, and `VERIFY`. They adapt the interface without redefining protocol
semantics. A `PROCEED` RECHECK permits the plan only; the next phase still
requires an explicit launch.

## Local role integration boundary

Pi is the primary local/cloud harness. Qwen Code remains an optional
compatibility/Qwen-specialist client and is not the primary local client.

`llm-manifest.json` is the sole authority for local model inventory,
compatibility profiles, endpoint routes, and context layers. The three
`LOCAL_*` assignments remain `UNDECIDED`; `LOCAL_CODE` currently projects the
qualified Qwen3.8 Halogen route. The manifest records `MODEL_MAX_CTX`,
`RUNTIME_CTX`, `SLOT_CTX`, and `CLIENT_EFFECTIVE_CTX` separately. Qwen owns
only its native compaction/history behavior.

The `qg`, `qc`, and `qv` wrappers resolve the role and endpoint through the
read-only `llm project --role LOCAL_*` interface and append only the selected
role binding. Wrapper arguments cannot replace the route, advisor, or fallback
policy. Qwen is local-only with cloud fallback disabled and does not start or
stop local runtimes. Direct CLI/Desktop settings are generated projections.

`scripts/llm` is the only local runtime lifecycle owner; its profile arguments,
health checks, identity checks, and transitions derive from the manifest. Pi
uses the same local route projections while retaining its DeepSeek cloud
default and built-in cloud providers. OpenCode is parked without local routes
or lifecycle integration.

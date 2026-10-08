---
name: local-models
description: Select manifest-projected local models in Pi while keeping runtime lifecycle in scripts/llm.
---

Pi is the primary local/cloud harness. It keeps DeepSeek
`deepseek/deepseek-flash` as its cloud default and exposes the four current
local models from `llm-manifest.json` through `neuralengine-local`:

| Model | Pi model ID | Context | Output |
| --- | --- | ---: | ---: |
| Qwen3.8 | `qwen3.8-27b` | 65536 | 16384 |
| Nemotron 3 Nano | `/models/gguf/nemotron-3-nano-30b-a3b/nvidia_Nemotron-3-Nano-30B-A3B-Q5_K_M.gguf` | 32768 | 4096 |
| Qwen3-Coder | `/models/gguf/qwen3-coder-30b-a3b/Qwen3-Coder-30B-A3B-Instruct-UD-Q4_K_XL.gguf` | 32768 | `null` |
| Gemma 4 Vision | `/models/gguf/gemma4-26b-a4b/gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf` | 32768 | 4096 |

Use Pi's supported selector rather than a shell-only wrapper:

```text
pi --model neuralengine-local/qwen3.8-27b
pi --model neuralengine-local//models/gguf/nemotron-3-nano-30b-a3b/nvidia_Nemotron-3-Nano-30B-A3B-Q5_K_M.gguf
pi --model neuralengine-local//models/gguf/qwen3-coder-30b-a3b/Qwen3-Coder-30B-A3B-Instruct-UD-Q4_K_XL.gguf
pi --model neuralengine-local//models/gguf/gemma4-26b-a4b/gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf
pi --model deepseek/deepseek-flash
```

The interactive selector is also available with `Ctrl+P`. The global
`local-model-projection` extension maps these selections to `scripts/llm`
profiles. `scripts/llm` is the only runtime lifecycle owner; the extension
requests `switch-json` and `stop-owned-json` only. `STARTED` runtimes are
stopped only with their exact profile and PID, while `BORROWED` runtimes are
preserved. Qwen Code uses selected role projections through `qg`, `qc`, and
`qv` only as an optional compatibility/Qwen-specialist client.

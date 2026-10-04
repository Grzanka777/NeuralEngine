---
name: local-models
description: Explain the retired Pi local-model interface and route local work to Qwen Code.
---

Pi uses DeepSeek `deepseek-flash` only and cannot manage local runtimes.
For local work use Qwen Code: `qg` for GENERAL, `qc` for CODE, and `qv` for VISION.
`scripts/llm` is the sole local runtime manager. No local fallback is permitted in Pi.
Do not run retired Pi adapters or historical lifecycle test fixtures.

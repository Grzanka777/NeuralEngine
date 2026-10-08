# Pi operating contract

`PRIMARY_LOCAL_HARNESS=Pi`. Pi is the primary day-to-day local and cloud client.
It keeps the `deepseek/deepseek-flash` cloud default and can select manifest-
projected local routes. The GLOBAL `local-model-projection` extension reads
`llm-manifest.json` and registers all four verified local models through
`neuralengine-local`: Qwen3.8, Nemotron, Qwen3-Coder, and Gemma Vision.
`LOCAL_CODE` points to the qualified Qwen3.8 Halogen route; final role
assignments remain undecided. The extension registers route metadata only;
`scripts/llm` remains the only runtime lifecycle owner. Pi's built-in cloud
provider catalog remains available.

Select a model with Pi's normal selector, for example:

```text
pi --model neuralengine-local/qwen3.8-27b
pi --model neuralengine-local//models/gguf/nemotron-3-nano-30b-a3b/nvidia_Nemotron-3-Nano-30B-A3B-Q5_K_M.gguf
pi --model neuralengine-local//models/gguf/qwen3-coder-30b-a3b/Qwen3-Coder-30B-A3B-Instruct-UD-Q4_K_XL.gguf
pi --model neuralengine-local//models/gguf/gemma4-26b-a4b/gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf
pi --model deepseek/deepseek-flash
```

Interactive Pi sessions can use `Ctrl+P` for the same catalog. Qwen Code is an
optional compatibility/Qwen-specialist client, not the primary harness.
OpenCode remains parked without local routes or lifecycle ownership.

Keep the project Guard byte-for-byte and keep Command Protocol. The protocol
skill is installed globally from `integrations/pi/skills/command-protocol`;
its reference files remain exact copies of the canonical repository documents.
Project prompts add instructions separately from the selected model.

`integrations/pi/manifest.json` declares GLOBAL and PROJECT_LOCAL resources.
`uv run --no-sync python scripts/sync-pi-resources` installs GLOBAL resources
without changing unrelated files. `uv run --no-sync python
scripts/sync-llm-client-projections` materializes manifest-derived route
allowlists while preserving the DeepSeek cloud default.

`scripts/pi-model`, `scripts/pi-local`, and `scripts/challenger` remain retired.
The normal project entrypoint is the installed `pi` command with Pi project
auto-discovery. `scripts/pi.py` is an optional path-preserving launcher for
nested checkout directories; it does not own model lifecycle. Do not install
historical local lifecycle fixtures.

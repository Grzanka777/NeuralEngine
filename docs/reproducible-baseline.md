# Reproducible baseline reconstruction

This document is the repository-owned reconstruction contract for the current
NeuralEngine/OpenCode workflow. It describes a candidate product checkpoint;
it does not make the current dirty checkout a release and it does not include
external payloads or host configuration.

## 1. What comes from Git

An authorized product checkpoint must contain:

- `pyproject.toml` and `uv.lock`;
- the existing `src/neural_engine/**` package, including the OpenCode
  compatibility, handoff, context, ports, and local-adapter modules;
- the corresponding deterministic tests under `tests/`;
- `scripts/llm` and `scripts/opencode-watch`;
- the operator documentation, including this contract and the current README.

The following are deliberately outside the product baseline: `AGENTS.md`
governance changes that have not been separately closed, `benchmarks/`,
`.agent-work/`, model payloads, llama.cpp build trees, the live OpenCode home,
the live Brain, and live shell configuration.

## 2. What stays external

The following state is supplied by the host or an operator-managed artifact:

- Python 3.14 or newer and `uv`;
- the rolling OpenCode executable and its user configuration;
- the OpenCode lifecycle plugin and default agent file;
- the `llama-server` executable and six GGUF/MTP/projector artifacts;
- the selected NeuralEngine home and its Brain contents;
- optional fish convenience functions.

External state must not be copied wholesale into Git. In particular, do not
copy OpenCode databases, mutable session state, credentials, model files, or
Brain records into the repository.

## 3. What must be installed or provided

For the repository package, use the locked dependency graph in `uv.lock` and
Python `>=3.14`. Development may use the editable project environment:

```bash
uv sync
uv run neural --help
```

The production/reconstruction path is separate: synchronize an explicitly
selected candidate or checkpoint source with `uv sync --locked --no-dev
--no-editable` (see section 5). The current production `uv` tool is not the
reconstruction source of truth.

Install the two repository-owned executable helpers from that same selected
source:

```bash
install -m 0755 scripts/llm "$HOME/.local/bin/llm"
install -m 0755 scripts/opencode-watch "$HOME/.local/bin/opencode-watch"
```

The first file is a Python executable without a `.py` suffix. Validate it with
Python syntax checks, not `bash -n`; `scripts/opencode-watch` is the shell
script and is validated with `bash -n`.

## 4. Capabilities and paths that must exist

The OpenCode and local-model paths must satisfy the contracts below:

| Capability | Required contract |
| --- | --- |
| `neural` | An executable installed from the selected candidate source. |
| `llm` | An executable copy of `scripts/llm` on `PATH`; it must report `STOPPED` before a no-start validation. |
| `opencode-watch` | An executable copy of `scripts/opencode-watch` on `PATH`. |
| `opencode` | An executable rolling OpenCode command on `PATH`; exact version is diagnostic, not a gate. |
| `llama-server` | An executable compatible with the launcher arguments and local Vulkan profile. |
| Local endpoints | CODE `127.0.0.1:18080`, GENERAL `127.0.0.1:18081`, VISION `127.0.0.1:18082`; only one profile runs at a time. |
| Neural home | One existing absolute directory selected by `NEURAL_HOME`, or the default `~/.neural`; no fallback is used for an invalid override. |

The launcher preserves the verified profile arguments, model selection,
quantization, context size, batching, and speculative settings. Relocation is
limited to explicit path environment variables; it is not a profile redesign:

```text
NEURALENGINE_LLAMA_SERVER
NEURALENGINE_GENERAL_MODEL
NEURALENGINE_GENERAL_MTP
NEURALENGINE_CODE_MODEL
NEURALENGINE_VISION_MODEL
NEURALENGINE_VISION_MMPROJ
NEURALENGINE_VISION_MTP
```

Unset variables retain the current host defaults:

```text
llama-server: /home/grzanka/Work/LLM/strix-llama.cpp/build-vulkan/bin/llama-server
GENERAL model: /models/gguf/qwen3.6-35b-a3b/Qwen3.6-35B-A3B-Q4_K_M.gguf
GENERAL MTP:   /models/gguf/qwen3.6-35b-a3b/mtp/mtp-Qwen3.6-35B-A3B-Q4_0.gguf
CODE model:    /models/gguf/qwen3-coder-30b-a3b/Qwen3-Coder-30B-A3B-Instruct-UD-Q4_K_XL.gguf
VISION model:  /models/gguf/gemma4-26b-a4b/gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf
VISION mmproj: /models/gguf/gemma4-26b-a4b/mmproj-BF16.gguf
VISION MTP:   /models/gguf/gemma4-26b-a4b/MTP/mtp-gemma-4-26B-A4B-it-Q8_0.gguf
```

On another equivalent host, set every required override to an absolute path
before invoking `llm`. Do not mix artifacts from different profiles or silently
substitute a different model. The six model paths must be regular files and
the runtime path must be executable. Record optional SHA-256 evidence outside
Git when an operator needs to prove artifact identity.

## 5. Production installation of `neural`

Use an unpacked repository checkpoint or an explicitly assembled candidate
source, not the live dirty development checkout. The production environment is
the candidate's `.venv`; `neural` is executed from that environment:

```bash
uv --directory /absolute/path/to/neuralengine-candidate \
  sync --locked --no-dev --no-editable
/absolute/path/to/neuralengine-candidate/.venv/bin/neural --help
```

`--locked` asserts that the selected `uv.lock` remains unchanged and makes the
lockfile the dependency source of truth. `--no-editable` installs the project
as a copied package, so the environment does not resolve through the source
checkout. `uv tool install /path/to/project` is intentionally not the
production command: it creates a non-editable environment but resolves the
project's dependency ranges independently of the project's `uv.lock`.

For a disposable reconstruction probe, isolate the source, project
environment, and helper executables so the current `~/.local/bin/neural` is
untouched:

```bash
probe_root=$(mktemp -d /tmp/neuralengine-locked-sync.XXXXXX)
cp -a /absolute/path/to/neuralengine-candidate/. "$probe_root/source/"
uv --directory "$probe_root/source" sync --locked --no-dev --no-editable
PATH="$probe_root/source/.venv/bin:$PATH" neural --help
```

Prove both boundaries by inspecting the installed package metadata and runtime
versions. The installed `direct_url.json` must contain `"editable": false`,
the imported `neural_engine` path must be below the isolated `.venv` rather
than `/home/grzanka/Work/NeuralEngine`, and every runtime package version must
match:

```bash
uv --directory "$probe_root/source" export --frozen --no-dev \
  --no-emit-project --format requirements.txt
```

Compare that frozen export with `importlib.metadata` from
`"$probe_root/source/.venv/bin/python"`; the comparison must be exact for the
selected Python/platform environment.

## 6. Installation of `llm` and `opencode-watch`

Copy the executable files from the same candidate source with their executable
mode preserved:

```bash
install -m 0755 /absolute/path/to/neuralengine-candidate/scripts/llm \
  "$HOME/.local/bin/llm"
install -m 0755 /absolute/path/to/neuralengine-candidate/scripts/opencode-watch \
  "$HOME/.local/bin/opencode-watch"
```

For an isolated probe, install them into a disposable `bin` directory and put
that directory first on `PATH`. `opencode-watch` accepts `OPENCODE_BIN` and
`LLM_PATH` overrides for testing or relocation; normal use resolves `opencode`
from `PATH` and `llm` from `$HOME/.local/bin/llm`.

## 7. OpenCode config, plugin, and agent contract

OpenCode is a rolling external platform. The required compatibility contract is
capability-based:

- `opencode` is executable and responds to `--version`;
- the resolved user config is valid JSON and sets
  `default_agent` to `arch-data-engineer`;
- the config defines these provider/model IDs:
  `llama-general/qwen3.6-general-local`,
  `llama-code/qwen3-coder-local`, and
  `llama-vision/gemma4-vision-local`;
- the model endpoints use the local ports from section 4;
- `agents/arch-data-engineer.md` exists and is readable below the resolved
  OpenCode config directory;
- `plugin/llm-autostart.js` is readable, maps each exact provider/model ID to
  `general`, `code`, or `vision`, and calls the executable launcher as
  `llm switch <role>` through `Bun.spawnSync`;
- the plugin and wrapper do not directly read or write the NeuralEngine Brain.

The plugin's `const LLM = "..."` value must point to the installed executable
launcher. A sanitized configuration may use a placeholder while being
assembled, but the placeholder must be replaced before validation. Do not copy
the live config, plugin, or agent file without reviewing it for secrets and
host-specific state. A minimal configuration must retain the exact IDs above;
OpenCode's exact version and automatic update policy are not product pins.

## 8. llama.cpp and model artifacts

The launcher requires one `llama-server` executable plus these external
artifacts:

| Lane | Artifacts |
| --- | --- |
| GENERAL | one Qwen3.6 GGUF and its MTP GGUF |
| CODE | one Qwen3-Coder GGUF |
| VISION | one Gemma 4 GGUF, one `mmproj` GGUF, and one MTP GGUF |

The exact current-default paths and relocation variables are listed in section
4. A reconstruction must provide all files required by the selected lanes,
check regular-file/executable capabilities before starting, and leave the
launcher in `STOPPED` state after validation. The repository does not provide
the llama.cpp build, download instructions, model payloads, or a model hash
manifest; those are operator-owned external prerequisites. Do not change the
verified llama-server build, GPU/runtime stack, or launcher profile arguments as
part of baseline reconstruction.

## 9. Selecting and restoring `NEURAL_HOME`

`NEURAL_HOME` selects the complete NeuralEngine home. It must be an existing,
accessible absolute directory; the application fails closed for an invalid
override and does not silently use `~/.neural`. All Brain, project, log,
configuration, and version paths derive from that one resolved home.

The current host's live selection is:

```text
NEURAL_HOME=/home/grzanka/Work/NeuralEngine-State
Brain=/home/grzanka/Work/NeuralEngine-State/brain
```

That absolute path is current-host evidence, not a universal product
requirement. A reconstruction on another host should choose its own existing
absolute directory and set `NEURAL_HOME` explicitly.

For a user-managed backup, preserve the complete selected Neural home,
including `brain/`, `VERSION`, `config.toml`, and the canonical store
directories. For an adopted trusted Brain, also preserve the external trust
binding at:

```text
~/.config/neural-engine/brain-trust-binding.json
```

Preserve file contents and restrictive permissions. Logs and other generated
operational files may be retained for forensics but are not a substitute for
the Brain or trust metadata. This task does not perform a backup or restore.

After restoring to a new existing directory, point the process at the restored
home and run only these read-only checks first:

```bash
export NEURAL_HOME=/absolute/path/to/restored-neural-home
neural status
neural doctor
```

`neural doctor` must report `READY`, zero failed checks, readable records, and
passing integrity/manifest checks. A trusted adopted restore must also report
matching Brain identity/generation (`TRUSTED_CURRENT`); do not hand-edit trust
metadata or binding files to force that result. If only a fresh empty home is
wanted, initialize it explicitly with `neural init` instead of treating a
failed restore as an empty Brain.

## 10. Canonical daily entrypoint

The repository baseline uses the direct installed wrapper:

```bash
opencode-watch
```

It forwards the original OpenCode arguments, owns only the LLM lifecycle it
can verify, and performs idempotent cleanup. It does not start a background
watcher or perform automatic OpenCode adaptation. `ow` and `neural-open` may be
defined as optional fish convenience functions, but they are not required for
the reproducible baseline and the repository does not modify the live fish
configuration.

## 11. Reconstruction health checks

Run these checks in order after installing the selected candidate and external
prerequisites:

```bash
python -m py_compile /absolute/path/to/candidate/scripts/llm
bash -n /absolute/path/to/candidate/scripts/opencode-watch
neural status
neural doctor
neural opencode doctor
llm state
```

The expected final state is `llm state` → `STOPPED`. `neural status`,
`neural doctor`, and `neural opencode doctor` are read-only checks. The
OpenCode preflight reports the installed version for diagnostics but gates on
the executable, config, model IDs, plugin, wrapper, and safety boundary rather
than an exact version. Do not use the health sequence to start a model or to
write the Brain.

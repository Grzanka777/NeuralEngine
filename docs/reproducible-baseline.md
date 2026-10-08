# Reproducible baseline reconstruction

This document is the repository-owned reconstruction contract for the current
NeuralEngine local model stack. It describes a candidate product checkpoint;
it does not make the current dirty checkout a release and it does not include
external payloads or host configuration.

## 1. What comes from Git

An authorized product checkpoint must contain:

- `pyproject.toml` and `uv.lock`;
- the existing `src/neural_engine/**` package, including the OpenCode
  compatibility, handoff, context, ports, and local-adapter modules;
- the corresponding deterministic tests under `tests/`;
- `llm-manifest.json`, `scripts/llm`, `scripts/llm-regression-gate`, and
  `scripts/validate-llm-manifest`, `scripts/sync-llm-client-projections`, and
  the deprecated direct OpenCode compatibility passthrough;
- the repo-owned Pi and Qwen Code bindings, including
  `integrations/pi/manifest.json`;
- the operator documentation, including this contract and the current README.

The following are deliberately outside the product baseline: `AGENTS.md`
governance changes that have not been separately closed, `benchmarks/`,
`.agent-work/`, model payloads, llama.cpp build trees, the live OpenCode home,
the live Brain, and live shell configuration.

## 2. What stays external

The repository defines the active LLM contract in `llm-manifest.json`; host
artifacts remain operator-managed while client settings are generated
projections:

- Python and `uv` for the selected repository checkpoint;
- the rolling OpenCode executable and optional user configuration;
- the `llama-server` executable selected by the active manifest;
- model and auxiliary files required by active roles in the manifest;
- the selected NeuralEngine home and its Brain contents;
- optional fish convenience functions.

MTP files are required only when an active role's manifest entry enables MTP.
In the 2026-10-05 checkpoint described below, MTP is disabled for all active
roles. External state must not be copied wholesale into Git. In particular, do
not copy OpenCode databases, mutable session state, credentials, model files,
or Brain records into the repository.

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

### Repository LLM contract

`llm-manifest.json` is the authority for active roles, model assets, endpoints,
launcher profiles, and Pi/Qwen client contracts. `scripts/llm` implements the
local runtime contract; the Pi and Qwen configurations are derived bindings.
Use `scripts/llm-regression-gate fast` for static repository checks plus local
asset inventory, or `scripts/llm-regression-gate fast --repo-only` for CI-safe
repository checks without host model files. Both modes are read-only and do
not start a model or make network requests. See
[`llm-regression-gate.md`](llm-regression-gate.md) for output and exit codes.

Current checkpoint summary (2026-10-07; the manifest remains authoritative):

`PRIMARY_LOCAL_HARNESS=Pi`. Pi is the primary local/cloud harness. Qwen Code
is optional compatibility/Qwen-specialist support, and OpenCode is parked
outside the active local production path.

| Client or role | Active contract in this checkpoint |
| --- | --- |
| `LOCAL_GENERAL` | Assignment undecided; Nemotron current deployment projection at `http://127.0.0.1:18081/v1`. |
| `LOCAL_CODE` | Assignment undecided; qualified Qwen3.8-27B Halogen projection at `http://127.0.0.1:8731/v1`, client context 65536 and output cap 16384. |
| `LOCAL_VISION` | Assignment undecided; Gemma 4 current deployment projection with `mmproj` at `http://127.0.0.1:18082/v1`. |
| Pi | Primary local + cloud harness; manifest-projected local routes plus built-in cloud providers; DeepSeek `deepseek-flash` remains default. |
| Qwen Code | Optional compatibility/Qwen-specialist client; default `LOCAL_GENERAL` compatibility projection; cloud fallback disabled. |
| OpenCode | Parked; no local route authority or runtime lifecycle. |

The three `LOCAL_*` assignments remain `UNDECIDED`. The named runtime profiles
are current-deployment compatibility projections retained for existing
clients. `scripts/llm` is the sole lifecycle owner and permits only one local
profile at a time. The manifest distinguishes model maximum, runtime, slot,
and client-effective context; client compaction stays in each harness. Qwen3.8
is qualified for the LOCAL_CODE projection from R4.1; R2.3 remains NOT_RUN and
benchmark execution stays frozen in this migration.

### Host-specific prerequisites

The host must provide the runtime and every asset required by the selected
manifest. The current inventory check requires each active model and auxiliary
asset to be a non-empty regular file; MTP is checked only when enabled in the
manifest. These host facts are not a second repository contract.

| Capability | Host requirement |
| --- | --- |
| `neural` | An executable installed from the selected candidate source. |
| `llm` | An executable installation of `scripts/llm` on `PATH`. |
| `opencode-watch` | An executable installation of `scripts/opencode-watch` on `PATH`, if the optional OpenCode wrapper is used. |
| `opencode` | An external rolling OpenCode command, if the optional OpenCode integration is used; its version is diagnostic. |
| `llama-server` | An executable at the runtime path selected by the active manifest. |
| Local models | The active model and auxiliary asset paths selected by the active manifest. |
| Local endpoints | The host and ports selected by active manifest roles; the checkpoint values are listed above. |
| Neural home | One existing absolute directory selected by `NEURAL_HOME`, or the default `~/.neural`; no fallback is used for an invalid override. |

Runtime and model paths are selected only by the manifest. Environment path
overrides are ignored so they cannot create a second profile authority:

```text
NEURALENGINE_LLAMA_SERVER
NEURALENGINE_GENERAL_MODEL
NEURALENGINE_CODE_MODEL
NEURALENGINE_VISION_MODEL
NEURALENGINE_VISION_MMPROJ
```

When relocating to another host, edit the manifest and validate the resulting
projection. Do not configure duplicate client model maps or enable MTP based
on a previous baseline.

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
mode preserved. The compatibility entrypoint forwards to OpenCode directly and
does not inspect or manage local runtimes:

```bash
install -m 0755 /absolute/path/to/neuralengine-candidate/scripts/llm \
  "$HOME/.local/bin/llm"
install -m 0755 /absolute/path/to/neuralengine-candidate/scripts/opencode-watch \
  "$HOME/.local/bin/opencode-watch"
```

For an isolated probe, install them into a disposable `bin` directory and put
that directory first on `PATH`. `opencode-watch` accepts `OPENCODE_BIN` for
testing or relocation and does not call `llm`.

## 7. Pi, Qwen Code, and optional OpenCode integration

The active Pi and Qwen Code contracts are declared in `llm-manifest.json`.
Their user/project configuration is derived state and must be checked against
that manifest rather than used as an independent source of expected values.

Pi is the primary day-to-day local/cloud entrypoint. Its supported selector
exposes Qwen3.8, Nemotron, Qwen3-Coder, Gemma Vision, and the built-in DeepSeek
cloud catalog. Use `pi --model provider/id` or Pi's interactive `Ctrl+P`
selector; do not maintain a second shell-only model map.

- Pi registers manifest-derived local routes and retains built-in cloud
  providers. Its DeepSeek cloud default is unchanged, and Pi owns no runtime
  lifecycle.
- Qwen Code is local-only, defaults to `LOCAL_GENERAL`, and has no cloud
  fallback. Settings, context, output caps, and wrapper routes are generated
  from the manifest; Qwen owns no runtime lifecycle.

OpenCode is parked. The managed user configuration has no local providers or
local model selection, and its Fish entrypoints call OpenCode directly.
OpenCode compatibility detection remains available for deliberate future
reactivation; it is not part of the active local model stack.

## 8. Local runtime and model assets

`scripts/llm` is the sole local runtime manager and permits only one local
profile to be active at a time. The selected runtime, model paths, role
arguments, and required auxiliary assets are defined by `llm-manifest.json`;
`scripts/llm` implements that contract. This document does not pin a parallel
runtime configuration.

Each current deployment profile requires its model file; VISION also requires
its `mmproj`. The host-bound `MODEL_INVENTORY` check in the full fast gate
verifies these assets without starting the runtime. The repository-only mode
skips inventory and reports it as `NOT_RUN`.

The exact runtime build, backend, file paths, and profile parameters are
host-specific checkpoint values. Keep them in the manifest/runtime contract
and use the gate to detect drift. The previous baseline documented Qwen3.6/MTP
asset paths; those are historical and must not be restored as current settings.

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

## 10. OpenCode compatibility entrypoint

The deprecated direct passthrough is:

```bash
opencode-watch
```

It forwards the original OpenCode arguments without starting, checking, or
stopping any local runtime. `ow` and `neural-open` call OpenCode directly.
OpenCode remains parked until a separate deliberate reactivation task.

## 11. Reconstruction health checks

Run the static gate before host-specific checks. CI can use the repository-only
mode without local model files; the full mode also checks the local model
inventory. Neither mode starts a model or queries an endpoint.

```bash
scripts/llm-regression-gate fast --repo-only
scripts/llm-regression-gate fast
```

After installing the selected candidate and external prerequisites, run the
remaining checks in order:

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
OpenCode preflight reports the installed version for diagnostics and gates on
capabilities rather than a fixed version. Do not use the health sequence to
start a model or to write the Brain.

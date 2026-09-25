# Phase 7 — Local LLM launcher

## Created files

- `/home/grzanka/.config/systemd/user/llm-general.service`
- `/home/grzanka/.config/systemd/user/llm-code.service`
- `/home/grzanka/.local/bin/llm` (mode `0755`)

The requested report is this file. The project review artifact is kept
separately under `.agent-work/reviews/`.

No target file existed before this change, so no replacement backup was needed.

## Frozen service commands

`llm-general.service`:

```text
/home/grzanka/Work/LLM/strix-llama.cpp/build-vulkan/bin/llama-server -m /models/gguf/qwen3.6-35b-a3b/Qwen3.6-35B-A3B-Q4_K_M.gguf -dev Vulkan0 -ngl 999 -c 32768 -b 2048 -ub 1024 -np 1 -fa on --cache-prompt --metrics --spec-type draft-mtp --spec-draft-model /models/gguf/qwen3.6-35b-a3b/mtp/mtp-Qwen3.6-35B-A3B-Q4_0.gguf --spec-draft-device Vulkan0 --spec-draft-ngl 999 --spec-draft-n-max 3 --host 127.0.0.1 --port 18081
```

`llm-code.service`:

```text
/home/grzanka/Work/LLM/strix-llama.cpp/build-vulkan/bin/llama-server -m /models/gguf/qwen3-coder-30b-a3b/Qwen3-Coder-30B-A3B-Instruct-UD-Q4_K_XL.gguf -dev Vulkan0 -ngl 999 -c 32768 -b 2048 -ub 1024 -np 1 -fa on --cache-prompt --metrics --host 127.0.0.1 --port 18080
```

Both units have a reciprocal `Conflicts=`, `Restart=on-failure`,
`KillSignal=SIGTERM`, a 90-second graceful-stop window, and journal output.
They are `static` (not enabled for boot).

## Validation

Verified before installation:

- runtime binary: `/home/grzanka/Work/LLM/strix-llama.cpp/build-vulkan/bin/llama-server`
- runtime commit: `5f851647fe5ed795dfd6c0a3fba543114879e874`
- general GGUF, general MTP GGUF, and code GGUF all existed and were readable.

`systemd-analyze --user verify` passed for both unit files. `sh -n` passed for
the launcher.

The smoke sequence completed successfully:

1. `llm status` reported `LLM STOPPED`.
2. `llm general` returned `GENERAL READY`, model endpoint
   `http://127.0.0.1:18081/v1/models` returned the general model, and exactly
   one `llama-server` PID listened only on `127.0.0.1:18081`.
3. `llm code` stopped GENERAL, returned `CODE READY`, model endpoint
   `http://127.0.0.1:18080/v1/models` returned the code model, and exactly one
   `llama-server` PID listened only on `127.0.0.1:18080`.
4. `llm general` stopped CODE and restored the general endpoint with exactly
   one server PID on port 18081.
5. `llm stop` stopped both services; `llm status` reported `LLM STOPPED`, no
   matching server process remained, and neither port was listening.

During both successful model loads, the journal recorded `model loaded` and
the expected localhost listener. No OOM, Vulkan-failure, or CPU-fallback
message was observed. The live process arguments retained `-dev Vulkan0` and
`-ngl 999` for both profiles. No generation or benchmark request was made.

## Rollback

```fish
llm stop
rm /home/grzanka/.config/systemd/user/llm-general.service
rm /home/grzanka/.config/systemd/user/llm-code.service
rm /home/grzanka/.local/bin/llm
systemctl --user daemon-reload
```

## Usage

```fish
llm general
llm code
llm stop
llm status
llm logs
llm general logs
llm code logs
```

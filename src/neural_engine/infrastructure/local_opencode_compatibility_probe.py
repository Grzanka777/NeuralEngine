import json
import os
import re
import shutil
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path

from neural_engine.ports.opencode_compatibility import (
    OpencodeCapabilityObservation,
    OpencodeCompatibilityEvidence,
)

_REQUIRED_MODELS: tuple[tuple[str, str, bool], ...] = (
    ("llama-general", "qwen3.6-general-local", True),
    ("llama-code", "qwen3-coder-local", True),
    ("llama-vision", "gemma4-vision-local", False),
)
_LLM_DECLARATION = re.compile(r"const\s+LLM\s*=\s*['\"]([^'\"]+)['\"]")
_VERSION_PREFIX = re.compile(r"opencode\s+v?\S+", re.IGNORECASE)

CommandRunner = Callable[[Sequence[str], float], subprocess.CompletedProcess[str]]
Which = Callable[[str], str | None]


def _run_command(command: Sequence[str], timeout: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        check=False,
        text=True,
        timeout=timeout,
    )


class LocalOpencodeCompatibilityProbe:
    """Inspect the supported OpenCode integration without starting a service."""

    def __init__(
        self,
        *,
        opencode_command: str = "opencode",
        wrapper_command: str = "opencode-watch",
        config_path: Path | None = None,
        plugin_path: Path | None = None,
        agent_directory: Path | None = None,
        which: Which = shutil.which,
        command_runner: CommandRunner = _run_command,
    ) -> None:
        config_directory = (
            Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "opencode"
        )
        self._opencode_command = opencode_command
        self._wrapper_command = wrapper_command
        self._config_path = config_path or config_directory / "opencode.json"
        self._plugin_path = plugin_path or config_directory / "plugin" / "llm-autostart.js"
        self._agent_directory = agent_directory or config_directory / "agents"
        self._which = which
        self._command_runner = command_runner

    def inspect(self) -> OpencodeCompatibilityEvidence:
        executable_path = self._which(self._opencode_command)
        version = self._read_version(executable_path)
        config, config_observation = self._read_config()
        plugin_text, plugin_observation, llm_path = self._read_plugin()
        wrapper_path = self._resolve_executable(self._wrapper_command)

        capabilities = [
            OpencodeCapabilityObservation(
                "executable",
                executable_path is not None,
                (
                    str(executable_path)
                    if executable_path is not None
                    else f"{self._opencode_command!r} was not found on PATH"
                ),
                True,
            ),
            OpencodeCapabilityObservation(
                "version",
                True if version is not None else None,
                version or "executable responded without a readable version",
                False,
            ),
            config_observation,
            self._agent_observation(config),
            *self._model_observations(config),
            plugin_observation,
            self._vision_lifecycle_observation(plugin_text, llm_path),
            self._wrapper_observation(wrapper_path),
            self._safety_observation(plugin_text, wrapper_path),
        ]
        model_ids = tuple(
            (f"{provider}/{model}", model)
            for provider, model, _critical in _REQUIRED_MODELS
            if self._model_configured(config, provider, model)
        )
        return OpencodeCompatibilityEvidence(
            version=version,
            capabilities=tuple(capabilities),
            wrapper_path=wrapper_path,
            llm_path=llm_path,
            model_ids=model_ids,
        )

    def _read_version(self, executable_path: str | None) -> str | None:
        if executable_path is None:
            return None
        try:
            result = self._command_runner((executable_path, "--version"), 5.0)
        except OSError, subprocess.TimeoutExpired:
            return None
        if result.returncode != 0:
            return None
        output = (result.stdout or result.stderr).strip()
        if not output:
            return None
        match = _VERSION_PREFIX.search(output)
        return match.group(0) if match else output.splitlines()[0]

    def _read_config(
        self,
    ) -> tuple[dict[str, object], OpencodeCapabilityObservation]:
        try:
            raw = json.loads(self._config_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            return {}, OpencodeCapabilityObservation(
                "config",
                None,
                f"could not read {self._config_path}: {error}",
                True,
            )
        if not isinstance(raw, dict):
            return {}, OpencodeCapabilityObservation(
                "config", None, f"{self._config_path} does not contain a JSON object", True
            )
        return raw, OpencodeCapabilityObservation("config", True, str(self._config_path), True)

    def _agent_observation(self, config: dict[str, object]) -> OpencodeCapabilityObservation:
        agent = config.get("default_agent")
        if not isinstance(agent, str) or not agent:
            return OpencodeCapabilityObservation(
                "agent contract", None, "default_agent is missing or invalid", True
            )
        path = self._agent_directory / f"{agent}.md"
        return OpencodeCapabilityObservation(
            "agent contract",
            path.is_file() and os.access(path, os.R_OK),
            f"default_agent={agent}; file={path}",
            True,
        )

    def _model_observations(
        self, config: dict[str, object]
    ) -> tuple[OpencodeCapabilityObservation, ...]:
        return tuple(
            OpencodeCapabilityObservation(
                f"provider/model {provider}/{model}",
                self._model_configured(config, provider, model),
                (
                    "configured"
                    if self._model_configured(config, provider, model)
                    else "missing from the resolved provider configuration"
                ),
                critical,
            )
            for provider, model, critical in _REQUIRED_MODELS
        )

    @staticmethod
    def _model_configured(config: dict[str, object], provider: str, model: str) -> bool:
        providers = config.get("provider")
        if not isinstance(providers, dict):
            return False
        provider_config = providers.get(provider)
        if not isinstance(provider_config, dict):
            return False
        models = provider_config.get("models")
        return isinstance(models, dict) and isinstance(models.get(model), dict)

    def _read_plugin(
        self,
    ) -> tuple[str | None, OpencodeCapabilityObservation, Path | None]:
        try:
            source = self._plugin_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            return (
                None,
                OpencodeCapabilityObservation(
                    "lifecycle integration",
                    None,
                    f"could not read {self._plugin_path}: {error}",
                    True,
                ),
                None,
            )
        llm_match = _LLM_DECLARATION.search(source)
        llm_path = Path(llm_match.group(1)) if llm_match else None
        required_markers = (
            'Bun.spawnSync([LLM, "switch", role]',
            '"llama-general/qwen3.6-general-local"',
            '"llama-code/qwen3-coder-local"',
        )
        integration_ok = all(marker in source for marker in required_markers)
        llm_ok = llm_path is not None and llm_path.is_file() and os.access(llm_path, os.X_OK)
        return (
            source,
            OpencodeCapabilityObservation(
                "lifecycle integration",
                integration_ok and llm_ok,
                (
                    f"plugin={self._plugin_path}; llm={llm_path}"
                    if integration_ok and llm_ok
                    else "plugin mapping or executable llm launcher is unavailable"
                ),
                True,
            ),
            llm_path,
        )

    def _resolve_executable(self, command: str) -> Path | None:
        resolved = self._which(command)
        if resolved is None:
            return None
        path = Path(resolved)
        return path if path.is_file() and os.access(path, os.X_OK) else None

    @staticmethod
    def _vision_lifecycle_observation(
        plugin_text: str | None,
        llm_path: Path | None,
    ) -> OpencodeCapabilityObservation:
        available = (
            plugin_text is not None
            and '"llama-vision/gemma4-vision-local"' in plugin_text
            and llm_path is not None
            and llm_path.is_file()
            and os.access(llm_path, os.X_OK)
        )
        return OpencodeCapabilityObservation(
            "VISION lifecycle integration",
            available if plugin_text is not None else None,
            "configured" if available else "optional VISION routing is unavailable",
            False,
        )

    @staticmethod
    def _wrapper_observation(path: Path | None) -> OpencodeCapabilityObservation:
        return OpencodeCapabilityObservation(
            "wrapper",
            path is not None,
            str(path) if path is not None else "opencode-watch is not executable on PATH",
            True,
        )

    @staticmethod
    def _safety_observation(
        plugin_text: str | None,
        wrapper_path: Path | None,
    ) -> OpencodeCapabilityObservation:
        if plugin_text is None or wrapper_path is None:
            return OpencodeCapabilityObservation(
                "Brain safety boundary", None, "integration source could not be inspected", True
            )
        try:
            wrapper_text = wrapper_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            return OpencodeCapabilityObservation(
                "Brain safety boundary", None, f"wrapper could not be inspected: {error}", True
            )
        prohibited = re.compile(r"(?i)(?<![a-z0-9_-])(?:brain|neural)(?![a-z0-9_-])")
        if prohibited.search(plugin_text) or prohibited.search(wrapper_text):
            return OpencodeCapabilityObservation(
                "Brain safety boundary",
                False,
                "OpenCode integration contains a direct NeuralEngine/Brain command reference",
                True,
            )
        return OpencodeCapabilityObservation(
            "Brain safety boundary",
            True,
            "plugin and wrapper do not bypass the explicit NeuralEngine write boundary",
            True,
        )


class LocalOpencodeLiveSmokeRunner:
    """Run one explicit marker-only smoke through the existing wrapper."""

    def __init__(
        self,
        *,
        command_runner: CommandRunner = _run_command,
        llm_state_runner: CommandRunner = _run_command,
    ) -> None:
        self._command_runner = command_runner
        self._llm_state_runner = llm_state_runner

    def run(
        self,
        evidence: OpencodeCompatibilityEvidence,
        *,
        lane: str,
    ) -> tuple[bool, str]:
        if evidence.wrapper_path is None or evidence.llm_path is None:
            return False, "live smoke prerequisites are unavailable"
        model_id = dict(evidence.model_ids).get(
            "llama-general/qwen3.6-general-local"
            if lane == "general"
            else "llama-code/qwen3-coder-local"
        )
        if model_id is None:
            return False, f"{lane} model is not configured"
        try:
            before = self._llm_state_runner((str(evidence.llm_path), "state"), 5.0)
        except (OSError, subprocess.TimeoutExpired) as error:
            return False, f"could not inspect LLM state before smoke: {error}"
        before_state = before.stdout.strip()
        if before.returncode != 0 or before_state != "STOPPED":
            return (
                False,
                f"live smoke requires pre-state STOPPED, observed {before_state or 'UNKNOWN'}",
            )
        command = (
            str(evidence.wrapper_path),
            "run",
            "--standalone",
            "--model",
            (
                "llama-general/qwen3.6-general-local"
                if lane == "general"
                else "llama-code/qwen3-coder-local"
            ),
            "say only: NEURALENGINE_OPENCODE_COMPAT_SMOKE_OK",
        )
        try:
            result = self._command_runner(command, 180.0)
        except (OSError, subprocess.TimeoutExpired) as error:
            return False, f"live smoke could not complete: {error}"
        try:
            after = self._llm_state_runner((str(evidence.llm_path), "state"), 5.0)
        except (OSError, subprocess.TimeoutExpired) as error:
            return False, f"live smoke completed but final LLM state was unavailable: {error}"
        after_state = after.stdout.strip()
        if result.returncode != 0:
            return False, f"wrapper exited {result.returncode}: {result.stderr.strip()}"
        if "NEURALENGINE_OPENCODE_COMPAT_SMOKE_OK" not in result.stdout:
            return False, "wrapper completed without the expected smoke marker"
        if after.returncode != 0 or after_state != "STOPPED":
            return (
                False,
                f"live smoke cleanup failed; final LLM state is {after_state or 'UNKNOWN'}",
            )
        return True, f"{lane.upper()} marker smoke passed; final LLM state STOPPED"

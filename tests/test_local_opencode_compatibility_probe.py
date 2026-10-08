import json
from collections.abc import Sequence
from pathlib import Path
from subprocess import CompletedProcess

from neural_engine.application.opencode_compatibility_service import (
    OpencodeCompatibilityService,
)
from neural_engine.domain.opencode_compatibility import OpencodeCompatibilityState
from neural_engine.infrastructure.local_opencode_compatibility_probe import (
    LocalOpencodeCompatibilityProbe,
    LocalOpencodeLiveSmokeRunner,
)
from neural_engine.ports.opencode_compatibility import OpencodeCompatibilityEvidence


class NoopSmokeRunner:
    def run(
        self,
        evidence: OpencodeCompatibilityEvidence,
        *,
        lane: str,
    ) -> tuple[bool, str]:
        return True, "not requested"


def _fixture(tmp_path: Path) -> tuple[Path, Path, dict[str, str]]:
    config_directory = tmp_path / "config" / "opencode"
    (config_directory / "agents").mkdir(parents=True)
    (config_directory / "plugin").mkdir()
    agent = config_directory / "agents" / "arch-data-engineer.md"
    agent.write_text("agent", encoding="utf-8")

    config = {
        "default_agent": "arch-data-engineer",
        "provider": {
            "llama-general": {"models": {"qwen3.6-general-local": {}}},
            "llama-vision": {"models": {"gemma4-vision-local": {}}},
        },
    }
    (config_directory / "opencode.json").write_text(json.dumps(config), encoding="utf-8")

    llm = tmp_path / "llm"
    llm.write_text("#!/bin/sh\n", encoding="utf-8")
    llm.chmod(0o755)
    plugin = config_directory / "plugin" / "llm-autostart.js"
    plugin.write_text(
        f'''const LLM = "{llm}";
const ROLE_BY_MODEL = new Map([
  ["llama-general/qwen3.6-general-local", "general"],
  ["llama-vision/gemma4-vision-local", "vision"],
]);
Bun.spawnSync([LLM, "switch", role]);
''',
        encoding="utf-8",
    )
    wrapper = tmp_path / "opencode-watch"
    wrapper.write_text("#!/bin/sh\n", encoding="utf-8")
    wrapper.chmod(0o755)
    executable = tmp_path / "opencode"
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    executable.chmod(0o755)
    commands = {"opencode": str(executable), "opencode-watch": str(wrapper)}
    return config_directory, plugin, commands


def test_probe_accepts_a_compatible_future_version_without_starting_services(
    tmp_path: Path,
) -> None:
    config_directory, plugin, commands = _fixture(tmp_path)

    def which(command: str) -> str | None:
        return commands.get(command)

    def run(command: Sequence[str], timeout: float) -> CompletedProcess[str]:
        assert list(command)[-1] == "--version"
        assert timeout == 5.0
        return CompletedProcess(command, 0, "opencode v99.4.1\n", "")

    probe = LocalOpencodeCompatibilityProbe(
        config_path=config_directory / "opencode.json",
        plugin_path=plugin,
        agent_directory=config_directory / "agents",
        which=which,
        command_runner=run,
    )
    report = OpencodeCompatibilityService(probe, NoopSmokeRunner()).inspect()

    assert report.version == "opencode v99.4.1"
    assert report.compatibility is OpencodeCompatibilityState.PASS
    assert {check.name for check in report.checks} >= {
        "executable",
        "version",
        "config",
        "agent contract",
        "lifecycle integration",
        "wrapper",
        "Brain safety boundary",
        "CODE role",
    }
    code = next(check for check in report.checks if check.name == "CODE role")
    assert "UNFILLED/unsupported" in code.detail


def test_stale_code_mapping_blocks_compatibility_preflight(tmp_path: Path) -> None:
    config_directory, plugin, commands = _fixture(tmp_path)
    config_path = config_directory / "opencode.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["provider"]["llama-code"] = {"models": {"retired": {}}}
    config_path.write_text(json.dumps(config), encoding="utf-8")
    agent_directory = config_directory / "agents"
    (agent_directory / "arch-data-engineer.md").write_text(
        "model: llama-code/retired\n", encoding="utf-8"
    )

    probe = LocalOpencodeCompatibilityProbe(
        config_path=config_path,
        plugin_path=plugin,
        agent_directory=agent_directory,
        which=commands.get,
        command_runner=lambda command, timeout: CompletedProcess(
            command, 0, "opencode v7.0.0\n", ""
        ),
    )
    report = OpencodeCompatibilityService(probe, NoopSmokeRunner()).inspect()

    assert report.compatibility is OpencodeCompatibilityState.BLOCKED
    code = next(check for check in report.checks if check.name == "CODE role")
    assert "stale CODE model mapping" in code.detail


def test_enabled_coder_agent_cannot_fall_back_to_the_general_model(tmp_path: Path) -> None:
    config_directory, plugin, commands = _fixture(tmp_path)
    config_path = config_directory / "opencode.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["agents"] = {"coder": {"mode": "primary"}}
    config_path.write_text(json.dumps(config), encoding="utf-8")
    agent_directory = config_directory / "agents"
    (agent_directory / "coder.md").write_text("name: coder\n", encoding="utf-8")

    probe = LocalOpencodeCompatibilityProbe(
        config_path=config_path,
        plugin_path=plugin,
        agent_directory=agent_directory,
        which=commands.get,
        command_runner=lambda command, timeout: CompletedProcess(
            command, 0, "opencode v7.0.0\n", ""
        ),
    )
    report = OpencodeCompatibilityService(probe, NoopSmokeRunner()).inspect()

    assert report.compatibility is OpencodeCompatibilityState.BLOCKED
    code = next(check for check in report.checks if check.name == "CODE role")
    assert "enabled coder agent" in code.detail


def test_code_live_smoke_refuses_without_inspecting_or_starting_models() -> None:
    evidence = OpencodeCompatibilityEvidence(
        version=None,
        capabilities=(),
        wrapper_path=Path("/tmp/opencode-watch"),
        llm_path=Path("/tmp/llm"),
        model_ids=(("llama-general/qwen3.6-general-local", "qwen3.6-general-local"),),
    )
    runner = LocalOpencodeLiveSmokeRunner(
        command_runner=lambda *_: (_ for _ in ()).throw(AssertionError("must not run")),
        llm_state_runner=lambda *_: (_ for _ in ()).throw(AssertionError("must not inspect")),
    )

    passed, detail = runner.run(evidence, lane="code")

    assert passed is False
    assert "CODE role is UNFILLED/unsupported" in detail


def test_missing_vision_model_is_degraded(tmp_path: Path) -> None:
    config_directory, plugin, commands = _fixture(tmp_path)
    config_path = config_directory / "opencode.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    del config["provider"]["llama-vision"]
    config_path.write_text(json.dumps(config), encoding="utf-8")

    probe = LocalOpencodeCompatibilityProbe(
        config_path=config_path,
        plugin_path=plugin,
        agent_directory=config_directory / "agents",
        which=commands.get,
        command_runner=lambda command, timeout: CompletedProcess(
            command, 0, "opencode v7.0.0\n", ""
        ),
    )
    report = OpencodeCompatibilityService(probe, NoopSmokeRunner()).inspect()

    assert report.compatibility is OpencodeCompatibilityState.DEGRADED
    vision = next(check for check in report.checks if "vision" in check.name.lower())
    assert vision.state is OpencodeCompatibilityState.DEGRADED


def test_brain_reference_in_integration_is_blocked(tmp_path: Path) -> None:
    config_directory, plugin, commands = _fixture(tmp_path)
    plugin.write_text(plugin.read_text(encoding="utf-8") + "neural brain write\n", encoding="utf-8")
    probe = LocalOpencodeCompatibilityProbe(
        config_path=config_directory / "opencode.json",
        plugin_path=plugin,
        agent_directory=config_directory / "agents",
        which=commands.get,
        command_runner=lambda command, timeout: CompletedProcess(
            command, 0, "opencode v7.0.0\n", ""
        ),
    )
    report = OpencodeCompatibilityService(probe, NoopSmokeRunner()).inspect()

    assert report.compatibility is OpencodeCompatibilityState.BLOCKED
    safety = next(check for check in report.checks if check.name == "Brain safety boundary")
    assert safety.state is OpencodeCompatibilityState.BLOCKED


def test_version_from_stderr_when_stdout_is_whitespace_only(tmp_path: Path) -> None:
    """Test that version is correctly extracted from stderr when stdout contains only whitespace."""
    config_directory, plugin, commands = _fixture(tmp_path)

    def run(command: Sequence[str], timeout: float) -> CompletedProcess[str]:
        assert list(command)[-1] == "--version"
        assert timeout == 5.0
        # Simulate a case where stdout is whitespace-only and stderr contains version
        return CompletedProcess(command, 0, "   \n\t  \n", "opencode v8.0.0\n")

    probe = LocalOpencodeCompatibilityProbe(
        config_path=config_directory / "opencode.json",
        plugin_path=plugin,
        agent_directory=config_directory / "agents",
        which=commands.get,
        command_runner=run,
    )
    report = OpencodeCompatibilityService(probe, NoopSmokeRunner()).inspect()

    assert report.version == "opencode v8.0.0"
    assert report.compatibility is OpencodeCompatibilityState.PASS


def test_version_from_stdout_when_both_contain_text(tmp_path: Path) -> None:
    """Test that version is correctly extracted from stdout when both streams contain text."""
    config_directory, plugin, commands = _fixture(tmp_path)

    def run(command: Sequence[str], timeout: float) -> CompletedProcess[str]:
        assert list(command)[-1] == "--version"
        assert timeout == 5.0
        # Both streams contain text, stdout should be preferred
        return CompletedProcess(command, 0, "opencode v9.0.0\n", "additional info\n")

    probe = LocalOpencodeCompatibilityProbe(
        config_path=config_directory / "opencode.json",
        plugin_path=plugin,
        agent_directory=config_directory / "agents",
        which=commands.get,
        command_runner=run,
    )
    report = OpencodeCompatibilityService(probe, NoopSmokeRunner()).inspect()

    assert report.version == "opencode v9.0.0"
    assert report.compatibility is OpencodeCompatibilityState.PASS

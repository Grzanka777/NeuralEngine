from __future__ import annotations

import runpy
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


@pytest.fixture
def runner() -> dict[str, Any]:
    return runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/pi-local"))


@pytest.fixture
def adapter() -> dict[str, Any]:
    return runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/pi-model"))


def _fake_adapter() -> SimpleNamespace:
    calls: list[tuple[str, str]] = []

    class FakeAdapter:
        PROVIDERS = {
            "GENERAL": "neural-general",
            "CODE": "neural-code",
            "GPTOSS": "local-gptoss",
        }
        MODELS = {
            "GENERAL": "/models/general.gguf",
            "CODE": "/models/code.gguf",
            "GPTOSS": "/models/patch.gguf",
        }
        SwitchError = RuntimeError

        @staticmethod
        def scan() -> dict[str, None]:
            return {"GENERAL": None, "CODE": None, "GPTOSS": None}

        @staticmethod
        def identify(_states: object) -> None:
            return None

        @staticmethod
        def switch(role: str) -> SimpleNamespace:
            calls.append(("switch", role))
            return SimpleNamespace(profile=role)

        @staticmethod
        def stop_current() -> None:
            calls.append(("stop", ""))

    return SimpleNamespace(module=FakeAdapter, calls=calls)


def _install_guard(root: Path) -> Path:
    path = root / ".pi/extensions/neuralengine-guard.ts"
    path.parent.mkdir(parents=True)
    path.write_text("export default function guard() {}\n", encoding="utf-8")
    return path


@pytest.fixture
def policy(tmp_path: Path) -> Path:
    path = tmp_path / "policy.json"
    path.write_text(
        f'{{"ROLE":"CODE","WORKSPACE_ROOT":"{tmp_path}"}}',
        encoding="utf-8",
    )
    return path


def test_code_runner_selects_exact_provider_model_and_bounded_policy(
    runner: dict[str, Any], policy: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _fake_adapter()
    executable = tmp_path / "pi"
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable.chmod(0o755)
    guard = _install_guard(tmp_path)
    observed: dict[str, Any] = {}

    def fake_run(
        command: list[str], *, cwd: Path, env: dict[str, str], check: bool
    ) -> subprocess.CompletedProcess[str]:
        observed.update(command=command, cwd=cwd, env=env, check=check)
        return subprocess.CompletedProcess(command, 0)

    namespace = runner["_run_role"].__globals__
    monkeypatch.setitem(namespace, "ROOT", tmp_path)
    monkeypatch.setitem(namespace, "PI_ENTRYPOINT", executable)
    monkeypatch.setitem(namespace, "_load_adapter", lambda: fake.module)
    monkeypatch.setitem(namespace["subprocess"].__dict__, "run", fake_run)

    assert runner["_run_role"]("CODE", ["--print", "task"], str(policy)) == 0
    assert observed["command"] == [
        str(executable),
        "--provider",
        "neural-code",
        "--model",
        "/models/code.gguf",
        "--extension",
        str(guard),
        "--print",
        "task",
    ]
    assert observed["env"]["NEURAL_PI_BOUNDED_CODE"] == "1"
    assert observed["env"]["NEURAL_PI_POLICY_FILE"] == "policy.json"
    assert fake.calls == [("switch", "CODE"), ("stop", "")]


@pytest.mark.parametrize(
    ("role", "provider", "model"),
    [
        ("GENERAL", "neural-general", "/models/general.gguf"),
        ("GPTOSS", "local-gptoss", "/models/patch.gguf"),
    ],
)
def test_runner_maps_general_and_patch_without_fallback(
    runner: dict[str, Any],
    role: str,
    provider: str,
    model: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _fake_adapter()
    executable = tmp_path / "pi"
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable.chmod(0o755)
    observed: dict[str, Any] = {}

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        observed.update(command=command, **kwargs)
        return subprocess.CompletedProcess(command, 0)

    namespace = runner["_run_role"].__globals__
    monkeypatch.setitem(namespace, "ROOT", tmp_path)
    monkeypatch.setitem(namespace, "PI_ENTRYPOINT", executable)
    monkeypatch.setitem(namespace, "_load_adapter", lambda: fake.module)
    monkeypatch.setitem(namespace["subprocess"].__dict__, "run", fake_run)

    policy: str | None = None
    if role == "GPTOSS":
        guard = _install_guard(tmp_path)
        patch_policy = tmp_path / "patch-policy.json"
        patch_policy.write_text(
            f'{{"ROLE":"PATCH","WORKSPACE_ROOT":"{tmp_path}"}}',
            encoding="utf-8",
        )
        policy = str(patch_policy)
    assert runner["_run_role"](role, ["--print", "task"], policy) == 0
    assert observed["command"][1:5] == ["--provider", provider, "--model", model]
    if role == "GPTOSS":
        assert observed["env"]["NEURAL_PI_BOUNDED_CODE"] == "1"
        assert observed["command"][5:7] == ["--extension", str(guard)]
    else:
        assert "NEURAL_PI_BOUNDED_CODE" not in observed["env"]


def test_runner_rejects_provider_override(runner: dict[str, Any]) -> None:
    with pytest.raises(runner["LocalPiError"], match="do not override --provider"):
        runner["_reject_role_overrides"](["--provider", "wrong"])


@pytest.mark.parametrize(
    "arguments",
    [
        ["--no-extensions"],
        ["-ne"],
        ["--extension", "other.ts"],
        ["-e", "other.ts"],
        ["--extension=other.ts"],
    ],
)
def test_bounded_runner_rejects_extension_loader_overrides(
    runner: dict[str, Any], arguments: list[str]
) -> None:
    with pytest.raises(runner["LocalPiError"], match="requires the project Guard"):
        runner["_reject_role_overrides"](arguments, guard_required=True)


def test_general_preserves_extension_loader_passthrough(runner: dict[str, Any]) -> None:
    runner["_reject_role_overrides"](["--no-extensions"], guard_required=False)


def test_argument_separator_keeps_extension_like_prompt_positional(
    runner: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    observed: dict[str, Any] = {}

    def fake_run(role: str, arguments: list[str], policy: str | None) -> int:
        observed.update(role=role, arguments=arguments, policy=policy)
        return 0

    monkeypatch.setitem(runner["main"].__globals__, "_run_role", fake_run)

    assert runner["main"](["code", "--policy", "policy.json", "--", "--no-extensions"]) == 0
    assert observed == {
        "role": "CODE",
        "arguments": ["--", "--no-extensions"],
        "policy": "policy.json",
    }


def test_bounded_runner_fails_closed_when_guard_is_missing(
    runner: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(runner["_guard_extension_path"].__globals__, "ROOT", tmp_path)

    with pytest.raises(runner["LocalPiError"], match="required Guard extension is unavailable"):
        runner["_guard_extension_path"]()


def test_runner_propagates_pi_exit_and_guarded_cleanup(
    runner: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _fake_adapter()
    executable = tmp_path / "pi"
    executable.write_text("#!/bin/sh\nexit 7\n", encoding="utf-8")
    executable.chmod(0o755)

    namespace = runner["_run_role"].__globals__
    monkeypatch.setitem(namespace, "ROOT", tmp_path)
    monkeypatch.setitem(namespace, "PI_ENTRYPOINT", executable)
    monkeypatch.setitem(namespace, "_load_adapter", lambda: fake.module)
    monkeypatch.setitem(
        namespace["subprocess"].__dict__,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(command, 7),
    )

    assert runner["_run_role"]("GENERAL", [], None) == 7
    assert fake.calls == [("switch", "GENERAL"), ("stop", "")]


def test_vision_is_fail_closed(runner: dict[str, Any], capsys: pytest.CaptureFixture[str]) -> None:
    assert runner["main"](["vision"]) == 1
    assert "VISION is UNFILLED" in capsys.readouterr().err


def test_pi_model_status_stopped_reports_mapping(
    adapter: dict[str, Any], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setitem(
        adapter["status"].__globals__,
        "scan",
        lambda: {"GENERAL": None, "CODE": None, "GPTOSS": None},
    )
    monkeypatch.setitem(
        adapter["status"].__globals__,
        "_catalog_matches",
        lambda: ("OK", "exact role/provider/model mapping"),
    )

    assert adapter["status"]() == 0
    output = capsys.readouterr().out
    assert "LIFECYCLE=STOPPED" in output
    assert "ACTIVE_ROLE=NONE" in output
    assert "PI_MAPPING_GENERAL_PROVIDER=neural-general" in output
    assert "PI_MAPPING_CODE_PROVIDER=neural-code" in output
    assert "PI_MAPPING_PATCH_PROVIDER=local-gptoss" in output
    assert "FALLBACK=DISABLED" in output
    assert "VISION=UNFILLED/FAIL_CLOSED" in output


def test_pi_model_status_running_reports_actual_identity(
    adapter: dict[str, Any], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    listener = adapter["Listener"]("CODE", 123)
    monkeypatch.setitem(
        adapter["status"].__globals__,
        "scan",
        lambda: {"GENERAL": None, "CODE": (123,), "GPTOSS": None},
    )
    monkeypatch.setitem(adapter["status"].__globals__, "identify", lambda _states: listener)
    monkeypatch.setitem(
        adapter["status"].__globals__,
        "_catalog_matches",
        lambda: ("OK", "exact role/provider/model mapping"),
    )

    assert adapter["status"]() == 0
    output = capsys.readouterr().out
    assert "LIFECYCLE=RUNNING" in output
    assert "ACTIVE_ROLE=CODE" in output
    assert "ACTIVE_PID=123" in output
    assert "ACTIVE_ENDPOINT=http://127.0.0.1:18080/v1" in output
    assert "ACTUAL_IDENTITY=/models/gguf/nemotron-3-nano-30b-a3b/" in output

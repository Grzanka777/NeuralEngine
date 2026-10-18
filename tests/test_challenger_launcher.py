"""Ownership and profile checks for the local challengers."""

from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import sys
from contextlib import nullcontext
from pathlib import Path
from types import ModuleType

import pytest


def load_challenger() -> ModuleType:
    path = Path(__file__).resolve().parents[1] / "scripts/challenger"
    loader = importlib.machinery.SourceFileLoader("challenger", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    loader.exec_module(module)
    return module


challenger = load_challenger()


def test_supported_challenger_profiles_and_state_directory() -> None:
    assert set(challenger.PROFILES) == {"gptoss"}
    assert challenger.PROFILES["gptoss"].model == Path(
        "/models/gguf/gpt-oss-20b/gpt-oss-20b-MXFP4.gguf"
    )
    assert challenger.state_dir().name == "neural-challenger"


def test_gptoss_profile_uses_requested_native_runtime_defaults() -> None:
    profile = challenger.PROFILES["gptoss"]
    assert (
        profile.expected_sha256
        == json.loads((Path(__file__).resolve().parents[1] / "llm-manifest.json").read_text())[
            "roles"
        ]["PATCH"]["model_sha256"]
    )
    assert profile.expected_sha256 is not None
    assert (profile.port, profile.model.name) == (18086, "gpt-oss-20b-MXFP4.gguf")
    assert profile.command_for() == profile.command_for(context=32768, batch=2048, ubatch=1024)
    assert profile.command[profile.command.index("-ngl") + 1] == "999"
    assert profile.command[profile.command.index("-fa") + 1] == "on"
    assert profile.command[profile.command.index("--parallel") + 1] == "1"
    assert "--jinja" in profile.command
    assert "--chat-template" not in profile.command
    tuned = profile.command_for(context=65536, batch=4096, ubatch=2048)
    assert tuned[tuned.index("-c") + 1] == "65536"
    assert tuned[tuned.index("-b") + 1] == "4096"
    assert tuned[tuned.index("-ub") + 1] == "2048"


@pytest.mark.parametrize(
    "context,batch,ubatch",
    [(16384, 2048, 1024), (32768, 8192, 1024), (32768, 1024, 2048)],
)
def test_gptoss_runtime_rejects_unapproved_combinations(
    context: int, batch: int, ubatch: int
) -> None:
    with pytest.raises(RuntimeError):
        challenger.PROFILES["gptoss"].command_for(context=context, batch=batch, ubatch=ubatch)


def test_unknown_listener_is_never_borrowed(monkeypatch: pytest.MonkeyPatch) -> None:
    profile = challenger.PROFILES["gptoss"]
    monkeypatch.setattr(challenger, "listener_pids", lambda port: (True, (441,)))
    monkeypatch.setattr(challenger, "owned_process", lambda pid, selected: False)
    with pytest.raises(RuntimeError, match="unknown or unhealthy"):
        challenger.active_pid(profile)


def test_owned_listener_requires_matching_model(monkeypatch: pytest.MonkeyPatch) -> None:
    profile = challenger.PROFILES["gptoss"]
    monkeypatch.setattr(challenger, "listener_pids", lambda port: (True, (441,)))
    monkeypatch.setattr(challenger, "owned_process", lambda pid, selected: True)
    monkeypatch.setattr(challenger, "endpoint_identity", lambda selected: False)
    with pytest.raises(RuntimeError, match="unknown or unhealthy"):
        challenger.active_pid(profile)


@pytest.mark.parametrize("conflict_port", (18081, 18087))
def test_start_refuses_to_run_beside_a_conflicting_listener(
    conflict_port: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile = challenger.PROFILES["gptoss"]
    monkeypatch.setattr(challenger, "lifecycle_lock", nullcontext)
    monkeypatch.setattr(challenger, "verify_model_artifact", lambda selected: None)
    monkeypatch.setattr(challenger, "active_pid", lambda selected: None)
    monkeypatch.setattr(
        challenger,
        "listener_pids",
        lambda port: (port == conflict_port, (555,) if port == conflict_port else ()),
    )
    monkeypatch.setattr(
        challenger.subprocess,
        "Popen",
        lambda *args, **kwargs: pytest.fail("production listener must prevent launch"),
    )
    with pytest.raises(
        RuntimeError,
        match=f"conflicting listener is already active on port {conflict_port}",
    ):
        challenger.start(profile)


def test_guarded_stop_refuses_replaced_pid(monkeypatch: pytest.MonkeyPatch) -> None:
    profile = challenger.PROFILES["gptoss"]
    monkeypatch.setattr(challenger, "active_pid", lambda selected: 442)
    monkeypatch.setattr(
        challenger, "lifecycle_lock", lambda: __import__("contextlib").nullcontext()
    )
    monkeypatch.setattr(challenger.os, "kill", lambda *args: pytest.fail("unexpected kill"))
    with pytest.raises(RuntimeError, match="expected pid 441, found 442"):
        challenger.stop(profile, 441)


def test_unmanaged_matching_server_cannot_be_stopped(monkeypatch: pytest.MonkeyPatch) -> None:
    profile = challenger.PROFILES["gptoss"]
    monkeypatch.setattr(challenger, "active_pid", lambda selected: 441)
    monkeypatch.setattr(
        challenger, "lifecycle_lock", lambda: __import__("contextlib").nullcontext()
    )
    monkeypatch.setattr(challenger, "recorded_owner", lambda selected, pid: False)
    monkeypatch.setattr(challenger.os, "kill", lambda *args: pytest.fail("unexpected kill"))
    with pytest.raises(RuntimeError, match="no matching challenger ownership record"):
        challenger.stop(profile, 441)


def test_owner_record_binds_pid_and_process_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile = challenger.PROFILES["gptoss"]
    monkeypatch.setattr(challenger, "state_dir", lambda: tmp_path)
    monkeypatch.setattr(challenger, "process_start_time", lambda pid: "12345")
    challenger.record_owner(profile, 441)
    assert challenger.recorded_owner(profile, 441)
    assert not challenger.recorded_owner(profile, 442)
    monkeypatch.setattr(challenger, "process_start_time", lambda pid: "12346")
    assert not challenger.recorded_owner(profile, 441)


def test_retired_qwen_challenger_wrappers_are_absent() -> None:
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    for name in ("qglm", "qq38", "qwen-challenger"):
        assert not (scripts / name).exists()

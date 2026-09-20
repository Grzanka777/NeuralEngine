from __future__ import annotations

import importlib.util
import multiprocessing
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest


def _load_launcher(module_name: str = "neural_engine_llm_launcher") -> ModuleType:
    launcher_path = Path(__file__).parents[1] / "scripts" / "llm"
    loader = SourceFileLoader(module_name, str(launcher_path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Could not load launcher at {launcher_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


launcher = _load_launcher()


def _acquire_lock_in_child(lock_path: str, acquired: Any) -> None:
    with launcher.lifecycle_lock(Path(lock_path)):
        acquired.set()


def _profile(tmp_path: Path) -> Any:
    model = tmp_path / "model.gguf"
    mtp = tmp_path / "mtp.gguf"
    runtime = tmp_path / "llama-server"
    for path in (model, mtp, runtime):
        path.touch()
    runtime.chmod(runtime.stat().st_mode | 0o111)
    return launcher.GeneralProfile(model=model, mtp=mtp, runtime=runtime)


def _code_profile(tmp_path: Path) -> Any:
    model = tmp_path / "code-model.gguf"
    runtime = tmp_path / "llama-server"
    for path in (model, runtime):
        path.touch()
    runtime.chmod(runtime.stat().st_mode | 0o111)
    return launcher.CodeProfile(model=model, runtime=runtime)


def _vision_profile(tmp_path: Path) -> Any:
    model = tmp_path / "vision-model.gguf"
    mmproj = tmp_path / "mmproj.gguf"
    mtp = tmp_path / "vision-mtp.gguf"
    runtime = tmp_path / "llama-server"
    for path in (model, mmproj, mtp, runtime):
        path.touch()
    runtime.chmod(runtime.stat().st_mode | 0o111)
    return launcher.VisionProfile(model=model, mmproj=mmproj, mtp=mtp, runtime=runtime)


def _free_ports(_: int) -> Any:
    return launcher.PortState(listening=False)


def test_launcher_artifact_paths_can_be_relocated_without_changing_profiles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configured_paths = {
        "NEURALENGINE_GENERAL_MODEL": tmp_path / "general.gguf",
        "NEURALENGINE_GENERAL_MTP": tmp_path / "general-mtp.gguf",
        "NEURALENGINE_CODE_MODEL": tmp_path / "code.gguf",
        "NEURALENGINE_VISION_MODEL": tmp_path / "vision.gguf",
        "NEURALENGINE_VISION_MMPROJ": tmp_path / "vision-mmproj.gguf",
        "NEURALENGINE_VISION_MTP": tmp_path / "vision-mtp.gguf",
        "NEURALENGINE_LLAMA_SERVER": tmp_path / "llama-server",
    }
    for name, path in configured_paths.items():
        monkeypatch.setenv(name, str(path))

    configured = _load_launcher("neural_engine_llm_launcher_configured")

    assert configured_paths["NEURALENGINE_GENERAL_MODEL"] == configured.GENERAL_MODEL
    assert configured_paths["NEURALENGINE_GENERAL_MTP"] == configured.GENERAL_MTP
    assert configured_paths["NEURALENGINE_CODE_MODEL"] == configured.CODE_MODEL
    assert configured_paths["NEURALENGINE_VISION_MODEL"] == configured.VISION_MODEL
    assert configured_paths["NEURALENGINE_VISION_MMPROJ"] == configured.VISION_MMPROJ
    assert configured_paths["NEURALENGINE_VISION_MTP"] == configured.VISION_MTP
    assert configured_paths["NEURALENGINE_LLAMA_SERVER"] == configured.LLAMA_SERVER
    assert configured.DEFAULT_PROFILE.runtime == configured.LLAMA_SERVER
    assert configured.DEFAULT_CODE_PROFILE.runtime == configured.LLAMA_SERVER
    assert configured.DEFAULT_CODE_PROFILE.arguments()[1] == str(configured.CODE_MODEL)
    assert configured.DEFAULT_PROFILE.arguments()[1] == str(configured.GENERAL_MODEL)
    assert configured.VisionProfile().arguments()[1] == str(configured.VISION_MODEL)


def test_missing_model_is_reported_before_launch(tmp_path: Path) -> None:
    profile = _profile(tmp_path)
    profile.model.unlink()
    launched = False

    def process_factory(*args: Any, **kwargs: Any) -> Any:
        nonlocal launched
        launched = True
        return None

    with pytest.raises(launcher.LauncherError, match="model does not exist"):
        launcher.start_general(
            profile,
            port_reader=_free_ports,
            process_factory=process_factory,
        )

    assert launched is False


def test_missing_runtime_is_reported_before_launch(tmp_path: Path) -> None:
    profile = _profile(tmp_path)
    profile.runtime.unlink()

    with pytest.raises(launcher.LauncherError, match="llama-server runtime does not exist"):
        launcher.start_general(profile, port_reader=_free_ports)


def test_port_already_occupied_refuses_to_launch(tmp_path: Path) -> None:
    profile = _profile(tmp_path)
    calls: list[int] = []

    def occupied_ports(port: int) -> Any:
        calls.append(port)
        return launcher.PortState(listening=port == 18080, pids=(1234,))

    with pytest.raises(launcher.LauncherError, match="18080"):
        launcher.start_general(
            profile,
            port_reader=occupied_ports,
            identity_checker=lambda _pid, _profile: False,
        )

    # 18081 is read first for the idempotency pre-scan; CONFLICT_PORTS follow
    assert calls == [18081, 18080, 18081, 18082, 18084]


def test_start_reports_endpoint_after_health_success(tmp_path: Path, capsys: Any) -> None:
    profile = _profile(tmp_path)
    log_path = tmp_path / "state" / "general.log"
    started: dict[str, Any] = {}

    class FakeProcess:
        pid = 4321

        def poll(self) -> None:
            return None

    def process_factory(command: tuple[str, ...], **kwargs: Any) -> FakeProcess:
        started["command"] = command
        started["kwargs"] = kwargs
        return FakeProcess()

    launcher.start_general(
        profile,
        port_reader=_free_ports,
        process_factory=process_factory,
        health_waiter=lambda selected: selected is profile,
        log_path=lambda: log_path,
    )

    output = capsys.readouterr().out
    assert "GENERAL READY" in output
    assert "endpoint: http://127.0.0.1:18081/v1" in output
    assert "pid: 4321" in output
    assert started["command"] == profile.command()
    assert started["kwargs"]["start_new_session"] is True


def test_health_wait_succeeds_after_initial_failure() -> None:
    checks = iter((False, True))

    assert launcher.wait_for_health(
        timeout_seconds=1,
        poll_seconds=0,
        health_check=lambda: next(checks),
    )


def test_health_wait_times_out_without_success() -> None:
    times = iter((0.0, 0.0, 1.0))

    assert not launcher.wait_for_health(
        timeout_seconds=0.5,
        poll_seconds=0,
        health_check=lambda: False,
        clock=lambda: next(times),
        sleeper=lambda _: None,
    )


def test_code_profile_has_only_the_frozen_non_speculative_arguments(tmp_path: Path) -> None:
    profile = _code_profile(tmp_path)

    assert profile.command() == (
        str(profile.runtime),
        "-m",
        str(profile.model),
        "-dev",
        "Vulkan0",
        "-ngl",
        "999",
        "-c",
        "32768",
        "-b",
        "2048",
        "-ub",
        "1024",
        "-np",
        "1",
        "-fa",
        "on",
        "--cache-prompt",
        "--metrics",
        "--host",
        "127.0.0.1",
        "--port",
        "18080",
    )
    assert "--spec-type" not in profile.command()
    assert "--spec-draft-model" not in profile.command()
    assert "--mtp" not in profile.command()


def test_code_missing_model_is_reported_before_launch(tmp_path: Path) -> None:
    profile = _code_profile(tmp_path)
    profile.model.unlink()
    launched = False

    def process_factory(*args: Any, **kwargs: Any) -> Any:
        nonlocal launched
        launched = True
        return None

    with pytest.raises(launcher.LauncherError, match="CODE start refused: model does not exist"):
        launcher.start_code(
            profile,
            port_reader=_free_ports,
            process_factory=process_factory,
        )

    assert launched is False


def test_code_missing_runtime_is_reported_before_launch(tmp_path: Path) -> None:
    profile = _code_profile(tmp_path)
    profile.runtime.unlink()

    with pytest.raises(
        launcher.LauncherError,
        match="CODE start refused: llama-server runtime does not exist",
    ):
        launcher.start_code(profile, port_reader=_free_ports)


def test_code_non_executable_runtime_is_reported_before_launch(tmp_path: Path) -> None:
    profile = _code_profile(tmp_path)
    profile.runtime.chmod(0o644)

    with pytest.raises(
        launcher.LauncherError,
        match="CODE start refused: runtime is not executable",
    ):
        launcher.start_code(profile, port_reader=_free_ports)


@pytest.mark.parametrize("blocked_port", (18080, 18081, 18084))
def test_code_refuses_any_conflicting_listener(tmp_path: Path, blocked_port: int) -> None:
    profile = _code_profile(tmp_path)
    launched = False

    def process_factory(*args: Any, **kwargs: Any) -> Any:
        nonlocal launched
        launched = True
        return None

    def occupied_ports(port: int) -> Any:
        return launcher.PortState(listening=port == blocked_port, pids=(1234,))

    with pytest.raises(launcher.LauncherError, match=str(blocked_port)):
        launcher.start_code(
            profile,
            port_reader=occupied_ports,
            process_factory=process_factory,
        )

    assert launched is False


def test_code_health_accepts_only_http_200_healthy_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile = _code_profile(tmp_path)

    class FakeResponse:
        status = 200

        def __init__(self, payload: bytes) -> None:
            self.payload = payload

        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, *args: Any) -> None:
            return None

        def read(self, *args: Any) -> bytes:
            return self.payload

    monkeypatch.setattr(
        launcher.urllib.request,
        "urlopen",
        lambda *args, **kwargs: FakeResponse(b'{"status":"ok"}'),
    )
    assert launcher._code_health_ok(profile) is True

    monkeypatch.setattr(
        launcher.urllib.request,
        "urlopen",
        lambda *args, **kwargs: FakeResponse(b'{"status":"loading model"}'),
    )
    assert launcher._code_health_ok(profile) is False


def test_code_health_timeout_terminates_started_process(tmp_path: Path) -> None:
    profile = _code_profile(tmp_path)
    state: dict[str, Any] = {"terminated": False, "waited": False}

    class FakeProcess:
        pid = 4322

        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            state["terminated"] = True

        def wait(self, timeout: float) -> None:
            state["waited"] = timeout == 5

    with pytest.raises(launcher.LauncherError, match="did not become healthy"):
        launcher.start_code(
            profile,
            port_reader=_free_ports,
            process_factory=lambda *args, **kwargs: FakeProcess(),
            health_waiter=lambda _: False,
            log_path=lambda: tmp_path / "state" / "code.log",
        )

    assert state == {"terminated": True, "waited": True}


def test_start_code_reports_endpoint_after_health_success(tmp_path: Path, capsys: Any) -> None:
    profile = _code_profile(tmp_path)
    log_path = tmp_path / "state" / "code.log"
    started: dict[str, Any] = {}

    class FakeProcess:
        pid = 4323

        def poll(self) -> None:
            return None

    def process_factory(command: tuple[str, ...], **kwargs: Any) -> FakeProcess:
        started["command"] = command
        started["kwargs"] = kwargs
        return FakeProcess()

    launcher.start_code(
        profile,
        port_reader=_free_ports,
        process_factory=process_factory,
        health_waiter=lambda selected: selected is profile,
        log_path=lambda: log_path,
    )

    output = capsys.readouterr().out
    assert "CODE READY" in output
    assert "endpoint: http://127.0.0.1:18080/v1" in output
    assert "pid: 4323" in output
    assert started["command"] == profile.command()
    assert started["kwargs"]["start_new_session"] is True


def test_vision_profile_matches_verified_frozen_arguments(tmp_path: Path) -> None:
    profile = _vision_profile(tmp_path)

    assert profile.command() == (
        str(profile.runtime),
        "-m",
        str(profile.model),
        "--mmproj",
        str(profile.mmproj),
        "-dev",
        "Vulkan0",
        "-ngl",
        "999",
        "-c",
        "32768",
        "-b",
        "2048",
        "-ub",
        "1024",
        "-np",
        "1",
        "-fa",
        "on",
        "-ctk",
        "f16",
        "-ctv",
        "f16",
        "--cache-prompt",
        "--spec-type",
        "draft-mtp",
        "--spec-draft-model",
        str(profile.mtp),
        "--spec-draft-device",
        "Vulkan0",
        "--spec-draft-ngl",
        "999",
        "--spec-draft-n-max",
        "2",
        "--host",
        "127.0.0.1",
        "--port",
        "18082",
    )
    assert "--spec-type=draft-eagle3" not in profile.command()
    assert "--spec-default" not in profile.command()


def test_vision_missing_main_model_is_reported_before_launch(tmp_path: Path) -> None:
    profile = _vision_profile(tmp_path)
    profile.model.unlink()
    launched = False

    def process_factory(*args: Any, **kwargs: Any) -> Any:
        nonlocal launched
        launched = True
        return None

    with pytest.raises(launcher.LauncherError, match="VISION start refused: model does not exist"):
        launcher.start_vision(
            profile,
            port_reader=_free_ports,
            process_factory=process_factory,
        )

    assert launched is False


def test_vision_missing_runtime_is_reported_before_launch(tmp_path: Path) -> None:
    profile = _vision_profile(tmp_path)
    profile.runtime.unlink()

    with pytest.raises(
        launcher.LauncherError,
        match="VISION start refused: llama-server runtime does not exist",
    ):
        launcher.start_vision(profile, port_reader=_free_ports)


def test_vision_non_executable_runtime_is_reported_before_launch(tmp_path: Path) -> None:
    profile = _vision_profile(tmp_path)
    profile.runtime.chmod(0o644)

    with pytest.raises(
        launcher.LauncherError,
        match="VISION start refused: runtime is not executable",
    ):
        launcher.start_vision(profile, port_reader=_free_ports)


@pytest.mark.parametrize("missing_field", ("mmproj", "mtp"))
def test_vision_missing_required_auxiliary_file_is_reported(
    tmp_path: Path, missing_field: str
) -> None:
    profile = _vision_profile(tmp_path)
    getattr(profile, missing_field).unlink()

    with pytest.raises(launcher.LauncherError, match="VISION start refused"):
        launcher.start_vision(profile, port_reader=_free_ports)


@pytest.mark.parametrize("blocked_port", (18080, 18081, 18082, 18084))
def test_vision_refuses_any_conflicting_listener(tmp_path: Path, blocked_port: int) -> None:
    profile = _vision_profile(tmp_path)
    launched = False

    def process_factory(*args: Any, **kwargs: Any) -> Any:
        nonlocal launched
        launched = True
        return None

    def occupied_ports(port: int) -> Any:
        return launcher.PortState(listening=port == blocked_port, pids=(1234,))

    with pytest.raises(launcher.LauncherError, match=str(blocked_port)):
        launcher.start_vision(
            profile,
            port_reader=occupied_ports,
            process_factory=process_factory,
        )

    assert launched is False


def test_vision_health_accepts_http_200_healthy_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile = _vision_profile(tmp_path)

    class FakeResponse:
        status = 200

        def __init__(self, payload: bytes) -> None:
            self.payload = payload

        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, *args: Any) -> None:
            return None

        def read(self, *args: Any) -> bytes:
            return self.payload

    monkeypatch.setattr(
        launcher.urllib.request,
        "urlopen",
        lambda *args, **kwargs: FakeResponse(b'{"status":"ok"}'),
    )
    assert launcher._vision_health_ok(profile) is True

    monkeypatch.setattr(
        launcher.urllib.request,
        "urlopen",
        lambda *args, **kwargs: FakeResponse(b'{"status":"loading model"}'),
    )
    assert launcher._vision_health_ok(profile) is False


def test_start_vision_reports_endpoint_after_health_success(tmp_path: Path, capsys: Any) -> None:
    profile = _vision_profile(tmp_path)
    log_path = tmp_path / "state" / "vision.log"
    started: dict[str, Any] = {}

    class FakeProcess:
        pid = 4330

        def poll(self) -> None:
            return None

    def process_factory(command: tuple[str, ...], **kwargs: Any) -> FakeProcess:
        started["command"] = command
        started["kwargs"] = kwargs
        return FakeProcess()

    launcher.start_vision(
        profile,
        port_reader=_free_ports,
        process_factory=process_factory,
        health_waiter=lambda selected: selected is profile,
        log_path=lambda: log_path,
    )

    output = capsys.readouterr().out
    assert "VISION READY" in output
    assert "endpoint: http://127.0.0.1:18082/v1" in output
    assert "pid: 4330" in output
    assert started["command"] == profile.command()
    assert started["kwargs"]["start_new_session"] is True


def test_vision_health_timeout_terminates_started_process(tmp_path: Path) -> None:
    profile = _vision_profile(tmp_path)
    state: dict[str, Any] = {"terminated": False, "waited": False}

    class FakeProcess:
        pid = 4331

        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            state["terminated"] = True

        def wait(self, timeout: float) -> None:
            state["waited"] = timeout == 5

    with pytest.raises(launcher.LauncherError, match="did not become healthy"):
        launcher.start_vision(
            profile,
            port_reader=_free_ports,
            process_factory=lambda *args, **kwargs: FakeProcess(),
            health_waiter=lambda _: False,
            log_path=lambda: tmp_path / "state" / "vision.log",
        )

    assert state == {"terminated": True, "waited": True}


def test_status_reports_no_profile_running(capsys: Any) -> None:
    launcher.status_profiles(port_reader=_free_ports)

    output = capsys.readouterr().out
    assert "LLM STOPPED" in output
    assert "profile: none" in output
    assert "active port: none" in output


def test_status_reports_identifiable_code_profile(capsys: Any) -> None:
    launcher.status_profiles(
        port_reader=lambda port: launcher.PortState(
            listening=port == 18080,
            pids=(4324,) if port == 18080 else (),
        ),
        code_identity_checker=lambda pid, _: pid == 4324,
        code_health_check=lambda _: True,
    )

    output = capsys.readouterr().out
    assert "profile: CODE" in output
    assert "active port: 18080" in output
    assert "health: OK" in output
    assert "pid: 4324" in output


def test_status_reports_identifiable_general_profile(capsys: Any) -> None:
    launcher.status_profiles(
        port_reader=lambda port: launcher.PortState(
            listening=port == 18081,
            pids=(4325,) if port == 18081 else (),
        ),
        general_identity_checker=lambda pid, _: pid == 4325,
        general_health_check=lambda _: True,
    )

    output = capsys.readouterr().out
    assert "profile: GENERAL" in output
    assert "active port: 18081" in output
    assert "health: OK" in output
    assert "pid: 4325" in output


def test_status_reports_identifiable_vision_profile(capsys: Any) -> None:
    launcher.status_profiles(
        port_reader=lambda port: launcher.PortState(
            listening=port == 18082,
            pids=(4332,) if port == 18082 else (),
        ),
        vision_identity_checker=lambda pid, _: pid == 4332,
        vision_health_check=lambda _: True,
    )

    output = capsys.readouterr().out
    assert "profile: VISION" in output
    assert "active port: 18082" in output
    assert "health: OK" in output
    assert "pid: 4332" in output


def test_status_reports_conflicting_supported_ports(capsys: Any) -> None:
    launcher.status_profiles(
        port_reader=lambda port: launcher.PortState(
            listening=port in (18080, 18081),
            pids=(4326,) if port == 18080 else (4327,) if port == 18081 else (),
        ),
        code_health_check=lambda _: True,
        general_health_check=lambda _: True,
    )

    output = capsys.readouterr().out
    assert "profile: CONFLICT" in output
    assert "active ports: 18080, 18081" in output
    assert "CODE pid: 4326" in output
    assert "GENERAL pid: 4327" in output


def test_status_reports_conflict_involving_vision(capsys: Any) -> None:
    launcher.status_profiles(
        port_reader=lambda port: launcher.PortState(
            listening=port in (18081, 18082),
            pids=(4333,) if port == 18081 else (4334,) if port == 18082 else (),
        ),
        general_health_check=lambda _: True,
        vision_health_check=lambda _: True,
    )

    output = capsys.readouterr().out
    assert "profile: CONFLICT" in output
    assert "active ports: 18081, 18082" in output
    assert "GENERAL pid: 4333" in output
    assert "VISION pid: 4334" in output


def test_machine_state_reports_stopped_without_listeners() -> None:
    assert launcher.active_profile_state(port_reader=_free_ports) == "STOPPED"


@pytest.mark.parametrize(
    ("port", "expected"),
    ((18080, "CODE"), (18081, "GENERAL"), (18082, "VISION")),
)
def test_machine_state_reports_only_verified_profile(
    port: int,
    expected: str,
) -> None:
    pid = 4400 + port

    assert (
        launcher.active_profile_state(
            port_reader=lambda selected: launcher.PortState(
                listening=selected == port,
                pids=(pid,) if selected == port else (),
            ),
            code_identity_checker=lambda selected, _: selected == pid,
            general_identity_checker=lambda selected, _: selected == pid,
            vision_identity_checker=lambda selected, _: selected == pid,
            code_health_check=lambda _: True,
            general_health_check=lambda _: True,
            vision_health_check=lambda _: True,
        )
        == expected
    )


def test_machine_state_fails_closed_for_conflict_or_unverified_listener() -> None:
    assert (
        launcher.active_profile_state(
            port_reader=lambda selected: launcher.PortState(
                listening=selected in (18080, 18081),
                pids=(4401,) if selected == 18080 else (4402,) if selected == 18081 else (),
            ),
            code_health_check=lambda _: True,
            general_health_check=lambda _: True,
        )
        == "UNKNOWN"
    )
    assert (
        launcher.active_profile_state(
            port_reader=lambda selected: launcher.PortState(
                listening=selected == 18081,
                pids=(4403,) if selected == 18081 else (),
            ),
            general_identity_checker=lambda _pid, _: False,
            general_health_check=lambda _: True,
        )
        == "UNKNOWN"
    )


def test_switch_from_stopped_starts_target_and_verifies_it(tmp_path: Path, capsys: Any) -> None:
    states = iter(("STOPPED", "GENERAL"))
    started = False

    def start_target() -> None:
        nonlocal started
        started = True

    launcher.switch_profile(
        "general",
        state_reader=lambda: next(states),
        starter=start_target,
        lock_path=tmp_path / "lifecycle.lock",
    )

    assert started is True
    assert "GENERAL READY" not in capsys.readouterr().out


def test_switch_to_already_ready_profile_does_not_restart(tmp_path: Path, capsys: Any) -> None:
    started = False

    def start_target() -> None:
        nonlocal started
        started = True

    launcher.switch_profile(
        "general",
        state_reader=lambda: "GENERAL",
        starter=start_target,
        lock_path=tmp_path / "lifecycle.lock",
    )

    assert started is False
    assert capsys.readouterr().out.strip() == "GENERAL ALREADY READY"


def test_switch_stops_old_profile_before_starting_new(tmp_path: Path) -> None:
    states = iter(("GENERAL", "STOPPED", "CODE"))
    events: list[str] = []

    launcher.switch_profile(
        "code",
        state_reader=lambda: next(states),
        stopper=lambda: events.append("stop"),
        starter=lambda: events.append("start"),
        lock_path=tmp_path / "lifecycle.lock",
    )

    assert events == ["stop", "start"]


def test_switch_refuses_unknown_state_without_stopping_or_starting(tmp_path: Path) -> None:
    events: list[str] = []

    with pytest.raises(launcher.LauncherError, match="current LLM state is UNKNOWN"):
        launcher.switch_profile(
            "code",
            state_reader=lambda: "UNKNOWN",
            stopper=lambda: events.append("stop"),
            starter=lambda: events.append("start"),
            lock_path=tmp_path / "lifecycle.lock",
        )

    assert events == []


def test_switch_reports_failure_without_automatic_fallback(tmp_path: Path) -> None:
    with pytest.raises(launcher.LauncherError, match="SWITCH FAILED: target unavailable"):
        launcher.switch_profile(
            "vision",
            state_reader=lambda: "STOPPED",
            starter=lambda: (_ for _ in ()).throw(launcher.LauncherError("target unavailable")),
            lock_path=tmp_path / "lifecycle.lock",
        )


def test_lifecycle_lock_serializes_competing_processes(tmp_path: Path) -> None:
    context = multiprocessing.get_context("fork")
    acquired = context.Event()
    lock_path = tmp_path / "lifecycle.lock"

    with launcher.lifecycle_lock(lock_path):
        child = context.Process(
            target=_acquire_lock_in_child,
            args=(str(lock_path), acquired),
        )
        child.start()
        assert acquired.wait(0.2) is False

    assert acquired.wait(5) is True
    child.join(timeout=5)
    assert child.exitcode == 0


def test_stop_expected_identity_refuses_ownership_drift() -> None:
    signalled = False

    def killer(_: int, __: int) -> None:
        nonlocal signalled
        signalled = True

    with pytest.raises(launcher.LauncherError, match="ownership mismatch"):
        launcher.stop_active_profiles(
            port_reader=lambda port: launcher.PortState(
                listening=port == 18080,
                pids=(2222,) if port == 18080 else (),
            ),
            code_identity_checker=lambda pid, _: pid == 2222,
            expected_profile="CODE",
            expected_pid=1111,
            killer=killer,
        )

    assert signalled is False


def test_stop_active_safely_stops_code(capsys: Any) -> None:
    signalled: list[tuple[int, int]] = []

    launcher.stop_active_profiles(
        port_reader=lambda port: launcher.PortState(
            listening=port == 18080,
            pids=(4328,) if port == 18080 else (),
        ),
        code_identity_checker=lambda pid, _: pid == 4328,
        killer=lambda pid, sig: signalled.append((pid, sig)),
        closed_waiter=lambda port: port == 18080,
    )

    assert signalled == [(4328, launcher.signal.SIGTERM)]
    output = capsys.readouterr().out
    assert "CODE STOPPED" in output
    assert "port 18080: closed" in output


def test_stop_active_safely_stops_general(capsys: Any) -> None:
    signalled: list[tuple[int, int]] = []

    launcher.stop_active_profiles(
        port_reader=lambda port: launcher.PortState(
            listening=port == 18081,
            pids=(4329,) if port == 18081 else (),
        ),
        general_identity_checker=lambda pid, _: pid == 4329,
        killer=lambda pid, sig: signalled.append((pid, sig)),
        closed_waiter=lambda port: port == 18081,
    )

    assert signalled == [(4329, launcher.signal.SIGTERM)]
    assert "GENERAL STOPPED" in capsys.readouterr().out


def test_stop_active_safely_stops_vision(capsys: Any) -> None:
    signalled: list[tuple[int, int]] = []

    launcher.stop_active_profiles(
        port_reader=lambda port: launcher.PortState(
            listening=port == 18082,
            pids=(4335,) if port == 18082 else (),
        ),
        vision_identity_checker=lambda pid, _: pid == 4335,
        killer=lambda pid, sig: signalled.append((pid, sig)),
        closed_waiter=lambda port: port == 18082,
    )

    assert signalled == [(4335, launcher.signal.SIGTERM)]
    output = capsys.readouterr().out
    assert "VISION STOPPED" in output
    assert "port 18082: closed" in output


def test_stop_active_refuses_conflicting_profiles() -> None:
    with pytest.raises(launcher.LauncherError, match="conflict"):
        launcher.stop_active_profiles(
            port_reader=lambda port: launcher.PortState(listening=port in (18080, 18081))
        )


def test_stop_active_refuses_conflict_involving_vision() -> None:
    with pytest.raises(launcher.LauncherError, match="conflict"):
        launcher.stop_active_profiles(
            port_reader=lambda port: launcher.PortState(listening=port in (18080, 18082))
        )


def test_stop_active_refuses_ambiguous_code_owner() -> None:
    with pytest.raises(launcher.LauncherError, match="ambiguous"):
        launcher.stop_active_profiles(
            port_reader=lambda port: launcher.PortState(
                listening=port == 18080,
                pids=(100, 200) if port == 18080 else (),
            )
        )


def test_stop_active_refuses_ambiguous_vision_owner() -> None:
    with pytest.raises(launcher.LauncherError, match="ambiguous"):
        launcher.stop_active_profiles(
            port_reader=lambda port: launcher.PortState(
                listening=port == 18082,
                pids=(300, 400) if port == 18082 else (),
            )
        )


def test_stop_active_refuses_unrelated_code_process_without_signalling() -> None:
    signalled = False

    def killer(_: int, __: int) -> None:
        nonlocal signalled
        signalled = True

    with pytest.raises(launcher.LauncherError, match="not the verified CODE profile"):
        launcher.stop_active_profiles(
            port_reader=lambda port: launcher.PortState(
                listening=port == 18080,
                pids=(9877,) if port == 18080 else (),
            ),
            code_identity_checker=lambda _pid, _profile: False,
            killer=killer,
        )

    assert signalled is False


def test_stop_active_refuses_unrelated_vision_process_without_signalling() -> None:
    signalled = False

    def killer(_: int, __: int) -> None:
        nonlocal signalled
        signalled = True

    with pytest.raises(launcher.LauncherError, match="not the verified VISION profile"):
        launcher.stop_active_profiles(
            port_reader=lambda port: launcher.PortState(
                listening=port == 18082,
                pids=(9878,) if port == 18082 else (),
            ),
            vision_identity_checker=lambda _pid, _profile: False,
            killer=killer,
        )

    assert signalled is False


def test_stop_refuses_unverified_process_without_signalling() -> None:
    signalled = False

    def killer(_: int, __: int) -> None:
        nonlocal signalled
        signalled = True

    with pytest.raises(launcher.LauncherError, match="not the verified GENERAL profile"):
        launcher.stop_general(
            port_reader=lambda _: launcher.PortState(listening=True, pids=(9876,)),
            identity_checker=lambda _pid, _profile: False,
            killer=killer,
        )

    assert signalled is False


def test_stop_refuses_ambiguous_process_owners() -> None:
    with pytest.raises(launcher.LauncherError, match="ambiguous"):
        launcher.stop_general(
            port_reader=lambda _: launcher.PortState(listening=True, pids=(100, 200)),
        )


def test_stop_signals_verified_process_and_requires_closed_port(capsys: Any) -> None:
    signalled: list[tuple[int, int]] = []

    launcher.stop_general(
        port_reader=lambda _: launcher.PortState(listening=True, pids=(2468,)),
        identity_checker=lambda _pid, _profile: True,
        killer=lambda pid, sig: signalled.append((pid, sig)),
        closed_waiter=lambda _port: True,
    )

    assert signalled == [(2468, launcher.signal.SIGTERM)]
    assert "port 18081: closed" in capsys.readouterr().out


# ===========================================================================
# Idempotency tests
# ===========================================================================


def _occupied_own_port(own_port: int, pid: int) -> Any:
    """Port reader helper: only the given port is occupied, with the given PID."""

    def reader(port: int) -> Any:
        return launcher.PortState(
            listening=port == own_port, pids=(pid,) if port == own_port else ()
        )

    return reader


# ---------------------------------------------------------------------------
# GENERAL idempotency
# ---------------------------------------------------------------------------


def test_general_already_running_verified_healthy_returns_success(
    tmp_path: Path, capsys: Any
) -> None:
    """Exact verified + healthy GENERAL -> ALREADY READY, no spawn."""
    profile = _profile(tmp_path)
    spawned = False

    def process_factory(*args: Any, **kwargs: Any) -> Any:
        nonlocal spawned
        spawned = True
        return None

    launcher.start_general(
        profile,
        port_reader=_occupied_own_port(profile.port, 7777),
        process_factory=process_factory,
        identity_checker=lambda pid, _: pid == 7777,
        health_check=lambda _: True,
    )

    output = capsys.readouterr().out
    assert "GENERAL ALREADY READY" in output
    assert "endpoint: http://127.0.0.1:18081/v1" in output
    assert "pid: 7777" in output
    assert spawned is False


def test_general_already_running_but_unhealthy_refuses(tmp_path: Path) -> None:
    """Correct PID but unhealthy endpoint -> refuse (not idempotent)."""
    profile = _profile(tmp_path)

    with pytest.raises(launcher.LauncherError, match="18081"):
        launcher.start_general(
            profile,
            port_reader=_occupied_own_port(profile.port, 7778),
            identity_checker=lambda pid, _: pid == 7778,
            health_check=lambda _: False,
        )


def test_general_already_running_unknown_pid_refuses(tmp_path: Path) -> None:
    """Unknown PID (ss returned no PIDs) -> refuse."""
    profile = _profile(tmp_path)

    def reader(port: int) -> Any:
        return launcher.PortState(listening=port == profile.port, pids=())

    with pytest.raises(launcher.LauncherError, match="18081"):
        launcher.start_general(
            profile,
            port_reader=reader,
            identity_checker=lambda pid, _: True,
            health_check=lambda _: True,
        )


def test_general_already_running_wrong_command_refuses(tmp_path: Path) -> None:
    """Correct PID exists but cmdline does not match profile -> refuse."""
    profile = _profile(tmp_path)

    with pytest.raises(launcher.LauncherError, match="18081"):
        launcher.start_general(
            profile,
            port_reader=_occupied_own_port(profile.port, 7779),
            identity_checker=lambda _pid, _profile: False,
            health_check=lambda _: True,
        )


def test_general_already_ready_output_contains_exact_pid(tmp_path: Path, capsys: Any) -> None:
    """ALREADY READY output contains the exact PID from the port scan."""
    profile = _profile(tmp_path)

    launcher.start_general(
        profile,
        port_reader=_occupied_own_port(profile.port, 9999),
        identity_checker=lambda pid, _: pid == 9999,
        health_check=lambda _: True,
    )

    output = capsys.readouterr().out
    assert "pid: 9999" in output


# ---------------------------------------------------------------------------
# CODE idempotency
# ---------------------------------------------------------------------------


def test_code_already_running_verified_healthy_returns_success(tmp_path: Path, capsys: Any) -> None:
    """Exact verified + healthy CODE -> CODE ALREADY READY, no spawn."""
    profile = _code_profile(tmp_path)
    spawned = False

    def process_factory(*args: Any, **kwargs: Any) -> Any:
        nonlocal spawned
        spawned = True
        return None

    launcher.start_code(
        profile,
        port_reader=_occupied_own_port(profile.port, 8800),
        process_factory=process_factory,
        identity_checker=lambda pid, _: pid == 8800,
        health_check=lambda _: True,
    )

    output = capsys.readouterr().out
    assert "CODE ALREADY READY" in output
    assert "endpoint: http://127.0.0.1:18080/v1" in output
    assert "pid: 8800" in output
    assert spawned is False


# ---------------------------------------------------------------------------
# VISION idempotency
# ---------------------------------------------------------------------------


def test_vision_already_running_verified_healthy_returns_success(
    tmp_path: Path, capsys: Any
) -> None:
    """Exact verified + healthy VISION -> VISION ALREADY READY, no spawn."""
    profile = _vision_profile(tmp_path)
    spawned = False

    def process_factory(*args: Any, **kwargs: Any) -> Any:
        nonlocal spawned
        spawned = True
        return None

    launcher.start_vision(
        profile,
        port_reader=_occupied_own_port(profile.port, 8820),
        process_factory=process_factory,
        identity_checker=lambda pid, _: pid == 8820,
        health_check=lambda _: True,
    )

    output = capsys.readouterr().out
    assert "VISION ALREADY READY" in output
    assert "endpoint: http://127.0.0.1:18082/v1" in output
    assert "pid: 8820" in output
    assert spawned is False


# ---------------------------------------------------------------------------
# Cross-profile conflict: GENERAL requested while CODE is active
# ---------------------------------------------------------------------------


def test_general_requested_while_code_active_refuses(tmp_path: Path) -> None:
    """llm general + CODE running on 18080 -> refuse (no idempotency for another profile)."""
    profile = _profile(tmp_path)

    # CODE port (18080) is occupied, GENERAL port (18081) is free
    def reader(port: int) -> Any:
        return launcher.PortState(listening=port == 18080, pids=(5555,) if port == 18080 else ())

    with pytest.raises(launcher.LauncherError, match="18080"):
        launcher.start_general(
            profile,
            port_reader=reader,
            identity_checker=lambda _pid, _profile: False,
            health_check=lambda _: False,
        )


# ---------------------------------------------------------------------------
# Multiple supported ports simultaneously -> refuse
# ---------------------------------------------------------------------------


def test_general_requested_while_own_and_another_port_occupied_refuses(
    tmp_path: Path,
) -> None:
    """Own port (18081) plus another supported port (18080) both occupied -> refuse.

    The own-port is occupied but unverified, so idempotency does not apply,
    and the full conflict scan catches both ports.
    """
    profile = _profile(tmp_path)

    def reader(port: int) -> Any:
        return launcher.PortState(
            listening=port in (18080, 18081),
            pids=(5556,) if port in (18080, 18081) else (),
        )

    with pytest.raises(launcher.LauncherError, match="18081"):
        launcher.start_general(
            profile,
            port_reader=reader,
            identity_checker=lambda _pid, _profile: False,
            health_check=lambda _: False,
        )


# ---------------------------------------------------------------------------
# Port 18084 conflict: always refused regardless of idempotency
# ---------------------------------------------------------------------------


def test_general_refuses_when_port_18084_is_occupied(tmp_path: Path) -> None:
    """18084 occupied -> refuse; existing conflict behavior is preserved."""
    profile = _profile(tmp_path)

    # Own port (18081) is free; 18084 is occupied by some process
    def reader(port: int) -> Any:
        return launcher.PortState(listening=port == 18084, pids=(5557,) if port == 18084 else ())

    with pytest.raises(launcher.LauncherError, match="18084"):
        launcher.start_general(
            profile,
            port_reader=reader,
            identity_checker=lambda _pid, _profile: False,
            health_check=lambda _: False,
        )


# ---------------------------------------------------------------------------
# Exit-code 0 via CLI when ALREADY READY
# ---------------------------------------------------------------------------


def test_main_returns_zero_when_general_already_ready(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """main() must return 0 (exit code 0) when GENERAL ALREADY READY."""
    profile = _profile(tmp_path)

    monkeypatch.setattr(launcher, "DEFAULT_PROFILE", profile)
    monkeypatch.setattr(
        launcher,
        "port_state",
        lambda port: launcher.PortState(
            listening=port == profile.port,
            pids=(6001,) if port == profile.port else (),
        ),
    )
    monkeypatch.setattr(launcher, "is_general_process", lambda pid, _: pid == 6001)
    monkeypatch.setattr(launcher, "_health_ok", lambda _: True)

    result = launcher.main(["general"])
    assert result == 0


# ---------------------------------------------------------------------------
# Regression: cold start still works
# ---------------------------------------------------------------------------


def test_general_cold_start_still_works(tmp_path: Path, capsys: Any) -> None:
    """When no port is occupied, start_general starts normally (regression)."""
    profile = _profile(tmp_path)
    log_path = tmp_path / "state" / "general.log"

    class FakeProcess:
        pid = 4400

        def poll(self) -> None:
            return None

    spawned = False

    def process_factory(*args: Any, **kwargs: Any) -> FakeProcess:
        nonlocal spawned
        spawned = True
        return FakeProcess()

    launcher.start_general(
        profile,
        port_reader=_free_ports,
        process_factory=process_factory,
        health_waiter=lambda _: True,
        log_path=lambda: log_path,
        identity_checker=lambda _pid, _profile: False,
        health_check=lambda _: False,
    )

    assert spawned is True
    output = capsys.readouterr().out
    assert "GENERAL READY" in output
    assert "GENERAL ALREADY READY" not in output


# ---------------------------------------------------------------------------
# detect_verified_running_profile unit tests
# ---------------------------------------------------------------------------


def test_detect_verified_running_profile_returns_pid_when_all_conditions_met() -> None:
    state = launcher.PortState(listening=True, pids=(1111,))
    result = launcher.detect_verified_running_profile(
        state,
        identity_checker=lambda pid: pid == 1111,
        health_check=lambda: True,
    )
    assert result == 1111


def test_detect_verified_running_profile_returns_none_for_multiple_pids() -> None:
    state = launcher.PortState(listening=True, pids=(1111, 2222))
    result = launcher.detect_verified_running_profile(
        state,
        identity_checker=lambda pid: True,
        health_check=lambda: True,
    )
    assert result is None


def test_detect_verified_running_profile_returns_none_for_no_pids() -> None:
    state = launcher.PortState(listening=True, pids=())
    result = launcher.detect_verified_running_profile(
        state,
        identity_checker=lambda pid: True,
        health_check=lambda: True,
    )
    assert result is None


def test_detect_verified_running_profile_returns_none_when_identity_fails() -> None:
    state = launcher.PortState(listening=True, pids=(3333,))
    result = launcher.detect_verified_running_profile(
        state,
        identity_checker=lambda pid: False,
        health_check=lambda: True,
    )
    assert result is None


def test_detect_verified_running_profile_returns_none_when_health_fails() -> None:
    state = launcher.PortState(listening=True, pids=(4444,))
    result = launcher.detect_verified_running_profile(
        state,
        identity_checker=lambda pid: pid == 4444,
        health_check=lambda: False,
    )
    assert result is None

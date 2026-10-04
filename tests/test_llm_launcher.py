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


def test_production_roles_and_challenger_conflict_port_are_exact() -> None:
    assert launcher.GENERAL_PORT == 18081
    assert launcher.CODE_PORT == 18080
    assert launcher.CONFLICT_PORTS == (18080, 18081, 18082, 18086, 18087)
    assert str(launcher.GENERAL_MODEL).startswith("/models/gguf/nemotron-3-nano-30b-a3b/")
    assert str(launcher.CODE_MODEL).startswith("/models/gguf/qwen3-coder-30b-a3b/")
    assert 18082 in launcher.CONFLICT_PORTS


def test_vision_routes_to_supported_lifecycle(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    events: list[str] = []
    monkeypatch.setattr(launcher, "_lifecycle_lock_path", lambda: tmp_path / "lock")
    monkeypatch.setattr(launcher, "start_vision", lambda: events.append("vision"))
    monkeypatch.setattr(launcher, "start_profile", lambda role: events.append(f"start:{role}"))
    monkeypatch.setattr(launcher, "switch_profile", lambda role: events.append(f"switch:{role}"))
    assert launcher.main(["vision"]) == 0
    assert launcher.main(["start", "vision"]) == 0
    assert launcher.main(["switch", "vision"]) == 0
    assert events == ["vision", "start:vision", "switch:vision"]


def _acquire_lock_in_child(lock_path: str, acquired: Any) -> None:
    with launcher.lifecycle_lock(Path(lock_path)):
        acquired.set()


def _profile(tmp_path: Path) -> Any:
    model = tmp_path / "model.gguf"
    runtime = tmp_path / "llama-server"
    for path in (model, runtime):
        path.touch()
    runtime.chmod(runtime.stat().st_mode | 0o111)
    return launcher.GeneralProfile(model=model, runtime=runtime)


def _code_profile(tmp_path: Path) -> Any:
    model = tmp_path / "nemotron.gguf"
    runtime = tmp_path / "llama-server"
    model.touch()
    runtime.touch()
    runtime.chmod(runtime.stat().st_mode | 0o111)
    return launcher.CodeProfile(model=model, runtime=runtime)


def _free_ports(_: int) -> Any:
    return launcher.PortState(listening=False)


def test_serve_general_execs_exact_profile_and_refuses_conflicting_port(tmp_path: Path) -> None:
    profile = _profile(tmp_path)
    executed: list[tuple[str, tuple[str, ...]]] = []

    launcher.serve_general(
        profile,
        port_reader=_free_ports,
        process_replacer=lambda path, argv: executed.append((path, tuple(argv))),
    )
    assert executed == [(str(profile.runtime), profile.command())]

    with pytest.raises(launcher.LauncherError, match="18082"):
        launcher.serve_general(
            profile,
            port_reader=lambda port: launcher.PortState(listening=port == 18082),
            process_replacer=lambda *_: pytest.fail("conflicting listener must prevent exec"),
        )
    assert len(executed) == 1


def test_main_serve_uses_foreground_runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    requested: list[str] = []
    monkeypatch.setattr(launcher, "_lifecycle_lock_path", lambda: tmp_path / "lifecycle.lock")
    monkeypatch.setattr(launcher, "serve_general", lambda: requested.append("GENERAL"))
    monkeypatch.setattr(launcher, "serve_code", lambda: requested.append("CODE"))

    assert launcher.main(["serve"]) == 0
    assert launcher.main(["serve", "code"]) == 0
    assert requested == ["GENERAL", "CODE"]


def test_serve_code_execs_verified_profile_and_refuses_conflict(tmp_path: Path) -> None:
    profile = _code_profile(tmp_path)
    executed: list[tuple[str, tuple[str, ...]]] = []
    launcher.serve_code(
        profile,
        port_reader=_free_ports,
        process_replacer=lambda path, argv: executed.append((path, tuple(argv))),
    )
    assert executed == [(str(profile.runtime), profile.command())]
    with pytest.raises(launcher.LauncherError, match="18081"):
        launcher.serve_code(
            profile,
            port_reader=lambda port: launcher.PortState(listening=port == 18081),
            process_replacer=lambda *_: pytest.fail("conflicting listener must prevent exec"),
        )


def test_serve_releases_shared_lock_before_waiting_for_server_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile = _code_profile(tmp_path)
    events: list[str] = []

    class FakeProcess:
        pid = 1234

        def poll(self) -> None:
            return None

        def wait(self) -> int:
            events.append("wait")
            return 0

        def terminate(self) -> None:
            events.append("terminate")

    from contextlib import contextmanager

    @contextmanager
    def recording_lock() -> Any:
        events.append("acquired")
        try:
            yield
        finally:
            events.append("released")

    def spawn(*args: Any, **kwargs: Any) -> FakeProcess:
        events.append("spawn")
        return FakeProcess()

    def healthy(_: Any) -> bool:
        events.append("health")
        return True

    monkeypatch.setattr(launcher, "lifecycle_lock", recording_lock)
    launcher.serve_code(
        profile,
        port_reader=_free_ports,
        process_factory=spawn,
        health_waiter=healthy,
    )

    assert events == ["acquired", "spawn", "health", "released", "wait"]


def test_serve_readiness_failure_releases_real_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile = _code_profile(tmp_path)
    lock_path = tmp_path / "lifecycle.lock"
    monkeypatch.setattr(launcher, "_lifecycle_lock_path", lambda: lock_path)

    class FailedProcess:
        pid = 5678

        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            return None

        def wait(self, timeout: float | None = None) -> int:
            return 0

    with pytest.raises(launcher.LauncherError, match="health"):
        launcher.serve_code(
            profile,
            port_reader=_free_ports,
            process_factory=lambda *args, **kwargs: FailedProcess(),
            health_waiter=lambda _: False,
        )

    context = multiprocessing.get_context("fork")
    acquired = context.Event()
    child = context.Process(target=_acquire_lock_in_child, args=(str(lock_path), acquired))
    child.start()
    assert acquired.wait(5) is True
    child.join(timeout=5)
    assert child.exitcode == 0


def test_launcher_artifact_paths_can_be_relocated_without_changing_profiles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configured_paths = {
        "NEURALENGINE_GENERAL_MODEL": tmp_path / "general.gguf",
        "NEURALENGINE_VISION_MMPROJ": tmp_path / "mmproj.gguf",
        "NEURALENGINE_LLAMA_SERVER": tmp_path / "llama-server",
    }
    for name, path in configured_paths.items():
        monkeypatch.setenv(name, str(path))

    configured = _load_launcher("neural_engine_llm_launcher_configured")

    assert configured_paths["NEURALENGINE_GENERAL_MODEL"] == configured.GENERAL_MODEL
    assert configured_paths["NEURALENGINE_VISION_MMPROJ"] == configured.VISION_MMPROJ
    assert configured_paths["NEURALENGINE_LLAMA_SERVER"] == configured.LLAMA_SERVER
    assert configured.DEFAULT_PROFILE.runtime == configured.LLAMA_SERVER
    assert configured.DEFAULT_PROFILE.arguments()[1] == str(configured.GENERAL_MODEL)


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
    assert calls == [18081, 18080, 18081, 18082, 18086, 18087]


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


def test_profiles_use_production_context_limits() -> None:
    profiles = (
        (launcher.DEFAULT_PROFILE, "32768"),
        (launcher.DEFAULT_CODE_PROFILE, "32768"),
        (launcher.DEFAULT_VISION_PROFILE, "32768"),
    )

    for profile, expected_context in profiles:
        arguments = profile.arguments()
        context_index = arguments.index("-c")
        assert arguments[context_index + 1] == expected_context


def test_status_reports_no_profile_running(capsys: Any) -> None:
    launcher.status_profiles(port_reader=_free_ports)

    output = capsys.readouterr().out
    assert "LLM STOPPED" in output
    assert "profile: none" in output
    assert "active port: none" in output


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


def test_status_reports_conflicting_supported_ports(capsys: Any) -> None:
    launcher.status_profiles(
        port_reader=lambda port: launcher.PortState(
            listening=port in (18080, 18081),
            pids=(4326,) if port == 18080 else (4327,) if port == 18081 else (),
        ),
        general_health_check=lambda _: True,
    )

    output = capsys.readouterr().out
    assert "profile: CONFLICT" in output
    assert "active ports: 18080, 18081" in output


def test_status_does_not_identify_an_unverified_code_listener(capsys: Any) -> None:
    launcher.status_profiles(
        port_reader=lambda port: launcher.PortState(
            listening=port == 18080,
            pids=(4328,) if port == 18080 else (),
        )
    )

    output = capsys.readouterr().out
    assert "profile: unknown" in output
    assert "profile: CODE" not in output


def test_code_identity_requires_exact_command_and_health() -> None:
    def reader(port: int) -> Any:
        return launcher.PortState(listening=port == 18080, pids=(5501,) if port == 18080 else ())

    assert (
        launcher.active_profile_state(
            port_reader=reader,
            code_identity_checker=lambda pid, _: pid == 5501,
            code_health_check=lambda _: True,
        )
        == "CODE"
    )
    assert launcher.active_profile_identity(
        port_reader=reader,
        code_identity_checker=lambda pid, _: pid == 5501,
        code_health_check=lambda _: True,
    ) == ("CODE", 5501)
    assert (
        launcher.active_profile_state(
            port_reader=reader,
            code_identity_checker=lambda _pid, _: False,
            code_health_check=lambda _: True,
        )
        == "UNKNOWN"
    )


def test_code_start_uses_verified_vulkan_profile(tmp_path: Path, capsys: Any) -> None:
    profile = _code_profile(tmp_path)
    commands: list[tuple[str, ...]] = []

    class Process:
        pid = 5502

    def process_factory(command: tuple[str, ...], **_kwargs: Any) -> Process:
        commands.append(tuple(command))
        return Process()

    launcher.start_code(
        profile,
        port_reader=_free_ports,
        process_factory=process_factory,
        health_waiter=lambda _: True,
        log_path=lambda: tmp_path / "code.log",
    )
    assert commands == [profile.command()]
    args = profile.arguments()
    assert args[args.index("-dev") + 1] == "Vulkan0"
    assert "CODE READY" in capsys.readouterr().out


def test_code_stop_requires_expected_identity(capsys: Any) -> None:
    signalled: list[int] = []

    def reader(port: int) -> Any:
        return launcher.PortState(listening=port == 18080, pids=(5503,) if port == 18080 else ())

    with pytest.raises(launcher.LauncherError, match="ownership mismatch"):
        launcher.stop_active_profiles(
            port_reader=reader,
            expected_profile="CODE",
            expected_pid=5504,
            killer=lambda pid, _sig: signalled.append(pid),
        )
    assert signalled == []
    launcher.stop_active_profiles(
        port_reader=reader,
        expected_profile="CODE",
        expected_pid=5503,
        code_identity_checker=lambda pid, _: pid == 5503,
        killer=lambda pid, _sig: signalled.append(pid),
        closed_waiter=lambda port: port == 18080,
    )
    assert signalled == [5503]
    assert "CODE STOPPED" in capsys.readouterr().out


def test_machine_state_reports_stopped_without_listeners() -> None:
    assert launcher.active_profile_state(port_reader=_free_ports) == "STOPPED"


def test_machine_state_fails_closed_for_conflict_or_unverified_listener() -> None:
    assert (
        launcher.active_profile_state(
            port_reader=lambda selected: launcher.PortState(
                listening=selected in (18080, 18081),
                pids=(4401,) if selected == 18080 else (4402,) if selected == 18081 else (),
            ),
            general_health_check=lambda _: True,
        )
        == "UNKNOWN"
    )
    assert (
        launcher.active_profile_state(
            port_reader=lambda selected: launcher.PortState(
                listening=selected in (18080, 18082),
                pids=(4404,) if selected in (18080, 18082) else (),
            ),
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


def test_main_routes_start_profile_to_atomic_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested: list[str | None] = []
    monkeypatch.setattr(launcher, "start_profile", lambda profile: requested.append(profile))

    assert launcher.main(["start", "general"]) == 0
    assert requested == ["general"]


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


def test_switch_refuses_unknown_state_without_stopping_or_starting(tmp_path: Path) -> None:
    events: list[str] = []

    with pytest.raises(launcher.LauncherError, match="current LLM state is UNKNOWN"):
        launcher.switch_profile(
            "general",
            state_reader=lambda: "UNKNOWN",
            stopper=lambda: events.append("stop"),
            starter=lambda: events.append("start"),
            lock_path=tmp_path / "lifecycle.lock",
        )

    assert events == []


def test_switch_reports_failure_without_automatic_fallback(tmp_path: Path) -> None:
    with pytest.raises(launcher.LauncherError, match="SWITCH FAILED: target unavailable"):
        launcher.switch_profile(
            "general",
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


def test_lifecycle_lock_releases_after_failure(tmp_path: Path) -> None:
    lock_path = tmp_path / "lifecycle.lock"
    with pytest.raises(RuntimeError, match="precheck failed"), launcher.lifecycle_lock(lock_path):
        raise RuntimeError("precheck failed")

    context = multiprocessing.get_context("fork")
    acquired = context.Event()
    child = context.Process(
        target=_acquire_lock_in_child,
        args=(str(lock_path), acquired),
    )
    child.start()
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
                listening=port == 18081,
                pids=(2222,) if port == 18081 else (),
            ),
            expected_profile="GENERAL",
            expected_pid=1111,
            killer=killer,
        )

    assert signalled is False


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


def test_vision_port_is_unknown_and_never_signalled() -> None:
    signalled = False

    def killer(_: int, __: int) -> None:
        nonlocal signalled
        signalled = True

    def port_reader(port: int) -> Any:
        return launcher.PortState(
            listening=port == 18082,
            pids=(4812,) if port == 18082 else (),
        )

    assert launcher.active_profile_state(port_reader=port_reader) == "UNKNOWN"
    with pytest.raises(launcher.LauncherError, match="not the verified VISION profile"):
        launcher.stop_active_profiles(port_reader=port_reader, killer=killer)
    assert signalled is False


def test_stop_active_refuses_conflicting_profiles() -> None:
    with pytest.raises(launcher.LauncherError, match="conflict"):
        launcher.stop_active_profiles(
            port_reader=lambda port: launcher.PortState(listening=port in (18080, 18081))
        )


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


# ---------------------------------------------------------------------------
# VISION idempotency
# ---------------------------------------------------------------------------


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
# Challenger ports conflict: always refused regardless of idempotency
# ---------------------------------------------------------------------------


def test_general_refuses_when_port_18086_is_occupied(tmp_path: Path) -> None:
    """18086 occupied -> refuse; challenger exclusivity is preserved."""
    profile = _profile(tmp_path)

    # Own port (18081) is free; 18086 is occupied by some process
    def reader(port: int) -> Any:
        return launcher.PortState(listening=port == 18086, pids=(5557,) if port == 18086 else ())

    with pytest.raises(launcher.LauncherError, match="18086"):
        launcher.start_general(
            profile,
            port_reader=reader,
            identity_checker=lambda _pid, _profile: False,
            health_check=lambda _: False,
        )


def test_general_refuses_when_port_18087_is_occupied(tmp_path: Path) -> None:
    """A stale listener on retired port 18087 remains conflict-only."""
    profile = _profile(tmp_path)

    def reader(port: int) -> Any:
        return launcher.PortState(listening=port == 18087, pids=(5558,) if port == 18087 else ())

    with pytest.raises(launcher.LauncherError, match="18087"):
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
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    """main() must return 0 (exit code 0) when GENERAL ALREADY READY."""
    profile = _profile(tmp_path)

    monkeypatch.setenv("NEURALENGINE_GENERAL_MODEL", str(profile.model))
    monkeypatch.setenv("NEURALENGINE_LLAMA_SERVER", str(profile.runtime))
    configured = _load_launcher("neural_engine_llm_launcher_general_ready_cli")
    assert configured.DEFAULT_PROFILE.model == profile.model
    assert configured.DEFAULT_PROFILE.runtime == profile.runtime

    monkeypatch.setattr(
        configured,
        "port_state",
        lambda port: configured.PortState(
            listening=port == profile.port,
            pids=(6001,) if port == profile.port else (),
        ),
    )
    monkeypatch.setattr(configured, "is_general_process", lambda pid, _: pid == 6001)
    monkeypatch.setattr(configured, "_health_ok", lambda _: True)
    monkeypatch.setattr(configured, "_lifecycle_lock_path", lambda: tmp_path / "lifecycle.lock")

    result = configured.main(["general"])
    assert result == 0
    assert "GENERAL ALREADY READY" in capsys.readouterr().out


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


@pytest.mark.parametrize("name,port", [("GENERAL", 18081), ("CODE", 18080), ("VISION", 18082)])
def test_all_roles_require_exact_identity_and_health(name: str, port: int) -> None:
    def reader(candidate: int) -> Any:
        return launcher.PortState(
            listening=candidate == port, pids=(7101,) if candidate == port else ()
        )

    checks = {
        f"{name.lower()}_identity_checker": lambda pid, _: pid == 7101,
        f"{name.lower()}_health_check": lambda _: True,
    }
    assert launcher.active_profile_identity(port_reader=reader, **checks) == (name, 7101)
    checks[f"{name.lower()}_identity_checker"] = lambda *_: False
    assert launcher.active_profile_state(port_reader=reader, **checks) == "UNKNOWN"


def test_vision_requires_mmproj_before_start(tmp_path: Path) -> None:
    profile = launcher.VisionProfile(
        model=tmp_path / "gemma.gguf",
        mmproj=tmp_path / "missing.gguf",
        runtime=tmp_path / "llama-server",
    )
    profile.model.touch()
    profile.runtime.touch(mode=0o700)
    with pytest.raises(launcher.LauncherError, match="mmproj does not exist"):
        launcher.start_vision(profile, process_factory=lambda *_: pytest.fail("must not spawn"))


def test_vision_baseline_disables_reasoning_and_mtp() -> None:
    args = launcher.DEFAULT_VISION_PROFILE.arguments()
    assert args[args.index("--reasoning") + 1] == "off"
    assert args[args.index("--mmproj") + 1] == str(launcher.VISION_MMPROJ)
    assert not any("spec" in arg or "mtp" in arg for arg in args)


def test_switch_passes_exact_ownership_to_stop(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    states = iter(("GENERAL", "STOPPED", "CODE"))
    stops: list[dict[str, Any]] = []
    monkeypatch.setattr(launcher, "active_profile_identity", lambda: ("GENERAL", 7201))
    monkeypatch.setattr(launcher, "stop_active_profiles", lambda **kw: stops.append(kw))
    launcher.switch_profile(
        "code",
        state_reader=lambda: next(states),
        starter=lambda: None,
        lock_path=tmp_path / "lock",
    )
    assert stops == [{"expected_profile": "GENERAL", "expected_pid": 7201}]


@pytest.mark.parametrize("role", ["general", "code", "vision"])
def test_already_ready_does_not_ignore_second_listener(tmp_path: Path, role: str) -> None:
    if role == "general":
        profile = _profile(tmp_path)
    elif role == "code":
        profile = _code_profile(tmp_path)
    else:
        base = _profile(tmp_path)
        mmproj = tmp_path / "mmproj.gguf"
        mmproj.touch()
        profile = launcher.VisionProfile(model=base.model, runtime=base.runtime, mmproj=mmproj)
    with pytest.raises(launcher.LauncherError, match="18087"):
        getattr(launcher, f"start_{role}")(
            profile,
            port_reader=lambda port: launcher.PortState(
                listening=port in {profile.port, 18087},
                pids=(8001,),
            ),
            identity_checker=lambda *_: True,
            health_check=lambda *_: True,
            process_factory=lambda *_: pytest.fail("must not spawn"),
        )

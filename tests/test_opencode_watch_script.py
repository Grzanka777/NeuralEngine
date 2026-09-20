"""Integration tests for the thin scripts/opencode-watch wrapper."""

import os
import shlex
import signal
import subprocess
import time
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "opencode-watch"


def install_mock_llm(
    tmp_path: Path,
    states: list[str],
    *,
    stop_exit: int = 0,
    identities: list[str] | None = None,
) -> tuple[Path, Path, Path]:
    state_file = tmp_path / "llm-states"
    state_file.write_text("\n".join(states) + "\n", encoding="utf-8")
    state_count_file = tmp_path / "llm-state-count"
    identity_file = tmp_path / "llm-identities"
    identity_file.write_text("\n".join(identities or ["STOPPED"]) + "\n", encoding="utf-8")
    identity_count_file = tmp_path / "llm-identity-count"
    stop_log = tmp_path / "llm-stop.log"
    mock_llm = tmp_path / "mock_llm"
    state_file_literal = shlex.quote(str(state_file))
    state_count_literal = shlex.quote(str(state_count_file))
    identity_file_literal = shlex.quote(str(identity_file))
    identity_count_literal = shlex.quote(str(identity_count_file))
    stop_log_literal = shlex.quote(str(stop_log))
    mock_llm.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail

case "$1" in
    state)
        count=0
        if [[ -f {state_count_literal} ]]; then
            count="$(<{state_count_literal})"
        fi
        count=$((count + 1))
        printf '%s\\n' "$count" >{state_count_literal}
        value="$(sed -n "$count"p {state_file_literal})"
        if [[ -z "$value" ]]; then
            exit 3
        fi
    printf '%s\\n' "$value"
        ;;
    identity)
        count=0
        if [[ -f {identity_count_literal} ]]; then
            count="$(<{identity_count_literal})"
        fi
        count=$((count + 1))
        printf '%s\\n' "$count" >{identity_count_literal}
        value="$(sed -n "$count"p {identity_file_literal})"
        if [[ -z "$value" ]]; then
            value="$(tail -n 1 {identity_file_literal})"
        fi
        if [[ -z "$value" ]]; then
            exit 3
        fi
        printf '%s\\n' "$value"
        ;;
    stop)
        printf '%s\\n' stop >>{stop_log_literal}
        exit {stop_exit}
        ;;
    *)
        exit 2
        ;;
esac
""",
        encoding="utf-8",
    )
    mock_llm.chmod(0o755)
    return mock_llm, stop_log, state_count_file


def install_mock_opencode(
    tmp_path: Path,
    *,
    exit_code: int = 0,
    args_file: Path | None = None,
    sleep_seconds: float = 0,
    identity_update: tuple[Path, str] | None = None,
    identity_update_after_cleanup_marker: tuple[Path, str] | None = None,
    signal_aware: bool = False,
) -> Path:
    mock_opencode = tmp_path / "mock_opencode"
    args_block = ""
    if args_file is not None:
        args_block = f"""
for arg in "$@"; do
    printf '%s\\n' "$arg" >>{shlex.quote(str(args_file))}
done
"""
    sleep_block = f"sleep {sleep_seconds}" if sleep_seconds and not signal_aware else ""
    identity_update_block = ""
    if identity_update is not None:
        identity_path, identity = identity_update
        identity_update_block = (
            f"printf '%s\\n' {shlex.quote(identity)} >{shlex.quote(str(identity_path))}"
        )
    if identity_update_after_cleanup_marker is not None:
        identity_path, identity = identity_update_after_cleanup_marker
        identity_update_block = (
            "(while ! grep -q 'Ownership monitor stopped; final ownership check follows.' "
            '"${STATE_DIR}/opencode-watch.log"; do sleep 0.001; done; '
            f"printf '%s\\n' {shlex.quote(identity)} >{shlex.quote(str(identity_path))}) &"
        )
    signal_aware_block = ""
    if signal_aware:
        signal_aware_block = (
            "exec python3 -c "
            "'import signal,time; "
            "signal.signal(signal.SIGINT, lambda *_: exit(0)); "
            "signal.signal(signal.SIGTERM, lambda *_: exit(0)); "
            "signal.signal(signal.SIGHUP, lambda *_: exit(0)); "
            "time.sleep(60)'\n"
        )
    mock_opencode.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
{args_block}
{sleep_block}
{identity_update_block}
{signal_aware_block}
printf '%s\\n' OPENCODE_STDOUT
printf '%s\\n' OPENCODE_STDERR >&2
exit {exit_code}
""",
        encoding="utf-8",
    )
    mock_opencode.chmod(0o755)
    return mock_opencode


def run_wrapper(
    tmp_path: Path,
    *,
    llm_states: list[str],
    opencode_exit: int = 0,
    llm_stop_exit: int = 0,
    args: list[str] | None = None,
    opencode_args_file: Path | None = None,
    opencode_sleep: float = 0,
    llm_identities: list[str] | None = None,
    identity_update: tuple[Path, str] | None = None,
    identity_update_after_cleanup_marker: tuple[Path, str] | None = None,
    neural_marker_file: Path,
) -> tuple[subprocess.CompletedProcess[str], Path, Path, Path]:
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    mock_opencode = install_mock_opencode(
        tmp_path,
        exit_code=opencode_exit,
        args_file=opencode_args_file,
        sleep_seconds=opencode_sleep,
        identity_update=identity_update,
        identity_update_after_cleanup_marker=identity_update_after_cleanup_marker,
    )
    mock_llm, stop_log, state_count_file = install_mock_llm(
        tmp_path,
        llm_states,
        stop_exit=llm_stop_exit,
        identities=llm_identities,
    )
    mock_neural = tmp_path / "mock_neural"
    mock_neural.write_text(
        f"#!/usr/bin/env bash\nprintf '%s\\n' invoked >{shlex.quote(str(neural_marker_file))}\n",
        encoding="utf-8",
    )
    mock_neural.chmod(0o755)
    env = {
        **os.environ,
        "OPENCODE_BIN": str(mock_opencode),
        "LLM_PATH": str(mock_llm),
        "NEURAL_PATH": str(mock_neural),
        "OPENCODE_DB_PATH": str(tmp_path / "must-not-be-read.db"),
        "STATE_DIR": str(state_dir),
        "OWNERSHIP_POLL_SECONDS": "0.01",
    }
    result = subprocess.run(
        [str(SCRIPT_PATH), *(args or [])],
        cwd=project_dir,
        env=env,
        capture_output=True,
        text=True,
        timeout=5,
    )
    return result, state_dir, stop_log, state_count_file


def launch_wrapper(
    tmp_path: Path,
    *,
    llm_identities: list[str],
    opencode_sleep: float,
) -> tuple[subprocess.Popen[str], Path, Path]:
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    mock_opencode = install_mock_opencode(
        tmp_path,
        sleep_seconds=opencode_sleep,
        signal_aware=True,
    )
    mock_llm, stop_log, _ = install_mock_llm(tmp_path, ["STOPPED"], identities=llm_identities)
    env = {
        **os.environ,
        "OPENCODE_BIN": str(mock_opencode),
        "LLM_PATH": str(mock_llm),
        "STATE_DIR": str(state_dir),
        "OWNERSHIP_POLL_SECONDS": "0.01",
    }
    process = subprocess.Popen(
        [str(SCRIPT_PATH)],
        cwd=project_dir,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return process, state_dir, stop_log


def test_wrapper_forwards_arguments_and_stdio_without_runtime_watchers(tmp_path: Path) -> None:
    args_file = tmp_path / "opencode-args"
    neural_marker = tmp_path / "neural-invoked"
    result, state_dir, stop_log, state_count_file = run_wrapper(
        tmp_path,
        llm_states=["STOPPED", "STOPPED"],
        args=["--session", "ses_user_supplied", "value with spaces"],
        opencode_args_file=args_file,
        neural_marker_file=neural_marker,
    )

    assert result.returncode == 0
    assert result.stdout == "OPENCODE_STDOUT\n"
    assert result.stderr == "OPENCODE_STDERR\n"
    assert args_file.read_text(encoding="utf-8").splitlines() == [
        "--session",
        "ses_user_supplied",
        "value with spaces",
    ]
    assert not neural_marker.exists()
    assert not stop_log.exists()
    assert state_count_file.read_text(encoding="utf-8").splitlines() == ["1"]
    log_content = (state_dir / "opencode-watch.log").read_text(encoding="utf-8")
    assert "pre-launch LLM state: STOPPED" in log_content
    assert "OpenCode exited (exit code 0)" in log_content
    assert "resolved session" not in log_content
    assert "watcher" not in log_content.lower()
    assert not (state_dir / "opencode-watch.pid").exists()


def test_wrapper_stops_one_new_healthy_profile_after_stopped_baseline(tmp_path: Path) -> None:
    result, state_dir, stop_log, state_count_file = run_wrapper(
        tmp_path,
        llm_states=["STOPPED", "GENERAL"],
        llm_identities=["GENERAL 4321", "GENERAL 4321"],
        opencode_sleep=0.1,
        neural_marker_file=tmp_path / "neural-invoked",
    )

    assert result.returncode == 0
    assert stop_log.read_text(encoding="utf-8").splitlines() == ["stop"]
    assert state_count_file.read_text(encoding="utf-8").splitlines() == ["1"]
    log_content = (state_dir / "opencode-watch.log").read_text(encoding="utf-8")
    assert "Recorded wrapper-owned LLM identity: GENERAL 4321" in log_content
    assert "verified wrapper-owned GENERAL 4321" in log_content
    assert "LLM stop result: success (GENERAL 4321)" in log_content


@pytest.mark.parametrize("pre_state", ("GENERAL", "CODE", "VISION", "UNKNOWN"))
def test_wrapper_preserves_preexisting_or_unknown_llm_state(
    tmp_path: Path,
    pre_state: str,
) -> None:
    result, state_dir, stop_log, state_count_file = run_wrapper(
        tmp_path,
        llm_states=[pre_state],
        neural_marker_file=tmp_path / "neural-invoked",
    )

    assert result.returncode == 0
    assert not stop_log.exists()
    assert state_count_file.read_text(encoding="utf-8").splitlines() == ["1"]
    log_content = (state_dir / "opencode-watch.log").read_text(encoding="utf-8")
    assert f"pre-launch LLM state: {pre_state}" in log_content
    assert f"preserve pre-existing or unverified state ({pre_state})" in log_content


def test_wrapper_does_not_stop_when_stopped_baseline_has_no_active_profile(
    tmp_path: Path,
) -> None:
    result, state_dir, stop_log, _ = run_wrapper(
        tmp_path,
        llm_states=["STOPPED", "STOPPED"],
        neural_marker_file=tmp_path / "neural-invoked",
    )

    assert result.returncode == 0
    assert not stop_log.exists()
    log_content = (state_dir / "opencode-watch.log").read_text(encoding="utf-8")
    assert "no wrapper-owned profile was observed; no action" in log_content


def test_wrapper_fails_closed_when_shutdown_state_is_unknown(tmp_path: Path) -> None:
    result, state_dir, stop_log, _ = run_wrapper(
        tmp_path,
        llm_states=["STOPPED", "UNKNOWN"],
        neural_marker_file=tmp_path / "neural-invoked",
    )

    assert result.returncode == 0
    assert not stop_log.exists()
    log_content = (state_dir / "opencode-watch.log").read_text(encoding="utf-8")
    assert "no wrapper-owned profile was observed; no action" in log_content


def test_wrapper_preserves_opencode_exit_code_when_llm_stop_fails(tmp_path: Path) -> None:
    result, state_dir, stop_log, _ = run_wrapper(
        tmp_path,
        llm_states=["STOPPED", "CODE"],
        llm_identities=["CODE 2468", "CODE 2468"],
        opencode_sleep=0.1,
        opencode_exit=42,
        llm_stop_exit=7,
        neural_marker_file=tmp_path / "neural-invoked",
    )

    assert result.returncode == 42
    assert stop_log.read_text(encoding="utf-8").splitlines() == ["stop"]
    log_content = (state_dir / "opencode-watch.log").read_text(encoding="utf-8")
    assert "WARNING: LLM stop result: failed (CODE 2468)" in log_content
    assert "Cleanup complete (exit code 42)" in log_content


@pytest.mark.parametrize("signal_number", (signal.SIGINT, signal.SIGTERM, signal.SIGHUP))
def test_wrapper_signal_cleanup_stops_owned_profile_once(
    tmp_path: Path, signal_number: signal.Signals
) -> None:
    process, state_dir, stop_log = launch_wrapper(
        tmp_path,
        llm_identities=["GENERAL 5001"],
        opencode_sleep=5,
    )

    pid_file = state_dir / "opencode-watch.pid"
    for _ in range(100):
        if (
            pid_file.exists()
            and (state_dir / "opencode-watch.log").exists()
            and "Recorded wrapper-owned"
            in (state_dir / "opencode-watch.log").read_text(encoding="utf-8")
        ):
            break
        time.sleep(0.01)

    process.send_signal(signal_number)
    stdout, stderr = process.communicate(timeout=5)

    assert process.returncode == 128 + signal_number
    assert stdout == ""
    assert stderr == ""
    assert stop_log.read_text(encoding="utf-8").splitlines() == ["stop"]
    assert not pid_file.exists()
    log_content = (state_dir / "opencode-watch.log").read_text(encoding="utf-8")
    assert log_content.count("LLM stop result: success") == 1


def test_wrapper_preserves_profile_after_ownership_drift(tmp_path: Path) -> None:
    identity_file = tmp_path / "llm-identities"
    result, state_dir, stop_log, _ = run_wrapper(
        tmp_path,
        llm_states=["STOPPED"],
        llm_identities=["GENERAL 6001"],
        opencode_sleep=0.1,
        identity_update_after_cleanup_marker=(identity_file, "CODE 6002"),
        neural_marker_file=tmp_path / "neural-invoked",
    )

    assert result.returncode == 0
    assert not stop_log.exists()
    log_content = (state_dir / "opencode-watch.log").read_text(encoding="utf-8")
    assert "ownership mismatch (owned GENERAL 6001, current CODE 6002)" in log_content


def test_wrapper_does_not_remove_a_pid_file_owned_by_another_process(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    pid_file = state_dir / "opencode-watch.pid"
    pid_file.write_text(str(os.getpid()), encoding="utf-8")

    result = subprocess.run(
        [str(SCRIPT_PATH)],
        cwd=project_dir,
        env={**os.environ, "STATE_DIR": str(state_dir)},
        capture_output=True,
        text=True,
        timeout=5,
    )

    assert result.returncode == 1
    assert "Wrapper already running" in result.stderr
    assert pid_file.read_text(encoding="utf-8") == str(os.getpid())


def test_wrapper_source_has_no_automatic_opencode_context_runtime() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "sqlite3" not in source
    assert "OPENCODE_DB" not in source
    assert "NEURAL_PATH" not in source
    assert "handoff watch" not in source
    assert "WATCHER_PID" not in source
    assert "context-pressure" not in source

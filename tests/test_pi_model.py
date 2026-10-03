"""The Pi adapter refuses ambiguous or unknown listeners before a lifecycle action."""

from __future__ import annotations

import json
import runpy
from contextlib import nullcontext
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def adapter() -> dict[str, Any]:
    return runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/pi-model"))


def test_supported_pi_topology_is_exact(adapter: dict[str, Any]) -> None:
    assert adapter["PORTS"] == {
        "GENERAL": 18081,
        "CODE": 18080,
        "GPTOSS": 18086,
    }
    assert set(adapter["MODELS"]) == {"GENERAL", "CODE", "GPTOSS"}
    assert adapter["MODELS"] == {
        "GENERAL": "/models/gguf/qwen3.6-35b-a3b/Qwen3.6-35B-A3B-Q4_K_M.gguf",
        "CODE": "/models/gguf/nemotron-3-nano-30b-a3b/nvidia_Nemotron-3-Nano-30B-A3B-Q5_K_M.gguf",
        "GPTOSS": "/models/gguf/gpt-oss-20b/gpt-oss-20b-MXFP4.gguf",
    }
    assert adapter["MODELS"]["GENERAL"].startswith("/models/gguf/qwen3.6-35b-a3b/")
    assert adapter["CHALLENGER_NAMES"] == {"GPTOSS": "gptoss"}
    assert adapter["UNFILLED_ROLES"] == {"VISION"}
    assert adapter["CONFLICT_ONLY_PORTS"] == (18082, 18087)


def test_patch_alias_routes_to_gptoss(adapter: dict[str, Any]) -> None:
    assert adapter["normalize_target"]("patch") == "GPTOSS"


def _states(listener: Any | None = None) -> dict[str, tuple[int, ...] | None]:
    result: dict[str, tuple[int, ...] | None] = dict.fromkeys(("GENERAL", "CODE", "GPTOSS"), None)
    if listener is not None:
        result[listener.profile] = (listener.pid,)
    return result


def _identify_states(adapter: dict[str, Any], states: dict[str, tuple[int, ...] | None]) -> Any:
    active = [(profile, pids) for profile, pids in states.items() if pids is not None]
    if not active:
        return None
    if len(active) != 1 or len(active[0][1]) != 1:
        raise adapter["SwitchError"]("multiple or ambiguous listeners")
    profile, pids = active[0]
    if profile == "GPTOSS":
        return adapter["Listener"](profile, pids[0], 32768, 2048, 1024)
    return adapter["Listener"](profile, pids[0])


@pytest.mark.parametrize(
    ("profile", "pid", "output"),
    [
        (
            "GENERAL",
            101,
            "GENERAL STARTED BY THIS INVOCATION\nownership: GENERAL pid=101",
        ),
        ("CODE", 202, "CODE STARTED BY THIS INVOCATION\nownership: CODE pid=202"),
        ("GPTOSS", 303, "gptoss STARTED BY THIS INVOCATION pid=303"),
    ],
)
def test_switch_reports_exact_runtime_started_by_this_invocation(
    adapter: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    profile: str,
    pid: int,
    output: str,
) -> None:
    namespace = adapter["switch"].__globals__
    listener = (
        adapter["Listener"](profile, pid, 32768, 2048, 1024)
        if profile == "GPTOSS"
        else adapter["Listener"](profile, pid)
    )
    snapshots = iter((_states(), _states(), _states(listener)))
    commands: list[tuple[str, str, int | None]] = []

    def command(name: str, action: str, pid: int | None = None, **_kwargs: Any) -> str:
        commands.append((name, action, pid))
        return output

    monkeypatch.setitem(namespace, "switch_lock", nullcontext)
    monkeypatch.setitem(namespace, "validate_catalog_entry", lambda _profile: None)
    monkeypatch.setitem(namespace, "scan", lambda: next(snapshots))
    monkeypatch.setitem(namespace, "identify", lambda values: _identify_states(adapter, values))
    monkeypatch.setitem(namespace, "command", command)

    result = adapter["switch"](profile)

    assert result.listener == listener
    assert result.ownership == "STARTED"
    assert (result.expected_profile, result.expected_pid) == (profile, pid)
    assert commands == [(profile, "start", None)]


@pytest.mark.parametrize(("profile", "pid"), [("GENERAL", 101), ("CODE", 202), ("GPTOSS", 303)])
def test_switch_marks_matching_runtime_borrowed(
    adapter: dict[str, Any], monkeypatch: pytest.MonkeyPatch, profile: str, pid: int
) -> None:
    namespace = adapter["switch"].__globals__
    listener = (
        adapter["Listener"](profile, pid, 32768, 2048, 1024)
        if profile == "GPTOSS"
        else adapter["Listener"](profile, pid)
    )
    monkeypatch.setitem(namespace, "switch_lock", nullcontext)
    monkeypatch.setitem(namespace, "validate_catalog_entry", lambda _profile: None)
    monkeypatch.setitem(namespace, "scan", lambda: _states(listener))
    monkeypatch.setitem(namespace, "identify", lambda values: _identify_states(adapter, values))
    monkeypatch.setitem(
        namespace,
        "command",
        lambda *_args, **_kwargs: pytest.fail("matching runtime must be borrowed"),
    )

    result = adapter["switch"](profile)

    assert result.listener == listener
    assert result.ownership == "BORROWED"


def test_switch_classifies_runtime_raced_in_by_another_starter_as_borrowed(
    adapter: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    namespace = adapter["switch"].__globals__
    listener = adapter["Listener"]("GENERAL", 404)
    snapshots = iter((_states(), _states(), _states(listener)))
    monkeypatch.setitem(namespace, "switch_lock", nullcontext)
    monkeypatch.setitem(namespace, "validate_catalog_entry", lambda _profile: None)
    monkeypatch.setitem(namespace, "scan", lambda: next(snapshots))
    monkeypatch.setitem(namespace, "identify", lambda values: _identify_states(adapter, values))
    monkeypatch.setitem(namespace, "command", lambda *_args, **_kwargs: "GENERAL ALREADY READY")

    result = adapter["switch"]("GENERAL")

    assert result.listener == listener
    assert result.ownership == "BORROWED"


def test_switch_refuses_pid_changed_after_start_and_cleans_only_reported_pid(
    adapter: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    namespace = adapter["switch"].__globals__
    replacement = adapter["Listener"]("GENERAL", 200)
    snapshots = iter((_states(), _states(), _states(replacement)))
    commands: list[tuple[str, str, int | None]] = []

    def command(name: str, action: str, pid: int | None = None, **_kwargs: Any) -> str:
        commands.append((name, action, pid))
        return "GENERAL STARTED BY THIS INVOCATION\nownership: GENERAL pid=100"

    monkeypatch.setitem(namespace, "switch_lock", nullcontext)
    monkeypatch.setitem(namespace, "validate_catalog_entry", lambda _profile: None)
    monkeypatch.setitem(namespace, "scan", lambda: next(snapshots))
    monkeypatch.setitem(namespace, "identify", lambda values: _identify_states(adapter, values))
    monkeypatch.setitem(namespace, "command", command)

    with pytest.raises(adapter["SwitchError"], match="started pid=100.*found pid=200"):
        adapter["switch"]("GENERAL")

    assert commands == [("GENERAL", "start", None), ("GENERAL", "stop", 100)]


def test_start_ownership_parser_rejects_ambiguous_output(adapter: dict[str, Any]) -> None:
    output = "GENERAL STARTED BY THIS INVOCATION\nownership: GENERAL pid=100\nGENERAL ALREADY READY"
    with pytest.raises(adapter["SwitchError"], match="unambiguous STARTED or BORROWED"):
        adapter["_start_ownership"]("GENERAL", output)


def _install_stop_fakes(
    adapter: dict[str, Any], monkeypatch: pytest.MonkeyPatch, snapshots: list[Any]
) -> list[tuple[str, str, int | None]]:
    namespace = adapter["stop_owned"].__globals__
    remaining = iter(snapshots)
    commands: list[tuple[str, str, int | None]] = []
    monkeypatch.setitem(namespace, "switch_lock", nullcontext)
    monkeypatch.setitem(namespace, "scan", lambda: next(remaining))
    monkeypatch.setitem(namespace, "identify", lambda values: _identify_states(adapter, values))

    def command(name: str, action: str, pid: int | None = None, **_kwargs: Any) -> str:
        commands.append((name, action, pid))
        return "STOPPED"

    monkeypatch.setitem(namespace, "command", command)
    return commands


def test_stop_owned_stops_exact_started_listener(
    adapter: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    listener = adapter["Listener"]("CODE", 123)
    result = adapter["SwitchResult"](listener, "STARTED")
    commands = _install_stop_fakes(adapter, monkeypatch, [_states(listener), _states(listener)])

    assert adapter["stop_owned"](result) is True
    assert commands == [("CODE", "stop", 123)]


@pytest.mark.parametrize(
    "replacement",
    [
        None,
        ("CODE", 200),
        ("GENERAL", 300),
    ],
    ids=("disappeared", "same-profile-replacement", "different-profile-replacement"),
)
def test_stop_owned_preserves_disappeared_or_replaced_runtime(
    adapter: dict[str, Any], monkeypatch: pytest.MonkeyPatch, replacement: Any
) -> None:
    owned = adapter["Listener"]("CODE", 100)
    current = None
    if replacement is not None:
        profile, pid = replacement
        current = adapter["Listener"](profile, pid)
    result = adapter["SwitchResult"](owned, "STARTED")
    commands = _install_stop_fakes(adapter, monkeypatch, [_states(current)])

    assert adapter["stop_owned"](result) is False
    assert commands == []


def test_stop_owned_rechecks_identity_before_stopping(
    adapter: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    owned = adapter["Listener"]("CODE", 100)
    replacement = adapter["Listener"]("CODE", 200)
    result = adapter["SwitchResult"](owned, "STARTED")
    commands = _install_stop_fakes(adapter, monkeypatch, [_states(owned), _states(replacement)])

    assert adapter["stop_owned"](result) is False
    assert commands == []


def test_stop_owned_never_stops_borrowed_runtime(
    adapter: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    result = adapter["SwitchResult"](adapter["Listener"]("GENERAL", 100), "BORROWED")
    namespace = adapter["stop_owned"].__globals__
    monkeypatch.setitem(
        namespace, "scan", lambda: pytest.fail("borrowed runtime must not be inspected for stop")
    )

    assert adapter["stop_owned"](result) is False


def test_installed_pi_catalog_has_only_supported_local_mappings() -> None:
    catalog_path = Path.home() / ".pi" / "agent" / "models.json"
    if not catalog_path.is_file():
        pytest.skip("host Pi model catalog is not installed")
    providers = json.loads(catalog_path.read_text())["providers"]
    supported = {
        "neural-general": {
            "baseUrl": "http://127.0.0.1:18081/v1",
            "api": "openai-completions",
            "apiKey": "local",
            "models": [
                {
                    "id": "/models/gguf/qwen3.6-35b-a3b/Qwen3.6-35B-A3B-Q4_K_M.gguf",
                    "name": "NeuralEngine GENERAL",
                    "contextWindow": 65536,
                    "maxTokens": 8192,
                }
            ],
        },
        "local-gptoss": {
            "baseUrl": "http://127.0.0.1:18086/v1",
            "api": "openai-completions",
            "apiKey": "local",
            "models": [
                {
                    "id": "/models/gguf/gpt-oss-20b/gpt-oss-20b-MXFP4.gguf",
                    "name": "GPT-OSS 20B MXFP4 (local challenger)",
                    "input": ["text"],
                    "contextWindow": 32768,
                    "maxTokens": 4096,
                    "reasoning": True,
                    "compat": {"supportsReasoningEffort": True},
                }
            ],
        },
        "neural-code": {
            "baseUrl": "http://127.0.0.1:18080/v1",
            "api": "openai-completions",
            "apiKey": "local",
            "models": [
                {
                    "id": (
                        "/models/gguf/nemotron-3-nano-30b-a3b/"
                        "nvidia_Nemotron-3-Nano-30B-A3B-Q5_K_M.gguf"
                    ),
                    "name": "NeuralEngine CODE / Nemotron Q5",
                    "contextWindow": 32768,
                    "maxTokens": 7000,
                }
            ],
        },
    }
    assert {name: providers[name] for name in supported} == supported
    assert set(providers) == {"neural-general", "neural-code", "local-gptoss"}
    gptoss = providers["local-gptoss"]
    assert gptoss["baseUrl"] == "http://127.0.0.1:18086/v1"
    assert len(gptoss["models"]) == 1
    model = gptoss["models"][0]
    assert model["id"] == "/models/gguf/gpt-oss-20b/gpt-oss-20b-MXFP4.gguf"
    assert (model["contextWindow"], model["maxTokens"]) == (32768, 4096)
    assert model["reasoning"] is True
    assert model["compat"]["supportsReasoningEffort"] is True
    assert "neural-vision" not in providers


def test_vision_is_unfilled_before_listener_discovery(
    adapter: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(
        adapter["switch"].__globals__, "scan", lambda: pytest.fail("must reject VISION first")
    )
    with pytest.raises(adapter["SwitchError"], match="VISION is UNFILLED/unsupported"):
        adapter["switch"]("VISION")


def test_retired_challenger_port_is_conflict_only(
    adapter: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(
        adapter["run"].__globals__,
        "run",
        lambda *args: "LISTEN 0 128 127.0.0.1:18087 0.0.0.0:*\n",
    )
    with pytest.raises(adapter["SwitchError"], match="conflict-only unsupported port 18087"):
        adapter["scan"]()


def test_code_port_is_recognized_as_supported(
    adapter: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(
        adapter["run"].__globals__,
        "run",
        lambda *args: (
            'LISTEN 0 128 127.0.0.1:18080 0.0.0.0:* users:(("llama-server",pid=123,fd=1))\n'
        ),
    )
    assert adapter["scan"]()["CODE"] == (123,)


def test_vision_port_is_conflict_only_without_a_model_mapping(
    adapter: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(
        adapter["run"].__globals__,
        "run",
        lambda *args: (
            'LISTEN 0 128 127.0.0.1:18082 0.0.0.0:* users:(("llama-server",pid=124,fd=1))\n'
        ),
    )
    with pytest.raises(adapter["SwitchError"], match="conflict-only unsupported port 18082"):
        adapter["scan"]()


def test_scan_includes_gptoss_and_unknown_owner(
    adapter: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    assert adapter["PORTS"]["GPTOSS"] == 18086
    assert adapter["MODELS"]["GPTOSS"].startswith("/models/gguf/gpt-oss-20b/")
    monkeypatch.setitem(
        adapter["run"].__globals__,
        "run",
        lambda *args: "LISTEN 0 128 127.0.0.1:18086 0.0.0.0:*\n",
    )
    states = adapter["scan"]()
    assert states["GPTOSS"] == ()
    with pytest.raises(adapter["SwitchError"], match="no unique visible PID"):
        adapter["identify"](states)


def test_multiple_profiles_refused_before_action(adapter: dict[str, Any]) -> None:
    states = dict.fromkeys(adapter["PORTS"], None)
    states["GENERAL"] = (123,)
    states["GPTOSS"] = (456,)
    with pytest.raises(adapter["SwitchError"], match="multiple listeners"):
        adapter["identify"](states)


def test_wrong_model_identity_refused(
    adapter: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(
        adapter["identify"].__globals__,
        "run",
        lambda *args: "gptoss READY pid=456 context=32768 batch=2048 ubatch=1024",
    )
    monkeypatch.setitem(adapter["identify"].__globals__, "model_identity", lambda name: False)
    states = dict.fromkeys(adapter["PORTS"], None)
    states["GPTOSS"] = (456,)
    with pytest.raises(adapter["SwitchError"], match="wrong model identity"):
        adapter["identify"](states)


def test_switch_rechecks_all_ports_after_start(
    adapter: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    namespace = adapter["switch"].__globals__
    stopped = dict.fromkeys(adapter["PORTS"], None)
    conflict = {**stopped, "GPTOSS": (456,), "GENERAL": (789,)}
    snapshots = iter((stopped, stopped, conflict))
    actions: list[tuple[str, str]] = []

    def command(name: str, action: str, **_kwargs: Any) -> str:
        actions.append((name, action))
        return "gptoss STARTED BY THIS INVOCATION pid=456" if action == "start" else ""

    monkeypatch.setitem(namespace, "switch_lock", nullcontext)
    monkeypatch.setitem(namespace, "scan", lambda: next(snapshots))
    monkeypatch.setitem(namespace, "command", command)
    with pytest.raises(adapter["SwitchError"], match="multiple listeners"):
        adapter["switch"]("GPTOSS")
    assert actions == [("GPTOSS", "start")]


def test_unknown_gptoss_listener_never_stopped(
    adapter: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    namespace = adapter["switch"].__globals__
    states = {**dict.fromkeys(adapter["PORTS"], None), "GPTOSS": ()}
    actions: list[tuple[str, str]] = []
    monkeypatch.setitem(namespace, "switch_lock", nullcontext)
    monkeypatch.setitem(namespace, "scan", lambda: states)
    monkeypatch.setitem(namespace, "command", lambda name, action: actions.append((name, action)))
    with pytest.raises(adapter["SwitchError"], match="no unique visible PID"):
        adapter["switch"]("GENERAL")
    assert actions == []


def test_gptoss_start_forwards_only_requested_runtime_settings(
    adapter: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    namespace = adapter["command"].__globals__
    calls: list[tuple[str, ...]] = []

    def fake_run(*args: str) -> str:
        calls.append(args)
        return ""

    monkeypatch.setitem(namespace, "run", fake_run)
    adapter["command"]("GPTOSS", "start", context=65536, batch=4096, ubatch=2048)
    assert calls == [
        (
            str(Path(__file__).resolve().parents[1] / "scripts/challenger"),
            "start",
            "gptoss",
            "--context",
            "65536",
            "--batch",
            "4096",
            "--ubatch",
            "2048",
        )
    ]


@pytest.mark.parametrize(
    ("profile", "expected_command"),
    [
        (
            "CODE",
            ("scripts/llm", "stop", "--expected-profile", "CODE", "--expected-pid", "123"),
        ),
        (
            "GPTOSS",
            ("scripts/challenger", "stop", "gptoss", "--expected-pid", "123"),
        ),
    ],
)
def test_command_stop_forwards_exact_profile_and_pid(
    adapter: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    profile: str,
    expected_command: tuple[str, ...],
) -> None:
    namespace = adapter["command"].__globals__
    calls: list[tuple[str, ...]] = []

    def fake_run(*args: str) -> str:
        calls.append(args)
        return "STOPPED"

    monkeypatch.setitem(namespace, "run", fake_run)
    adapter["command"](profile, "stop", 123)

    assert len(calls) == 1
    assert calls[0][1:] == expected_command[1:]
    assert calls[0][0].endswith(expected_command[0].split("/")[-1])


def test_gptoss_identification_requires_exact_model_and_reports_profile(
    adapter: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    namespace = adapter["identify"].__globals__
    states = dict.fromkeys(adapter["PORTS"], None)
    states["GPTOSS"] = (456,)
    calls: list[tuple[str, ...]] = []

    def fake_run(*args: str) -> str:
        calls.append(args)
        return "gptoss READY pid=456 context=32768 batch=2048 ubatch=1024"

    monkeypatch.setitem(namespace, "run", fake_run)
    monkeypatch.setitem(namespace, "model_identity", lambda name: name == "GPTOSS")
    listener = adapter["identify"](states)
    assert (listener.profile, listener.pid, listener.context, listener.batch, listener.ubatch) == (
        "GPTOSS",
        456,
        32768,
        2048,
        1024,
    )
    assert calls[0][-2:] == ("status", "gptoss")


# ---------------------------------------------------------------------------
# Machine API — switch-json and stop-owned-json
# ---------------------------------------------------------------------------


def _make_switch_result(
    adapter: dict[str, Any],
    profile: str,
    pid: int,
    ownership: str,
) -> Any:
    """Build a SwitchResult matching the adapter's dataclasses."""
    listener = (
        adapter["Listener"](profile, pid, 32768, 2048, 1024)
        if profile == "GPTOSS"
        else adapter["Listener"](profile, pid)
    )
    return adapter["SwitchResult"](listener=listener, ownership=ownership)


# --- switch-json schema contract ---


@pytest.mark.parametrize(
    ("profile", "pid", "ownership", "expected_role"),
    [
        ("GENERAL", 101, "STARTED", "GENERAL"),
        ("GENERAL", 101, "BORROWED", "GENERAL"),
        ("CODE", 202, "STARTED", "CODE"),
        ("CODE", 202, "BORROWED", "CODE"),
        ("GPTOSS", 303, "STARTED", "PATCH"),
        ("GPTOSS", 303, "BORROWED", "PATCH"),
    ],
)
def test_switch_json_schema(
    adapter: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    profile: str,
    pid: int,
    ownership: str,
    expected_role: str,
) -> None:
    """switch-json emits a single valid JSON document with required fields."""
    switch_result = _make_switch_result(adapter, profile, pid, ownership)
    monkeypatch.setitem(
        adapter["_switch_json"].__globals__,
        "switch",
        lambda target, **_kw: switch_result,
    )
    monkeypatch.setitem(
        adapter["_switch_json"].__globals__,
        "normalize_target",
        lambda r: r.upper().replace("PATCH", "GPTOSS"),
    )

    import io

    buf = io.StringIO()
    monkeypatch.setattr("sys.stdout", buf)
    rc = adapter["_switch_json"](profile, context=None, batch=None, ubatch=None)

    assert rc == 0, "expected exit 0 on success"
    doc = json.loads(buf.getvalue())

    assert doc["api_version"] == 1
    assert doc["operation"] == "switch"
    assert doc["ownership"] == ownership
    assert doc["role"] == expected_role
    assert doc["profile"] == profile
    assert doc["pid"] == pid
    assert doc["endpoint"] == f"http://127.0.0.1:{adapter['PORTS'][profile]}/v1"


def test_switch_json_stdout_contains_only_json(
    adapter: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """No human-readable text may appear on stdout in JSON mode."""
    switch_result = _make_switch_result(adapter, "GENERAL", 99, "STARTED")
    monkeypatch.setitem(
        adapter["_switch_json"].__globals__, "switch", lambda target, **_kw: switch_result
    )
    monkeypatch.setitem(
        adapter["_switch_json"].__globals__,
        "normalize_target",
        lambda r: r.upper(),
    )
    import io

    buf = io.StringIO()
    monkeypatch.setattr("sys.stdout", buf)
    adapter["_switch_json"]("GENERAL", context=None, batch=None, ubatch=None)

    lines = [line for line in buf.getvalue().splitlines() if line.strip()]
    assert len(lines) == 1, "stdout must contain exactly one line"
    json.loads(lines[0])  # must parse without error


def test_switch_json_failure_exits_nonzero_with_no_json(
    adapter: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """On switch failure, exit is non-zero and stdout is empty (no bogus JSON)."""
    monkeypatch.setitem(
        adapter["_switch_json"].__globals__,
        "switch",
        lambda target, **_kw: (_ for _ in ()).throw(adapter["SwitchError"]("simulated failure")),
    )
    monkeypatch.setitem(
        adapter["_switch_json"].__globals__,
        "normalize_target",
        lambda r: r.upper(),
    )
    import io

    out = io.StringIO()
    err = io.StringIO()
    monkeypatch.setattr("sys.stdout", out)
    monkeypatch.setattr("sys.stderr", err)
    rc = adapter["_switch_json"]("GENERAL", context=None, batch=None, ubatch=None)

    assert rc != 0
    assert out.getvalue().strip() == "", "stdout must be empty on failure"
    assert err.getvalue().strip() != "", "stderr must contain diagnostic"


def test_switch_json_unsupported_role_exits_2(
    adapter: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unknown/unsupported role returns exit code 2, no JSON on stdout."""
    import io

    out = io.StringIO()
    err = io.StringIO()
    monkeypatch.setattr("sys.stdout", out)
    monkeypatch.setattr("sys.stderr", err)
    rc = adapter["_switch_json"]("BOGUS_ROLE", context=None, batch=None, ubatch=None)

    assert rc == 2
    assert out.getvalue().strip() == ""


def test_switch_json_vision_rejected(
    adapter: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """VISION is explicitly rejected by switch-json."""
    import io

    out = io.StringIO()
    err = io.StringIO()
    monkeypatch.setattr("sys.stdout", out)
    monkeypatch.setattr("sys.stderr", err)
    rc = adapter["_switch_json"]("VISION", context=None, batch=None, ubatch=None)

    assert rc == 2
    assert out.getvalue().strip() == ""


# --- stop-owned-json contract ---


@pytest.mark.parametrize("profile", ("GENERAL", "CODE", "GPTOSS", "PATCH"))
def test_stop_owned_json_stops_verified_listener_with_discovered_metadata(
    adapter: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    profile: str,
) -> None:
    canonical_profile = "GPTOSS" if profile == "PATCH" else profile
    listener = (
        adapter["Listener"](canonical_profile, 303, 32768, 2048, 1024)
        if canonical_profile == "GPTOSS"
        else adapter["Listener"](canonical_profile, 303)
    )
    commands = _install_stop_fakes(adapter, monkeypatch, [_states(listener), _states(listener)])

    assert adapter["_stop_owned_json"](profile, 303) == 0
    assert commands == [(canonical_profile, "stop", 303)]
    assert json.loads(capsys.readouterr().out) == {
        "api_version": 1,
        "operation": "stop_owned",
        "result": "STOPPED",
        "profile": canonical_profile,
        "pid": 303,
    }


@pytest.mark.parametrize("verification_step", (0, 1), ids=("initial", "recheck"))
@pytest.mark.parametrize(
    "replacement",
    [("GPTOSS", 404), ("GENERAL", 303), None],
    ids=("same-profile-new-pid", "different-profile-same-pid", "disappeared"),
)
def test_stop_owned_json_preserves_gptoss_replacement_or_disappearance(
    adapter: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    verification_step: int,
    replacement: tuple[str, int] | None,
) -> None:
    owned = adapter["Listener"]("GPTOSS", 303, 32768, 2048, 1024)
    current = adapter["Listener"](*replacement) if replacement is not None else None
    snapshots = [_states(owned)] * verification_step + [_states(current)]
    commands = _install_stop_fakes(adapter, monkeypatch, snapshots)

    assert adapter["_stop_owned_json"]("GPTOSS", 303) == 0
    assert commands == []
    assert json.loads(capsys.readouterr().out) == {
        "api_version": 1,
        "operation": "stop_owned",
        "result": "NOT_OWNED_OR_REPLACED",
        "profile": "GPTOSS",
        "pid": 303,
    }


def test_stop_owned_json_ignores_tuning_metadata_changes_between_identity_checks(
    adapter: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    namespace = adapter["stop_owned"].__globals__
    listeners = iter(
        [
            adapter["Listener"]("GPTOSS", 303, 32768, 2048, 1024),
            adapter["Listener"]("GPTOSS", 303, 65536, 1024, 512),
        ]
    )
    commands: list[tuple[str, str, int]] = []
    monkeypatch.setitem(namespace, "switch_lock", nullcontext)
    monkeypatch.setitem(namespace, "scan", lambda: _states())
    monkeypatch.setitem(namespace, "identify", lambda _states: next(listeners))
    monkeypatch.setitem(
        namespace, "command", lambda profile, action, pid: commands.append((profile, action, pid))
    )

    assert adapter["_stop_owned_json"]("GPTOSS", 303) == 0
    assert commands == [("GPTOSS", "stop", 303)]
    assert json.loads(capsys.readouterr().out)["result"] == "STOPPED"


def test_stop_owned_preserves_borrowed_gptoss_with_discovered_metadata(
    adapter: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    result = adapter["SwitchResult"](
        adapter["Listener"]("GPTOSS", 303, 32768, 2048, 1024), "BORROWED"
    )
    namespace = adapter["stop_owned"].__globals__
    monkeypatch.setitem(
        namespace, "scan", lambda: pytest.fail("borrowed runtime must not be scanned")
    )
    monkeypatch.setitem(
        namespace, "command", lambda *_args: pytest.fail("borrowed runtime must not be stopped")
    )

    assert adapter["stop_owned"](result) is False


def test_stop_owned_json_refuses_unverified_runtime_identity(
    adapter: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    namespace = adapter["stop_owned"].__globals__
    monkeypatch.setitem(namespace, "switch_lock", nullcontext)
    monkeypatch.setitem(namespace, "scan", lambda: _states())

    def refuse_identity(_states: Any) -> None:
        raise adapter["SwitchError"]("wrong model identity")

    monkeypatch.setitem(namespace, "identify", refuse_identity)
    monkeypatch.setitem(
        namespace, "command", lambda *_args: pytest.fail("unverified runtime must not be stopped")
    )

    assert adapter["_stop_owned_json"]("GPTOSS", 303) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "wrong model identity" in output.err


def test_stop_owned_json_delegates_to_stop_owned_started(
    adapter: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """stop-owned-json calls stop_owned() and emits STOPPED for an owned runtime."""
    calls: list[Any] = []

    def fake_stop_owned(result: Any) -> bool:
        calls.append(result)
        return True  # simulates successful stop

    monkeypatch.setitem(adapter["_stop_owned_json"].__globals__, "stop_owned", fake_stop_owned)
    import io

    buf = io.StringIO()
    monkeypatch.setattr("sys.stdout", buf)
    rc = adapter["_stop_owned_json"]("GENERAL", 12345)

    assert rc == 0
    assert len(calls) == 1
    assert calls[0].ownership == "STARTED"
    assert calls[0].expected_profile == "GENERAL"
    assert calls[0].expected_pid == 12345

    doc = json.loads(buf.getvalue())
    assert doc["api_version"] == 1
    assert doc["operation"] == "stop_owned"
    assert doc["result"] == "STOPPED"
    assert doc["profile"] == "GENERAL"
    assert doc["pid"] == 12345


def test_stop_owned_json_not_owned_or_replaced(
    adapter: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """stop-owned-json emits NOT_OWNED_OR_REPLACED when stop_owned() returns False."""
    monkeypatch.setitem(
        adapter["_stop_owned_json"].__globals__, "stop_owned", lambda _result: False
    )
    import io

    buf = io.StringIO()
    monkeypatch.setattr("sys.stdout", buf)
    rc = adapter["_stop_owned_json"]("CODE", 9999)

    assert rc == 0
    doc = json.loads(buf.getvalue())
    assert doc["result"] == "NOT_OWNED_OR_REPLACED"
    assert doc["profile"] == "CODE"
    assert doc["pid"] == 9999


def test_stop_owned_json_patch_alias_resolves_to_gptoss(
    adapter: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """PATCH alias is resolved to GPTOSS before calling stop_owned()."""
    calls: list[Any] = []

    def fake_stop_owned(result: Any) -> bool:
        calls.append(result)
        return True

    monkeypatch.setitem(adapter["_stop_owned_json"].__globals__, "stop_owned", fake_stop_owned)
    import io

    buf = io.StringIO()
    monkeypatch.setattr("sys.stdout", buf)
    rc = adapter["_stop_owned_json"]("PATCH", 303)

    assert rc == 0
    assert calls[0].expected_profile == "GPTOSS"
    doc = json.loads(buf.getvalue())
    assert doc["profile"] == "GPTOSS"


def test_stop_owned_json_unsupported_profile_exits_2(
    adapter: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unknown profile returns exit 2, no JSON on stdout."""
    import io

    out = io.StringIO()
    err = io.StringIO()
    monkeypatch.setattr("sys.stdout", out)
    monkeypatch.setattr("sys.stderr", err)
    rc = adapter["_stop_owned_json"]("BOGUS", 1)

    assert rc == 2
    assert out.getvalue().strip() == ""


def test_stop_owned_json_switch_error_exits_nonzero_no_json(
    adapter: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """SwitchError from stop_owned() → non-zero exit, empty stdout."""
    monkeypatch.setitem(
        adapter["_stop_owned_json"].__globals__,
        "stop_owned",
        lambda _result: (_ for _ in ()).throw(
            adapter["SwitchError"]("listener changed before stop")
        ),
    )
    import io

    out = io.StringIO()
    err = io.StringIO()
    monkeypatch.setattr("sys.stdout", out)
    monkeypatch.setattr("sys.stderr", err)
    rc = adapter["_stop_owned_json"]("GENERAL", 1)

    assert rc == 1
    assert out.getvalue().strip() == ""
    assert err.getvalue().strip() != ""


# --- Replacement / disappeared PID semantics (delegate to stop_owned) ---


def test_stop_owned_json_replacement_same_profile_preserved(
    adapter: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """stop_owned() returns False if a different PID is now running → NOT_OWNED_OR_REPLACED."""
    monkeypatch.setitem(adapter["_stop_owned_json"].__globals__, "stop_owned", lambda _r: False)
    import io

    buf = io.StringIO()
    monkeypatch.setattr("sys.stdout", buf)
    rc = adapter["_stop_owned_json"]("GENERAL", 100)

    assert rc == 0
    doc = json.loads(buf.getvalue())
    assert doc["result"] == "NOT_OWNED_OR_REPLACED"


def test_stop_owned_json_disappeared_owned_pid_is_safe_noop(
    adapter: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """If owned PID has already exited, stop_owned() returns False → NOT_OWNED_OR_REPLACED."""
    monkeypatch.setitem(adapter["_stop_owned_json"].__globals__, "stop_owned", lambda _r: False)
    import io

    buf = io.StringIO()
    monkeypatch.setattr("sys.stdout", buf)
    rc = adapter["_stop_owned_json"]("CODE", 555)

    assert rc == 0
    doc = json.loads(buf.getvalue())
    assert doc["result"] == "NOT_OWNED_OR_REPLACED"


# --- API version constant ---


def test_machine_api_version_is_1(adapter: dict[str, Any]) -> None:
    """The versioned constant must be 1 for the initial stable API."""
    assert adapter["_MACHINE_API_VERSION"] == 1


# --- Human CLI compatibility ---


def test_human_cli_still_produces_readable_output(
    adapter: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Human-readable CLI (positional target) output format is unchanged."""
    switch_result = _make_switch_result(adapter, "GENERAL", 42, "STARTED")
    namespace = adapter["main"].__globals__
    import io

    out = io.StringIO()
    monkeypatch.setattr("sys.stdout", out)
    monkeypatch.setattr("sys.argv", ["pi-model", "GENERAL"])
    monkeypatch.setitem(namespace, "switch", lambda target, **_kw: switch_result)
    monkeypatch.setitem(namespace, "normalize_target", lambda r: r.upper())
    monkeypatch.setitem(namespace, "validate_catalog_entry", lambda _: None)

    rc = adapter["main"]()
    output = out.getvalue().strip()

    assert rc == 0
    # Human output is not JSON.
    with pytest.raises((json.JSONDecodeError, ValueError)):
        json.loads(output)
    # Human output contains recognisable tokens.
    assert "READY" in output
    assert "pid=42" in output

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
    monkeypatch.setitem(namespace, "switch_lock", nullcontext)
    monkeypatch.setitem(namespace, "scan", lambda: next(snapshots))
    monkeypatch.setitem(
        namespace, "command", lambda name, action, **kwargs: actions.append((name, action))
    )
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

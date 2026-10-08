"""Regression gate tests for authority, projections, and ownership boundaries."""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load_gate() -> ModuleType:
    path = ROOT / "scripts/llm-regression-gate"
    loader = SourceFileLoader("neuralengine_llm_regression_gate_tests", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    loader.exec_module(module)
    return module


GATE = _load_gate()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    files = (
        "llm-manifest.json",
        "scripts/llm",
        "scripts/validate-llm-manifest",
        "scripts/llm-regression-gate",
        "scripts/sync-llm-client-projections",
        "scripts/qwen-role.fish",
        "scripts/opencode-watch",
        "integrations/pi/extensions/local-model-projection.ts",
        ".qwen/settings.json",
        ".pi/settings.json",
    )
    for relative in files:
        source = ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return root


def _report(root: Path) -> tuple[dict[str, Any], int]:
    return cast(tuple[dict[str, Any], int], GATE.evaluate(root, repo_only=True))


def _read(root: Path, relative: str) -> dict[str, Any]:
    path = root / relative
    return cast(dict[str, Any], json.loads(path.read_text()))


def _write(root: Path, relative: str, value: dict[str, Any]) -> None:
    (root / relative).write_text(json.dumps(value, indent=2))


def test_current_repository_contract_passes_repo_only(repo: Path) -> None:
    report, exit_code = _report(repo)
    assert exit_code == 0
    assert report["status"] == "PASS"
    assert report["checks"]["MODEL_INVENTORY"]["status"] == "NOT_RUN"


def test_assignment_or_challenger_promotion_fails_role_schema(repo: Path) -> None:
    manifest = _read(repo, "llm-manifest.json")
    manifest["roles"]["LOCAL_GENERAL"]["assignment"] = "nemotron-q5"
    _write(repo, "llm-manifest.json", manifest)
    report, exit_code = _report(repo)
    assert exit_code == 1
    assert report["checks"]["ROLE_SCHEMA"]["status"] == "FAIL"


def test_qwen_route_drift_fails_client_projection(repo: Path) -> None:
    settings = _read(repo, ".qwen/settings.json")
    settings["modelProviders"]["openai"][0]["baseUrl"] = "http://127.0.0.1:19999/v1"
    _write(repo, ".qwen/settings.json", settings)
    report, exit_code = _report(repo)
    assert exit_code == 1
    assert report["checks"]["CLIENT_PROJECTION"]["status"] == "FAIL"


def test_pi_cloud_default_and_local_route_allowlist_are_both_required(repo: Path) -> None:
    settings = _read(repo, ".pi/settings.json")
    settings["enabledModels"] = ["deepseek/deepseek-flash"]
    _write(repo, ".pi/settings.json", settings)
    report, exit_code = _report(repo)
    assert exit_code == 1
    assert report["checks"]["CLIENT_PROJECTION"]["status"] == "FAIL"
    settings["enabledModels"].append("neuralengine-local/LOCAL_GENERAL")
    settings["defaultProvider"] = "neuralengine-local"
    settings["defaultModel"] = "LOCAL_GENERAL"
    _write(repo, ".pi/settings.json", settings)
    report, exit_code = _report(repo)
    assert exit_code == 1


def test_second_lifecycle_owner_is_rejected(repo: Path) -> None:
    path = repo / "scripts/qwen-role.fish"
    path.write_text(path.read_text() + "\nllm start general\n")
    report, exit_code = _report(repo)
    assert exit_code == 1
    assert report["checks"]["LIFECYCLE_OWNERSHIP"]["status"] == "FAIL"


def test_opencode_local_route_reactivation_is_rejected(repo: Path) -> None:
    _write(repo, "opencode.json", {"provider": {"llama-code": {"models": {}}}})
    report, exit_code = _report(repo)
    assert exit_code == 1
    assert report["checks"]["OPENCODE_PARKED"]["status"] == "FAIL"


def test_invalid_schema_returns_structured_error(repo: Path) -> None:
    manifest = _read(repo, "llm-manifest.json")
    manifest["schema_version"] = 1
    _write(repo, "llm-manifest.json", manifest)
    report, exit_code = _report(repo)
    assert exit_code == 2
    assert report["status"] == "ERROR"
    assert report["findings"]


def test_lifecycle_owner_drift_is_contract_failure(repo: Path) -> None:
    manifest = _read(repo, "llm-manifest.json")
    manifest["runtime_manager"] = "pi"
    _write(repo, "llm-manifest.json", manifest)
    report, exit_code = _report(repo)
    assert exit_code == 1
    assert report["findings"]


def test_primary_harness_drift_is_contract_failure(repo: Path) -> None:
    manifest = _read(repo, "llm-manifest.json")
    manifest["client_harness"]["primary_local_harness"] = "Qwen Code"
    _write(repo, "llm-manifest.json", manifest)
    report, exit_code = _report(repo)
    assert exit_code == 1
    assert any("primary local harness must be Pi" in item["message"] for item in report["findings"])


def test_fast_gate_is_static_and_does_not_launch_or_probe_network(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import socket
    import subprocess

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("repo-only regression gate performed a runtime or network probe")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    report, exit_code = _report(repo)
    assert exit_code == 0
    assert report["status"] == "PASS"

"""Contract tests for the static LLM regression gate."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import shutil
import socket
import subprocess
import sys
import urllib.request
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load_gate() -> ModuleType:
    path = ROOT / "scripts/llm-regression-gate"
    loader = SourceFileLoader("neuralengine_llm_regression_gate", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    loader.exec_module(module)
    return module


GATE = _load_gate()


def _copy_tree(source: Path, destination: Path) -> None:
    shutil.copytree(source, destination, dirs_exist_ok=True)


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Build an isolated active configuration and temporary host assets."""
    root = tmp_path / "repo"
    root.mkdir()
    for relative in (
        "scripts/llm",
        "scripts/validate-llm-manifest",
        "scripts/qwen-role.fish",
        "llm-manifest.json",
        "integrations/pi",
        "integrations/opencode/command-protocol",
        "control-plane/governor.ts",
        "docs/command-protocol",
        "docs/control-plane-governor.md",
        ".pi",
        ".qwen",
        "QWEN.md",
    ):
        source = ROOT / relative
        destination = root / relative
        if source.is_dir():
            _copy_tree(source, destination)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

    manifest_path = root / "llm-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    replacements: dict[str, str] = {}
    original_runtime = next(iter(manifest["roles"].values()))["runtime_binary"]
    runtime_build = root / "host-assets/runtime-build"
    runtime_path = runtime_build / "bin/llama-server"
    runtime_path.parent.mkdir(parents=True)
    runtime_path.write_bytes(b"runtime fixture")
    for role_name, role in manifest["roles"].items():
        model_path = root / "host-assets/models" / f"{role_name.lower()}.gguf"
        model_path.parent.mkdir(parents=True, exist_ok=True)
        model_path.write_bytes(f"asset for {role_name}".encode())
        replacements[role["model_path"]] = str(model_path)
        role["model_path"] = str(model_path)
        role["expected_v1_models_id"] = str(model_path)
        role["runtime_binary"] = str(runtime_path)
        role["runtime_build"] = str(runtime_build)
        if "mmproj_path" in role:
            mmproj_path = root / "host-assets/models" / f"{role_name.lower()}-projector.gguf"
            mmproj_path.write_bytes(b"auxiliary fixture")
            replacements[role["mmproj_path"]] = str(mmproj_path)
            role["mmproj_path"] = str(mmproj_path)
    manifest_path.write_text(json.dumps(manifest, indent=2))

    launcher_path = root / "scripts/llm"
    launcher = launcher_path.read_text()
    for old, new in replacements.items():
        launcher = launcher.replace(old, new)
    launcher = launcher.replace(original_runtime, str(runtime_path))
    launcher_path.write_text(launcher)

    relative_paths = (
        ".qwen/settings.json",
        "scripts/qwen-role.fish",
        *(str(path.relative_to(root)) for path in (root / ".qwen/agents").glob("*.md")),
    )
    for relative in relative_paths:
        path = root / relative
        contents = path.read_text()
        for old, new in replacements.items():
            contents = contents.replace(old, new)
        path.write_text(contents)
    qwen_path = root / ".qwen/settings.json"
    qwen = json.loads(qwen_path.read_text())
    for model in qwen["modelProviders"]["openai"]:
        role = next(
            item for item in manifest["roles"].values() if item["model_path"] == model["id"]
        )
        model["baseUrl"] = f"http://{role['host']}:{role['port']}/v1"
    qwen["model"]["name"] = manifest["roles"][manifest["clients"]["qwen"]["default_role"]][
        "model_path"
    ]
    qwen_path.write_text(json.dumps(qwen, indent=2))

    for variable in GATE.PATH_OVERRIDE_NAMES:
        monkeypatch.delenv(variable, raising=False)
    return root


def _report(root: Path, *, repo_only: bool = True) -> tuple[dict[str, Any], int]:
    return cast(tuple[dict[str, Any], int], GATE.evaluate(root, repo_only=repo_only))


def _manifest(root: Path) -> dict[str, Any]:
    path = root / "llm-manifest.json"
    return cast(dict[str, Any], json.loads(path.read_text()))


def _write_manifest(root: Path, manifest: dict[str, Any]) -> None:
    (root / "llm-manifest.json").write_text(json.dumps(manifest, indent=2))


def _status(report: dict[str, Any], check: str) -> str:
    return cast(str, report["checks"][check]["status"])


def _finding_codes(report: dict[str, Any]) -> set[str]:
    return {cast(str, finding["code"]) for finding in report["findings"]}


def _edit_json(path: Path, mutate: Any) -> dict[str, Any]:
    value = json.loads(path.read_text())
    mutate(value)
    path.write_text(json.dumps(value, indent=2))
    return cast(dict[str, Any], value)


def test_current_repository_contract_passes_repo_only(repo: Path) -> None:
    for path in (repo / "host-assets").rglob("*"):
        if path.is_file():
            path.unlink()
    report, status = _report(repo, repo_only=True)
    assert status == 0
    assert report["status"] == "PASS"
    assert report["scope"] == ["REPO_BOUND"]
    assert _status(report, "MODEL_INVENTORY") == "NOT_RUN"


def test_valid_local_host_inventory_passes(repo: Path) -> None:
    report, status = _report(repo, repo_only=False)
    assert status == 0
    assert report["scope"] == ["REPO_BOUND", "HOST_BOUND"]
    assert _status(report, "MODEL_INVENTORY") == "PASS"


@pytest.mark.parametrize("role", ["GENERAL", "CODE"])
def test_qwen_model_drift_fails_role_matrix(repo: Path, role: str) -> None:
    agent_name = {"GENERAL": "general", "CODE": "coder"}[role]
    path = repo / ".qwen/agents" / f"{agent_name}.md"
    path.write_text(path.read_text().replace('model: "openai:', 'model: "openai:/unknown/'))
    report, status = _report(repo)
    assert status == 1
    assert _status(report, "ROLE_MATRIX") == "FAIL"


def test_endpoint_drift_fails_endpoint_matrix(repo: Path) -> None:
    path = repo / ".qwen/settings.json"
    settings = json.loads(path.read_text())
    settings["modelProviders"]["openai"][0]["baseUrl"] = "https://example.invalid/v1"
    path.write_text(json.dumps(settings))
    report, status = _report(repo)
    assert status == 1
    assert _status(report, "ENDPOINT_MATRIX") == "FAIL"


def test_qwen_wrapper_endpoint_host_drift_fails(repo: Path) -> None:
    path = repo / "scripts/qwen-role.fish"
    path.write_text(path.read_text().replace("127.0.0.1:$port", "remote.example:$port"))
    report, status = _report(repo)
    assert status == 1
    assert _status(report, "ENDPOINT_MATRIX") == "FAIL"


def test_qwen_fallback_model_flag_fails_cloud_fallback_contract(repo: Path) -> None:
    path = repo / "scripts/qwen-role.fish"
    path.write_text(
        path.read_text().replace(
            "/home/grzanka/.local/bin/qwen --auth-type openai",
            "/home/grzanka/.local/bin/qwen --fallback-model remote:model --auth-type openai",
        )
    )
    report, status = _report(repo)
    assert status == 1
    assert "QWEN_CLOUD_FALLBACK_DRIFT" in _finding_codes(report)
    assert _status(report, "HOST_CONTRACT_CONFIG") == "FAIL"


def _replace_qwen_forwarded_guard(path: Path, replacement: str) -> None:
    source = path.read_text()
    start = source.index("        if string match -qr -- ")
    end_marker = "        end\n"
    end = source.index(end_marker, start) + len(end_marker)
    path.write_text(source[:start] + replacement + source[end:])


def test_valid_forwarded_guard_rejects_fallback_model(repo: Path) -> None:
    path = repo / "scripts/qwen-role.fish"
    report, status = _report(repo)
    assert status == 0
    assert "QWEN_CLOUD_FALLBACK_DRIFT" not in _finding_codes(report)
    assert GATE._forwarded_fallback_args_are_rejected(path.read_text())


def test_cloud_fallback_disabled_rejects_forwarded_fallback_model(repo: Path) -> None:
    path = repo / "scripts/qwen-role.fish"
    source = path.read_text()
    mutated = source.replace("--fallback-?model|", "--no-fallback-?model|", 1)
    assert mutated != source
    path.write_text(mutated)
    report, status = _report(repo)
    assert status == 1
    assert "QWEN_CLOUD_FALLBACK_DRIFT" in _finding_codes(report)
    assert _status(report, "HOST_CONTRACT_CONFIG") == "FAIL"


def test_qwen_fallback_guard_comment_does_not_count_as_proof(repo: Path) -> None:
    path = repo / "scripts/qwen-role.fish"
    _replace_qwen_forwarded_guard(
        path,
        "        # string match -qr -- '^--fallback-?model$' (string lower -- \"$arg\")\n"
        '        if test -z "$arg"\n'
        "            continue\n"
        "        end\n",
    )
    report, status = _report(repo)
    assert status == 1
    assert "QWEN_CLOUD_FALLBACK_DRIFT" in _finding_codes(report)


def test_qwen_fallback_mention_without_rejection_does_not_count(repo: Path) -> None:
    path = repo / "scripts/qwen-role.fish"
    _replace_qwen_forwarded_guard(
        path,
        '        if test "$arg" = "--help"\n'
        "            echo 'Example: --fallback-model remote:model'\n"
        "            return 2\n"
        "        end\n",
    )
    report, status = _report(repo)
    assert status == 1
    assert "QWEN_CLOUD_FALLBACK_DRIFT" in _finding_codes(report)


def test_forwarded_fallback_guard_requirement_follows_manifest_authority(repo: Path) -> None:
    manifest = _manifest(repo)
    manifest["clients"]["qwen"]["cloud_fallback"] = True
    _write_manifest(repo, manifest)
    path = repo / "scripts/qwen-role.fish"
    _replace_qwen_forwarded_guard(path, '        if test -z "$arg"\n        end\n')
    report, status = _report(repo)
    assert status == 0
    assert "QWEN_CLOUD_FALLBACK_DRIFT" not in _finding_codes(report)


@pytest.mark.parametrize(("alias", "expected_role"), [("qg", "GENERAL"), ("qc", "CODE")])
def test_qwen_public_shortcut_keeps_its_role_binding(
    repo: Path, alias: str, expected_role: str
) -> None:
    report, status = _report(repo)
    assert status == 0
    assert "QWEN_SHORTCUT_ROLE_DRIFT" not in _finding_codes(report)
    wrapper = (repo / "scripts/qwen-role.fish").read_text()
    assert f"function {alias} " in wrapper
    assert f"__qwen_profile_run {expected_role} " in wrapper


def test_swapped_qwen_public_shortcut_roles_fail(repo: Path) -> None:
    path = repo / "scripts/qwen-role.fish"
    wrapper = path.read_text()
    qg = re.search(r"(?ms)^function qg\b[^\n]*\n(?P<body>.*?)^end\s*$", wrapper)
    qc = re.search(r"(?ms)^function qc\b[^\n]*\n(?P<body>.*?)^end\s*$", wrapper)
    assert qg is not None and qc is not None
    qg_body, qc_body = qg.group("body"), qc.group("body")
    wrapper = (
        wrapper.replace(qg_body, "\0", 1).replace(qc_body, qg_body, 1).replace("\0", qc_body, 1)
    )
    path.write_text(wrapper)
    report, status = _report(repo)
    assert status == 1
    assert "QWEN_SHORTCUT_ROLE_DRIFT" in _finding_codes(report)
    assert _status(report, "ROLE_MATRIX") == "FAIL"


def test_pi_local_routing_reintroduced_fails(repo: Path) -> None:
    manifest = _manifest(repo)
    local_role = next(iter(manifest["roles"].values()))
    path = repo / ".pi/settings.json"
    settings = json.loads(path.read_text())
    settings["defaultModel"] = local_role["model_path"]
    settings["enabledModels"] = [f"openai/{local_role['model_path']}"]
    path.write_text(json.dumps(settings))
    report, status = _report(repo)
    assert status == 1
    assert _status(report, "HOST_CONTRACT_CONFIG") == "FAIL"
    assert _status(report, "ACTIVE_REFERENCE_RESOLUTION") == "FAIL"


def test_qwen_cloud_route_reintroduced_fails(repo: Path) -> None:
    path = repo / ".qwen/settings.json"
    settings = json.loads(path.read_text())
    settings["modelProviders"]["remote"] = [
        {"id": "unregistered-cloud-model", "baseUrl": "https://example.invalid/v1"}
    ]
    path.write_text(json.dumps(settings))
    report, status = _report(repo)
    assert status == 1
    assert _status(report, "HOST_CONTRACT_CONFIG") == "FAIL"
    assert _status(report, "ACTIVE_REFERENCE_RESOLUTION") == "FAIL"


def test_second_active_lifecycle_manager_fails(repo: Path) -> None:
    extension = repo / ".pi/extensions/second-manager.ts"
    extension.write_text('import { spawn } from "node:child_process"; spawn("llama-server");\n')
    report, status = _report(repo)
    assert status == 1
    assert _status(report, "LIFECYCLE_CONFIG") == "FAIL"


@pytest.mark.parametrize("command", ["start", "switch", "stop"])
def test_active_pi_extension_cannot_invoke_llm_lifecycle(repo: Path, command: str) -> None:
    extension = repo / ".pi/extensions/second-manager.ts"
    extension.write_text(
        'import { execFileSync } from "node:child_process";\n'
        f'execFileSync("llm", ["{command}", "general"]);\n'
    )
    report, status = _report(repo)
    assert status == 1
    assert "PI_LOCAL_LIFECYCLE_DRIFT" in _finding_codes(report)
    assert _status(report, "LIFECYCLE_CONFIG") == "FAIL"


def test_pi_lifecycle_in_retired_fixture_is_not_scanned(repo: Path) -> None:
    retired = repo / "tests/fixtures/retired_pi/old-extension.ts"
    retired.parent.mkdir(parents=True)
    retired.write_text(
        'import { execFileSync } from "node:child_process";\n'
        'execFileSync("llm", ["start", "general"]);\n'
    )
    report, status = _report(repo)
    assert status == 0
    assert "PI_LOCAL_LIFECYCLE_DRIFT" not in _finding_codes(report)


def test_pi_lifecycle_comments_are_not_treated_as_active_code(repo: Path) -> None:
    extension = repo / ".pi/extensions/commented-manager.ts"
    extension.write_text(
        '// execFileSync("llm", ["start", "general"]);\n'
        'const note = "lifecycle stays in scripts/llm";\n'
    )
    report, status = _report(repo)
    assert status == 0
    assert "PI_LOCAL_LIFECYCLE_DRIFT" not in _finding_codes(report)


def test_pi_deepseek_enforcer_destination_drift_fails(repo: Path) -> None:
    path = repo / "integrations/pi/manifest.json"
    integration = json.loads(path.read_text())
    enforcer = next(item for item in integration["resources"] if item["name"] == "deepseek-only")
    enforcer["destination"] = "inactive/deepseek-only.ts"
    path.write_text(json.dumps(integration, indent=2))
    report, status = _report(repo)
    assert status == 1
    assert "PI_RESOURCE_DESTINATION_DRIFT" in _finding_codes(report)
    assert _status(report, "HOST_CONTRACT_CONFIG") == "FAIL"


@pytest.mark.parametrize("mode", ["--json", "text"])
def test_invalid_authoritative_endpoint_returns_structured_exit_two(
    repo: Path, mode: str, capsys: Any
) -> None:
    manifest = _manifest(repo)
    manifest["roles"]["GENERAL"]["port"] = 99999
    _write_manifest(repo, manifest)
    arguments = ["fast", "--repo-only"] + ([] if mode == "text" else [mode])
    assert GATE.main(arguments, repo_root=repo) == 2
    output = capsys.readouterr().out
    assert "Traceback" not in output
    if mode == "--json":
        result = json.loads(output)
        assert result["status"] == "ERROR"
        assert "INVALID_SCHEMA_OR_INPUT" in {finding["code"] for finding in result["findings"]}
    else:
        assert "ERROR" in output
        assert "INVALID_SCHEMA_OR_INPUT" in output


def test_invalid_derived_endpoint_is_contract_failure_without_traceback(
    repo: Path,
) -> None:
    path = repo / ".qwen/settings.json"
    settings = json.loads(path.read_text())
    settings["modelProviders"]["openai"][0]["baseUrl"] = "http://127.0.0.1:99999/v1"
    path.write_text(json.dumps(settings))
    report, status = _report(repo)
    assert status == 1
    assert report["status"] == "FAIL"
    assert _status(report, "ENDPOINT_MATRIX") == "FAIL"


def test_active_unknown_model_reference_fails(repo: Path) -> None:
    path = repo / ".qwen/settings.json"
    settings = json.loads(path.read_text())
    settings["modelProviders"]["openai"][0]["id"] = "unregistered-model"
    path.write_text(json.dumps(settings))
    report, status = _report(repo)
    assert status == 1
    assert _status(report, "ACTIVE_REFERENCE_RESOLUTION") == "FAIL"


def test_active_unknown_profile_reference_fails(repo: Path) -> None:
    path = repo / "scripts/qwen-role.fish"
    path.write_text(
        path.read_text().replace("__qwen_profile_run GENERAL", "__qwen_profile_run RETIRED")
    )
    report, status = _report(repo)
    assert status == 1
    assert _status(report, "ACTIVE_REFERENCE_RESOLUTION") == "FAIL"


def test_historical_unknown_references_are_ignored(repo: Path) -> None:
    retired = repo / ".qwen/retired-agents/old-unknown.md"
    retired.write_text('model: "provider:unregistered-retired-model"\nNEURALENGINE_ROLE=RETIRED\n')
    evidence = repo / "tests/fixtures/retired_pi/old-config.json"
    evidence.parent.mkdir(parents=True)
    evidence.write_text('{"model":"unregistered-historical-model"}')
    report, status = _report(repo)
    assert status == 0
    assert _status(report, "ACTIVE_REFERENCE_RESOLUTION") == "PASS"


def test_missing_command_protocol_binding_fails(repo: Path) -> None:
    (repo / "QWEN.md").write_text("# Adapter without protocol references\n")
    report, status = _report(repo)
    assert status == 1
    assert _status(report, "COMMAND_PROTOCOL_BINDING") == "FAIL"


def test_missing_guard_binding_fails(repo: Path) -> None:
    path = repo / "integrations/pi/manifest.json"
    manifest = json.loads(path.read_text())
    manifest["resources"] = [
        resource
        for resource in manifest["resources"]
        if resource.get("name") != "neuralengine-guard"
    ]
    path.write_text(json.dumps(manifest))
    report, status = _report(repo)
    assert status == 1
    assert _status(report, "GUARD_BINDING") == "FAIL"


def test_missing_model_asset_fails_host_inventory(repo: Path) -> None:
    manifest = _manifest(repo)
    Path(manifest["roles"]["GENERAL"]["model_path"]).unlink()
    report, status = _report(repo, repo_only=False)
    assert status == 1
    assert _status(report, "MODEL_INVENTORY") == "FAIL"


@pytest.mark.parametrize("asset_kind", ["empty", "directory", "symlink"])
def test_model_inventory_requires_nonempty_regular_assets(repo: Path, asset_kind: str) -> None:
    manifest = _manifest(repo)
    asset = Path(manifest["roles"]["GENERAL"]["model_path"])
    asset.unlink()
    if asset_kind == "empty":
        asset.touch()
    elif asset_kind == "directory":
        asset.mkdir()
    else:
        target = asset.with_suffix(".target")
        target.write_bytes(b"target")
        asset.symlink_to(target)
    report, status = _report(repo, repo_only=False)
    assert status == 1
    assert _status(report, "MODEL_INVENTORY") == "FAIL"


def test_model_inventory_derives_projector_requirement_from_contract(repo: Path) -> None:
    manifest = _manifest(repo)
    role = next(value for value in manifest["roles"].values() if "mmproj_path" in value)
    Path(role["mmproj_path"]).unlink()
    report, status = _report(repo, repo_only=False)
    assert status == 1
    assert _status(report, "MODEL_INVENTORY") == "FAIL"


def test_repo_only_passes_without_any_model_assets(repo: Path) -> None:
    for path in (repo / "host-assets").rglob("*"):
        if path.is_file():
            path.unlink()
    report, status = _report(repo, repo_only=True)
    assert status == 0
    assert _status(report, "MODEL_INVENTORY") == "NOT_RUN"


def test_json_output_order_is_deterministic(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(GATE.time, "perf_counter_ns", lambda: 1_000_000)
    first, first_code = _report(repo)
    second, second_code = _report(repo)
    assert first_code == second_code == 0
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert list(first["checks"]) == [name for name, _ in GATE.CHECKS]
    assert set(first) >= {"status", "mode", "scope", "duration_ms", "checks", "findings"}
    assert all(set(check) >= {"type", "status"} for check in first["checks"].values())


def test_exit_codes_distinguish_pass_contract_fail_and_invalid_input(
    repo: Path, capsys: Any
) -> None:
    assert GATE.main(["fast", "--repo-only", "--json"], repo_root=repo) == 0
    path = repo / ".pi/settings.json"
    settings = json.loads(path.read_text())
    settings["defaultModel"] = "unknown-model"
    path.write_text(json.dumps(settings))
    assert GATE.main(["fast", "--repo-only"], repo_root=repo) == 1
    manifest = _manifest(repo)
    manifest["schema_version"] = 99
    _write_manifest(repo, manifest)
    assert GATE.main(["fast", "--repo-only", "--json"], repo_root=repo) == 2
    assert "INVALID_SCHEMA_OR_INPUT" in capsys.readouterr().out


def test_infrastructure_error_uses_exit_code_three(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = GATE._load_json

    def broken(path: Path) -> dict[str, Any]:
        if path.name == "llm-manifest.json":
            raise GATE.InfrastructureError("unreadable manifest")
        return cast(dict[str, Any], original(path))

    monkeypatch.setattr(GATE, "_load_json", broken)
    report, status = _report(repo)
    assert status == 3
    assert report["status"] == "ERROR"


def test_gate_never_starts_models_queries_network_or_creates_listeners(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("runtime or network operation attempted")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    protected = [
        repo / ".pi/settings.json",
        repo / ".qwen/settings.json",
        repo / "llm-manifest.json",
    ]
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in protected}
    report, status = _report(repo)
    after = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in protected}
    assert status == 0
    assert report["status"] == "PASS"
    assert before == after

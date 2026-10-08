"""Manifest authority, route projection, and context-layer contract tests."""

from __future__ import annotations

import importlib.util
import json
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load_module(path: Path, name: str) -> ModuleType:
    loader = SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    loader.exec_module(module)
    return module


def _manifest() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((ROOT / "llm-manifest.json").read_text()))


def _validate(manifest: dict[str, Any], tmp_path: Path | None = None) -> list[str]:
    path = ROOT / "llm-manifest.json"
    if tmp_path is not None:
        path = tmp_path / "llm-manifest.json"
        path.write_text(json.dumps(manifest, indent=2))
    validator = _load_module(
        ROOT / "scripts/validate-llm-manifest", "neuralengine_manifest_test_validator"
    )
    return cast(
        list[str],
        validator.validate(path, check_host=False, check_host_assets=False, repo_root=ROOT),
    )


def test_manifest_has_undecided_roles_and_separate_compatibility_profiles() -> None:
    manifest = _manifest()
    assert set(manifest["roles"]) == {"LOCAL_GENERAL", "LOCAL_CODE", "LOCAL_VISION"}
    assert all(role["assignment"] == "UNDECIDED" for role in manifest["roles"].values())
    assert manifest["roles"]["LOCAL_GENERAL"]["projection_status"] == (
        "CURRENT_DEPLOYMENT_COMPATIBILITY_ONLY"
    )
    assert manifest["roles"]["LOCAL_CODE"]["projection_status"] == (
        "QUALIFIED_LOCAL_CODE_CANONICAL"
    )
    assert manifest["roles"]["LOCAL_VISION"]["projection_status"] == (
        "CURRENT_DEPLOYMENT_COMPATIBILITY_ONLY"
    )
    assert "PATCH" not in manifest["roles"]
    assert manifest["challengers"]["qwen38"]["status"] == "QUALIFIED"
    assert manifest["challengers"]["qwen38"]["qualified_roles"] == ["LOCAL_CODE"]
    assert manifest["challengers"]["qwen38"]["eligible_for_role_assignment"] is True


def test_context_layers_are_explicit_and_capacity_bounded() -> None:
    manifest = _manifest()
    for profile in manifest["runtime_profiles"].values():
        layers = profile["context_layers"]
        assert set(layers) == {"model_max_ctx", "runtime_ctx", "slot_ctx", "client_effective_ctx"}
        model = manifest["models"][profile["model_ref"]]
        model_max = model["model_max_ctx"]["tokens"]
        assert layers["client_effective_ctx"] <= min(
            model_max, layers["runtime_ctx"], layers["slot_ctx"]
        )
    assert manifest["challengers"]["qwen38"]["qualification"]["R2.1_slot_ctx"] == 65536
    assert manifest["challengers"]["qwen38"]["qualification"]["R2.3"] == "NOT_RUN"
    assert manifest["challengers"]["qwen38"]["qualification"]["R4.1"] == "PASS"


def test_launcher_profiles_are_manifest_derived_and_runtime_is_not_started() -> None:
    launcher = _load_module(ROOT / "scripts/llm", "neuralengine_manifest_test_launcher")
    manifest = _manifest()
    bindings = {
        "current-general": launcher.DEFAULT_PROFILE,
        "current-code": launcher.DEFAULT_CODE_PROFILE,
        "current-qwen3-coder": launcher.DEFAULT_QWEN3_CODER_PROFILE,
        "current-vision": launcher.DEFAULT_VISION_PROFILE,
    }
    for profile_name, profile in manifest["runtime_profiles"].items():
        runtime_profile = bindings[profile_name]
        model = manifest["models"][profile["model_ref"]]
        endpoint = profile["endpoint"]
        assert str(runtime_profile.model) == model["artifact_path"]
        assert str(runtime_profile.runtime) == profile["runtime"]["binary"]
        assert (
            runtime_profile.endpoint()
            == f"http://{endpoint['host']}:{endpoint['port']}{endpoint['path']}"
        )
        assert runtime_profile.arguments()
    projection = launcher.project_role("LOCAL_CODE")
    assert projection["assignment"] == "UNDECIDED"
    assert projection["projection_status"] == "QUALIFIED_LOCAL_CODE_CANONICAL"
    assert projection["model_id"] == "qwen3.8-27b"
    assert projection["endpoint"] == "http://127.0.0.1:8731/v1"
    assert projection["slot_ctx"] == 65536
    assert projection["max_output_tokens"] == 16384


def test_manifest_validator_accepts_current_contract() -> None:
    assert _validate(_manifest()) == []


@pytest.mark.parametrize(
    "mutate,expected",
    [
        (
            lambda manifest: manifest["roles"].update({"PATCH": {"assignment": "UNDECIDED"}}),
            "exactly LOCAL_GENERAL",
        ),
        (
            lambda manifest: manifest["roles"]["LOCAL_GENERAL"].update(
                {"assignment": "nemotron-q5"}
            ),
            "must remain UNDECIDED",
        ),
        (
            lambda manifest: manifest["runtime_profiles"]["current-general"]["endpoint"].update(
                {"port": 19000}
            ),
            "endpoint does not match manifest",
        ),
        (
            lambda manifest: manifest["runtime_profiles"]["current-code"]["context_layers"].update(
                {"context": 32768}
            ),
            "context layer schema",
        ),
        (
            lambda manifest: manifest["runtime_profiles"]["current-vision"][
                "context_layers"
            ].update({"client_effective_ctx": 40000}),
            "exceeds a capacity layer",
        ),
        (
            lambda manifest: manifest["challengers"]["qwen38"].update({"status": "CHALLENGER"}),
            "qualification must be scoped",
        ),
    ],
)
def test_manifest_validator_rejects_contract_drift(
    tmp_path: Path, mutate: Any, expected: str
) -> None:
    manifest = _manifest()
    mutate(manifest)
    errors = _validate(manifest, tmp_path)
    assert any(expected in error for error in errors)


def test_manifest_validator_rejects_conflicting_runtime_argument_template(tmp_path: Path) -> None:
    manifest = _manifest()
    manifest["runtime_profiles"]["current-code"]["arguments"].append("--parallel")
    manifest["runtime_profiles"]["current-code"]["arguments"].append("2")
    errors = _validate(manifest, tmp_path)
    assert any("arguments are not manifest-derived" in error for error in errors)


def test_manifest_has_no_ambiguous_context_fields(tmp_path: Path) -> None:
    validator = _load_module(
        ROOT / "scripts/validate-llm-manifest", "neuralengine_manifest_context_test"
    )
    manifest = _manifest()
    manifest["runtime_profiles"]["current-general"]["context"] = 32768
    path = tmp_path / "ambiguous-context-fixture.json"
    path.write_text(json.dumps(manifest))
    errors = validator.validate(path, check_host=False, check_host_assets=False)
    assert any("ambiguous context" in error for error in errors)

"""The manifest detects operational drift without starting a model."""

from __future__ import annotations

import importlib.util
import json
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _validator() -> ModuleType:
    path = ROOT / "scripts/validate-llm-manifest"
    loader = SourceFileLoader("neuralengine_llm_manifest_validator", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    loader.exec_module(module)
    return module


@pytest.fixture
def validator(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """Independent profile oracle and temporary artifacts avoid host dependence."""
    module = _validator()
    profiles = []
    cache = tmp_path / "CMakeCache.txt"
    cache.write_text("GGML_VULKAN:BOOL=ON\nGGML_HIP:BOOL=OFF\nGGML_BACKEND_DL:BOOL=OFF\n")
    monkeypatch.setattr(Path, "is_file", lambda self: True)
    original_read_text = Path.read_text

    def read_text(path: Path, *args: Any, **kwargs: Any) -> str:
        if path.name == "CMakeCache.txt":
            return original_read_text(cache)
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read_text)
    manifest = json.loads((ROOT / "llm-manifest.json").read_text())
    for name, port, ubatch, fa in (
        ("GENERAL", 18081, 512, "auto"),
        ("CODE", 18080, 1024, "on"),
        ("VISION", 18082, 512, "auto"),
    ):
        role = manifest["roles"][name]
        args: tuple[str, ...] = (
            "-c",
            "32768",
            "-b",
            "2048",
            "-ub",
            str(ubatch),
            "-ngl",
            "999",
            "-dev",
            "Vulkan0",
            "-fa",
            fa,
            "--parallel",
            "1",
            "--jinja",
        )
        if name == "VISION":
            args += ("--reasoning", "off", "--mmproj", role["mmproj_path"])
        profiles.append(
            SimpleNamespace(
                model=Path(role["model_path"]),
                runtime=Path(role["runtime_binary"]),
                host="127.0.0.1",
                port=port,
                arguments=lambda args=args: args,
            )
        )
    monkeypatch.setattr(
        module,
        "_load_script",
        lambda *_: SimpleNamespace(
            DEFAULT_PROFILE=profiles[0],
            DEFAULT_CODE_PROFILE=profiles[1],
            DEFAULT_VISION_PROFILE=profiles[2],
        ),
    )
    return module


def test_manifest_matches_authorized_profiles(validator: ModuleType) -> None:
    assert validator.validate(ROOT / "llm-manifest.json", check_host=False) == []


@pytest.mark.parametrize("role", ["GENERAL", "CODE", "VISION"])
@pytest.mark.parametrize("field,value", [("port", 19000), ("context", 16384), ("ubatch", 1)])
def test_validator_detects_role_drift(
    validator: ModuleType, tmp_path: Path, role: str, field: str, value: int
) -> None:
    altered = json.loads((ROOT / "llm-manifest.json").read_text())
    altered["roles"][role][field] = value
    path = tmp_path / "drift.json"
    path.write_text(json.dumps(altered))
    assert any(
        role in error and field in error for error in validator.validate(path, check_host=False)
    )


@pytest.mark.parametrize("role", ["GENERAL", "CODE", "VISION"])
def test_validator_detects_model_path_drift(
    validator: ModuleType, tmp_path: Path, role: str
) -> None:
    altered = json.loads((ROOT / "llm-manifest.json").read_text())
    altered["roles"][role]["model_path"] = "/models/wrong.gguf"
    path = tmp_path / "drift.json"
    path.write_text(json.dumps(altered))
    assert any(f"{role} model" in error for error in validator.validate(path, check_host=False))


def test_validator_rejects_ambiguous_code_parallel() -> None:
    validator = _validator()
    errors: list[str] = []
    for args in (("--parallel", "2"), ("--parallel", "1", "--parallel", "2")):
        validator._expect_single_flag(
            errors, args, label="CODE --parallel", flag="--parallel", expected="1"
        )
    assert len(errors) == 2


def test_validator_rejects_duplicate_or_contradictory_jinja_toggle() -> None:
    validator = _validator()
    errors: list[str] = []
    for args in (("--jinja", "--jinja"), ("--jinja", "--no-jinja")):
        validator._expect_single_toggle(
            errors, args, label="CODE --jinja", enabled="--jinja", disabled="--no-jinja"
        )
    assert len(errors) == 2


def _client_fixture() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    roles = json.loads((ROOT / "llm-manifest.json").read_text())["roles"]
    pi = {"defaultProvider": "deepseek", "defaultModel": "deepseek-flash"}
    qwen = {
        "model": {"name": roles["GENERAL"]["model_path"]},
        "modelProviders": {
            "openai": [
                {
                    "id": role["model_path"],
                    "baseUrl": f"http://127.0.0.1:{role['port']}/v1",
                    "generationConfig": {"contextWindowSize": 32768},
                }
                for role in roles.values()
            ]
        },
    }
    return roles, pi, qwen


def test_builtin_deepseek_without_local_catalog_is_valid() -> None:
    roles, pi, qwen = _client_fixture()
    errors: list[str] = []
    _validator()._validate_client_settings(errors, roles, {"providers": {}}, (pi,), (qwen,))
    assert errors == []


def test_cloud_qwen_and_local_pi_catalog_are_rejected() -> None:
    roles, pi, qwen = _client_fixture()
    qwen["modelProviders"]["deepseek"] = [{"id": "deepseek-flash"}]
    errors: list[str] = []
    _validator()._validate_client_settings(
        errors, roles, {"providers": {"local": {}}}, (pi,), (qwen,)
    )
    assert "Pi contains non-DeepSeek provider entries" in errors
    assert "Qwen contains cloud provider routing" in errors


def test_wrong_endpoint_or_context_is_rejected() -> None:
    roles, pi, qwen = _client_fixture()
    qwen["modelProviders"]["openai"][0]["baseUrl"] = "https://example.invalid/v1"
    qwen["modelProviders"]["openai"][1]["generationConfig"]["contextWindowSize"] = 1
    errors: list[str] = []
    _validator()._validate_client_settings(errors, roles, {"providers": {}}, (pi,), (qwen,))
    assert "Qwen local endpoint drift" in errors
    assert "Qwen local context drift" in errors


def test_cloud_advisor_or_auth_routing_is_rejected() -> None:
    roles, pi, qwen = _client_fixture()
    qwen["advisorModel"] = "cloud-model"
    qwen["security"] = {"auth": {"selectedType": "cloud"}}
    errors: list[str] = []
    _validator()._validate_client_settings(errors, roles, {"providers": {}}, (pi,), (qwen,))
    assert "Qwen auth routing drift" in errors
    assert "Qwen contains non-local advisor routing" in errors

"""The canonical manifest detects operational drift without starting a model."""

from __future__ import annotations

import importlib.util
import json
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import ModuleType

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


def test_host_manifest_matches_active_client_configuration() -> None:
    assert _validator().validate(ROOT / "llm-manifest.json") == []


def test_validator_detects_code_context_drift(tmp_path: Path) -> None:
    altered = json.loads((ROOT / "llm-manifest.json").read_text())
    altered["clients"]["pi_code_context"] = 16384
    path = tmp_path / "drift.json"
    path.write_text(json.dumps(altered))

    assert any("Pi CODE context" in error for error in _validator().validate(path))


def test_validator_rejects_ambiguous_code_parallel() -> None:
    validator = _validator()
    errors: list[str] = []
    validator._expect_single_flag(
        errors,
        ("--parallel", "2"),
        label="CODE --parallel",
        flag="--parallel",
        expected="1",
    )
    validator._expect_single_flag(
        errors,
        ("--parallel", "1", "--parallel", "2"),
        label="CODE --parallel",
        flag="--parallel",
        expected="1",
    )
    assert len(errors) == 2


def test_validator_rejects_duplicate_or_contradictory_jinja_toggle() -> None:
    validator = _validator()
    errors: list[str] = []
    validator._expect_single_toggle(
        errors,
        ("--jinja", "--jinja"),
        label="CODE --jinja",
        enabled="--jinja",
        disabled="--no-jinja",
    )
    validator._expect_single_toggle(
        errors,
        ("--jinja", "--no-jinja"),
        label="CODE --jinja",
        enabled="--jinja",
        disabled="--no-jinja",
    )
    assert len(errors) == 2


def test_validator_rejects_wrong_patch_sha(tmp_path: Path) -> None:
    altered = json.loads((ROOT / "llm-manifest.json").read_text())
    altered["roles"]["PATCH"]["model_sha256"] = "0" * 64
    path = tmp_path / "wrong-patch-sha.json"
    path.write_text(json.dumps(altered))

    assert any("PATCH expected SHA" in error for error in _validator().validate(path))

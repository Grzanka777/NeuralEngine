"""Production contract for Pi as the primary local/cloud harness."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]


def _manifest() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((ROOT / "llm-manifest.json").read_text()))


def test_primary_harness_boundary_is_explicit_and_role_neutral() -> None:
    manifest = _manifest()

    assert manifest["client_harness"] == {
        "primary_local_harness": "Pi",
        "qwen_code": "OPTIONAL_COMPATIBILITY_QWEN_SPECIALIST",
        "opencode": "PARKED",
    }
    assert all(role["assignment"] == "UNDECIDED" for role in manifest["roles"].values())

    pi = manifest["clients"]["pi"]
    assert pi["provider"] == "neuralengine-local"
    assert pi["cloud_default_provider"] == "deepseek"
    assert pi["cloud_default_model"] == "deepseek-flash"
    assert pi["local_profiles"] == [
        "current-code",
        "current-general",
        "current-qwen3-coder",
        "current-vision",
    ]


def test_pi_project_settings_enable_all_four_local_routes_without_cloud_drift() -> None:
    manifest = _manifest()
    settings = cast(dict[str, Any], json.loads((ROOT / ".pi/settings.json").read_text()))
    pi = manifest["clients"]["pi"]
    expected = {
        f"{pi['provider']}/{manifest['models'][manifest['runtime_profiles'][profile]['model_ref']]['model_id']}"
        for profile in pi["local_profiles"]
    }

    assert expected <= set(settings["enabledModels"])
    assert settings["defaultProvider"] == "deepseek"
    assert settings["defaultModel"] == "deepseek-flash"


def test_active_client_docs_keep_pi_primary_and_qwen_opencode_boundaries() -> None:
    sources = {
        relative: (ROOT / relative).read_text(encoding="utf-8")
        for relative in (
            "README.md",
            ".pi/README.md",
            ".pi/skills/local-models/SKILL.md",
            "QWEN.md",
            "docs/reproducible-baseline.md",
            "docs/llm-regression-gate.md",
            "integrations/pi/skills/command-protocol/SKILL.md",
        )
    }
    combined = "\n".join(sources.values())

    assert "PRIMARY_LOCAL_HARNESS=Pi" in combined
    assert "optional compatibility" in combined.lower()
    assert "OpenCode is parked" in combined
    assert "scripts/llm" in combined
    assert "Qwen Code and Pi are local clients" not in combined


def test_manifest_preserves_context_output_and_capability_metadata() -> None:
    manifest = _manifest()
    profiles = manifest["runtime_profiles"]
    expected = {
        "current-code": (65536, 16384, "chat"),
        "current-general": (32768, 4096, "chat"),
        "current-qwen3-coder": (32768, None, "chat"),
        "current-vision": (32768, 4096, "vision"),
    }
    for profile_name, (context, output, kind) in expected.items():
        profile = profiles[profile_name]
        model = manifest["models"][profile["model_ref"]]
        assert profile["context_layers"]["client_effective_ctx"] == context
        assert profile["max_output_tokens"] == output
        assert model["kind"] == kind

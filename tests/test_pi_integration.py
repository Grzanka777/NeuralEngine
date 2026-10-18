from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

REPOSITORY_ROOT = Path(__file__).parents[1]
PI_ROOT = REPOSITORY_ROOT / ".pi"
COMMANDS = (
    "arch",
    "checkpoint",
    "fix",
    "kill",
    "next",
    "optimize",
    "recheck",
    "research",
    "seek",
    "ship",
)

GENERAL_MODEL = "Qwen3.6"
CODE_MODEL = "Nemotron Q5"
PATCH_MODEL = "GPT-OSS"
ROLE_SKILL = PI_ROOT / "skills/neuralengine-roles/SKILL.md"
FORBIDDEN_PROVIDERS = ("openai", "openai-codex", "google", "anthropic")
SECRET_MARKERS = (
    "sk-",
    "AIza",
    "ghp_",
    "xoxb-",
    "-----BEGIN",
    "api_key=",
    "apikey=",
    "password=",
    "secret=",
)


def _settings() -> dict[str, Any]:
    raw = json.loads((PI_ROOT / "settings.json").read_text(encoding="utf-8"))
    return cast("dict[str, Any]", raw)


def _role_line(text: str, role: str) -> str:
    return next(line for line in text.splitlines() if line.strip().startswith(f"| {role} "))


def test_pi_project_settings_select_local_general_and_existing_adapters() -> None:
    settings = _settings()

    assert "enabledModels" not in settings
    assert settings["defaultProvider"] == "neural-general"
    assert GENERAL_MODEL in settings["defaultModel"]
    assert settings["extensions"] == ["extensions/neuralengine-guard.ts"]
    assert settings["skills"] == [
        "skills/neuralengine-development",
        "skills/neuralengine-roles",
        "skills/local-models",
    ]
    assert settings["prompts"] == ["prompts"]

    assert (PI_ROOT / "extensions/neuralengine-guard.ts").is_file()
    assert (PI_ROOT / "skills/neuralengine-development/SKILL.md").is_file()
    assert ROLE_SKILL.is_file()
    assert (REPOSITORY_ROOT / ".claude/skills/neuralengine/SKILL.md").is_file()
    assert (REPOSITORY_ROOT / "integrations/opencode/command-protocol/SKILL.md").is_file()


def test_pi_project_prompt_inventory_is_complete() -> None:
    prompt_root = PI_ROOT / "prompts"

    assert tuple(sorted(path.stem for path in prompt_root.glob("*.md"))) == tuple(
        sorted((*COMMANDS, "review", "reviewer"))
    )

    for command in COMMANDS:
        assert (prompt_root / f"{command}.md").is_file()


def test_pi_project_has_no_automatic_cloud_fallback() -> None:
    settings = _settings()
    assert settings["defaultProvider"] not in FORBIDDEN_PROVIDERS
    append_system = (PI_ROOT / "APPEND_SYSTEM.md").read_text(encoding="utf-8")
    assert "Cloud escalation is explicit" in append_system
    assert "no automatic cloud fallback" in append_system


def test_pi_role_skill_maps_local_capabilities() -> None:
    text = ROLE_SKILL.read_text(encoding="utf-8")
    assert GENERAL_MODEL in _role_line(text, "GENERAL")
    assert CODE_MODEL in _role_line(text, "CODE")
    assert PATCH_MODEL in _role_line(text, "PATCH")
    assert "UNFILLED" in _role_line(text, "VISION")
    assert "workflow overlays on GENERAL" in text


def test_pi_append_system_declares_policy_and_roles() -> None:
    text = (PI_ROOT / "APPEND_SYSTEM.md").read_text(encoding="utf-8")
    for marker in (
        "1.0.0",
        GENERAL_MODEL,
        CODE_MODEL,
        PATCH_MODEL,
        "Command Protocol",
        "defense in depth",
        "authorization",
        "confirmation cannot bypass",
        "session-owned",
    ):
        assert marker in text


def test_pi_docs_describe_distribution_and_explicit_cloud_escalation() -> None:
    text = (REPOSITORY_ROOT / "docs/pi-integration.md").read_text(encoding="utf-8")
    for marker in (
        "1.0.0",
        GENERAL_MODEL,
        CODE_MODEL,
        PATCH_MODEL,
        "auth.json",
        "models-store.json",
        "automatic",
        "integrations/pi/manifest.json",
        "~/.pi/agent/",
        "PROJECT_LOCAL",
        "two identity revalidations",
    ):
        assert marker in text


def test_pi_guard_is_a_tool_call_guard_with_no_provider_or_brain_writer() -> None:
    guard = (PI_ROOT / "extensions/neuralengine-guard.ts").read_text(encoding="utf-8")

    assert 'pi.on("tool_call"' in guard
    assert "classifyProtectedCommand" in guard
    assert "git" in guard
    assert "neural" in guard
    assert "sudo" in guard
    assert "rm" in guard
    assert "auth.json" not in guard
    assert "OPENAI_API_KEY" not in guard
    assert "GEMINI_API_KEY" not in guard
    assert "DEEPSEEK_API_KEY" not in guard


def test_pi_project_configuration_introduces_no_credentials_or_secrets() -> None:
    config_paths = (
        PI_ROOT / "settings.json",
        PI_ROOT / "APPEND_SYSTEM.md",
        PI_ROOT / "extensions/neuralengine-guard.ts",
        PI_ROOT / "skills/neuralengine-development/SKILL.md",
        ROLE_SKILL,
    )

    for path in config_paths:
        text = path.read_text(encoding="utf-8")
        for marker in SECRET_MARKERS:
            assert marker not in text, f"unexpected secret-like {marker!r} in {path}"

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

FLASH_MODEL = "deepseek/deepseek-flash"
PRO_MODEL = "deepseek/deepseek-v4-pro"
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


def test_pi_project_settings_are_deepseek_only_and_reference_existing_adapters() -> None:
    settings = _settings()

    assert settings["enabledModels"] == ["deepseek/*"]
    assert settings["extensions"] == ["extensions/neuralengine-guard.ts"]
    assert settings["skills"] == [
        "skills/neuralengine-development",
        "skills/neuralengine-roles",
        "../integrations/opencode/command-protocol",
    ]
    assert settings["prompts"] == ["../integrations/opencode/command-protocol/commands"]

    assert (PI_ROOT / "extensions/neuralengine-guard.ts").is_file()
    assert (PI_ROOT / "skills/neuralengine-development/SKILL.md").is_file()
    assert ROLE_SKILL.is_file()
    assert (REPOSITORY_ROOT / ".claude/skills/neuralengine/SKILL.md").is_file()
    assert (REPOSITORY_ROOT / "integrations/opencode/command-protocol/SKILL.md").is_file()


def test_pi_reuses_the_existing_command_protocol_prompt_inventory() -> None:
    prompt_root = REPOSITORY_ROOT / "integrations/opencode/command-protocol/commands"

    assert tuple(sorted(path.stem for path in prompt_root.glob("*.md"))) == COMMANDS

    for command in COMMANDS:
        assert (prompt_root / f"{command}.md").is_file()


def test_pi_project_settings_do_not_allow_other_providers() -> None:
    enabled = " ".join(_settings()["enabledModels"])

    for provider in FORBIDDEN_PROVIDERS:
        assert provider not in enabled

    append_system = (PI_ROOT / "APPEND_SYSTEM.md").read_text(encoding="utf-8")
    assert "DeepSeek-only" in append_system


def test_pi_role_skill_maps_flash_and_pro_models() -> None:
    text = ROLE_SKILL.read_text(encoding="utf-8")

    assert FLASH_MODEL in _role_line(text, "FLASH")
    assert PRO_MODEL in _role_line(text, "PRO")
    assert "FLASH" in text
    assert "PRO" in text


def test_pi_append_system_declares_policy_and_roles() -> None:
    append_system = (PI_ROOT / "APPEND_SYSTEM.md").read_text(encoding="utf-8")

    assert "1.0.0" in append_system
    assert "DeepSeek-only" in append_system
    assert FLASH_MODEL in append_system
    assert PRO_MODEL in append_system
    assert "Command Protocol" in append_system
    assert "defense in depth" in append_system
    assert "authorization" in append_system.lower()


def test_pi_docs_describe_deepseek_only_policy_and_role_split() -> None:
    docs = (REPOSITORY_ROOT / "docs/pi-integration.md").read_text(encoding="utf-8")

    assert "1.0.0" in docs
    assert "DeepSeek-only" in docs
    assert FLASH_MODEL in docs
    assert PRO_MODEL in docs
    assert "auth.json" in docs
    assert "models-store.json" in docs
    assert "automatic" in docs.lower()


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

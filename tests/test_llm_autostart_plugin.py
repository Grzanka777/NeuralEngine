from pathlib import Path

import pytest

PLUGIN_PATH = Path.home() / ".config" / "opencode" / "plugin" / "llm-autostart.js"


@pytest.mark.skipif(not PLUGIN_PATH.is_file(), reason="local OpenCode plugin is not installed")
def test_local_model_plugin_routes_through_llm_switch() -> None:
    source = PLUGIN_PATH.read_text(encoding="utf-8")

    assert 'Bun.spawnSync([LLM, "switch", role]' in source
    assert "Bun.spawnSync([LLM, role]" not in source
    assert '"llama-general/qwen3.6-general-local"' in source
    assert '"llama-code/qwen3-coder-local"' in source
    assert '"llama-vision/gemma4-vision-local"' in source

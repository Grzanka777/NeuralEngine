"""Exercise role wrappers without starting a real runtime or making API calls."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
MODELS = {
    "qg": ("GENERAL", "nemotron", "18081", "general"),
    "qc": ("CODE", "Qwen3-Coder", "18080", "coder"),
    "qv": ("VISION", "gemma", "18082", "vision"),
}


@pytest.fixture
def wrapper(tmp_path: Path) -> tuple[Path, Path]:
    if shutil.which("fish") is None:
        pytest.skip("fish unavailable")
    events = tmp_path / "events.jsonl"
    llm = tmp_path / "llm"
    qwen = tmp_path / "qwen"
    for path, body in (
        (
            llm,
            """import os, sys, json
from pathlib import Path
with Path(os.environ['EVENTS']).open('a') as f: f.write(json.dumps(['llm', *sys.argv[1:]])+'\\n')
if sys.argv[1]=='start':
 role=sys.argv[2].upper()
 print(role+' ALREADY READY' if os.environ.get('BORROWED') else role+' STARTED BY THIS INVOCATION')
 if not os.environ.get('BORROWED'): print('ownership: '+role+' pid=4242')
""",
        ),
        (
            qwen,
            """import os, sys, json
from pathlib import Path
with Path(os.environ['EVENTS']).open('a') as f: f.write(json.dumps(['qwen', *sys.argv[1:]])+'\\n')
sys.exit(int(os.environ.get('QWEN_EXIT','0')))
""",
        ),
    ):
        path.write_text("#!/usr/bin/env python3\n" + body)
        path.chmod(0o755)
    text = (REPO / "scripts/qwen-role.fish").read_text()
    text = text.replace("/home/grzanka/.local/bin/llm", str(llm))
    text = text.replace("/home/grzanka/.local/bin/qwen", str(qwen))
    text = text.replace("/home/grzanka/Work/NeuralEngine", str(REPO))
    source = tmp_path / "roles.fish"
    source.write_text(text)
    return source, events


def run_wrapper(
    wrapper: tuple[Path, Path], command: str, **extra: str
) -> tuple[subprocess.CompletedProcess[str], list[list[str]]]:
    source, events = wrapper
    result = subprocess.run(
        ["fish", "--no-config", "-c", f"source {source}; {command}"],
        env={**os.environ, "EVENTS": str(events), **extra},
        capture_output=True,
        text=True,
        check=False,
    )
    calls = (
        [json.loads(line) for line in events.read_text().splitlines()] if events.exists() else []
    )
    return result, calls


@pytest.mark.parametrize("command", MODELS)
def test_role_binds_model_endpoint_instructions_and_owned_stop(
    wrapper: tuple[Path, Path], command: str
) -> None:
    result, calls = run_wrapper(wrapper, command)
    assert result.returncode == 0, result.stderr
    role, model, port, _ = MODELS[command]
    assert calls[0] == ["llm", "start", role.lower()]
    qwen = calls[1]
    assert model in qwen[qwen.index("--model") + 1]
    assert qwen[qwen.index("--openai-base-url") + 1] == f"http://127.0.0.1:{port}/v1"
    instructions = qwen[qwen.index("--append-system-prompt") + 1]
    assert not instructions.startswith("---")
    assert f"NEURALENGINE_ROLE={role}" in instructions
    assert "canonical Command Protocol" in instructions
    assert calls[2] == ["llm", "stop", "--expected-profile", role, "--expected-pid", "4242"]


def test_borrowed_runtime_is_preserved(wrapper: tuple[Path, Path]) -> None:
    result, calls = run_wrapper(wrapper, "qg", BORROWED="1")
    assert result.returncode == 0
    assert len(calls) == 2


def test_qwen_failure_still_stops_owned_runtime(wrapper: tuple[Path, Path]) -> None:
    result, calls = run_wrapper(wrapper, "qc", QWEN_EXIT="7")
    assert result.returncode == 7
    assert calls[-1][1] == "stop"


@pytest.mark.parametrize(
    "override",
    [
        "--model cloud",
        "--fallbackModel cloud",
        "--appendSystemPrompt escape",
        "--openaiBaseUrl https://example.org",
        "-mcloud",
        "--fallback-model cloud",
        "--openai-base-url https://example.org",
        "--append-system-prompt escape",
        "--advisor cloud",
        "--safe-mode",
    ],
)
def test_routing_override_fails_before_runtime(wrapper: tuple[Path, Path], override: str) -> None:
    result, calls = run_wrapper(wrapper, f"qg {override}")
    assert result.returncode == 2
    assert calls == []


def test_project_catalog_contains_only_local_roles() -> None:
    settings = json.loads((REPO / ".qwen/settings.json").read_text())
    providers = settings["modelProviders"]
    assert set(providers) == {"openai"}
    assert {model["name"] for model in providers["openai"]} == {
        "local-general",
        "local-code",
        "local-vision",
    }
    assert all(model["baseUrl"].startswith("http://127.0.0.1:") for model in providers["openai"])


def test_vision_catalog_explicitly_accepts_images() -> None:
    """Gemma is not recognized by Qwen's name-based modality inference."""
    settings = json.loads((REPO / ".qwen/settings.json").read_text())
    models = {model["name"]: model for model in settings["modelProviders"]["openai"]}
    assert models["local-vision"]["generationConfig"]["modalities"] == {"image": True}
    for role in ("local-general", "local-code"):
        assert not models[role]["generationConfig"].get("modalities", {}).get("image", False)

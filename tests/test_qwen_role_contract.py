"""Exercise Qwen role projections without starting runtimes or making requests."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((REPO / "llm-manifest.json").read_text())
ROUTES = {
    role: json.loads(
        subprocess.run(
            [str(REPO / "scripts/llm"), "project", "--role", role],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    )
    for role in MANIFEST["clients"]["qwen"]["local_roles"]
}


@pytest.fixture
def wrapper(tmp_path: Path) -> tuple[Path, Path]:
    if shutil.which("fish") is None:
        pytest.skip("fish unavailable")
    events = tmp_path / "events.jsonl"
    llm = tmp_path / "llm"
    qwen = tmp_path / "qwen"
    route_json = json.dumps(ROUTES)
    llm.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "with Path(os.environ['EVENTS']).open('a') as f:\n"
        " f.write(json.dumps(['llm', *sys.argv[1:]])+'\\n')\n"
        f"routes = json.loads({route_json!r})\n"
        "role=sys.argv[sys.argv.index('--role')+1]\n"
        "print(json.dumps(routes[role]))\n",
        encoding="utf-8",
    )
    qwen.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "with Path(os.environ['EVENTS']).open('a') as f:\n"
        " f.write(json.dumps(['qwen', *sys.argv[1:]])+'\\n')\n"
        "sys.exit(int(os.environ.get('QWEN_EXIT','0')))\n",
        encoding="utf-8",
    )
    for path in (llm, qwen):
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
        env={
            **os.environ,
            "EVENTS": str(events),
            "NEURALENGINE_ROOT": str(REPO),
            "NEURALENGINE_LLM": str(source.parent / "llm"),
            **extra,
        },
        capture_output=True,
        text=True,
        check=False,
    )
    calls = (
        [json.loads(line) for line in events.read_text().splitlines()] if events.exists() else []
    )
    return result, calls


@pytest.mark.parametrize(
    "command,role", [("qg", "LOCAL_GENERAL"), ("qc", "LOCAL_CODE"), ("qv", "LOCAL_VISION")]
)
def test_role_passes_manifest_route_and_instructions_without_lifecycle(
    wrapper: tuple[Path, Path], command: str, role: str
) -> None:
    result, calls = run_wrapper(wrapper, command)
    assert result.returncode == 0, result.stderr
    route = ROUTES[role]
    assert calls[0] == ["llm", "project", "--role", role]
    qwen = calls[1]
    assert qwen[qwen.index("--model") + 1] == route["model_id"]
    assert qwen[qwen.index("--openai-base-url") + 1] == route["endpoint"]
    instructions = qwen[qwen.index("--append-system-prompt") + 1]
    assert not instructions.startswith("---")
    assert f"NEURALENGINE_ROLE={role}" in instructions
    assert "canonical Command Protocol" not in instructions
    assert "Qwen owns no runtime lifecycle" in instructions
    assert len(calls) == 2


def test_qwen_failure_does_not_trigger_lifecycle(wrapper: tuple[Path, Path]) -> None:
    result, calls = run_wrapper(wrapper, "qc", QWEN_EXIT="7")
    assert result.returncode == 7
    assert len(calls) == 2
    assert all(call[0] != "llm" or call[1] == "project" for call in calls)


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
def test_routing_override_fails_before_manifest_projection(
    wrapper: tuple[Path, Path], override: str
) -> None:
    result, calls = run_wrapper(wrapper, f"qg {override}")
    assert result.returncode == 2
    assert calls == []


def test_project_catalog_is_manifest_derived() -> None:
    settings = json.loads((REPO / ".qwen/settings.json").read_text())
    providers = settings["modelProviders"]
    assert set(providers) == {"openai"}
    assert {model["name"] for model in providers["openai"]} == set(ROUTES)
    for model in providers["openai"]:
        route = ROUTES[model["name"]]
        assert model["id"] == route["model_id"]
        assert model["baseUrl"] == route["endpoint"]
        assert model["generationConfig"]["contextWindowSize"] == route["client_effective_ctx"]
        profile = MANIFEST["runtime_profiles"][
            MANIFEST["roles"][model["name"]]["current_deployment_profile"]
        ]
        assert model["generationConfig"]["maxTokens"] == profile["max_output_tokens"]


def test_vision_catalog_explicitly_accepts_images() -> None:
    settings = json.loads((REPO / ".qwen/settings.json").read_text())
    models = {model["name"]: model for model in settings["modelProviders"]["openai"]}
    assert models["LOCAL_VISION"]["generationConfig"]["modalities"] == {"image": True}
    for role in ("LOCAL_GENERAL", "LOCAL_CODE"):
        assert not models[role]["generationConfig"].get("modalities", {}).get("image", False)


def test_wrapper_source_contains_no_runtime_lifecycle_commands() -> None:
    source = (REPO / "scripts/qwen-role.fish").read_text()
    assert "llm start" not in source
    assert "llm stop" not in source
    assert "127.0.0.1:" not in source

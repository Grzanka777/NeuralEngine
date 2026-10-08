from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import cast

import pytest

SOURCE_LAUNCHER = Path(__file__).parents[1] / "scripts" / "pi.py"


def _fake_project(tmp_path: Path) -> tuple[Path, Path, Path]:
    root = tmp_path / "NeuralEngine"
    scripts = root / "scripts"
    pi_dir = root / ".pi"
    for directory in (
        scripts,
        pi_dir / "extensions",
        pi_dir / "skills",
        pi_dir / "prompts",
        root / "src" / "neural_engine",
        root / "tests",
    ):
        directory.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SOURCE_LAUNCHER, scripts / "pi.py")
    (pi_dir / "extensions" / "neuralengine-guard.ts").write_text("export default () => {};\n")
    (pi_dir / "skills" / "local-models.md").write_text("local models\n")
    (pi_dir / "prompts" / "review.md").write_text("review\n")
    (pi_dir / "settings.json").write_text(
        json.dumps(
            {
                "defaultProvider": "neural-general",
                "defaultModel": "/models/gguf/general.gguf",
                "defaultThinkingLevel": "off",
            }
        )
    )

    home = tmp_path / "home"
    pi_bin = home / ".local" / "bin"
    pi_bin.mkdir(parents=True)
    upstream = pi_bin / "pi.upstream"
    capture = tmp_path / "capture.json"
    upstream.write_text(
        f"#!{sys.executable}\n"
        "import json, os, pathlib, sys\n"
        "pathlib.Path(os.environ['PI_CAPTURE_FILE']).write_text(json.dumps({\n"
        "  'cwd': os.getcwd(), 'args': sys.argv[1:],\n"
        "  'project_root': os.environ.get('NEURALENGINE_PI_PROJECT_ROOT'),\n"
        "}))\n"
    )
    upstream.chmod(0o755)
    return root, home, capture


def _run_wrapper(
    root: Path,
    home: Path,
    capture: Path,
    cwd: Path,
    arguments: list[str],
    *,
    stale_root: str | None = None,
) -> dict[str, object]:
    env = os.environ.copy()
    env.update({"HOME": str(home), "PI_CAPTURE_FILE": str(capture)})
    if stale_root is not None:
        env["NEURALENGINE_PI_PROJECT_ROOT"] = stale_root
    result = subprocess.run(
        [sys.executable, str(root / "scripts" / "pi.py"), *arguments],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return cast(dict[str, object], json.loads(capture.read_text()))


def test_root_uses_pi_native_project_discovery_and_preserves_cwd(tmp_path: Path) -> None:
    root, home, capture = _fake_project(tmp_path)

    result = _run_wrapper(root, home, capture, root, [], stale_root="/tmp/stale-root")

    assert result == {"cwd": str(root), "args": [], "project_root": str(root)}


@pytest.mark.parametrize("relative_cwd", ("src", "tests", "src/neural_engine"))
def test_nested_directories_load_canonical_resources_without_changing_cwd(
    tmp_path: Path, relative_cwd: str
) -> None:
    root, home, capture = _fake_project(tmp_path)
    cwd = root / relative_cwd

    result = _run_wrapper(root, home, capture, cwd, [])

    assert result["cwd"] == str(cwd)
    assert result["project_root"] == str(root)
    args = result["args"]
    assert isinstance(args, list)
    assert args.count("--extension") == 1
    assert args[args.index("--extension") + 1] == str(
        root / ".pi" / "extensions" / "neuralengine-guard.ts"
    )
    assert args[args.index("--skill") + 1] == str(root / ".pi" / "skills")
    assert args[args.index("--prompt-template") + 1] == str(root / ".pi" / "prompts")
    assert args[args.index("--provider") + 1] == "neural-general"
    assert args[args.index("--model") + 1] == "/models/gguf/general.gguf"
    assert args[args.index("--thinking") + 1] == "off"
    assert list(root.rglob(".pi")) == [root / ".pi"]


def test_nested_user_model_override_wins_and_explicit_guard_is_not_duplicated(
    tmp_path: Path,
) -> None:
    root, home, capture = _fake_project(tmp_path)
    cwd = root / "src"
    extension = root / ".pi" / "extensions" / "neuralengine-guard.ts"

    result = _run_wrapper(
        root,
        home,
        capture,
        cwd,
        ["--extension", str(extension), "--model", "user-selected-model"],
    )

    args = result["args"]
    assert isinstance(args, list)
    assert args.count("--extension") == 1
    assert "--model" in args
    assert args[args.index("--model") + 1] == "user-selected-model"
    assert "/models/gguf/general.gguf" not in args


def test_home_and_sibling_paths_keep_ordinary_pi_behavior(tmp_path: Path) -> None:
    root, home, capture = _fake_project(tmp_path)
    outside = tmp_path / "NeuralEngine-copy"
    outside.mkdir()

    for cwd in (home, outside):
        result = _run_wrapper(
            root,
            home,
            capture,
            cwd,
            ["--model", "user-model"],
            stale_root=str(root),
        )
        assert result == {
            "cwd": str(cwd),
            "args": ["--model", "user-model"],
            "project_root": None,
        }


def test_home_behavior_does_not_depend_on_neuralengine_settings(tmp_path: Path) -> None:
    root, home, capture = _fake_project(tmp_path)
    (root / ".pi" / "settings.json").unlink()

    result = _run_wrapper(root, home, capture, home, [])

    assert result == {"cwd": str(home), "args": [], "project_root": None}


def test_symlinked_working_directory_uses_canonical_repository_root(tmp_path: Path) -> None:
    root, home, capture = _fake_project(tmp_path)
    link = tmp_path / "neuralengine-src-link"
    link.symlink_to(root / "src", target_is_directory=True)

    result = _run_wrapper(root, home, capture, link, [])

    assert result["cwd"] == str(root / "src")
    assert result["project_root"] == str(root)
    args = result["args"]
    assert isinstance(args, list)
    assert args[args.index("--extension") + 1] == str(
        root / ".pi" / "extensions" / "neuralengine-guard.ts"
    )

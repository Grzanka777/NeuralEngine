import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from collections.abc import Callable
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import ModuleType
from typing import cast

import pytest

COMMANDS = (
    "seek",
    "fix",
    "arch",
    "ship",
    "research",
    "optimize",
    "kill",
    "checkpoint",
    "recheck",
    "next",
)
CANONICAL_FILES = (
    "COMMAND_CORE_v1.2.md",
    "COMMAND_PROTOCOL_v1.2.md",
    "ENGINEERING_WORKFLOW_v1.1.md",
)


def _root() -> Path:
    return Path(__file__).parents[1]


def _run(operation: str, target: Path) -> subprocess.CompletedProcess[str]:
    script = _root() / "scripts" / "install-opencode-command-protocol"
    return subprocess.run(
        [
            sys.executable,
            str(script),
            operation,
            "--source-root",
            str(_root()),
            "--target-root",
            str(target),
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def _result(process: subprocess.CompletedProcess[str]) -> dict[str, object]:
    return cast(dict[str, object], json.loads(process.stdout))


def _errors(result: dict[str, object]) -> list[str]:
    return cast(list[str], result.get("errors", []))


def _managed_relatives() -> tuple[str, ...]:
    return (
        *sorted(("AGENTS.md", *(f"commands/{name}.md" for name in COMMANDS))),
        *sorted(f"skills/command-protocol/references/{name}" for name in CANONICAL_FILES),
        "skills/command-protocol/SKILL.md",
        "command-protocol.manifest.json",
    )


def _lexists(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def _existing_managed(target: Path) -> set[str]:
    return {relative for relative in _managed_relatives() if _lexists(target / relative)}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_installer_module() -> ModuleType:
    path = _root() / "scripts" / "install-opencode-command-protocol"
    loader = SourceFileLoader("installer_under_test", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _direct_install(module: ModuleType, target: Path) -> dict[str, object]:
    install = cast(Callable[[Path, Path], dict[str, object]], module.__dict__["install"])
    return install(_root(), target)


def test_installer_uses_explicit_temporary_target_and_is_deterministic(tmp_path: Path) -> None:
    first_target = tmp_path / "first-opencode-home"
    second_target = tmp_path / "second-opencode-home"

    first = _run("--install", first_target)
    second = _run("--install", second_target)
    assert first.returncode == 0, first.stderr + first.stdout
    assert second.returncode == 0, second.stderr + second.stdout

    first_manifest = json.loads(
        (first_target / "command-protocol.manifest.json").read_text(encoding="utf-8")
    )
    second_manifest = json.loads(
        (second_target / "command-protocol.manifest.json").read_text(encoding="utf-8")
    )
    assert first_manifest == second_manifest
    assert first_manifest["installer_id"] == "neuralengine-opencode-command-protocol"
    assert first_manifest["manifest_version"] == 2
    assert first_manifest["protocol_version"] == "1.2"
    assert first_manifest["workflow_version"] == "1.1"
    assert first_manifest["canonical_source_hashes"] == {
        name: _sha256(_root() / "docs" / "command-protocol" / name) for name in CANONICAL_FILES
    }

    installed_hashes = cast(dict[str, str], first_manifest["installed_hashes"])
    installed_files = cast(dict[str, dict[str, str]], first_manifest["installed_files"])
    assert set(installed_hashes) == set(installed_files)
    for relative, identity in installed_files.items():
        assert identity["disposition"] == "NEW"
        assert identity["sha256"] == installed_hashes[relative]
        installed = first_target / relative
        assert installed.is_file() and not installed.is_symlink()
        assert _sha256(installed) == identity["sha256"]
    assert str(first_target) not in json.dumps(first_manifest)

    checked = _run("--check", first_target)
    repeated = _run("--check", first_target)
    assert checked.returncode == 0, checked.stderr + checked.stdout
    assert repeated.returncode == 0
    assert checked.stdout == repeated.stdout


def test_installer_detects_stale_unexpected_and_version_drift(tmp_path: Path) -> None:
    target = tmp_path / "opencode-home"
    assert _run("--install", target).returncode == 0

    stale_path = target / "commands" / "seek.md"
    stale_path.write_text("stale", encoding="utf-8")
    stale = _run("--check", target)
    assert stale.returncode == 1
    assert "installed hash mismatch" in stale.stdout

    refused = _run("--install", target)
    assert refused.returncode == 1
    assert "managed destination collision: commands/seek.md" in refused.stdout
    assert stale_path.read_text(encoding="utf-8") == "stale"

    extra = target / "skills" / "command-protocol" / "unexpected.md"
    extra.write_text("unexpected", encoding="utf-8")
    unexpected = _run("--check", target)
    assert unexpected.returncode == 1
    assert "unexpected installer-owned material" in unexpected.stdout
    extra.unlink()

    manifest = target / "command-protocol.manifest.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["protocol_version"] = "9.9"
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    mismatch = _run("--check", target)
    assert mismatch.returncode == 1
    assert "protocol version mismatch" in mismatch.stdout


@pytest.mark.parametrize(
    ("relative", "kind"),
    (
        ("AGENTS.md", "file"),
        ("commands/seek.md", "file"),
        ("skills/command-protocol/SKILL.md", "file"),
        ("command-protocol.manifest.json", "file"),
        ("commands/fix.md", "symlink"),
        ("commands/arch.md", "directory"),
    ),
)
def test_installer_refuses_each_managed_collision_without_mutation(
    tmp_path: Path, relative: str, kind: str
) -> None:
    target = tmp_path / "opencode-home"
    destination = target / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    if kind == "file":
        destination.write_text(f"pre-existing:{relative}", encoding="utf-8")
    elif kind == "symlink":
        target_file = tmp_path / "symlink-target"
        target_file.write_text("pre-existing target", encoding="utf-8")
        destination.symlink_to(target_file)
    else:
        destination.mkdir()

    before_hash = _sha256(destination) if kind == "file" else None
    before_managed = _existing_managed(target)
    installed = _run("--install", target)

    assert installed.returncode == 1
    assert relative in installed.stdout
    assert _existing_managed(target) == before_managed
    if kind == "file":
        assert _sha256(destination) == before_hash
    elif kind == "symlink":
        assert destination.is_symlink()


def test_installer_aggregates_collisions_before_any_target_write(tmp_path: Path) -> None:
    target = tmp_path / "opencode-home"
    collisions = (
        "AGENTS.md",
        "commands/seek.md",
        "skills/command-protocol/SKILL.md",
        "command-protocol.manifest.json",
    )
    for relative in collisions:
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(f"pre-existing:{relative}", encoding="utf-8")
    before_managed = _existing_managed(target)

    installed = _run("--install", target)

    assert installed.returncode == 1
    for relative in collisions:
        assert relative in installed.stdout
    assert _existing_managed(target) == before_managed
    assert not (target / "commands" / "fix.md").exists()
    assert not (target / "commands" / "arch.md").exists()


def test_installer_allows_unrelated_existing_parent_material(tmp_path: Path) -> None:
    target = tmp_path / "opencode-home"
    (target / "skills").mkdir(parents=True)
    (target / "commands").mkdir()
    unrelated_command = target / "commands" / "unrelated.md"
    unrelated_skill = target / "skills" / "unrelated.md"
    unrelated_command.write_text("keep command", encoding="utf-8")
    unrelated_skill.write_text("keep skill", encoding="utf-8")

    installed = _run("--install", target)

    assert installed.returncode == 0, installed.stderr + installed.stdout
    assert unrelated_command.read_text(encoding="utf-8") == "keep command"
    assert unrelated_skill.read_text(encoding="utf-8") == "keep skill"


def test_installer_rejects_symlink_material_in_check_and_install(tmp_path: Path) -> None:
    target = tmp_path / "opencode-home"
    assert _run("--install", target).returncode == 0
    skill = target / "skills" / "command-protocol" / "SKILL.md"
    content = target / "skills" / "command-protocol" / "SKILL.copy.md"
    content.write_bytes(skill.read_bytes())
    skill.unlink()
    skill.symlink_to(content)

    checked = _run("--check", target)
    installed = _run("--install", target)
    assert checked.returncode == 1
    assert installed.returncode == 1
    assert skill.is_symlink()


def test_installer_rolls_back_after_publication_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_installer_module()
    target = tmp_path / "opencode-home"
    target.mkdir()
    unrelated = target / "commands" / "unrelated.md"
    unrelated.parent.mkdir()
    unrelated.write_text("keep", encoding="utf-8")
    original_copyfile = cast(
        Callable[[os.PathLike[str] | str, os.PathLike[str] | str], str],
        module.shutil.copyfile,
    )
    calls = 0

    def failing_copyfile(
        source: os.PathLike[str] | str, destination: os.PathLike[str] | str
    ) -> str:
        nonlocal calls
        calls += 1
        if calls == len(module.INSTALL_MAP) + 2:
            raise OSError("injected publication failure")
        return original_copyfile(source, destination)

    monkeypatch.setattr(module.shutil, "copyfile", failing_copyfile)
    result = _direct_install(module, target)

    assert result["ok"] is False
    assert "publication failed" in " ".join(_errors(result))
    assert _existing_managed(target) == set()
    assert unrelated.read_text(encoding="utf-8") == "keep"


def test_installer_preserves_external_change_and_reports_rollback_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_installer_module()
    target = tmp_path / "opencode-home"
    target.mkdir()
    original_copyfile = cast(
        Callable[[os.PathLike[str] | str, os.PathLike[str] | str], str],
        module.shutil.copyfile,
    )
    calls = 0

    def failing_copyfile(
        source: os.PathLike[str] | str, destination: os.PathLike[str] | str
    ) -> str:
        nonlocal calls
        calls += 1
        if calls == len(module.INSTALL_MAP) + 2:
            (target / "AGENTS.md").write_text("external actor", encoding="utf-8")
            raise OSError("injected publication failure after external change")
        return original_copyfile(source, destination)

    monkeypatch.setattr(module.shutil, "copyfile", failing_copyfile)
    result = _direct_install(module, target)

    assert result["ok"] is False
    errors = " ".join(_errors(result))
    assert "publication failed" in errors
    assert "rollback failed" in errors
    assert (target / "AGENTS.md").read_text(encoding="utf-8") == "external actor"
    assert _existing_managed(target) == {"AGENTS.md"}


def test_check_rejects_absent_manifest_without_writing(tmp_path: Path) -> None:
    target = tmp_path / "opencode-home"
    target.mkdir()
    before = list(target.iterdir())

    checked = _run("--check", target)

    assert checked.returncode == 1
    assert "manifest is missing" in checked.stdout
    assert list(target.iterdir()) == before

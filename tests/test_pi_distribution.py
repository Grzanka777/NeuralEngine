"""Contract tests for the canonical, manifest-driven Pi distribution."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "integrations/pi/manifest.json"
INSTALLER = ROOT / "scripts/sync-pi-resources"
LEGACY_WRAPPER = ROOT / "scripts/sync-pi-lifecycle-extension"
PROTOCOL_SOURCE = ROOT / "integrations/pi/skills/command-protocol"


def _run_installer(home: Path, script: Path = INSTALLER) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script)],
        cwd=ROOT,
        env={**os.environ, "HOME": str(home)},
        capture_output=True,
        text=True,
        check=False,
    )


def _manifest() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(MANIFEST.read_text(encoding="utf-8")))


def _all_files(root: Path) -> dict[Path, bytes]:
    return {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def test_manifest_schema_and_resource_classification() -> None:
    manifest = _manifest()

    assert set(manifest) == {"version", "resources"}
    assert manifest["version"] == 1
    assert isinstance(manifest["resources"], list)
    resources = manifest["resources"]
    assert resources
    assert len({resource["name"] for resource in resources}) == len(resources)
    assert all((ROOT / resource["source"]).exists() for resource in resources)

    global_resources = [resource for resource in resources if resource["scope"] == "GLOBAL"]
    assert len(global_resources) == 2
    assert len({resource["source"] for resource in global_resources}) == len(global_resources)
    assert all("destination" in resource for resource in global_resources)
    assert all(resource["scope"] == "PROJECT_LOCAL" for resource in resources[2:])
    assert all("destination" not in resource for resource in resources[2:])


def test_global_resources_have_one_source_outside_project_autoload_paths() -> None:
    manifest = _manifest()
    by_name = {resource["name"]: resource for resource in manifest["resources"]}

    assert by_name["deepseek-only"]["source"] == ("integrations/pi/extensions/deepseek-only.ts")
    assert by_name["command-protocol"]["source"] == ("integrations/pi/skills/command-protocol")
    assert not (ROOT / ".pi/extensions/deepseek-only.ts").exists()
    assert not (ROOT / ".pi/skills/command-protocol").exists()


def test_command_protocol_references_are_exact_canonical_copies() -> None:
    names = (
        "COMMAND_CORE_v1.2.md",
        "COMMAND_PROTOCOL_v1.2.md",
        "ENGINEERING_WORKFLOW_v1.1.md",
    )
    for name in names:
        canonical = ROOT / "docs/command-protocol" / name
        packaged = PROTOCOL_SOURCE / "references" / name
        assert packaged.read_bytes() == canonical.read_bytes()

    skill = (PROTOCOL_SOURCE / "SKILL.md").read_text(encoding="utf-8")
    assert "references/COMMAND_CORE_v1.2.md" in skill
    assert "references/COMMAND_PROTOCOL_v1.2.md" in skill
    assert "references/ENGINEERING_WORKFLOW_v1.1.md" in skill


def test_installer_creates_global_destinations_and_copies_exact_bytes(tmp_path: Path) -> None:
    home = tmp_path / "fresh-home"
    result = _run_installer(home)

    assert result.returncode == 0, result.stderr
    global_root = home / ".pi/agent"
    lifecycle_source = ROOT / "integrations/pi/extensions/deepseek-only.ts"
    lifecycle_target = global_root / "extensions/deepseek-only.ts"
    assert lifecycle_target.read_bytes() == lifecycle_source.read_bytes()

    protocol_target = global_root / "skills/command-protocol"
    assert _all_files(protocol_target) == _all_files(PROTOCOL_SOURCE)


def test_project_local_resources_are_excluded_from_global_install(tmp_path: Path) -> None:
    home = tmp_path / "home"
    result = _run_installer(home)

    assert result.returncode == 0, result.stderr
    global_root = home / ".pi/agent"
    assert not (global_root / "extensions/neuralengine-guard.ts").exists()
    assert not (global_root / "skills/local-models").exists()
    assert not (global_root / "prompts").exists()
    assert not (global_root / "settings.json").exists()


def test_installer_preserves_unrelated_global_resources(tmp_path: Path) -> None:
    home = tmp_path / "home"
    global_root = home / ".pi/agent"
    unrelated_extension = global_root / "extensions/user-extension.ts"
    unrelated_skill = global_root / "skills/user-skill/SKILL.md"
    unrelated_extension.parent.mkdir(parents=True)
    unrelated_skill.parent.mkdir(parents=True)
    unrelated_extension.write_bytes(b"user extension\n")
    unrelated_skill.write_bytes(b"user skill\n")

    result = _run_installer(home)

    assert result.returncode == 0, result.stderr
    assert unrelated_extension.read_bytes() == b"user extension\n"
    assert unrelated_skill.read_bytes() == b"user skill\n"


def test_installer_repairs_managed_copy_drift_without_deleting_unrelated_files(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    assert _run_installer(home).returncode == 0
    global_root = home / ".pi/agent"
    lifecycle_target = global_root / "extensions/deepseek-only.ts"
    unrelated = global_root / "extensions/keep.ts"
    lifecycle_target.write_text("drift\n", encoding="utf-8")
    unrelated.write_text("keep\n", encoding="utf-8")

    result = _run_installer(home)

    assert result.returncode == 0, result.stderr
    assert (
        lifecycle_target.read_bytes()
        == (ROOT / "integrations/pi/extensions/deepseek-only.ts").read_bytes()
    )
    assert unrelated.read_text(encoding="utf-8") == "keep\n"


def test_unexpected_file_in_managed_directory_is_reported_and_preserved(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    assert _run_installer(home).returncode == 0
    extra = home / ".pi/agent/skills/command-protocol/local-note.md"
    extra.write_text("preserve this\n", encoding="utf-8")

    result = _run_installer(home)

    assert result.returncode != 0
    assert "copy drift detected for command-protocol" in result.stderr
    assert extra.read_text(encoding="utf-8") == "preserve this\n"


def test_installer_is_idempotent_and_second_sync_changes_no_bytes(tmp_path: Path) -> None:
    home = tmp_path / "home"
    first = _run_installer(home)
    assert first.returncode == 0, first.stderr
    global_root = home / ".pi/agent"
    before = _all_files(global_root)
    mtimes = {path: (global_root / path).stat().st_mtime_ns for path in before}

    second = _run_installer(home)

    assert second.returncode == 0, second.stderr
    assert "unchanged: deepseek-only" in second.stdout
    assert "unchanged: command-protocol" in second.stdout
    assert _all_files(global_root) == before
    assert {path: (global_root / path).stat().st_mtime_ns for path in before} == mtimes


def test_lifecycle_and_command_protocol_are_not_project_auto_loaded() -> None:
    assert (ROOT / "integrations/pi/extensions/deepseek-only.ts").is_file()
    assert not (ROOT / ".pi/extensions/deepseek-only.ts").exists()
    assert not (ROOT / ".pi/skills/command-protocol").exists()


def test_missing_source_fails_before_creating_global_install(tmp_path: Path) -> None:
    fake_root = tmp_path / "repo"
    (fake_root / "scripts").mkdir(parents=True)
    (fake_root / "integrations/pi").mkdir(parents=True)
    fake_installer = fake_root / "scripts/sync-pi-resources"
    shutil.copyfile(INSTALLER, fake_installer)
    (fake_root / "integrations/pi/manifest.json").write_text(
        json.dumps(
            {
                "version": 1,
                "resources": [
                    {
                        "name": "missing",
                        "scope": "GLOBAL",
                        "source": "integrations/pi/not-here.ts",
                        "destination": "extensions/missing.ts",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    home = tmp_path / "home"

    result = _run_installer(home, fake_installer)

    assert result.returncode != 0
    assert "source does not exist" in result.stderr
    assert not (home / ".pi/agent").exists()


def test_invalid_manifest_version_fails_clearly(tmp_path: Path) -> None:
    fake_root = tmp_path / "repo"
    (fake_root / "scripts").mkdir(parents=True)
    (fake_root / "integrations/pi").mkdir(parents=True)
    fake_installer = fake_root / "scripts/sync-pi-resources"
    shutil.copyfile(INSTALLER, fake_installer)
    (fake_root / "integrations/pi/manifest.json").write_text(
        json.dumps({"version": 2, "resources": []}), encoding="utf-8"
    )

    result = _run_installer(tmp_path / "home", fake_installer)

    assert result.returncode != 0
    assert "unsupported Pi distribution manifest version" in result.stderr


def test_manifest_rejects_path_traversal(tmp_path: Path) -> None:
    fake_root = tmp_path / "repo"
    source = fake_root / "integrations/pi/source.ts"
    source.parent.mkdir(parents=True)
    source.write_text("source\n", encoding="utf-8")
    (fake_root / "scripts").mkdir()
    fake_installer = fake_root / "scripts/sync-pi-resources"
    shutil.copyfile(INSTALLER, fake_installer)
    (fake_root / "integrations/pi/manifest.json").write_text(
        json.dumps(
            {
                "version": 1,
                "resources": [
                    {
                        "name": "escape",
                        "scope": "GLOBAL",
                        "source": "integrations/pi/source.ts",
                        "destination": "../outside.ts",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = _run_installer(tmp_path / "home", fake_installer)

    assert result.returncode != 0
    assert "must not be absolute or traverse directories" in result.stderr
    assert not (tmp_path / "home/.pi/agent").exists()


def test_legacy_sync_command_delegates_to_canonical_installer(tmp_path: Path) -> None:
    result = _run_installer(tmp_path / "home", LEGACY_WRAPPER)

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "home/.pi/agent/extensions/deepseek-only.ts").read_bytes() == (
        ROOT / "integrations/pi/extensions/deepseek-only.ts"
    ).read_bytes()

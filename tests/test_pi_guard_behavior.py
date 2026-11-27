from __future__ import annotations

import json
import os
import shutil
import subprocess
from functools import lru_cache, partial
from pathlib import Path
from typing import cast

import pytest

REPOSITORY_ROOT = Path(__file__).parents[1]
GUARD_EXTENSION = REPOSITORY_ROOT / ".pi/extensions/neuralengine-guard.ts"
GUARD_PROBE = REPOSITORY_ROOT / "tests/pi_guard_probe.mjs"

GIT_REASON = "Git mutation requires separate explicit authorization"
NEURAL_REASON = "NeuralEngine durable-state mutation requires separate explicit authorization"
PRIVILEGED_REASON = "Privileged system mutation requires separate explicit authorization"
RECURSIVE_REASON = "Recursive removal requires separate explicit authorization"

PROTECTED_CASES: tuple[tuple[str, str], ...] = (
    ("git add .", GIT_REASON),
    ("git commit -m test", GIT_REASON),
    ("git push", GIT_REASON),
    ("git -C /tmp add .", GIT_REASON),
    ("git --no-pager commit -m test", GIT_REASON),
    ("sudo true", PRIVILEGED_REASON),
    ("rm -rf /tmp/example", RECURSIVE_REASON),
    ("neural decision add ...", NEURAL_REASON),
    ("uv run neural memory apply ...", NEURAL_REASON),
    ("uv run neural memory start ...", NEURAL_REASON),
)

ALLOWED_CASES: tuple[str, ...] = (
    "git status --short",
    "git diff",
    "git log -1",
    "git -C /tmp status --short",
    "git --no-pager log -1",
)


def _run_guard_probe(commands: tuple[str, ...]) -> dict[str, str | None]:
    result = subprocess.run(
        ["node", str(GUARD_PROBE), str(GUARD_EXTENSION), json.dumps(list(commands))],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    if result.returncode != 0:
        raise AssertionError(
            "Pi guard probe failed to execute the extension:\n"
            f"exit={result.returncode}\n{result.stderr}"
        )
    return cast("dict[str, str | None]", json.loads(result.stdout))


def _run_tool_call_probe(
    *,
    mode: str = "direct",
    tool_name: str = "write",
    target_path: str,
    cwd: Path,
    home: Path,
    project_root: Path | None = None,
    neural_home: Path | str | None = None,
    policy_path: Path | None = None,
    runtime_package: Path | None = None,
) -> dict[str, object]:
    spec: dict[str, object] = {
        "mode": mode,
        "toolName": tool_name,
        "path": target_path,
        "cwd": str(cwd),
        "home": str(home),
        "projectRoot": str(project_root or cwd),
        "neuralHome": str(neural_home) if neural_home is not None else None,
    }
    if policy_path is not None:
        spec["policyPath"] = str(policy_path)
    if runtime_package is not None:
        spec["runtimePackage"] = str(runtime_package)
    env = os.environ.copy()
    env.pop("NEURAL_HOME", None)
    env.pop("NEURAL_PI_BOUNDED_CODE", None)
    env.pop("NEURAL_PI_POLICY_FILE", None)
    result = subprocess.run(
        ["node", str(GUARD_PROBE), "--tool-call", str(GUARD_EXTENSION), json.dumps(spec)],
        cwd=REPOSITORY_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    if result.returncode != 0:
        raise AssertionError(
            "Pi guard tool-call probe failed to execute:\n"
            f"exit={result.returncode}\n{result.stderr}"
        )
    return cast("dict[str, object]", json.loads(result.stdout))


def _setup_synthetic_env(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    home = tmp_path / "home"
    neural_home = tmp_path / "neural-home"
    brain_obs = neural_home / "brain" / "observations"
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    _git(workspace, "init", "--quiet")
    (workspace / "src" / "safe.py").write_text("x = 1\n", encoding="utf-8")
    home.mkdir(parents=True)
    brain_obs.mkdir(parents=True)
    (brain_obs / "obs.json").write_text("{}\n", encoding="utf-8")
    return home, neural_home, brain_obs, workspace


@lru_cache(maxsize=1)
def _classifications() -> dict[str, str | None]:
    commands = tuple(command for command, _ in PROTECTED_CASES) + ALLOWED_CASES
    return _run_guard_probe(commands)


@pytest.mark.parametrize(("command", "reason"), PROTECTED_CASES)
def test_protected_command_is_classified_with_its_category_reason(
    command: str, reason: str
) -> None:
    assert _classifications()[command] == reason


@pytest.mark.parametrize("command", ALLOWED_CASES)
def test_allowed_command_is_not_classified(command: str) -> None:
    assert _classifications()[command] is None


def test_guard_exposes_four_distinct_reason_categories() -> None:
    reasons = {_classifications()[command] for command, _ in PROTECTED_CASES}
    assert reasons == {GIT_REASON, NEURAL_REASON, PRIVILEGED_REASON, RECURSIVE_REASON}


@pytest.mark.parametrize("tool_name", ["write", "edit"])
def test_direct_brain_write_and_edit_are_blocked(tmp_path: Path, tool_name: str) -> None:
    home, neural_home, brain_obs, workspace = _setup_synthetic_env(tmp_path)
    out = _run_tool_call_probe(
        tool_name=tool_name,
        target_path=str(brain_obs / "obs.json"),
        cwd=workspace,
        home=home,
        neural_home=neural_home,
    )
    assert out["reason"] == "Brain writes require separate authorization"


@pytest.mark.parametrize("tool_name", ["write", "edit"])
def test_symlink_file_into_brain_is_blocked(tmp_path: Path, tool_name: str) -> None:
    home, neural_home, brain_obs, workspace = _setup_synthetic_env(tmp_path)
    link_file = workspace / "obs-link.json"
    link_file.symlink_to(brain_obs / "obs.json")

    out = _run_tool_call_probe(
        tool_name=tool_name,
        target_path="obs-link.json",
        cwd=workspace,
        home=home,
        neural_home=neural_home,
    )
    assert out["reason"] == "Brain writes require separate authorization"


def test_symlinked_parent_directory_into_brain_is_blocked(tmp_path: Path) -> None:
    home, neural_home, brain_obs, workspace = _setup_synthetic_env(tmp_path)
    (workspace / "brain-link").symlink_to(brain_obs, target_is_directory=True)

    out = _run_tool_call_probe(
        tool_name="write",
        target_path="brain-link/obs.json",
        cwd=workspace,
        home=home,
        neural_home=neural_home,
    )
    assert out["reason"] == "Brain writes require separate authorization"


def test_aliased_neural_home_is_blocked(tmp_path: Path) -> None:
    home, neural_home, brain_obs, workspace = _setup_synthetic_env(tmp_path)
    home_alias = tmp_path / "neural-home-alias"
    home_alias.symlink_to(neural_home, target_is_directory=True)

    via_alias = _run_tool_call_probe(
        tool_name="write",
        target_path=str(home_alias / "brain" / "observations" / "obs.json"),
        cwd=workspace,
        home=home,
        neural_home=neural_home,
    )
    via_real = _run_tool_call_probe(
        tool_name="write",
        target_path=str(brain_obs / "obs.json"),
        cwd=workspace,
        home=home,
        neural_home=home_alias,
    )
    assert via_alias["reason"] == "Brain writes require separate authorization"
    assert via_real["reason"] == "Brain writes require separate authorization"


def test_nonexistent_target_under_aliased_brain_ancestor_is_blocked(tmp_path: Path) -> None:
    home, neural_home, _, workspace = _setup_synthetic_env(tmp_path)
    (workspace / "brain-dir").symlink_to(neural_home / "brain", target_is_directory=True)

    out = _run_tool_call_probe(
        tool_name="write",
        target_path="brain-dir/new-subdir/new-record.json",
        cwd=workspace,
        home=home,
        neural_home=neural_home,
    )
    assert out["reason"] == "Brain writes require separate authorization"


def test_broken_symlink_and_unresolvable_destination_fail_closed(tmp_path: Path) -> None:
    home, neural_home, _, workspace = _setup_synthetic_env(tmp_path)
    (workspace / "dangling").symlink_to(neural_home / "brain" / "observations" / "missing.json")
    (workspace / "dangling-dir").symlink_to(tmp_path / "does-not-exist")

    dangling_file = _run_tool_call_probe(
        tool_name="write",
        target_path="dangling",
        cwd=workspace,
        home=home,
        neural_home=neural_home,
    )
    dangling_child = _run_tool_call_probe(
        tool_name="write",
        target_path="dangling-dir/child.json",
        cwd=workspace,
        home=home,
        neural_home=neural_home,
    )
    blank_neural_home = _run_tool_call_probe(
        tool_name="write",
        target_path="src/safe.py",
        cwd=workspace,
        home=home,
        neural_home="",
    )
    assert isinstance(dangling_file["reason"], str)
    assert isinstance(dangling_child["reason"], str)
    assert isinstance(blank_neural_home["reason"], str)


def test_protected_git_destination_blocks_direct_and_symlink_writes(tmp_path: Path) -> None:
    home, neural_home, _, workspace = _setup_synthetic_env(tmp_path)
    (workspace / "git-alias").symlink_to(workspace / ".git", target_is_directory=True)

    direct = _run_tool_call_probe(
        tool_name="write",
        target_path=".git/HEAD",
        cwd=workspace,
        home=home,
        neural_home=neural_home,
    )
    aliased = _run_tool_call_probe(
        tool_name="edit",
        target_path="git-alias/HEAD",
        cwd=workspace,
        home=home,
        neural_home=neural_home,
    )
    assert direct["reason"] == "Direct Git metadata writes are blocked"
    assert aliased["reason"] == "Direct Git metadata writes are blocked"


def test_unrelated_safe_workspace_writes_are_allowed(tmp_path: Path) -> None:
    home, neural_home, _, workspace = _setup_synthetic_env(tmp_path)

    existing = _run_tool_call_probe(
        tool_name="edit",
        target_path="src/safe.py",
        cwd=workspace,
        home=home,
        neural_home=neural_home,
    )
    nonexistent = _run_tool_call_probe(
        tool_name="write",
        target_path="src/new_subdir/new_module.py",
        cwd=workspace,
        home=home,
        neural_home=neural_home,
    )
    assert existing["reason"] is None
    assert nonexistent["reason"] is None


def test_ordinary_guarded_session_without_governor_blocks_symlinked_brain_and_allows_workspace(
    tmp_path: Path,
) -> None:
    home, neural_home, brain_obs, workspace = _setup_synthetic_env(tmp_path)
    (workspace / "brain-alias").symlink_to(brain_obs, target_is_directory=True)

    blocked = _run_tool_call_probe(
        mode="session",
        tool_name="write",
        target_path="brain-alias/obs.json",
        cwd=workspace,
        home=home,
        neural_home=neural_home,
    )
    allowed = _run_tool_call_probe(
        mode="session",
        tool_name="write",
        target_path="src/safe.py",
        cwd=workspace,
        home=home,
        neural_home=neural_home,
    )
    assert blocked["decision"] == {
        "block": True,
        "reason": "Brain writes require separate authorization",
    }
    assert allowed["decision"] is None


RESOLUTION_REASON = "Protected destination could not be resolved; failing closed"
AMBIGUOUS_REASON = "Ambiguous Pi file path; use a plain filesystem path"
BRAIN_REASON = "Brain writes require separate authorization"
GIT_METADATA_REASON = "Direct Git metadata writes are blocked"


def _git(cwd: Path, *args: str) -> str:
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=True,
        timeout=15,
    )
    return result.stdout.strip()


@pytest.fixture(scope="module")
def pi_runtime_package() -> Path:
    configured = os.environ.get("PI_GUARD_RUNTIME_PACKAGE")
    if configured:
        return Path(configured).resolve(strict=True)
    executable = shutil.which("pi")
    if executable:
        for parent in Path(executable).resolve(strict=True).parents:
            manifest = parent / "package.json"
            if manifest.is_file() and json.loads(manifest.read_text()).get("name") == (
                "@earendil-works/pi-coding-agent"
            ):
                return parent
    pytest.fail("Pi mutation parity requires an installed package or PI_GUARD_RUNTIME_PACKAGE")


@pytest.mark.parametrize("tool_name", ["write", "edit"])
@pytest.mark.parametrize("representation", ["home", "at", "uri", "unicode"])
def test_ambiguous_destinations_are_refused(
    tmp_path: Path, pi_runtime_package: Path, tool_name: str, representation: str
) -> None:
    home, neural_home, _, workspace = _setup_synthetic_env(tmp_path)
    ordinary = workspace / "ordinary file"
    destination = home / ordinary.name if representation == "home" else ordinary
    destination.write_text("before", encoding="utf-8")
    raw = {
        "home": f"~/{ordinary.name}",
        "at": f"@{ordinary.name}",
        "uri": ordinary.as_uri(),
        "unicode": ordinary.name.replace(" ", "\u00a0"),
    }[representation]
    probe = partial(
        _run_tool_call_probe,
        tool_name=tool_name,
        target_path=raw,
        cwd=workspace,
        home=home,
        neural_home=neural_home,
    )
    observed = probe(mode="runtime", runtime_package=pi_runtime_package)
    assert isinstance(observed["pi"], str)
    assert destination.read_text(encoding="utf-8") == "after"
    assert probe(mode="session")["decision"] == {
        "block": True,
        "reason": AMBIGUOUS_REASON,
    }


@pytest.mark.parametrize("bounded", [False, True])
def test_admitted_pi_mutation_tools_use_expected_workspace_paths(
    tmp_path: Path, pi_runtime_package: Path, bounded: bool
) -> None:
    home, neural_home, brain_obs, workspace = _setup_synthetic_env(tmp_path)
    safe = workspace / "src" / "safe.py"
    safe.write_text("before", encoding="utf-8")
    new = workspace / "src" / "new.txt"
    (workspace / "alias").symlink_to(brain_obs, target_is_directory=True)
    policy = workspace / "policy.json"
    policy.write_text(
        json.dumps(
            {
                "ALLOWED_EDIT_FILES": ["src/safe.py", "src/new.txt"],
                "ALLOW_NEW_FILES": True,
                "VALIDATION_COMMANDS": ["uv run pytest tests/test_pi_guard_behavior.py -q"],
                "TEST_COMMANDS": ["uv run pytest tests/test_pi_guard_behavior.py -q"],
            }
        ),
        encoding="utf-8",
    )
    probe = partial(
        _run_tool_call_probe,
        mode="session",
        cwd=workspace,
        home=home,
        neural_home=neural_home,
        policy_path=policy if bounded else None,
    )
    for tool_name, raw, destination in [
        ("edit", "alias/../src/safe.py", safe),
        ("write", str(new), new),
    ]:
        result = probe(tool_name=tool_name, target_path=raw, runtime_package=pi_runtime_package)
        assert result["decision"] is None
        assert isinstance(result["runtime"], dict)
        assert destination.read_text(encoding="utf-8") == "after"
    refused = probe(tool_name="edit", target_path="@src/safe.py")
    assert refused["decision"] == {"block": True, "reason": AMBIGUOUS_REASON}
    assert (brain_obs / "obs.json").read_text(encoding="utf-8") == "{}\n"


@pytest.mark.parametrize("kind", ["existing", "new", "configured-home"])
def test_native_resolution_preserves_symlink_payload_and_configured_home(
    tmp_path: Path, kind: str
) -> None:
    home, neural_home, brain_obs, workspace = _setup_synthetic_env(tmp_path)
    (workspace / "branch").symlink_to(brain_obs, target_is_directory=True)
    (workspace / "observations").mkdir()
    (workspace / "observations" / "obs.json").write_text("workspace sentinel", encoding="utf-8")
    (workspace / "record").symlink_to("branch/../observations/obs.json")
    (workspace / "nested").symlink_to("branch/../observations")
    (brain_obs / "child").mkdir()
    (workspace / "home-link").symlink_to(brain_obs / "child", target_is_directory=True)
    # The configured path has a lexical fallback directory that differs from its native target.
    configured = f"{workspace}/home-link/../../.."
    assert Path(configured).resolve(strict=True) == neural_home
    cases: dict[str, tuple[str, Path | str]] = {
        "existing": ("record", neural_home),
        "new": ("nested/new/record.json", neural_home),
        "configured-home": (str(brain_obs / "obs.json"), configured),
    }
    target, selected_home = cases[kind]
    result = _run_tool_call_probe(
        target_path=target, cwd=workspace, home=home, neural_home=selected_home
    )
    assert result["reason"] == BRAIN_REASON
    assert (brain_obs / "obs.json").read_text(encoding="utf-8") == "{}\n"


@pytest.mark.parametrize("kind", ["missing", "file", "whitespace"])
def test_invalid_configured_home_refuses_safe_work(tmp_path: Path, kind: str) -> None:
    home, neural_home, _, workspace = _setup_synthetic_env(tmp_path)
    configured = {
        "missing": str(tmp_path / "missing"),
        "file": str(workspace / "src" / "safe.py"),
        "whitespace": f"{neural_home} ",
    }[kind]
    assert (
        _run_tool_call_probe(
            target_path="src/safe.py", cwd=workspace, home=home, neural_home=configured
        )["reason"]
        == RESOLUTION_REASON
    )


def test_git_metadata_protection_in_linked_worktree_and_nested_cwd(tmp_path: Path) -> None:
    home, neural_home, _, workspace = _setup_synthetic_env(tmp_path)
    linked = tmp_path / "linked"
    _git(workspace, "worktree", "add", "--orphan", "-b", "fixture", str(linked))
    admin, common = _git(
        linked, "rev-parse", "--absolute-git-dir", "--path-format=absolute", "--git-common-dir"
    ).splitlines()
    nested = linked / "nested"
    nested.mkdir()
    for target in (linked / ".git", Path(admin) / "HEAD", Path(common) / "new-metadata"):
        assert (
            _run_tool_call_probe(
                target_path=str(target), cwd=nested, home=home, neural_home=neural_home
            )["reason"]
            == GIT_METADATA_REASON
        )
    assert (
        _run_tool_call_probe(
            target_path="safe.txt", cwd=nested, home=home, neural_home=neural_home
        )["reason"]
        is None
    )
    common_marker = Path(admin) / "commondir"
    original = common_marker.read_text(encoding="utf-8")
    common_marker.write_text("missing-directory\n", encoding="utf-8")
    assert (
        _run_tool_call_probe(
            target_path="safe.txt", cwd=nested, home=home, neural_home=neural_home
        )["reason"]
        == RESOLUTION_REASON
    )
    common_marker.write_text(original, encoding="utf-8")
    (linked / ".git").write_text("invalid", encoding="utf-8")
    assert (
        _run_tool_call_probe(
            target_path="safe.txt", cwd=nested, home=home, neural_home=neural_home
        )["reason"]
        == RESOLUTION_REASON
    )

from __future__ import annotations

import json
import shutil
import subprocess
from functools import lru_cache
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
)

ALLOWED_CASES: tuple[str, ...] = (
    "git status --short",
    "git diff",
    "git log -1",
    "git -C /tmp status --short",
    "git --no-pager log -1",
)

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None,
    reason="node runtime is required to execute the Pi guard extension",
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

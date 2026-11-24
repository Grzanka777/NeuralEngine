"""The production launcher and PATCH challenger share one startup lock."""

from __future__ import annotations

import select
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKER = r"""
import importlib.machinery
import importlib.util
import pathlib
import sys

script, lock_path = map(pathlib.Path, sys.argv[1:])
loader = importlib.machinery.SourceFileLoader("lock_worker", str(script))
spec = importlib.util.spec_from_loader(loader.name, loader)
assert spec is not None
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
loader.exec_module(module)
with module.lifecycle_lock():
    print("entered", flush=True)
    sys.stdin.buffer.readline()
"""


def _wait_for_entered(process: subprocess.Popen[str], timeout: float = 5.0) -> None:
    assert process.stdout is not None
    readable, _, _ = select.select([process.stdout], [], [], timeout)
    assert readable, "timed out waiting for lock owner"
    assert process.stdout.readline().strip() == "entered"


@pytest.mark.parametrize("first,second", [("llm", "challenger"), ("challenger", "llm")])
def test_llm_and_challenger_serialize_cross_entrypoint_startup(
    tmp_path: Path, first: str, second: str
) -> None:
    state_home = tmp_path / "state"
    scripts = {"llm": ROOT / "scripts/llm", "challenger": ROOT / "scripts/challenger"}
    lock_path = state_home / "neuralengine/lifecycle.lock"
    env = {**__import__("os").environ, "XDG_STATE_HOME": str(state_home)}

    def worker(script: Path) -> subprocess.Popen[str]:
        return subprocess.Popen(
            [
                sys.executable,
                "-c",
                WORKER,
                str(script),
                str(lock_path),
            ],
            env=env,
            text=True,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    first_process = worker(scripts[first])
    second_process: subprocess.Popen[str] | None = None
    try:
        _wait_for_entered(first_process)
        second_process = worker(scripts[second])
        assert second_process.stdout is not None
        readable, _, _ = select.select([second_process.stdout], [], [], 0.2)
        assert not readable, "second entrypoint bypassed the shared startup lock"
        assert first_process.stdin is not None
        first_process.stdin.write("release\n")
        first_process.stdin.flush()
        _wait_for_entered(second_process)
        assert second_process.stdin is not None
        second_process.stdin.write("release\n")
        second_process.stdin.flush()
        first_process.wait(timeout=5)
        second_process.wait(timeout=5)
        assert first_process.returncode == 0
        assert second_process.returncode == 0
    finally:
        for process in (first_process, second_process):
            if process is not None and process.poll() is None:
                process.terminate()
                process.wait(timeout=5)

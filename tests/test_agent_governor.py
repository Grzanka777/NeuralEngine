"""Run the Pi extension's native Node test suite through pytest."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_agent_governor_node_suite() -> None:
    result = subprocess.run(
        ["node", "--experimental-strip-types", "--test", "tests/test_agent_governor.mjs"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"Node Governor tests failed:\n{result.stdout}\n{result.stderr}"

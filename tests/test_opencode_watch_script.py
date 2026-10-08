"""The retired OpenCode wrapper must only forward to OpenCode."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "opencode-watch"


def test_compatibility_entrypoint_forwards_args_and_exit_status(tmp_path: Path) -> None:
    args_path = tmp_path / "args"
    mock = tmp_path / "opencode"
    mock.write_text(
        '#!/usr/bin/env bash\nprintf \'%s\\n\' "$@" >"$ARGS_PATH"\nexit 23\n',
        encoding="utf-8",
    )
    mock.chmod(0o755)
    result = subprocess.run(
        [str(SCRIPT_PATH), "--model", "user-supplied", "prompt with spaces"],
        env={**os.environ, "OPENCODE_BIN": str(mock), "ARGS_PATH": str(args_path)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 23
    assert args_path.read_text(encoding="utf-8").splitlines() == [
        "--model",
        "user-supplied",
        "prompt with spaces",
    ]


def test_compatibility_entrypoint_has_no_llm_lifecycle_calls() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "llm start" not in source
    assert "llm stop" not in source
    assert "identity" not in source
    assert 'exec "${OPENCODE_BIN}" "$@"' in source

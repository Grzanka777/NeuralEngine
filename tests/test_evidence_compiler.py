"""Deterministic evidence pack compiler contract tests."""

from __future__ import annotations

import ast
import runpy
from pathlib import Path
from typing import Any

import pytest

COMPILER_PATH = Path(__file__).resolve().parents[1] / "scripts/evidence-compiler"
COMPILER: dict[str, Any] = runpy.run_path(str(COMPILER_PATH))
render_evidence_pack = COMPILER["render_evidence_pack"]


def test_evidence_compiler_produces_every_required_field() -> None:
    rendered = render_evidence_pack({"task": "Fix the bounded editor"})
    for field in (
        "TASK",
        "SYMPTOM",
        "ROOT_CAUSE_OR_OPEN_QUESTION",
        "EXACT_FILES",
        "EXACT_SYMBOLS",
        "KNOWN_INVARIANTS",
        "KNOWN_TESTS",
        "FAILING_EVIDENCE",
        "ALLOWED_CHANGES",
        "FORBIDDEN_CHANGES",
        "VALIDATION_COMMANDS",
        "STOP_CONDITIONS",
    ):
        assert f"## {field}" in rendered


def test_missing_evidence_is_marked_unknown() -> None:
    rendered = render_evidence_pack({"task": "Inspect one failure"})
    assert "## SYMPTOM\nUNKNOWN" in rendered
    assert "## EXACT_FILES\n- UNKNOWN" in rendered
    assert "## VALIDATION_COMMANDS\n- UNKNOWN" in rendered


def test_identical_input_has_deterministic_output() -> None:
    evidence = {
        "task": "Fix parsing",
        "exact_files": ["src/parser.py"],
        "known_tests": ["tests/test_parser.py::test_empty"],
        "validation_commands": ["uv run pytest tests/test_parser.py -q"],
    }
    assert render_evidence_pack(evidence) == render_evidence_pack(evidence)


def test_unknown_fields_and_malformed_values_are_rejected() -> None:
    with pytest.raises(ValueError, match="unknown evidence field"):
        render_evidence_pack({"task": "known", "root_cause": "guess"})
    with pytest.raises(ValueError, match="must contain only strings"):
        render_evidence_pack({"exact_files": ["src/a.py", 3]})


def test_compiler_imports_only_standard_library_modules() -> None:
    tree = ast.parse(COMPILER_PATH.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".", maxsplit=1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".", maxsplit=1)[0])
    assert imports <= {
        "__future__",
        "argparse",
        "collections",
        "json",
        "pathlib",
        "sys",
        "typing",
    }


def test_hypothesis_is_inferred_until_evidence_explicitly_marks_it_known() -> None:
    rendered = render_evidence_pack(
        {
            "root_cause_or_open_question": "Parser may drop a field",
            "working_hypothesis": "Check decode",
        }
    )
    assert "- root_cause_or_open_question: INFERRED" in rendered
    assert "- working_hypothesis: INFERRED" in rendered
    assert "- symptom: UNKNOWN" in rendered
    with pytest.raises(ValueError, match="cannot be KNOWN"):
        render_evidence_pack({"evidence_status": {"symptom": "KNOWN"}})

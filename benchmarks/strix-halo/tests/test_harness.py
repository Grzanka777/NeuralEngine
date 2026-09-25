from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from typing import ClassVar

HARNESS_PATH = Path(__file__).resolve().parents[1] / "scripts" / "harness.py"


def load_harness() -> ModuleType:
    spec = importlib.util.spec_from_file_location("strix_harness", HARNESS_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load harness module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class HarnessTests(unittest.TestCase):
    harness: ClassVar[ModuleType]

    @classmethod
    def setUpClass(cls) -> None:
        cls.harness = load_harness()

    def test_numeric_summary_records_required_statistics(self) -> None:
        result = self.harness.numeric_summary([1.0, 2.0, 3.0, 4.0, 5.0])
        self.assertEqual(result["median"], 3.0)
        self.assertEqual(result["mean"], 3.0)
        self.assertAlmostEqual(result["standard_deviation"], 1.5811388300841898)
        self.assertEqual(result["min"], 1.0)
        self.assertEqual(result["max"], 5.0)

    def test_comparison_uses_observed_standard_deviation_as_noise_gate(self) -> None:
        left = {"mode": "off", "summary": {"tg_tps": {"median": 50.0, "standard_deviation": 2.0}}}
        right = {"mode": "n3", "summary": {"tg_tps": {"median": 51.0, "standard_deviation": 1.0}}}
        result = self.harness.compare_modes(left, right)
        self.assertEqual(result["verdict"], "NO SIGNIFICANT DIFFERENCE")

    def test_schema_validation_is_strict(self) -> None:
        self.assertTrue(
            self.harness.schema_valid_payload({"name": "z13", "count": 3, "active": True})
        )
        self.assertFalse(
            self.harness.schema_valid_payload({"name": "z13", "count": True, "active": True})
        )
        self.assertFalse(
            self.harness.schema_valid_payload(
                {"name": "z13", "count": 3, "active": True, "extra": "not allowed"}
            )
        )

    def test_tool_payload_classifies_bad_name_and_arguments(self) -> None:
        self.assertEqual(
            self.harness.tool_payload_status(
                {"tool": "lookup_record", "arguments": {"id": "NE-42"}}
            ),
            (True, False, False),
        )
        self.assertEqual(
            self.harness.tool_payload_status({"tool": "invented", "arguments": {"id": "NE-42"}}),
            (False, True, True),
        )

    def test_append_raw_preserves_one_json_object_per_line(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "raw.jsonl"
            self.harness.append_raw(path, {"run": 1, "value": "ALPHA"})
            self.harness.append_raw(path, {"run": 2, "value": "BRAVO"})
            records = [json.loads(line) for line in path.read_text().splitlines()]
        self.assertEqual(records, [{"run": 1, "value": "ALPHA"}, {"run": 2, "value": "BRAVO"}])

    def test_server_command_adds_mtp_only_when_requested(self) -> None:
        config = self.harness.load_json(self.harness.DEFAULT_CONFIG)
        model = Path(config["main_model"])
        off = self.harness.server_command(config, model, 0)
        n3 = self.harness.server_command(config, model, 3)
        self.assertNotIn("--spec-type", off)
        self.assertIn("--spec-type", n3)
        self.assertEqual(n3[n3.index("--spec-draft-n-max") + 1], "3")


if __name__ == "__main__":
    unittest.main()

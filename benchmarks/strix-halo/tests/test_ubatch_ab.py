from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import ModuleType
from typing import ClassVar
from unittest.mock import patch

DRIVER_PATH = Path(__file__).resolve().parents[1] / "scripts" / "ubatch_ab.py"


def load_driver() -> ModuleType:
    spec = importlib.util.spec_from_file_location("strix_ubatch_ab", DRIVER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load ubatch_ab module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class UbatchAbTests(unittest.TestCase):
    driver: ClassVar[ModuleType]
    base: ClassVar[dict]

    @classmethod
    def setUpClass(cls) -> None:
        cls.driver = load_driver()
        cls.base = cls.driver.harness.load_json(cls.driver.harness.DEFAULT_CONFIG)

    def arm_config(self, ubatch: int, context: int | None = None):
        return self.driver.prepare_arm_config(
            self.base, ubatch, self.driver.DEFAULT_PORT, context or int(self.base["context"])
        )

    def test_context_defaults_to_65536_and_allows_historical_32768(self) -> None:
        parser = self.driver.build_parser()
        self.assertEqual(parser.parse_args([]).context, 65536)
        self.assertEqual(parser.parse_args(["--context", "32768"]).context, 32768)

    def test_arms_differ_in_exactly_one_token(self) -> None:
        model = Path(self.base["main_model"])
        low = self.driver.faithful_server_command(self.arm_config(1024), model, self.driver.MTP_N)
        high = self.driver.faithful_server_command(self.arm_config(2048), model, self.driver.MTP_N)
        self.assertEqual(len(low), len(high))
        diffs = [
            index for index, pair in enumerate(zip(low, high, strict=True)) if pair[0] != pair[1]
        ]
        self.assertEqual(len(diffs), 1, f"arms must differ only in -ub, got {diffs}")
        index = diffs[0]
        self.assertEqual(low[index - 1], "-ub")
        self.assertEqual(low[index], "1024")
        self.assertEqual(high[index], "2048")

    def test_command_matches_frozen_production_flags(self) -> None:
        model = Path(self.base["main_model"])
        command = self.driver.faithful_server_command(
            self.arm_config(1024), model, self.driver.MTP_N
        )
        self.assertEqual(command[command.index("-fa") + 1], "on")
        self.assertEqual(command[command.index("-np") + 1], "1")
        self.assertEqual(command[command.index("-b") + 1], str(self.base["agent_batch"]))
        self.assertIn("--cache-prompt", command)
        self.assertIn("--metrics", command)
        self.assertEqual(command[command.index("--spec-draft-n-max") + 1], str(self.driver.MTP_N))
        self.assertEqual(command[command.index("--spec-type") + 1], "draft-mtp")

    def test_speculation_omitted_when_depth_zero(self) -> None:
        model = Path(self.base["main_model"])
        command = self.driver.faithful_server_command(self.arm_config(1024), model, 0)
        self.assertNotIn("--spec-type", command)
        self.assertNotIn("--spec-draft-model", command)

    def test_prefill_command_holds_everything_but_ubatch(self) -> None:
        model = Path(self.base["main_model"])
        low = self.driver.prefill_command(self.arm_config(1024), model, 1024)
        high = self.driver.prefill_command(self.arm_config(2048), model, 2048)
        diffs = [
            index for index, pair in enumerate(zip(low, high, strict=True)) if pair[0] != pair[1]
        ]
        self.assertEqual(len(diffs), 1)
        self.assertEqual(low[diffs[0] - 1], "-ub")
        self.assertEqual(low[low.index("-fa") + 1], "on")
        self.assertEqual(low[low.index("-n") + 1], "0")

    def test_prepare_arm_config_overrides_only_audited_knobs(self) -> None:
        original = dict(self.base)
        config = self.driver.prepare_arm_config(self.base, 2048, 18089, 65536)
        self.assertEqual(config["agent_ubatch"], 2048)
        self.assertEqual(config["prefill_ubatch"], 2048)
        self.assertEqual(config["port"], 18089)
        self.assertEqual(config["context"], 65536)
        for key, value in original.items():
            if key in {"agent_ubatch", "prefill_ubatch", "port", "context"}:
                continue
            self.assertEqual(config[key], value)
        self.assertEqual(self.base, original, "base config must not be mutated")

    def test_compare_metric_matches_harness_noise_rule(self) -> None:
        harness = self.driver.harness
        left = [50.0, 52.0, 48.0, 51.0, 49.0]
        right = [51.0, 53.0, 49.0, 52.0, 50.0]
        mine = self.driver.compare_metric("tg", left, right)
        modes = harness.compare_modes(
            {"mode": "ub1024", "summary": {"tg_tps": harness.numeric_summary(left)}},
            {"mode": "ub2048", "summary": {"tg_tps": harness.numeric_summary(right)}},
        )
        self.assertEqual(mine["verdict"], modes["verdict"])
        self.assertAlmostEqual(mine["absolute"], modes["absolute_tps"])
        self.assertAlmostEqual(mine["observed_noise"], modes["observed_noise_tps"])

    def test_parse_prefill_payload_ignores_generation_entries(self) -> None:
        payload = [
            {"n_prompt": 512, "n_gen": 0, "avg_ts": 600.0, "stddev_ts": 5.0},
            {"n_prompt": 8, "n_gen": 256, "avg_ts": 50.0, "stddev_ts": 1.0},
            {"n_prompt": 2048, "n_gen": 0, "avg_ts": 520.0},
        ]
        parsed = self.driver.parse_prefill_payload(payload)
        self.assertEqual(parsed[512], {"avg_ts": 600.0, "stddev_ts": 5.0})
        self.assertEqual(parsed[2048]["avg_ts"], 520.0)
        self.assertNotIn(8, parsed)
        with self.assertRaises(self.driver.harness.GateFailure):
            self.driver.parse_prefill_payload([payload[1]])

    def test_parse_suites_always_includes_tg_and_rejects_unknown(self) -> None:
        self.assertEqual(self.driver.parse_suites("prefill"), ("tg", "prefill"))
        self.assertEqual(self.driver.parse_suites("tg,cache"), ("tg", "cache"))
        with self.assertRaises(self.driver.harness.GateFailure):
            self.driver.parse_suites("bogus")

    def test_keyboard_interrupt_records_aborted_without_failure_gate(self) -> None:
        identities = {
            "runtime_sha256": "runtime-hash",
            "model_sha256": "model-hash",
            "draft_model_sha256": "draft-hash",
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            result_dir = Path(temporary_directory)
            stdout = StringIO()
            with (
                patch.object(self.driver.harness, "validate_environment", return_value=identities),
                patch.object(self.driver.harness, "create_result_dir", return_value=result_dir),
                patch.object(self.driver.harness, "hardware_snapshot", return_value={}),
                patch.object(self.driver, "run_arm", side_effect=KeyboardInterrupt),
                redirect_stdout(stdout),
            ):
                status = self.driver.main([])

            results = json.loads((result_dir / "results.json").read_text(encoding="utf-8"))
            summary = (result_dir / "summary.md").read_text(encoding="utf-8")

        self.assertEqual(status, 130)
        self.assertEqual(results["verdict"], "ABORTED")
        self.assertEqual(results["abort_reason"], "KeyboardInterrupt")
        self.assertEqual(results["resolved_config"]["context"], 65536)
        arm_command = results["arm_commands"]["ub1024"]
        self.assertEqual(arm_command[arm_command.index("-c") + 1], "65536")
        self.assertNotIn("failure_gate", results)
        self.assertIn("VERDICT: ABORTED", summary)
        self.assertIn("ABORT: KeyboardInterrupt", summary)
        self.assertNotIn("FAILURE GATE:", summary)
        self.assertTrue(stdout.getvalue().strip())


if __name__ == "__main__":
    unittest.main()

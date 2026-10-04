"""Current Pi routing and retired runtime boundaries, separate from historical tests."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("name", ["pi-model", "pi-local", "challenger"])
@pytest.mark.parametrize("operation", ["status", "GENERAL", "switch-json", "start", "stop"])
def test_retired_entrypoints_refuse_without_running_local_runtime(
    name: str, operation: str
) -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / name), operation],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "Retired local entrypoint" in result.stderr


def test_project_default_has_one_cloud_scope() -> None:
    settings = json.loads((ROOT / ".pi/settings.json").read_text())
    assert settings["defaultProvider"] == "deepseek"
    assert settings["defaultModel"] == "deepseek-flash"
    assert settings["enabledModels"] == ["deepseek/deepseek-flash"]


def test_cloud_policy_denies_other_models_without_any_local_lifecycle() -> None:
    script = """
import assert from "node:assert/strict";
import register, {allowedModel} from "./integrations/pi/extensions/deepseek-only.ts";
const handlers = new Map();
register({on: (name, handler) => handlers.set(name, handler)});
let aborted = 0, shutdown = 0;
const ctx = {model: {provider:"deepseek",id:"deepseek-flash"},
  abort: () => aborted++, shutdown: () => shutdown++};
await handlers.get("session_start")({}, ctx);
await handlers.get("before_provider_request")({}, ctx);
assert.deepEqual(await handlers.get("input")({}, ctx), {action:"continue"});
assert.equal(aborted, 0);
for (const model of [undefined,{provider:"deepseek",id:"deepseek-v4-pro"},
    {provider:"neural-general",id:"local"},{provider:"openai",id:"cloud"}]) {
  assert.equal(allowedModel(model), false);
  ctx.model = model;
  await handlers.get("model_select")({},ctx);
  await handlers.get("before_provider_request")({},ctx);
  assert.deepEqual(await handlers.get("input")({},ctx), {action:"handled"});
}
assert.equal(aborted, 12);
assert.equal(shutdown, 12);
console.log("cloud allowlist and denial handlers verified");
"""
    result = subprocess.run(
        ["node", "--experimental-strip-types", "--input-type=module", "-e", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr

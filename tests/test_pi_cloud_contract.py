"""Pi local route projection and retained cloud default contract."""

from __future__ import annotations

import json
import subprocess
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]


def _projection_module() -> Any:
    path = ROOT / "scripts/sync-llm-client-projections"
    loader = SourceFileLoader("neuralengine_client_projection_test", str(path))
    spec = spec_from_loader(loader.name, loader)
    assert spec is not None
    module = module_from_spec(spec)
    loader.exec_module(module)
    return module


def test_project_default_keeps_deepseek_and_enables_manifest_local_routes() -> None:
    manifest = json.loads((ROOT / "llm-manifest.json").read_text())
    settings = json.loads((ROOT / ".pi/settings.json").read_text())
    assert settings["defaultProvider"] == manifest["clients"]["pi"]["cloud_default_provider"]
    assert settings["defaultModel"] == manifest["clients"]["pi"]["cloud_default_model"]
    assert "deepseek/deepseek-flash" in settings["enabledModels"]
    assert all(
        f"{manifest['clients']['pi']['provider']}/{manifest['models'][manifest['runtime_profiles'][manifest['roles'][role]['current_deployment_profile']]['model_ref']]['model_id']}"
        in settings["enabledModels"]
        for role in manifest["clients"]["pi"]["local_roles"]
    )


def test_pi_projection_replaces_retired_local_provider_ids() -> None:
    manifest = cast(dict[str, Any], json.loads((ROOT / "llm-manifest.json").read_text()))
    projection = _projection_module()
    settings = {
        "enabledModels": [
            "deepseek/deepseek-flash",
            "neuralengine-local/retired-qwen3-coder",
            "other-provider/keep-me",
        ]
    }

    projected = projection.pi_projection(settings, manifest)
    enabled = projected["enabledModels"]
    assert "neuralengine-local/retired-qwen3-coder" not in enabled
    assert "other-provider/keep-me" in enabled
    assert "neuralengine-local/qwen3.8-27b" in enabled


def test_extension_projects_all_manifest_routes_and_retains_cloud_default() -> None:
    script = """
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import register, {projectLocalModels} from "./integrations/pi/extensions/local-model-projection.ts";
const manifest = JSON.parse(readFileSync("./llm-manifest.json", "utf8"));
const models = projectLocalModels(manifest);
assert.equal(models.length, 4);
for (const profileName of manifest.clients.pi.local_profiles) {
  const profile = manifest.runtime_profiles[profileName];
  const source = manifest.models[profile.model_ref];
  const model = models.find(candidate => candidate.name.startsWith(profileName));
  assert.ok(model);
  assert.equal(model.id, source.model_id);
  assert.equal(model.baseUrl, `http://${profile.endpoint.host}:${profile.endpoint.port}${profile.endpoint.path}`);
  assert.equal(model.contextWindow, profile.context_layers.client_effective_ctx);
  if (profile.max_output_tokens === null) assert.equal(model.maxTokens, 0);
  else assert.equal(model.maxTokens, profile.max_output_tokens);
}
let registered;
const handlers = new Map();
const calls = [];
let ownership = "STARTED";
let nextPid = 100;
const identities = {
  "current-code": "CODE",
  "current-general": "GENERAL",
  "current-qwen3-coder": "QWEN3_CODER",
  "current-vision": "VISION"
};
register({
  registerProvider: (name, config) => { registered = {name, config}; },
  on: (event, handler) => handlers.set(event, handler),
  exec: async (_command, args) => {
    calls.push(args);
    if (args[0] === "switch-json") {
      const profile = identities[args[1]];
      return {code: 0, stdout: JSON.stringify({
        api_version: 1, operation: "switch", ownership, profile,
        pid: nextPid++, endpoint: "http://127.0.0.1:1/v1"
      }), stderr: ""};
    }
    return {code: 0, stdout: JSON.stringify({
      api_version: 1, operation: "stop_owned", result: "STOPPED",
      profile: args[2], pid: Number(args[4])
    }), stderr: ""};
  }
});
assert.equal(registered.name, manifest.clients.pi.provider);
assert.equal(registered.config.models.length, 4);
assert.equal(registered.config.models[0].api, manifest.clients.pi.api);
const ctx = {cwd: "/tmp", hasUI: false, ui: {notify() {}, setStatus() {}}};
const select = handlers.get("model_select");
const shutdown = handlers.get("session_shutdown");
const qwenCoderId = "/models/gguf/qwen3-coder-30b-a3b/"
  + "Qwen3-Coder-30B-A3B-Instruct-UD-Q4_K_XL.gguf";
const gemmaId = "/models/gguf/gemma4-26b-a4b/"
  + "gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf";
await select({model: {provider: "neuralengine-local", id: "qwen3.8-27b"}}, ctx);
await select({model: {provider: "neuralengine-local", id: qwenCoderId}}, ctx);
assert.deepEqual(
  calls.slice(0, 3).map(call => call[0]),
  ["switch-json", "stop-owned-json", "switch-json"]
);
assert.equal(calls[1][2], "CODE");
await select({model: {provider: "deepseek", id: "deepseek-flash"}}, ctx);
assert.equal(calls[3][0], "stop-owned-json");
ownership = "BORROWED";
await select({model: {provider: "neuralengine-local", id: gemmaId}}, ctx);
const countBeforeShutdown = calls.length;
await shutdown({reason: "quit"}, ctx);
assert.equal(calls.length, countBeforeShutdown, "BORROWED runtime must not be stopped");
console.log("manifest local routes and lifecycle registered");
"""
    result = subprocess.run(
        ["node", "--experimental-strip-types", "--input-type=module", "-e", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    source = (ROOT / "integrations/pi/extensions/local-model-projection.ts").read_text()
    assert "child_process" not in source
    assert 'join(state.projectRoot, "scripts", "llm")' in source
    assert "switch-json" in source
    assert "stop-owned-json" in source
    assert "deepseek" not in source

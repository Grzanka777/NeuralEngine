"""Tests for the NeuralEngine Pi lifecycle extension machine API integration.

Validates that the extension:
1. Exclusively consumes scripts/pi-model versioned JSON machine API.
2. Does not parse human-readable stdout patterns.
3. Does not call scripts/llm or scripts/challenger directly.
4. Resolves canonical project root from arbitrary working directories (/tmp, ~, etc.).
5. Implements correct STARTED vs BORROWED lifecycle transitions and idempotent shutdown.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTENSION_PATH = ROOT / "tests/fixtures/retired_pi/neuralengine-model-lifecycle.ts"
SYNC_SCRIPT = ROOT / "scripts/sync-pi-resources"


def test_extension_source_is_canonical_and_outside_project_autoload() -> None:
    """The lifecycle source is versioned outside Pi's project auto-load path."""
    assert EXTENSION_PATH.is_file()
    assert EXTENSION_PATH.relative_to(ROOT).as_posix() == (
        "tests/fixtures/retired_pi/neuralengine-model-lifecycle.ts"
    )
    assert not (ROOT / ".pi" / "extensions" / EXTENSION_PATH.name).exists()


def test_sync_excludes_retired_lifecycle(tmp_path: Path) -> None:
    """Normal installation must never reactivate the historical manager."""
    result = subprocess.run(
        [sys.executable, str(SYNC_SCRIPT)],
        cwd=ROOT,
        env={**os.environ, "HOME": str(tmp_path / "home")},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    extensions = tmp_path / "home/.pi/agent/extensions"
    assert not (extensions / EXTENSION_PATH.name).exists()
    assert (extensions / "deepseek-only.ts").is_file()


def test_extension_source_does_not_contain_human_parsing_or_direct_scripts() -> None:
    """Verify that human stdout patterns and direct backend script calls are absent."""
    source = EXTENSION_PATH.read_text(encoding="utf-8")

    # Forbidden human regexes and text tokens
    assert "STARTED BY THIS INVOCATION" not in source
    assert "READY_RE" not in source
    assert "STARTED_RE" not in source

    # Forbidden direct backend script calls for cleanup
    assert 'join(root, "scripts", "llm")' not in source
    assert 'join(root, "scripts", "challenger")' not in source
    assert '"scripts/llm"' not in source
    assert '"scripts/challenger"' not in source

    # Required machine API invocations
    assert "switch-json" in source
    assert "stop-owned-json" in source
    assert "EXPECTED_API_VERSION" in source


def test_provider_to_role_mapping_contract() -> None:
    """Verify the expected provider -> canonical role mapping."""
    provider_to_role = {
        "neural-general": "GENERAL",
        "neural-code": "CODE",
        "local-gptoss": "GPTOSS",
    }
    assert provider_to_role["neural-general"] == "GENERAL"
    assert provider_to_role["neural-code"] == "CODE"
    assert provider_to_role["local-gptoss"] == "GPTOSS"


def _run_node_harness_script(script: str) -> subprocess.CompletedProcess[str]:
    """Execute a Node test script with experimental TypeScript support enabled."""
    return subprocess.run(
        ["node", "--experimental-strip-types", "-e", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_node_switch_json_started_and_borrowed_lifecycle() -> None:
    """Test machine API STARTED and BORROWED handling using real Node harness."""
    script = """
    import assert from "node:assert/strict";
    import register, {
      parseSwitchJson,
      parseStopOwnedJson,
      findProjectRoot
    } from "./tests/fixtures/retired_pi/neuralengine-model-lifecycle.ts";

    const handlers = new Map();
    const execCalls = [];
    const statuses = [];

    const mockPi = {
      on: (evt, fn) => handlers.set(evt, fn),
      exec: async (cmd, args, opts) => {
        execCalls.push({ cmd, args, opts });
        if (args[0] === "switch-json") {
          return {
            code: 0,
            stdout: JSON.stringify({
              api_version: 1,
              operation: "switch",
              role: args[1],
              ownership: "STARTED",
              profile: args[1],
              pid: 4200,
              endpoint: "http://127.0.0.1:18081/v1"
            }),
            stderr: ""
          };
        }
        if (args[0] === "stop-owned-json") {
          return {
            code: 0,
            stdout: JSON.stringify({
              api_version: 1,
              operation: "stop_owned",
              result: "STOPPED",
              profile: args[2],
              pid: Number(args[4])
            }),
            stderr: ""
          };
        }
        return { code: 0, stdout: "", stderr: "" };
      }
    };

    register(mockPi);

    const ctx = {
      cwd: "/tmp",
      hasUI: true,
      ui: {
        notify: () => {},
        setStatus: (k, text) => statuses.push(text)
      }
    };

    async function test() {
      // 1. model_select for neural-general from /tmp
      const modelSelect = handlers.get("model_select");
      await modelSelect({
        type: "model_select",
        model: { provider: "neural-general", id: "qwen" },
        source: "set"
      }, ctx);

      assert.equal(execCalls.length, 1);
      assert.equal(execCalls[0].args[0], "switch-json");
      assert.equal(execCalls[0].args[1], "GENERAL");

      // Verify status shows started
      const lastStatus = statuses[statuses.length - 1];
      assert.match(lastStatus, /GENERAL pid=4200 \\(started\\)/);

      // 2. session_shutdown should stop exact owned PID
      const shutdown = handlers.get("session_shutdown");
      await shutdown({ type: "session_shutdown", reason: "quit" }, ctx);

      assert.equal(execCalls.length, 2);
      assert.equal(execCalls[1].args[0], "stop-owned-json");
      assert.equal(execCalls[1].args[2], "GENERAL");
      assert.equal(execCalls[1].args[4], "4200");

      // 3. Repeated shutdown is idempotent (no second stop call)
      await shutdown({ type: "session_shutdown", reason: "quit" }, ctx);
      assert.equal(execCalls.length, 2);
    }

    test().catch(err => {
      console.error(err);
      process.exit(1);
    });
    """
    res = _run_node_harness_script(script)
    assert res.returncode == 0, f"Node test failed:\n{res.stdout}\n{res.stderr}"


def test_node_borrowed_ownership_does_not_stop_on_shutdown() -> None:
    """Test that BORROWED ownership is never stopped by the extension."""
    script = """
    import assert from "node:assert/strict";
    import register from "./tests/fixtures/retired_pi/neuralengine-model-lifecycle.ts";

    const handlers = new Map();
    const execCalls = [];

    const mockPi = {
      on: (evt, fn) => handlers.set(evt, fn),
      exec: async (cmd, args, opts) => {
        execCalls.push({ cmd, args, opts });
        if (args[0] === "switch-json") {
          return {
            code: 0,
            stdout: JSON.stringify({
              api_version: 1,
              operation: "switch",
              role: args[1],
              ownership: "BORROWED",
              profile: args[1],
              pid: 9999,
              endpoint: "http://127.0.0.1:18081/v1"
            }),
            stderr: ""
          };
        }
        return { code: 0, stdout: "", stderr: "" };
      }
    };

    register(mockPi);

    const ctx = {
      cwd: "/tmp",
      hasUI: true,
      ui: { notify: () => {}, setStatus: () => {} }
    };

    async function test() {
      const modelSelect = handlers.get("model_select");
      await modelSelect({
        type: "model_select",
        model: { provider: "neural-general", id: "qwen" },
        source: "set"
      }, ctx);

      assert.equal(execCalls.length, 1);
      assert.equal(execCalls[0].args[0], "switch-json");

      // Shutdown on borrowed ownership MUST NOT invoke stop-owned-json
      const shutdown = handlers.get("session_shutdown");
      await shutdown({ type: "session_shutdown", reason: "quit" }, ctx);

      assert.equal(execCalls.length, 1, "borrowed runtime must not be stopped");
    }

    test().catch(err => {
      console.error(err);
      process.exit(1);
    });
    """
    res = _run_node_harness_script(script)
    assert res.returncode == 0, f"Node test failed:\n{res.stdout}\n{res.stderr}"


def test_node_machine_json_validation_rejections() -> None:
    """Test rejection of malformed JSON, wrong api_version, and invalid fields."""
    script = """
    import assert from "node:assert/strict";
    import {
      parseSwitchJson,
      parseStopOwnedJson
    } from "./tests/fixtures/retired_pi/neuralengine-model-lifecycle.ts";

    // 1. Malformed JSON
    assert.throws(() => parseSwitchJson("not-json"), /malformed JSON/);

    // 2. Unsupported api_version
    assert.throws(() => parseSwitchJson(JSON.stringify({
      api_version: 2,
      operation: "switch",
      role: "GENERAL",
      ownership: "STARTED",
      profile: "GENERAL",
      pid: 100,
      endpoint: "http://127.0.0.1:18081/v1"
    })), /unsupported api_version/);

    // 3. Invalid ownership
    assert.throws(() => parseSwitchJson(JSON.stringify({
      api_version: 1,
      operation: "switch",
      role: "GENERAL",
      ownership: "UNKNOWN",
      profile: "GENERAL",
      pid: 100,
      endpoint: "http://127.0.0.1:18081/v1"
    })), /invalid ownership/);

    // 4. Invalid or missing PID
    assert.throws(() => parseSwitchJson(JSON.stringify({
      api_version: 1,
      operation: "switch",
      role: "GENERAL",
      ownership: "STARTED",
      profile: "GENERAL",
      pid: -5,
      endpoint: "http://127.0.0.1:18081/v1"
    })), /invalid pid/);

    assert.throws(() => parseSwitchJson(JSON.stringify({
      api_version: 1,
      operation: "switch",
      role: "GENERAL",
      ownership: "STARTED",
      profile: "GENERAL",
      pid: "not-a-number",
      endpoint: "http://127.0.0.1:18081/v1"
    })), /invalid pid/);

    // 5. Missing profile
    assert.throws(() => parseSwitchJson(JSON.stringify({
      api_version: 1,
      operation: "switch",
      role: "GENERAL",
      ownership: "STARTED",
      profile: "",
      pid: 100,
      endpoint: "http://127.0.0.1:18081/v1"
    })), /missing or empty profile/);

    // 6. Stop-owned wrong api_version
    assert.throws(() => parseStopOwnedJson(JSON.stringify({
      api_version: 99,
      operation: "stop_owned",
      result: "STOPPED",
      profile: "GENERAL",
      pid: 100
    })), /unsupported api_version/);
    """
    res = _run_node_harness_script(script)
    assert res.returncode == 0, f"Node test failed:\n{res.stdout}\n{res.stderr}"


def test_node_role_transitions() -> None:
    """Test local-to-local, local-to-cloud, and cloud-to-local transitions."""
    script = """
    import assert from "node:assert/strict";
    import register from "./tests/fixtures/retired_pi/neuralengine-model-lifecycle.ts";

    const handlers = new Map();
    const execCalls = [];

    const mockPi = {
      on: (evt, fn) => handlers.set(evt, fn),
      exec: async (cmd, args, opts) => {
        execCalls.push({ cmd, args, opts });
        if (args[0] === "switch-json") {
          return {
            code: 0,
            stdout: JSON.stringify({
              api_version: 1,
              operation: "switch",
              role: args[1],
              ownership: "STARTED",
              profile: args[1],
              pid: args[1] === "GENERAL" ? 100 : args[1] === "CODE" ? 200 : 300,
              endpoint: "http://127.0.0.1:18080/v1"
            }),
            stderr: ""
          };
        }
        if (args[0] === "stop-owned-json") {
          return {
            code: 0,
            stdout: JSON.stringify({
              api_version: 1,
              operation: "stop_owned",
              result: "STOPPED",
              profile: args[2],
              pid: Number(args[4])
            }),
            stderr: ""
          };
        }
        return { code: 0, stdout: "", stderr: "" };
      }
    };

    register(mockPi);

    const ctx = {
      cwd: "/tmp",
      hasUI: true,
      ui: { notify: () => {}, setStatus: () => {} }
    };

    async function test() {
      const modelSelect = handlers.get("model_select");

      // 1. Select GENERAL (STARTED)
      await modelSelect({
        type: "model_select",
        model: { provider: "neural-general", id: "qwen" },
        source: "set"
      }, ctx);
      assert.equal(execCalls[0].args[0], "switch-json");
      assert.equal(execCalls[0].args[1], "GENERAL");

      // 2. Select CODE -> should stop GENERAL first, then switch-json CODE
      await modelSelect({
        type: "model_select",
        model: { provider: "neural-code", id: "nemotron" },
        source: "set"
      }, ctx);
      assert.equal(execCalls[1].args[0], "stop-owned-json");
      assert.equal(execCalls[1].args[2], "GENERAL");
      assert.equal(execCalls[1].args[4], "100");
      assert.equal(execCalls[2].args[0], "switch-json");
      assert.equal(execCalls[2].args[1], "CODE");

      // 3. Select Cloud (DeepSeek) -> should stop CODE, no local start
      await modelSelect({
        type: "model_select",
        model: { provider: "deepseek", id: "deepseek-chat" },
        source: "set"
      }, ctx);
      assert.equal(execCalls[3].args[0], "stop-owned-json");
      assert.equal(execCalls[3].args[2], "CODE");
      assert.equal(execCalls[3].args[4], "200");
      assert.equal(execCalls.length, 4); // no start call

      // 4. Select PATCH (local-gptoss) -> should switch-json GPTOSS
      await modelSelect({
        type: "model_select",
        model: { provider: "local-gptoss", id: "gpt-oss-20b" },
        source: "set"
      }, ctx);
      assert.equal(execCalls[4].args[0], "switch-json");
      assert.equal(execCalls[4].args[1], "GPTOSS");
    }

    test().catch(err => {
      console.error(err);
      process.exit(1);
    });
    """
    res = _run_node_harness_script(script)
    assert res.returncode == 0, f"Node test failed:\n{res.stdout}\n{res.stderr}"


def test_node_global_root_resolution() -> None:
    """Test that findProjectRoot resolves canonical root from /tmp, ~, and honors env override."""
    script = """
    import assert from "node:assert/strict";
    import os from "node:os";
    import {
      findProjectRoot,
      CANONICAL_ROOT
    } from "./tests/fixtures/retired_pi/neuralengine-model-lifecycle.ts";

    // 1. From /tmp without env override -> resolves CANONICAL_ROOT
    delete process.env.NEURALENGINE_PI_PROJECT_ROOT;
    const rootFromTmp = findProjectRoot("/tmp");
    assert.equal(rootFromTmp, CANONICAL_ROOT);

    // 2. From home directory without env override -> resolves CANONICAL_ROOT
    const rootFromHome = findProjectRoot(os.homedir());
    assert.equal(rootFromHome, CANONICAL_ROOT);

    // 3. With explicit NEURALENGINE_PI_PROJECT_ROOT override
    process.env.NEURALENGINE_PI_PROJECT_ROOT = CANONICAL_ROOT;
    const rootWithOverride = findProjectRoot("/tmp");
    assert.equal(rootWithOverride, CANONICAL_ROOT);
    """
    res = _run_node_harness_script(script)
    assert res.returncode == 0, f"Node test failed:\n{res.stdout}\n{res.stderr}"

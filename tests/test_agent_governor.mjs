import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { test } from "node:test";

import { AgentGovernor, parseGovernorPolicy, parseQualificationPolicy, policySha256, classifyCommand, classifyGitCommand } from "../control-plane/governor.ts";
import registerPiExtension, { guardToolCall } from "../.pi/extensions/neuralengine-guard.ts";

const TEST_COMMAND = "uv run pytest tests/test_agent_governor.py -q";

test("Pi auto-discovery sees only the extension entrypoint", () => {
  const extensionFiles = readdirSync(new URL("../.pi/extensions/", import.meta.url))
    .filter((file) => /\.(?:[cm]?js|ts)$/.test(file))
    .sort();

  assert.deepEqual(extensionFiles, ["neuralengine-guard.ts"]);
  assert.equal(existsSync(new URL("../control-plane/governor.ts", import.meta.url)), true);
  const coreSource = readFileSync(new URL("../control-plane/governor.ts", import.meta.url), "utf8");
  const adapterSource = readFileSync(new URL("../.pi/extensions/neuralengine-guard.ts", import.meta.url), "utf8");
  assert.doesNotMatch(coreSource, /@earendil-works\/pi-coding-agent|\.pi\/|session_compact|"tool_call"/);
  assert.match(adapterSource, /\.\.\/\.\.\/control-plane\/governor\.ts/);
});

function repository(t) {
  const root = mkdtempSync(path.join(os.tmpdir(), "neuralengine-governor-"));
  mkdirSync(path.join(root, "src"));
  mkdirSync(path.join(root, "tests"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  return root;
}

function policy(overrides = {}) {
  return parseGovernorPolicy({
    ALLOWED_READ_FILES: ["src/worker.py", "tests/test_worker.py"],
    ALLOWED_EDIT_FILES: ["src/worker.py", "tests/test_worker.py"],
    VALIDATION_COMMANDS: [TEST_COMMAND],
    TEST_COMMANDS: [TEST_COMMAND],
    ...overrides,
  });
}

function governor(root, overrides = {}, history = [], save = () => {}) {
  return new AgentGovernor(policy(overrides), root, history, save);
}

function validation(instance, id, evidence, failed = true) {
  assert.equal(instance.handleEvent({ type: "TOOL_PRE", operation: "SHELL", callId: id, command: TEST_COMMAND }).allowed, true);
  return instance.handleEvent({ type: "TOOL_POST", operation: "SHELL", callId: id, failed, evidenceReference: evidence });
}

function setEnvironment(t, name, value) {
  const previous = process.env[name];
  if (value === undefined) delete process.env[name];
  else process.env[name] = value;
  t.after(() => {
    if (previous === undefined) delete process.env[name];
    else process.env[name] = previous;
  });
}

function piHarness(t, root, {
  boundedMode,
  policyPath,
  startSession = true,
  workingDirectory = root,
  projectRoot,
} = {}) {
  setEnvironment(t, "NEURAL_PI_BOUNDED_CODE", boundedMode);
  setEnvironment(t, "NEURAL_PI_POLICY_FILE", policyPath);
  setEnvironment(t, "NEURALENGINE_PI_PROJECT_ROOT", projectRoot);
  const handlers = new Map();
  const commands = new Map();
  const appended = [];
  const statuses = [];
  const notices = [];
  let shutdowns = 0;
  let aborted = false;
  registerPiExtension({
    on: (event, handler) => handlers.set(event, handler),
    registerCommand: (name, options) => commands.set(name, options),
    appendEntry: (customType, data) => appended.push({ customType, data }),
  });
  const context = {
    cwd: workingDirectory,
    sessionManager: { getBranch: () => [] },
    ui: {
      setStatus: (_key, status) => statuses.push(status),
      notify: (message) => notices.push(message),
    },
    abort: () => { aborted = true; },
    shutdown: () => { shutdowns += 1; },
  };
  if (startSession) handlers.get("session_start")({}, context);
  return {
    handlers,
    commands,
    appended,
    statuses,
    notices,
    context,
    get shutdowns() { return shutdowns; },
    get aborted() { return aborted; },
  };
}

test("edits outside the explicit allowlist are rejected", (t) => {
  const root = repository(t);
  writeFileSync(path.join(root, "src/other.py"), "value = 1\n");
  const instance = governor(root);
  const result = instance.checkToolCall("edit", {
    path: "src/other.py",
    edits: [{ oldText: "value = 1", newText: "value = 2" }],
  }, "edit-1");
  assert.equal(result.allowed, false);
  assert.match(result.reason, /outside ALLOWED_EDIT_FILES/);
  assert.equal(readFileSync(path.join(root, "src/other.py"), "utf8"), "value = 1\n");
});

test("unauthorized new file creation is rejected before mutation", (t) => {
  const root = repository(t);
  const instance = governor(root);
  const result = instance.checkToolCall("write", {
    path: "src/worker.py",
    content: "value = 1\n",
  }, "write-new");
  assert.equal(result.allowed, false);
  assert.match(result.reason, /new file creation is not authorized/);
  assert.equal(existsSync(path.join(root, "src/worker.py")), false);
});

test("a 923-line test replacement is rejected before mutation", (t) => {
  const root = repository(t);
  const target = path.join(root, "tests/test_worker.py");
  const original = Array.from({ length: 923 }, (_, index) => `assert value_${index} == ${index}`).join("\n") + "\n";
  const replacement = Array.from({ length: 50 }, (_, index) => `assert value == ${index}`).join("\n") + "\n";
  writeFileSync(target, original);
  const instance = governor(root, { MAX_DELETED_LINES: 2_000 });
  const result = instance.checkToolCall("write", { path: "tests/test_worker.py", content: replacement }, "shrink");
  assert.equal(result.allowed, false);
  assert.match(result.reason, /MAX_TEST_FILE_SHRINK_PERCENT/);
  assert.equal(readFileSync(target, "utf8"), original);
});

test("a deletion below the configured threshold is allowed", (t) => {
  const root = repository(t);
  const target = path.join(root, "src/worker.py");
  writeFileSync(target, "one\ntwo\nthree\nfour\n");
  const instance = governor(root, { MAX_DELETED_LINES: 2 });
  const input = { path: "src/worker.py", edits: [{ oldText: "two\nthree\n", newText: "two\n" }] };
  const result = instance.checkToolCall("edit", input, "delete-1");
  assert.equal(result.allowed, true);
  writeFileSync(target, "one\ntwo\nfour\n");
  instance.recordToolResult("edit", input, "delete-1", false);
  assert.deepEqual(instance.modifiedFiles, [target]);
});

test("an authorized existing file can be edited", (t) => {
  const root = repository(t);
  const target = path.join(root, "src/worker.py");
  writeFileSync(target, "value = 1\n");
  const instance = governor(root);
  const input = { path: "src/worker.py", edits: [{ oldText: "value = 1", newText: "value = 2" }] };
  const result = instance.checkToolCall("edit", input, "edit-allowed");
  assert.equal(result.allowed, true);
  writeFileSync(target, "value = 2\n");
  instance.recordToolResult("edit", input, "edit-allowed", false);
  assert.equal(instance.status().includes("files=1"), true);
});

test("parallel edits to one file do not pass duplicate pre-write checks", (t) => {
  const root = repository(t);
  writeFileSync(path.join(root, "src/worker.py"), "value = 1\n");
  const instance = governor(root);
  const first = { path: "src/worker.py", edits: [{ oldText: "value = 1", newText: "value = 2" }] };
  const second = { path: "src/worker.py", edits: [{ oldText: "value = 1", newText: "value = 3" }] };
  assert.equal(instance.checkToolCall("edit", first, "edit-first").allowed, true);
  const secondResult = instance.checkToolCall("edit", second, "edit-second");
  assert.equal(secondResult.allowed, false);
  assert.match(secondResult.reason, /mutation for this file is still pending/);
});

test("CODE changes cannot receive GREEN without successful post-edit tests", (t) => {
  const root = repository(t);
  const target = path.join(root, "src/worker.py");
  writeFileSync(target, "value = 1\n");
  const instance = governor(root);
  const edit = { path: "src/worker.py", edits: [{ oldText: "value = 1", newText: "value = 2" }] };
  assert.equal(instance.checkToolCall("edit", edit, "edit-green").allowed, true);
  writeFileSync(target, "value = 2\n");
  instance.recordToolResult("edit", edit, "edit-green", false);
  assert.equal(instance.isGreen, false);
  assert.equal(instance.checkToolCall("bash", { command: "the model says tests passed" }, "claim").allowed, false);
  assert.equal(instance.isGreen, false);

  assert.equal(instance.checkToolCall("bash", { command: TEST_COMMAND }, "test-pass").allowed, true);
  instance.recordToolResult("bash", { command: TEST_COMMAND }, "test-pass", false);
  assert.equal(instance.isGreen, true);
});

test("failed validation increments the correction count", (t) => {
  const root = repository(t);
  const instance = governor(root);
  assert.equal(instance.checkToolCall("bash", { command: TEST_COMMAND }, "test-fail").allowed, true);
  instance.recordToolResult("bash", { command: TEST_COMMAND }, "test-fail", true);
  assert.equal(instance.correctionCycles, 1);
});

test("correction budget exhaustion produces a controlled STOP", (t) => {
  const root = repository(t);
  const instance = governor(root, { MAX_CORRECTION_CYCLES: 2 });
  for (let index = 1; index <= 3; index += 1) {
    const id = `test-fail-${index}`;
    assert.equal(instance.checkToolCall("bash", { command: TEST_COMMAND }, id).allowed, true);
    instance.recordToolResult("bash", { command: TEST_COMMAND }, id, true);
  }
  assert.equal(instance.stopped, true);
  assert.match(instance.stopReason, /correction budget exhausted/);
  assert.equal(instance.checkToolCall("read", { path: "src/worker.py" }, "after-stop").allowed, false);
});

test("compaction budget exhaustion produces a controlled STOP", (t) => {
  const root = repository(t);
  const instance = governor(root, { MAX_COMPACTIONS: 1 });
  instance.recordCompaction();
  assert.equal(instance.stopped, false);
  instance.recordCompaction();
  assert.equal(instance.stopped, true);
  assert.match(instance.stopReason, /compaction budget exhausted/);
});

test("Governor counters survive session reconstruction and reject changed policy", (t) => {
  const root = repository(t);
  const snapshots = [];
  const first = governor(root, {}, [], (snapshot) => snapshots.push(snapshot));
  first.recordCompaction();
  const resumed = new AgentGovernor(policy(), root, snapshots);
  assert.equal(resumed.compactions, 1);
  const changed = new AgentGovernor(policy({ MAX_COMPACTIONS: 3 }), root, snapshots);
  assert.equal(changed.stopped, true);
  assert.match(changed.stopReason, /policy changed/);
});

test("bounded CODE blocks shell mutation and broad repository reconnaissance", (t) => {
  const root = repository(t);
  const instance = governor(root);
  assert.equal(instance.checkToolCall("bash", { command: "python -c 'open(\"src/worker.py\", \"w\")'" }, "shell").allowed, false);
  assert.equal(instance.checkToolCall("find", { path: "." }, "find").allowed, false);
  assert.equal(instance.checkToolCall("grep", { pattern: "TODO" }, "grep").allowed, false);
});

test("symlink paths are rejected even when their resolved target is in the repository", (t) => {
  const root = repository(t);
  const target = path.join(root, "src/worker.py");
  const other = path.join(root, "src/other.py");
  writeFileSync(other, "value = 1\n");
  symlinkSync(other, target);
  assert.throws(() => governor(root), /Policy path does not resolve inside the repository/);
});

test("Git mutation commands cannot be added to the inspection allowlist", () => {
  assert.throws(
    () => policy({ SAFE_GIT_COMMANDS: ["git reset --hard"] }),
    /built-in read-only inspection commands/,
  );
});

test("validation policy rejects shell composition and non-test claims", () => {
  assert.throws(
    () => policy({ VALIDATION_COMMANDS: ["uv run pytest tests/test_worker.py -q; touch /tmp/pwned"], TEST_COMMANDS: ["uv run pytest tests/test_worker.py -q; touch /tmp/pwned"] }),
    /single read-only/,
  );
  assert.throws(
    () => policy({ VALIDATION_COMMANDS: ["echo tests passed"], TEST_COMMANDS: ["echo tests passed"] }),
    /single read-only/,
  );
  assert.throws(
    () => policy({ VALIDATION_COMMANDS: ["uv run pytest --collect-only"], TEST_COMMANDS: ["uv run pytest --collect-only"] }),
    /single read-only/,
  );
});

test("failed state persistence forces STOP instead of losing safety state", (t) => {
  const root = repository(t);
  const instance = new AgentGovernor(policy(), root, [], () => {
    throw new Error("session append failed");
  });
  assert.equal(instance.stopped, true);
  assert.match(instance.stopReason, /persistence failed/);
  assert.equal(instance.isGreen, false);
});

test("bounded CODE with a missing policy is rejected before prompt or tool execution", (t) => {
  const root = repository(t);
  const pi = piHarness(t, root, { boundedMode: "1" });
  assert.equal(pi.shutdowns, 1);
  assert.match(pi.statuses.at(-1), /CODE governor: STOP/);

  let modelExecutions = 0;
  const input = pi.handlers.get("input")({ type: "input", text: "implement this", source: "interactive" }, pi.context);
  if (input?.action !== "handled") modelExecutions += 1;
  assert.equal(input.action, "handled");
  assert.equal(modelExecutions, 0);

  let toolExecutions = 0;
  const blocked = pi.handlers.get("tool_call")({
    toolName: "bash",
    toolCallId: "no-policy",
    input: { command: TEST_COMMAND },
  }, pi.context);
  if (!blocked?.block) toolExecutions += 1;
  assert.equal(blocked.block, true);
  assert.equal(toolExecutions, 0);
});

test("bounded CODE with an unreadable policy is rejected", (t) => {
  const root = repository(t);
  const policyDirectory = path.join(root, "policy-directory");
  mkdirSync(policyDirectory);
  const pi = piHarness(t, root, { boundedMode: "1", policyPath: policyDirectory });
  assert.equal(pi.shutdowns, 1);
  assert.match(pi.statuses.at(-1), /CODE governor: STOP/);
  assert.match(pi.notices.at(-1), /task policy could not be loaded/);
});

test("bounded CODE with an invalid policy is rejected", (t) => {
  const root = repository(t);
  const policyFile = path.join(root, "invalid-policy.json");
  writeFileSync(policyFile, "{invalid json");
  const pi = piHarness(t, root, { boundedMode: "1", policyPath: policyFile });
  assert.equal(pi.shutdowns, 1);
  assert.match(pi.statuses.at(-1), /CODE governor: STOP/);
});

test("bounded CODE with a structurally invalid policy is rejected", (t) => {
  const root = repository(t);
  const policyFile = path.join(root, "invalid-policy.json");
  writeFileSync(policyFile, JSON.stringify({ ...policy(), MAX_COMPACTIONS: -1 }));
  const pi = piHarness(t, root, { boundedMode: "1", policyPath: policyFile });
  assert.equal(pi.shutdowns, 1);
  assert.match(pi.notices.at(-1), /MAX_COMPACTIONS must be a non-negative integer/);
});

test("an empty policy path is a bounded CODE request and is rejected", (t) => {
  const root = repository(t);
  const pi = piHarness(t, root, { policyPath: "" });
  assert.equal(pi.shutdowns, 1);
  assert.match(pi.notices.at(-1), /NEURAL_PI_POLICY_FILE must not be empty/);
});

test("bounded CODE with a valid policy starts under Governor control", (t) => {
  const root = repository(t);
  const target = path.join(root, "src/worker.py");
  const policyFile = path.join(root, "task-policy.json");
  writeFileSync(target, "value = 1\n");
  writeFileSync(policyFile, JSON.stringify(policy()));
  const pi = piHarness(t, root, { boundedMode: "1", policyPath: policyFile });
  assert.equal(pi.shutdowns, 0);
  assert.match(pi.statuses.at(-1), /CODE governor: GREEN/);
  const result = pi.handlers.get("tool_call")({
    toolName: "edit",
    toolCallId: "valid-policy-edit",
    input: { path: "src/worker.py", edits: [{ oldText: "value = 1", newText: "value = 2" }] },
  }, pi.context);
  assert.equal(result, undefined);
});

test("bounded CODE from a nested cwd resolves policy paths from project root", (t) => {
  const root = repository(t);
  const nested = path.join(root, "src");
  const target = path.join(nested, "worker.py");
  const policyFile = path.join(root, "task-policy.json");
  writeFileSync(target, "value = 1\n");
  writeFileSync(policyFile, JSON.stringify(policy()));
  const pi = piHarness(t, root, {
    boundedMode: "1",
    policyPath: "task-policy.json",
    workingDirectory: nested,
    projectRoot: root,
  });

  const result = pi.handlers.get("tool_call")({
    toolName: "edit",
    toolCallId: "nested-project-edit",
    input: { path: "worker.py", edits: [{ oldText: "value = 1", newText: "value = 2" }] },
  }, pi.context);

  assert.equal(result, undefined);
  assert.equal(pi.context.cwd, nested);
});

test("invalid project root refuses bounded CODE before tool execution", (t) => {
  const root = repository(t);
  const otherRoot = mkdtempSync(path.join(os.tmpdir(), "neuralengine-other-root-"));
  t.after(() => rmSync(otherRoot, { recursive: true, force: true }));
  const policyFile = path.join(root, "task-policy.json");
  writeFileSync(policyFile, JSON.stringify(policy()));
  const pi = piHarness(t, root, {
    boundedMode: "1",
    policyPath: policyFile,
    projectRoot: otherRoot,
  });

  assert.equal(pi.shutdowns, 1);
  assert.match(pi.notices.at(-1), /does not contain the Pi working directory/);
  const result = pi.handlers.get("tool_call")({
    toolName: "write",
    toolCallId: "invalid-root-write",
    input: { path: "src/worker.py", content: "value = 1\n" },
  }, pi.context);
  assert.equal(result.block, true);
  assert.equal(result.terminate, true);
});

test("a bounded tool call before startup policy validation fails closed", (t) => {
  const root = repository(t);
  const pi = piHarness(t, root, { boundedMode: "1", startSession: false });
  const result = pi.handlers.get("tool_call")({
    toolName: "write",
    toolCallId: "before-session-start",
    input: { path: "src/worker.py", content: "value = 1\n" },
  }, pi.context);
  assert.equal(result.block, true);
  assert.equal(result.terminate, true);
  assert.equal(pi.shutdowns, 1);
  pi.handlers.get("agent_start")({}, pi.context);
  assert.equal(pi.aborted, true);
});

test("non-bounded workflows keep their existing startup and tool behavior", (t) => {
  const root = repository(t);
  const pi = piHarness(t, root);
  assert.equal(pi.shutdowns, 0);
  assert.match(pi.statuses.at(-1), /inactive/);
  const input = pi.handlers.get("input")({ type: "input", text: "hello", source: "interactive" }, pi.context);
  assert.equal(input, undefined);
  pi.handlers.get("agent_start")({}, pi.context);
  assert.equal(pi.aborted, false);
  const result = pi.handlers.get("tool_call")({
    toolName: "write",
    toolCallId: "non-bounded-write",
    input: { path: "src/worker.py", content: "value = 1\n" },
  }, pi.context);
  assert.equal(result, undefined);
});

test("Pi hooks load scope, record tool evidence, and expose Governor status", (t) => {
  const root = repository(t);
  const target = path.join(root, "src/worker.py");
  const policyFile = path.join(root, "task-policy.json");
  writeFileSync(target, "value = 1\n");
  writeFileSync(policyFile, JSON.stringify(policy()));
  const pi = piHarness(t, root, { policyPath: policyFile });
  const { handlers, commands, appended, statuses, notices, context } = pi;
  assert.match(statuses.at(-1), /CODE governor: GREEN/);
  const outOfScope = handlers.get("tool_call")({
    toolName: "write",
    toolCallId: "blocked-write",
    input: { path: "src/other.py", content: "value = 2\n" },
  }, context);
  assert.equal(outOfScope.block, true);

  const edit = { path: "src/worker.py", edits: [{ oldText: "value = 1", newText: "value = 2" }] };
  const approvedCall = {
    toolName: "edit",
    toolCallId: "edit-result",
    input: edit,
  };
  assert.equal(handlers.get("tool_call")(approvedCall, context), undefined);
  assert.throws(() => { approvedCall.input.path = "src/other.py"; }, TypeError);
  writeFileSync(target, "value = 2\n");
  handlers.get("tool_result")({
    toolName: "edit",
    toolCallId: "edit-result",
    input: edit,
    isError: false,
  }, context);
  assert.match(statuses.at(-1), /NOT GREEN/);

  handlers.get("tool_call")({
    toolName: "bash",
    toolCallId: "test-result",
    input: { command: TEST_COMMAND },
  }, context);
  handlers.get("tool_result")({
    toolName: "bash",
    toolCallId: "test-result",
    input: { command: TEST_COMMAND },
    isError: false,
  }, context);
  commands.get("governor").handler("status", context);
  assert.match(notices.at(-1), /Governor GREEN/);
  assert.equal(appended.some((entry) => entry.customType === "neuralengine-agent-governor-v0"), true);
  assert.equal(pi.aborted, false);
});

test("Pi final claim is recorded without changing the system verdict", (t) => {
  const root = repository(t);
  const policyFile = path.join(root, "policy.json");
  writeFileSync(policyFile, JSON.stringify({ ...policy(), RUN_ID: "pi-claim", WORKSPACE_ROOT: root }));
  const pi = piHarness(t, root, { policyPath: policyFile });
  pi.handlers.get("agent_end")({ messages: [{ role: "assistant", content: [{ type: "text", text: "DONE" }] }] }, pi.context);
  assert.match(pi.statuses.at(-1), /NOT GREEN/);
  assert.equal(pi.appended.some((entry) => entry.data.modelClaim === "DONE"), true);
});

test("existing Pi Brain and Git guards remain active", (t) => {
  const root = repository(t);
  const neuralHome = process.env.NEURAL_HOME ?? path.join(root, ".neural");
  const brainPath = path.join(neuralHome, "brain", "knowledge", "record.json");
  const gitPath = path.join(root, ".git", "index");
  assert.match(guardToolCall("write", { path: brainPath }, root, root), /Brain writes/);
  assert.match(guardToolCall("write", { path: gitPath }, root, root), /Git metadata/);
  assert.match(guardToolCall("bash", { command: "git commit -m forbidden" }, root, root), /Git staging/);
});

test("the Brain and Git path guards account for nested working directories", (t) => {
  const root = repository(t);
  const nested = path.join(root, "src");
  assert.match(
    guardToolCall("write", { path: "../.git/index" }, nested, root, root),
    /Git metadata/,
  );
});

test("v1 policy identity is canonical and binds a named workspace", (t) => {
  const root = repository(t);
  const raw = { ...policy(), RUN_ID: "m3-run", WORKSPACE_ROOT: root };
  const first = parseGovernorPolicy(raw);
  const reordered = parseGovernorPolicy(Object.fromEntries(Object.entries(raw).reverse()));
  assert.equal(policySha256(first), policySha256(reordered));
  assert.throws(() => parseGovernorPolicy({ ...raw, WORKSPACE_ROOT: undefined }), /WORKSPACE_ROOT/);
  const revision = parseGovernorPolicy({ ...raw, POLICY_REVISION: 2, MODE: "EXPANDED_EXECUTE", PREVIOUS_POLICY_SHA256: policySha256(first), EVIDENCE_PACK_REF: ".agent-work/evidence/task-1.md", EVIDENCE_PACK_SHA256: "0".repeat(64), ALLOWED_EDIT_FILES: [...first.ALLOWED_EDIT_FILES, "src/other.py"] });
  assert.notEqual(policySha256(revision), policySha256(first));
  const run = new AgentGovernor(first, root);
  assert.equal(run.policyHash, policySha256(first));
  assert.equal(run.systemVerdict, "VALIDATION_PENDING");
});

test("neutral events separate model claim, scope request, and system verdict", (t) => {
  const root = repository(t);
  writeFileSync(path.join(root, "src/other.py"), "value = 1\n");
  const instance = new AgentGovernor(parseGovernorPolicy({ ...policy(), RUN_ID: "task-1", WORKSPACE_ROOT: root }), root);
  instance.handleEvent({ type: "FINAL_CLAIM", claim: "DONE" });
  assert.equal(instance.systemVerdict, "VALIDATION_PENDING");
  const denied = instance.handleEvent({ type: "TOOL_PRE", operation: "EDIT", callId: "out", input: { path: "src/other.py" }, evidenceReference: "traceback-1" });
  assert.equal(denied.allowed, false);
  assert.equal(denied.outcome, "REQUEST_SCOPE_EXPANSION");
  assert.equal(instance.scopeExpansionRequests[0].runId, "task-1");
  assert.equal(instance.checkToolCall("write", { path: "src/other.py", content: "value = 2\n" }, "still-out").allowed, false);
  assert.equal(instance.auditRecord().model_claim, "DONE");
  assert.equal(instance.auditRecord().system_verdict, "VALIDATION_PENDING");
  assert.equal(instance.handleEvent({ type: "TOOL_PRE", operation: "SHELL", callId: "validate", command: TEST_COMMAND }).allowed, true);
  instance.handleEvent({ type: "TOOL_POST", operation: "SHELL", callId: "validate", failed: false, evidenceReference: "tool-result-1" });
  assert.equal(instance.systemVerdict, "GREEN");
});

test("execution modes and PATCH budget constrain mutation without blocking discovery", (t) => {
  const root = repository(t);
  const file = path.join(root, "src/worker.py");
  writeFileSync(file, "value = 1\n");
  const discover = new AgentGovernor(parseGovernorPolicy({ ...policy(), MODE: "DISCOVER" }), root);
  assert.equal(discover.checkToolCall("read", { path: "src/worker.py" }, "read").allowed, true);
  assert.equal(discover.checkToolCall("write", { path: "src/worker.py", content: "value = 2\n" }, "write").allowed, false);
  const bounded = governor(root);
  assert.equal(bounded.policy.MODE, "BOUNDED_EXECUTE");
  assert.equal(bounded.policy.ROLE, "CODE");
  assert.equal(bounded.checkToolCall("edit", { path: "src/worker.py", edits: [{ oldText: "value = 1", newText: "value = 2" }] }, "edit").allowed, true);
  assert.throws(() => policy({ ROLE: "PATCH" }), /ROLE=PATCH requires MODE=PATCH/);
  assert.throws(() => policy({ MODE: "PATCH", MAX_FILES_TOUCHED: 1, MAX_DELETED_LINES: 30 }), /MODE=PATCH requires ROLE=PATCH/);
  assert.throws(() => policy({ ROLE: "PATCH", MODE: "PATCH" }), /PATCH budget/);
  const patchPolicy = policy({ ROLE: "PATCH", MODE: "PATCH", MAX_FILES_TOUCHED: 1, MAX_DELETED_LINES: 30 });
  assert.equal(patchPolicy.MAX_FILES_TOUCHED, 1);
  assert.equal(patchPolicy.MAX_DELETED_LINES, 30);
  const patch = new AgentGovernor(patchPolicy, root);
  assert.equal(patch.checkToolCall("edit", { path: "src/worker.py", edits: [{ oldText: "value = 1", newText: "value = 2" }] }, "patch-edit").allowed, true);
  assert.equal(patch.checkToolCall("bash", { command: "git commit -m bad" }, "patch-commit").allowed, false);
  assert.equal(patch.checkToolCall("bash", { command: "git push" }, "patch-push").allowed, false);
});

test("shell and Git capabilities reject mutations and constrain read paths", (t) => {
  const root = repository(t);
  writeFileSync(path.join(root, "src/worker.py"), "value = 1\n");
  const instance = governor(root);
  assert.equal(classifyCommand("rg value src/worker.py"), "SHELL_READONLY");
  assert.equal(classifyCommand(TEST_COMMAND, [TEST_COMMAND]), "VALIDATION");
  assert.equal(classifyCommand("git status"), "GIT_READ");
  assert.equal(classifyCommand("git reset --hard"), "GIT_MUTATING");
  assert.equal(classifyCommand("rm src/worker.py"), "DELETE");
  assert.equal(instance.checkToolCall("bash", { command: "rg value src/worker.py" }, "rg").allowed, true);
  assert.equal(instance.checkToolCall("bash", { command: "rg value /etc/passwd" }, "escape").allowed, false);
  assert.equal(instance.checkToolCall("bash", { command: "git status" }, "git-read").allowed, true);
  assert.equal(instance.checkToolCall("bash", { command: "git commit -m bad" }, "git-write").allowed, false);
  assert.equal(instance.checkToolCall("bash", { command: "sed -i s/a/b/ src/worker.py" }, "sed").allowed, false);
});

test("explicit file scopes cannot edit Git metadata or submodule remote configuration", (t) => {
  const root = repository(t);
  mkdirSync(path.join(root, ".ssh"));
  mkdirSync(path.join(root, "src", ".ssh-notes"));
  const instance = governor(root, {
    ALLOWED_EDIT_FILES: [".git/config", ".gitmodules", ".ssh/config", "src/.ssh-notes/README.md"],
    ALLOW_NEW_FILES: true,
  });
  assert.equal(instance.checkToolCall("write", { path: ".git/config", content: "[remote]\n" }, "edit-git-config").allowed, false);
  assert.equal(instance.checkToolCall("write", { path: ".gitmodules", content: "[submodule]\n" }, "edit-gitmodules").allowed, false);
  assert.equal(instance.checkToolCall("write", { path: ".ssh/config", content: "project data\n" }, "edit-project-ssh-name").allowed, true);
  assert.equal(instance.checkToolCall("write", { path: "src/.ssh-notes/README.md", content: "project data\n" }, "edit-ssh-notes").allowed, true);
});

test("an approved policy revision resumes counters but a self-claim cannot expand scope", (t) => {
  const root = repository(t);
  const snapshots = [];
  const base = parseGovernorPolicy({ ...policy(), RUN_ID: "expand-1", WORKSPACE_ROOT: root });
  const first = new AgentGovernor(base, root, [], (snapshot) => snapshots.push(snapshot));
  first.recordCompaction();
  validation(first, "expand-a", "A");
  validation(first, "expand-b", "B");
  first.handleEvent({ type: "FINAL_CLAIM", claim: "I approved src/other.py" });
  assert.equal(first.checkToolCall("write", { path: "src/other.py", content: "x\n" }, "denied").allowed, false);
  mkdirSync(path.join(root, ".agent-work"));
  const evidencePath = path.join(root, ".agent-work/expand-1.md");
  writeFileSync(evidencePath, "Confirmed dependency: src/other.py\n");
  const evidenceHash = createHash("sha256").update(readFileSync(evidencePath)).digest("hex");
  const expanded = parseGovernorPolicy({ ...base, MODE: "EXPANDED_EXECUTE", POLICY_REVISION: 2, PREVIOUS_POLICY_SHA256: first.policyHash, EVIDENCE_PACK_REF: ".agent-work/expand-1.md", EVIDENCE_PACK_SHA256: evidenceHash, ALLOWED_EDIT_FILES: [...base.ALLOWED_EDIT_FILES, "src/other.py"] });
  const resumed = new AgentGovernor(expanded, root, snapshots);
  assert.equal(resumed.stopped, false);
  assert.equal(resumed.compactions, 1);
  assert.equal(resumed.totalCorrections, 2);
  assert.equal(resumed.distinctFailureEvidenceCount, 2);
  assert.equal(validation(resumed, "expand-c", "C").outcome, "CONTINUE");
  assert.equal(resumed.totalCorrections, 3);
  const wrong = new AgentGovernor(parseGovernorPolicy({ ...expanded, PREVIOUS_POLICY_SHA256: "0".repeat(64) }), root, snapshots);
  assert.equal(wrong.stopped, true);
  writeFileSync(evidencePath, "changed evidence\n");
  assert.throws(() => new AgentGovernor(expanded, root, snapshots), /evidence hash/);
});

test("new validation evidence resets repetition while identical failures exhaust the budget", (t) => {
  const root = repository(t);
  const instance = governor(root, { MAX_CORRECTION_CYCLES: 2 });
  const outcomes = [];
  for (const [id, evidence] of [["one", "trace-a"], ["two", "trace-b"], ["three", "trace-b"], ["four", "trace-b"]]) {
    instance.handleEvent({ type: "TOOL_PRE", operation: "SHELL", callId: id, command: TEST_COMMAND });
    outcomes.push(instance.handleEvent({ type: "TOOL_POST", operation: "SHELL", callId: id, failed: true, evidenceReference: evidence }).outcome);
  }
  assert.deepEqual(outcomes, ["CONTINUE", "CONTINUE", "REPLAN_REQUIRED", "STOP"]);
  assert.equal(instance.stopped, true);
  assert.match(instance.stopReason, /correction budget/);
});

test("repeated failures replan then stop, while novel failures have a separate total bound", (t) => {
  const root = repository(t);
  const repeated = governor(root, { MAX_REPEATED_FAILURES: 2, MAX_TOTAL_CORRECTIONS: 6 });
  assert.equal(validation(repeated, "a1", "A").outcome, "CONTINUE");
  assert.equal(validation(repeated, "a2", "A").outcome, "REPLAN_REQUIRED");
  assert.equal(validation(repeated, "a3", "A").outcome, "STOP");
  assert.equal(repeated.totalCorrections, 3);
  assert.equal(repeated.repeatedFailures, 2);
  const distinct = governor(root, { MAX_REPEATED_FAILURES: 2, MAX_TOTAL_CORRECTIONS: 6 });
  const outcomes = "ABCDEFG".split("").map((evidence) => validation(distinct, `distinct-${evidence}`, evidence).outcome);
  assert.deepEqual(outcomes, ["CONTINUE", "CONTINUE", "CONTINUE", "CONTINUE", "CONTINUE", "REPLAN_REQUIRED", "STOP"]);
  assert.equal(distinct.distinctFailureEvidenceCount, 7);
  assert.match(distinct.stopReason, /total correction budget/);
});

test("new evidence clears repeat pressure but not total history, and validation can reach GREEN", (t) => {
  const root = repository(t);
  const instance = governor(root, { RUN_ID: "recover-1", WORKSPACE_ROOT: root });
  assert.equal(instance.systemVerdict, "VALIDATION_PENDING");
  validation(instance, "a1", "A");
  assert.equal(validation(instance, "a2", "A").outcome, "REPLAN_REQUIRED");
  assert.equal(validation(instance, "b", "B").outcome, "CONTINUE");
  assert.equal(instance.repeatedFailures, 0);
  assert.equal(instance.totalCorrections, 3);
  assert.equal(instance.distinctFailureEvidenceCount, 2);
  assert.equal(validation(instance, "pass", "pass", false).outcome, "CONTINUE");
  assert.equal(instance.systemVerdict, "GREEN");
  assert.equal(instance.auditRecord().total_corrections, 3);
  assert.equal(instance.auditRecord().distinct_failure_evidence_count, 2);
  assert.equal(instance.auditRecord().repeated_failures, 0);
  assert.equal(validation(instance, "later-fail", "C").outcome, "CONTINUE");
  assert.equal(instance.systemVerdict, "VALIDATION_PENDING");
  assert.equal(instance.totalCorrections, 4);
  assert.equal(validation(instance, "recover-again", "pass", false).outcome, "CONTINUE");
  assert.equal(instance.systemVerdict, "GREEN");
});

test("distinct failures followed by a pass reach GREEN with cumulative correction history", (t) => {
  const root = repository(t);
  const instance = governor(root, { RUN_ID: "ab-pass", WORKSPACE_ROOT: root });
  validation(instance, "a", "A");
  validation(instance, "b", "B");
  assert.equal(validation(instance, "pass", "pass", false).outcome, "CONTINUE");
  assert.equal(instance.systemVerdict, "GREEN");
  assert.equal(instance.totalCorrections, 2);
  assert.equal(instance.distinctFailureEvidenceCount, 2);
});

test("snapshot and resume preserve correction history and repeat pressure", (t) => {
  const root = repository(t);
  const snapshots = [];
  const first = governor(root, { RUN_ID: "resume-1", WORKSPACE_ROOT: root }, [], (snapshot) => snapshots.push(snapshot));
  validation(first, "a1", "A");
  validation(first, "a2", "A");
  assert.equal(snapshots.at(-1).totalCorrections, 2);
  assert.equal(snapshots.at(-1).repeatedFailures, 1);
  assert.equal(snapshots.at(-1).distinctFailureEvidenceCount, 1);
  const resumed = governor(root, { RUN_ID: "resume-1", WORKSPACE_ROOT: root }, snapshots);
  assert.equal(resumed.totalCorrections, 2);
  assert.equal(resumed.repeatedFailures, 1);
  assert.equal(resumed.distinctFailureEvidenceCount, 1);
  assert.equal(validation(resumed, "a3", "A").outcome, "STOP");
});

test("pre-hardening snapshots reconstruct total corrections from validation history", (t) => {
  const root = repository(t);
  const snapshots = [];
  const first = governor(root, {}, [], (snapshot) => snapshots.push(snapshot));
  validation(first, "a", "A");
  validation(first, "b", "B");
  const { totalCorrections, repeatedFailures, distinctFailureEvidenceCount, lastFailureEvidence, ...oldSnapshot } = snapshots.at(-1);
  assert.equal(totalCorrections, 2);
  assert.equal(repeatedFailures, 0);
  assert.equal(distinctFailureEvidenceCount, 2);
  assert.equal(lastFailureEvidence, "B");
  const resumed = governor(root, {}, [oldSnapshot]);
  assert.equal(resumed.totalCorrections, 2);
  assert.equal(resumed.distinctFailureEvidenceCount, 2);
  assert.equal(validation(resumed, "b-again", "B").outcome, "REPLAN_REQUIRED");
});

test("legacy policy parsing stays compatible and qualification requires named v1 bounded execution", (t) => {
  const root = repository(t);
  const legacy = policy({ MAX_CORRECTION_CYCLES: 2 });
  assert.equal(legacy.RUN_ID, "legacy-v0");
  assert.equal(legacy.MAX_REPEATED_FAILURES, undefined);
  assert.equal(legacy.MAX_TOTAL_CORRECTIONS, undefined);
  assert.equal(new AgentGovernor(legacy, root).systemVerdict, "GREEN");
  assert.throws(() => parseQualificationPolicy(legacy), /named v1 RUN_ID/);
  assert.throws(() => parseQualificationPolicy({ ...legacy, RUN_ID: "m4", WORKSPACE_ROOT: root, MODE: "DISCOVER" }), /BOUNDED_EXECUTE/);
  const m4 = parseQualificationPolicy({ ...legacy, RUN_ID: "m4", WORKSPACE_ROOT: root, POLICY_REVISION: 1, MODE: "BOUNDED_EXECUTE", MAX_REPEATED_FAILURES: 2, MAX_TOTAL_CORRECTIONS: 6 });
  assert.equal(new AgentGovernor(m4, root).systemVerdict, "VALIDATION_PENDING");
});

test("qualification requires explicit correction limits and binds both into its SHA", (t) => {
  const root = repository(t);
  const raw = { ...policy(), RUN_ID: "m4-qwen-coder-recovery-lock", WORKSPACE_ROOT: root, POLICY_REVISION: 1, MODE: "BOUNDED_EXECUTE" };
  assert.equal(parseGovernorPolicy(raw).MAX_REPEATED_FAILURES, undefined);
  assert.equal(parseGovernorPolicy(raw).MAX_TOTAL_CORRECTIONS, undefined);
  assert.throws(() => parseQualificationPolicy({ ...raw, MAX_TOTAL_CORRECTIONS: 6 }), /MAX_REPEATED_FAILURES/);
  assert.throws(() => parseQualificationPolicy({ ...raw, MAX_REPEATED_FAILURES: 2 }), /MAX_TOTAL_CORRECTIONS/);
  const qualified = parseQualificationPolicy({ ...raw, MAX_REPEATED_FAILURES: 2, MAX_TOTAL_CORRECTIONS: 6 });
  assert.equal(qualified.MAX_REPEATED_FAILURES, 2);
  assert.equal(qualified.MAX_TOTAL_CORRECTIONS, 6);
  assert.notEqual(policySha256(qualified), policySha256(parseQualificationPolicy({ ...raw, MAX_REPEATED_FAILURES: 3, MAX_TOTAL_CORRECTIONS: 6 })));
  assert.notEqual(policySha256(qualified), policySha256(parseQualificationPolicy({ ...raw, MAX_REPEATED_FAILURES: 2, MAX_TOTAL_CORRECTIONS: 7 })));
  assert.equal(new AgentGovernor(qualified, root).systemVerdict, "VALIDATION_PENDING");
});

test("workspace root rejects a different checkout and a symlink escape", (t) => {
  const root = repository(t);
  const other = repository(t);
  const configured = parseGovernorPolicy({ ...policy(), RUN_ID: "root-1", WORKSPACE_ROOT: root });
  assert.throws(() => new AgentGovernor(configured, other), /workspace root/);
  symlinkSync(other, path.join(root, "src/outside"));
  const discover = governor(root, { MODE: "DISCOVER" });
  assert.equal(discover.checkToolCall("read", { path: "src/outside" }, "escape").allowed, false);
});


function fixtureGitBuffer(root, ...args) {
  return execFileSync("git", args, {
    cwd: root,
    encoding: "buffer",
    env: {
      ...process.env,
      GIT_TERMINAL_PROMPT: "0",
    },
    stdio: ["ignore", "pipe", "pipe"],
  });
}

function fixtureGit(root, ...args) {
  return fixtureGitBuffer(root, ...args).toString("utf8").trim();
}

function localGitFixture(t) {
  const root = repository(t);
  fixtureGit(root, "init", "--initial-branch=main");
  fixtureGit(root, "config", "user.name", "NeuralEngine Fixture");
  fixtureGit(root, "config", "user.email", "fixture@example.invalid");
  writeFileSync(path.join(root, "src", "worker.py"), "value = 1\n");
  fixtureGit(root, "add", "--", "src/worker.py");
  fixtureGit(root, "commit", "-m", "fixture base");
  const baseHead = fixtureGit(root, "rev-parse", "HEAD");
  const baseTree = fixtureGit(root, "rev-parse", "HEAD^{tree}");
  fixtureGit(root, "remote", "add", "origin", path.join(root, "unused-remote.git"));
  fixtureGit(root, "config", "branch.main.remote", "origin");
  fixtureGit(root, "config", "branch.main.merge", "refs/heads/main");
  fixtureGit(root, "update-ref", "refs/remotes/origin/main", baseHead);
  const createCommit = (parent, tree, message) =>
    fixtureGit(root, "commit-tree", tree, "-p", parent, "-m", message);
  return { root, baseHead, baseTree, createCommit, git: (...args) => fixtureGit(root, ...args) };
}

function gitGovernor(root, overrides = {}) {
  return new AgentGovernor(policy({ WORKSPACE_ROOT: root, ...overrides }), root);
}

test("Git reads remain subject to OBSERVE mode while available in bounded mode", (t) => {
  const root = repository(t);
  const commands = [
    "git status",
    "git diff",
    "git log",
    "git show",
    "git branch --show-current",
    "git rev-parse HEAD",
    "git remote -v",
    "git rev-list HEAD",
  ];
  const observe = gitGovernor(root, { MODE: "OBSERVE" });
  for (const [index, command] of commands.entries()) {
    assert.equal(classifyGitCommand(command), "GIT_READ", command);
    const decision = observe.checkToolCall("bash", { command }, "observe-git-read-" + index);
    assert.equal(decision.allowed, false, command);
    assert.match(decision.reason, /OBSERVE accepts file evidence only/);
  }

  const bounded = gitGovernor(root, { MODE: "BOUNDED_EXECUTE" });
  assert.equal(bounded.checkToolCall("bash", { command: "git status" }, "bounded-git-status").allowed, true);
});

test("default Git reader captures the staged diff and invalidates changed content and HEAD", (t) => {
  const { root, git } = localGitFixture(t);
  writeFileSync(path.join(root, "src", "worker.py"), "value = 2\n");
  git("add", "--", "src/worker.py");

  const instance = gitGovernor(root);
  const review = instance.prepareGitCommitAuthorization("reviewed change");
  const expectedDiff = fixtureGitBuffer(root, "diff", "--cached", "--binary", "--no-ext-diff", "--no-textconv", "--no-color");
  assert.deepEqual(review.stagedPaths, ["src/worker.py"]);
  assert.deepEqual(review.unstagedPaths, []);
  assert.equal(review.stagedDiffSha256, createHash("sha256").update(expectedDiff).digest("hex"));
  assert.equal(instance.authorizeGitCommit(review, true).allowed, true);
  assert.equal(instance.checkToolCall("bash", {
    command: "git push --no-follow-tags --recurse-submodules=no origin HEAD:refs/heads/main",
  }, "commit-review-does-not-authorize-push").allowed, false);

  writeFileSync(path.join(root, "src", "worker.py"), "value = 3\n");
  git("add", "--", "src/worker.py");
  const changedContent = instance.checkToolCall("bash", {
    command: 'git commit -m "reviewed change"',
  }, "commit-after-content-change");
  assert.equal(changedContent.allowed, false);
  assert.equal(changedContent.outcome, "STOP");
  assert.match(changedContent.reason, /AUTHORIZATION_INVALIDATED=YES/);
  assert.equal(instance.stopped, true);

  const second = gitGovernor(root);
  const headReview = second.prepareGitCommitAuthorization("head change");
  assert.equal(second.authorizeGitCommit(headReview, true).allowed, true);
  const currentHead = git("rev-parse", "HEAD");
  const tree = git("rev-parse", "HEAD^{tree}");
  const advancedHead = git("commit-tree", tree, "-p", currentHead, "-m", "fixture head advance");
  git("update-ref", "refs/heads/main", advancedHead);
  const changedHead = second.checkToolCall("bash", {
    command: 'git commit -m "head change"',
  }, "commit-after-head-change");
  assert.equal(changedHead.allowed, false);
  assert.equal(changedHead.outcome, "STOP");
  assert.match(changedHead.reason, /AUTHORIZATION_INVALIDATED=YES/);
});

test("default Git reader reports local ahead/behind counts and invalidates branch, remote, or HEAD changes", (t) => {
  for (const change of ["branch", "remote", "remote-config", "head", "behind"]) {
    const { root, baseHead, baseTree, createCommit, git } = localGitFixture(t);
    const localHead = createCommit(baseHead, baseTree, "fixture local commit");
    git("update-ref", "refs/heads/main", localHead);

    const instance = gitGovernor(root);
    const review = instance.prepareGitPushAuthorization();
    assert.equal(review.ahead, 1);
    assert.equal(review.behind, 0);

    if (change === "behind") {
      const remoteHead = createCommit(baseHead, baseTree, "fixture remote commit");
      git("update-ref", "refs/remotes/origin/main", remoteHead);
      const diverged = instance.prepareGitPushAuthorization();
      assert.equal(diverged.ahead, 1);
      assert.equal(diverged.behind, 1);
      assert.equal(instance.authorizeGitPush(diverged, true).allowed, false);
      continue;
    }

    assert.equal(instance.authorizeGitPush(review, true).allowed, true);
    if (change === "branch") {
      git("branch", "other", "HEAD");
      git("switch", "other");
      git("config", "branch.other.remote", "origin");
      git("config", "branch.other.merge", "refs/heads/other");
      git("update-ref", "refs/remotes/origin/other", baseHead);
    } else if (change === "remote") {
      git("remote", "set-url", "origin", path.join(root, "changed-remote.git"));
    } else if (change === "remote-config") {
      git("config", "--replace-all", "remote.origin.fetch", "+refs/heads/*:refs/remotes/origin/alternate/*");
    } else {
      const nextHead = createCommit(localHead, baseTree, "fixture second local commit");
      git("update-ref", "refs/heads/main", nextHead);
    }
    const result = instance.checkToolCall("bash", {
      command: "git push --no-follow-tags --recurse-submodules=no origin HEAD:refs/heads/main",
    }, "push-after-" + change + "-change");
    assert.equal(result.allowed, false, change);
    assert.equal(result.outcome, "STOP", change);
    assert.match(result.reason, /AUTHORIZATION_INVALIDATED=YES/, change);
    assert.equal(instance.stopped, true, change);
  }
});

test("fetch preflight permits remote-tracking-only refspecs and denies local-branch refspecs", (t) => {
  const { root, git } = localGitFixture(t);
  const safe = gitGovernor(root, { MODE: "BOUNDED_EXECUTE" });
  assert.equal(safe.checkToolCall("bash", { command: "git fetch origin" }, "fetch-remote-tracking-only").allowed, true);

  git("config", "--replace-all", "remote.origin.fetch", "+refs/heads/*:refs/heads/*");
  const unsafe = gitGovernor(root, { MODE: "BOUNDED_EXECUTE" });
  const deniedFetch = unsafe.checkToolCall("bash", { command: "git fetch origin" }, "fetch-local-branch-refspec");
  assert.equal(deniedFetch.allowed, false);
  assert.match(deniedFetch.reason, /local branch/);
});

test("a changed local remote configuration invalidates approval-time push preflight and stops", (t) => {
  const { root, baseHead, baseTree, createCommit, git } = localGitFixture(t);
  git("update-ref", "refs/heads/main", createCommit(baseHead, baseTree, "fixture local commit"));
  const instance = gitGovernor(root);
  const review = instance.prepareGitPushAuthorization();
  git("remote", "set-url", "origin", path.join(root, "changed-before-approval.git"));
  const receipt = instance.authorizeGitPush(review, true);
  assert.equal(receipt.allowed, false);
  assert.equal(receipt.authorizationInvalidated, true);
  assert.match(receipt.reason, /AUTHORIZATION_INVALIDATED=YES/);
  assert.equal(instance.stopped, true);
});

test("staging is bounded and broad staging uses one reviewed local Git snapshot", (t) => {
  const { root } = localGitFixture(t);
  writeFileSync(path.join(root, "src", "worker.py"), "value = 2\n");
  const scoped = gitGovernor(root, { AUTHORIZED_GIT_STAGE_PATHS: ["src/worker.py"] });
  assert.equal(scoped.checkToolCall("bash", {
    command: "git add -- src/worker.py",
  }, "stage-explicit-path").allowed, true);
  assert.equal(scoped.checkToolCall("bash", {
    command: "git add -- tests/test_worker.py",
  }, "stage-outside-scope").allowed, false);

  const broad = gitGovernor(root);
  const review = broad.prepareGitStageAuthorization();
  assert.equal(broad.authorizeGitStage(review, false).allowed, false);
  assert.equal(broad.authorizeGitStage(review, true).allowed, true);
  assert.equal(broad.checkToolCall("bash", { command: "git add -A" }, "stage-broad-reviewed").allowed, true);
  assert.equal(broad.checkToolCall("bash", { command: "git add ." }, "stage-broad-reuse").allowed, false);

  const stale = gitGovernor(root);
  const staleReview = stale.prepareGitStageAuthorization();
  assert.equal(stale.authorizeGitStage(staleReview, true).allowed, true);
  writeFileSync(path.join(root, "tests", "new.py"), "value = 1\n");
  const invalidated = stale.checkToolCall("bash", { command: "git add --all" }, "stage-after-change");
  assert.equal(invalidated.allowed, false);
  assert.equal(invalidated.outcome, "STOP");
  assert.match(invalidated.reason, /AUTHORIZATION_INVALIDATED=YES/);
  assert.equal(stale.stopped, true);
});

test("force push, remote mutation, authentication mutation, and protected paths stay denied", (t) => {
  const { root, baseHead, baseTree, createCommit, git } = localGitFixture(t);
  const localHead = createCommit(baseHead, baseTree, "fixture local commit");
  git("update-ref", "refs/heads/main", localHead);
  const instance = gitGovernor(root);
  const denied = [
    ["git push --force origin HEAD:refs/heads/main", "GIT_FORCE_PUSH"],
    ["git push -f", "GIT_FORCE_PUSH"],
    ["git push --force-with-lease", "GIT_FORCE_PUSH"],
    ["git remote add upstream /tmp/unused.git", "GIT_REMOTE_MUTATION"],
    ["git remote remove origin", "GIT_REMOTE_MUTATION"],
    ["git remote set-url origin /tmp/unused.git", "GIT_REMOTE_MUTATION"],
    ["git config remote.origin.url /tmp/unused.git", "GIT_REMOTE_MUTATION"],
    ["git config --global credential.helper store", "GIT_AUTH_MUTATION"],
    ["git config --global http.sslVerify false", "GIT_AUTH_MUTATION"],
    ["git config --global core.sshCommand ssh", "GIT_AUTH_MUTATION"],
    ["git credential approve", "GIT_AUTH_MUTATION"],
    ["ssh-keygen -p -f ~/.ssh/id_ed25519", "GIT_AUTH_MUTATION"],
    ["gh auth login", "GIT_AUTH_MUTATION"],
  ];
  for (const [index, [command, operation]] of denied.entries()) {
    assert.equal(classifyGitCommand(command), operation, command);
    assert.equal(instance.checkToolCall("bash", { command }, "denied-" + index).allowed, false, command);
  }

  const noScope = gitGovernor(root);
  for (const command of ["git add .", "git add -A", "git add --all"]) {
    assert.equal(noScope.checkToolCall("bash", { command }, "broad-" + command).allowed, false, command);
  }
});

import { readFileSync, realpathSync } from "node:fs";
import { createHash } from "node:crypto";
import path from "node:path";
import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
import { AgentGovernor, parseGovernorPolicy, type GovernorSnapshot, type GovernorEvent } from "../../control-plane/governor.ts";

const GOVERNOR_ENTRY_TYPE = "neuralengine-agent-governor-v0";
const BOUNDED_CODE_MODE = "NEURAL_PI_BOUNDED_CODE";
const GOVERNOR_POLICY_FILE = "NEURAL_PI_POLICY_FILE";
const PROJECT_ROOT_ENV = "NEURALENGINE_PI_PROJECT_ROOT";

function isInside(root: string, candidate: string): boolean {
  const relative = path.relative(root, candidate);
  return relative === "" || (relative !== ".." && !relative.startsWith(`..${path.sep}`) && !path.isAbsolute(relative));
}

function projectRootFor(cwd: string): string {
  const realCwd = realpathSync(cwd);
  const configuredRoot = process.env[PROJECT_ROOT_ENV];
  const root = realpathSync(configuredRoot ?? cwd);
  if (!isInside(root, realCwd)) {
    throw new Error(`${PROJECT_ROOT_ENV} does not contain the Pi working directory`);
  }
  return root;
}

function freezeToolInput(value: unknown, visited = new Set<object>()): void {
  if (typeof value !== "object" || value === null || visited.has(value)) return;
  visited.add(value);
  for (const child of Object.values(value)) freezeToolInput(child, visited);
  Object.freeze(value);
}

// A narrow early refusal for common policy violations. AGENTS.md remains authoritative.
const GIT_MUTATION_REASON = "Git staging and history operations require separate authorization";
const NEURAL_MUTATION_REASON = "Brain writes require separate authorization";
const PRIVILEGED_MUTATION_REASON = "Privileged system mutation requires separate explicit authorization";
const RECURSIVE_REMOVAL_REASON = "Recursive removal requires separate explicit authorization";

function tokenizeShellWords(command: string): string[] | undefined {
  if (/[;&|`$<>\\\n\r]/.test(command)) return undefined;
  const words: string[] = [];
  let index = 0;
  while (index < command.length) {
    while (/\s/.test(command[index] ?? "")) index += 1;
    if (index >= command.length) break;
    const quote = command[index] === "'" || command[index] === '"' ? command[index] : undefined;
    if (quote) {
      index += 1;
      const end = command.indexOf(quote, index);
      if (end < 0) return undefined;
      const word = command.slice(index, end);
      if (!word || word.includes(quote)) return undefined;
      words.push(word);
      index = end + 1;
      if (index < command.length && !/\s/.test(command[index] ?? "")) return undefined;
    } else {
      const start = index;
      while (index < command.length && !/\s/.test(command[index] ?? "")) index += 1;
      words.push(command.slice(start, index));
    }
  }
  return words.length > 0 ? words : undefined;
}

function isProtectedGitMutation(command: string): boolean {
  const words = tokenizeShellWords(command.trim());
  if (!words || words[0] !== "git" || !words[1]) return false;

  const optionsWithValues = new Set([
    "-C", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--config-env",
  ]);
  let index = 1;
  while (index < words.length && words[index]?.startsWith("-")) {
    const option = words[index] ?? "";
    index += optionsWithValues.has(option) ? 2 : 1;
  }

  const subcommand = words[index];
  if (!subcommand) return false;
  if (["add", "commit", "push", "merge", "tag", "rm", "reset", "clean", "stash", "rebase", "restore", "checkout"].includes(subcommand)) {
    return true;
  }
  return subcommand === "apply" && words.slice(index + 1).includes("--cached");
}

function classifyProtectedCommand(command: string): string | undefined {
  if (isProtectedGitMutation(command)) return GIT_MUTATION_REASON;
  if (/\bneural\s+(?:init\b|decision\s+(?:add\b|accept\b|action\s+add\b|outcome\s+add\b|review\s+add\b)|experience\s+(?:add\b|from-observation\b|from-review\b)|evaluation\s+add\b|knowledge\s+(?:add\b|from-experience\b)|playbook\s+add\b|proposal\s+(?:add\b|status\b)|revision\s+(?:add\b|activate\b|supersede\b|reject\b)|run\s+add\b|development-evidence\s+apply\b|brain\s+(?:recover\b|adopt\b))/i.test(command)) {
    return NEURAL_MUTATION_REASON;
  }
  if (/\bsudo(?:\s|$)/i.test(command)) return PRIVILEGED_MUTATION_REASON;
  if (/\brm\s+(?:-[^\s]*r[^\s]*\b|--recursive\b)/i.test(command)) return RECURSIVE_REMOVAL_REASON;
  return undefined;
}

export function guardToolCall(
  toolName: string,
  input: Record<string, unknown>,
  cwd: string,
  home: string,
  projectRoot = cwd,
): string | undefined {
  if (toolName === "write" || toolName === "edit") {
    if (typeof input.path !== "string") return "Missing file path";
    const target = path.resolve(cwd, input.path);
    const brain = path.resolve(process.env.NEURAL_HOME ?? path.join(home, ".neural"), "brain");
    const git = path.resolve(projectRoot, ".git");
    if (target === brain || target.startsWith(brain + path.sep)) return "Brain writes require separate authorization";
    if (target === git || target.startsWith(git + path.sep)) return "Direct Git metadata writes are blocked";
  }
  if (toolName === "bash") {
    if (typeof input.command !== "string") return "Missing shell command";
    const command = input.command;
    const protectedCommandReason = classifyProtectedCommand(command);
    if (protectedCommandReason) return protectedCommandReason;
  }
  return undefined;
}

function resolvePolicyRequest(): { requested: boolean; policyPath?: string; error?: string } {
  const mode = process.env[BOUNDED_CODE_MODE];
  const policyPath = process.env[GOVERNOR_POLICY_FILE];
  const invalidMode = mode !== undefined && mode !== "0" && mode !== "1";
  const requested = mode === "1" || invalidMode || policyPath !== undefined;
  if (!requested) return { requested: false };
  if (invalidMode) {
    return { requested: true, error: `${BOUNDED_CODE_MODE} must be "0" or "1"` };
  }
  if (policyPath === undefined) {
    return { requested: true, error: `${GOVERNOR_POLICY_FILE} is required for bounded CODE mode` };
  }
  if (policyPath.trim() === "") {
    return { requested: true, error: `${GOVERNOR_POLICY_FILE} must not be empty` };
  }
  return { requested: true, policyPath };
}

function boundedCodeWasRequested(): boolean {
  return resolvePolicyRequest().requested;
}

export default function (pi: ExtensionAPI): void {
  let governor: AgentGovernor | undefined;
  let governorLoadError: string | undefined;
  let startupRefusal: string | undefined;
  let shutdownRequested = false;
  let loadedPolicyPath: string | undefined;

  const operationFor = (toolName: string): GovernorEvent["operation"] | undefined => ({
    read: "READ", grep: "SEARCH", find: "SEARCH", ls: "SEARCH",
    edit: "EDIT", write: "CREATE", bash: "SHELL",
  })[toolName] as GovernorEvent["operation"] | undefined;

  const updateStatus = (ctx: ExtensionContext): void => {
    const status = governor
      ? `CODE governor: ${governor.status()}`
      : governorLoadError
        ? `CODE governor: STOP (${governorLoadError})`
        : "CODE governor: inactive (set NEURAL_PI_BOUNDED_CODE=1 for bounded CODE tasks)";
    ctx.ui.setStatus("neuralengine-agent-governor", status);
  };

  const refuseBoundedStart = (ctx: ExtensionContext, reason: string): void => {
    startupRefusal = reason;
    governorLoadError = reason;
    updateStatus(ctx);
    ctx.ui.notify(`Governor STOP: ${reason}`, "error");
    if (!shutdownRequested) {
      shutdownRequested = true;
      ctx.shutdown();
    }
  };

  pi.on("session_start", (_event, ctx) => {
    const request = resolvePolicyRequest();
    governor = undefined;
    governorLoadError = undefined;
    startupRefusal = undefined;
    shutdownRequested = false;
    loadedPolicyPath = undefined;
    if (request.requested) {
      try {
        if (request.error || !request.policyPath) throw new Error(request.error ?? "Governor policy path is missing");
        const projectRoot = projectRootFor(ctx.cwd);
        const policyPath = path.resolve(projectRoot, request.policyPath);
        loadedPolicyPath = realpathSync(policyPath);
        const history = ctx.sessionManager
          .getBranch()
          .filter((entry) => entry.type === "custom" && entry.customType === GOVERNOR_ENTRY_TYPE)
          .map((entry) => ("data" in entry ? entry.data : undefined));
        const persist = (snapshot: GovernorSnapshot): void => {
          pi.appendEntry(GOVERNOR_ENTRY_TYPE, snapshot);
        };
        const policy = parseGovernorPolicy(JSON.parse(readFileSync(loadedPolicyPath, "utf8")) as unknown);
        governor = new AgentGovernor(policy, projectRoot, history, persist, ctx.cwd);
        governor.handleEvent({ type: "SESSION_START" });
        if (governor.stopped) throw new Error(governor.stopReason ?? "Governor state could not be restored");
      } catch (error) {
        governorLoadError = error instanceof Error ? error.message : String(error);
        startupRefusal = `task policy could not be loaded: ${governorLoadError}`;
      }
    }
    if (startupRefusal) {
      refuseBoundedStart(ctx, startupRefusal);
      return;
    }
    updateStatus(ctx);
  });

  pi.on("input", (_event, ctx) => {
    if (startupRefusal) {
      refuseBoundedStart(ctx, startupRefusal);
      return { action: "handled" };
    }
    if (governor) { governor.handleEvent({ type: "PROMPT_ADMIT" }); return undefined; }
    if (!boundedCodeWasRequested()) return undefined;
    const reason = "bounded CODE policy was not loaded at session start";
    refuseBoundedStart(ctx, reason);
    return { action: "handled" };
  });

  pi.on("agent_start", (_event, ctx) => {
    const stopReason = startupRefusal ??
      (governor?.stopped
        ? governor.stopReason
        : !governor && boundedCodeWasRequested()
          ? "bounded CODE policy was not loaded at session start"
          : undefined);
    if (!stopReason) return;
    refuseBoundedStart(ctx, stopReason);
    ctx.abort();
  });

  pi.registerCommand("governor", {
    description: "Show deterministic bounded CODE task status",
    handler: (args, ctx) => {
      if (args.trim() && args.trim() !== "status") {
        ctx.ui.notify("Usage: /governor [status]", "error");
        return;
      }
      updateStatus(ctx);
      ctx.ui.notify(
        governor
          ? `Governor ${governor.status()}${governor.isGreen ? "" : "; model claims do not replace evidence"}`
          : governorLoadError
            ? `Governor STOP: ${governorLoadError}`
            : "Governor inactive; no bounded CODE policy was loaded.",
        governor?.stopped || governorLoadError ? "error" : governor?.isGreen ? "info" : "warning",
      );
    },
  });

  pi.on("tool_call", (event, ctx) => {
    let projectRoot = ctx.cwd;
    try {
      projectRoot = projectRootFor(ctx.cwd);
    } catch (error) {
      if (governor || boundedCodeWasRequested()) {
        const stopReason = error instanceof Error ? error.message : String(error);
        refuseBoundedStart(ctx, stopReason);
        return { block: true, reason: `Governor STOP: ${stopReason}`, terminate: true };
      }
    }
    const reason = guardToolCall(event.toolName, event.input, ctx.cwd, process.env.HOME ?? "", projectRoot);
    if (reason) return { block: true, reason };
    if (startupRefusal || (!governor && boundedCodeWasRequested())) {
      const stopReason = startupRefusal ?? "bounded CODE policy was not loaded at session start";
      refuseBoundedStart(ctx, stopReason);
      return { block: true, reason: `Governor STOP: ${stopReason}`, terminate: true };
    }
    if (!governor) return undefined;
    if ((event.toolName === "edit" || event.toolName === "write") && typeof event.input.path === "string") {
      const target = path.resolve(ctx.cwd, event.input.path);
      if (target === loadedPolicyPath) return { block: true, reason: "The active Governor policy is immutable during this run" };
    }
    const decision = governor.handleEvent({
      type: "TOOL_PRE", operation: operationFor(event.toolName),
      input: event.input, callId: event.toolCallId,
      evidenceReference: typeof event.input.evidenceReference === "string" ? event.input.evidenceReference : undefined,
    });
    updateStatus(ctx);
    if (!decision.allowed) return { block: true, reason: decision.reason, terminate: governor.stopped };
    // A later Pi extension must not rewrite the path or command after approval.
    freezeToolInput(event.input);
    return undefined;
  });

  pi.on("tool_result", (event, ctx) => {
    const output = (event as unknown as Record<string, unknown>).content;
    const evidenceReference = event.toolName === "bash" && output !== undefined
      ? createHash("sha256").update(JSON.stringify(output)).digest("hex") : undefined;
    governor?.handleEvent({ type: "TOOL_POST", operation: operationFor(event.toolName), input: event.input, callId: event.toolCallId, failed: event.isError, evidenceReference });
    updateStatus(ctx);
    if (governor?.stopped) {
      ctx.abort();
      ctx.ui.notify(`Governor STOP: ${governor.stopReason}`, "error");
    }
  });

  pi.on("session_compact", (_event, ctx) => {
    governor?.handleEvent({ type: "COMPACTION" });
    updateStatus(ctx);
    if (governor?.stopped) {
      ctx.abort();
      ctx.ui.notify(`Governor STOP: ${governor.stopReason}`, "error");
    }
  });

  pi.on("agent_end", (event, ctx) => {
    const finalMessage = [...event.messages].reverse().find((message) => message.role === "assistant");
    const content: Array<{ type?: string; text?: string }> = finalMessage?.role === "assistant" && Array.isArray(finalMessage.content)
      ? finalMessage.content : [];
    const claim = content.filter((item) => item.type === "text").map((item) => item.text ?? "").join("\n");
    if (claim) governor?.handleEvent({ type: "FINAL_CLAIM", claim });
    updateStatus(ctx);
  });

  pi.on("session_shutdown", () => { governor?.handleEvent({ type: "SESSION_END" }); });
}

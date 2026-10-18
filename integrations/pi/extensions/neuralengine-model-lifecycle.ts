/**
 * NeuralEngine Model Lifecycle Extension
 *
 * Automatically manages local llama-server lifecycle when Pi selects a
 * NeuralEngine local provider (neural-general, neural-code, local-gptoss).
 *
 * Lifecycle contract:
 *   STARTED  — runtime was started by this session; extension stops it on exit.
 *   BORROWED — runtime was already running; extension never stops it.
 *
 * Uses only the versioned machine API exposed by scripts/pi-model:
 *   switch-json <ROLE>                         → SwitchResult JSON
 *   stop-owned-json --profile P --pid N        → canonical stop_owned()
 *
 * No human-readable stdout is parsed.
 * No direct calls to scripts/llm or scripts/challenger are made.
 *
 * API version: 1 (api_version field in every machine response).
 */

import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join, resolve } from "node:path";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Machine API version this extension targets. Reject anything else. */
export const EXPECTED_API_VERSION = 1;

/** Provider → internal role name. */
export const PROVIDER_TO_ROLE: Record<string, string> = {
  "neural-general": "GENERAL",
  "neural-code": "CODE",
  "local-gptoss": "GPTOSS",
};

/** Internal role → display label (GPTOSS is presented as PATCH). */
export const ROLE_DISPLAY: Record<string, string> = {
  GENERAL: "GENERAL",
  CODE: "CODE",
  GPTOSS: "PATCH",
};

/**
 * Canonical NeuralEngine checkout used when no env override is present.
 * This is the single install-time constant; documented explicitly per AGENTS.md.
 */
export const CANONICAL_ROOT = "/home/grzanka/Work/NeuralEngine";

// ---------------------------------------------------------------------------
// Root resolution
// ---------------------------------------------------------------------------

/**
 * Resolve the canonical NeuralEngine project root.
 *
 * Priority:
 *   1. NEURALENGINE_PI_PROJECT_ROOT env var (set by scripts/pi-local or test harness).
 *   2. Dedicated global config file ~/.config/neuralengine/root (if present).
 *   3. CANONICAL_ROOT — the verified authoritative checkout.
 *   4. Walk up from cwd — compatibility fallback for non-standard layouts.
 *
 * Returns null only when every strategy fails, which triggers a visible
 * warning rather than a silent no-op.
 */
export function findProjectRoot(cwd: string): string | null {
  // 1. Explicit env override
  const envRoot = process.env["NEURALENGINE_PI_PROJECT_ROOT"];
  if (envRoot) {
    const marker = join(envRoot, "scripts", "pi-model");
    if (existsSync(marker)) return resolve(envRoot);
  }

  // 2. Dedicated global config file (if present)
  try {
    const home = process.env["HOME"] || homedir();
    const configPath = join(home, ".config", "neuralengine", "root");
    if (existsSync(configPath)) {
      const configured = readFileSync(configPath, "utf-8").trim();
      if (configured && existsSync(join(configured, "scripts", "pi-model"))) {
        return resolve(configured);
      }
    }
  } catch {
    // Ignore config file read errors and proceed to canonical fallback
  }

  // 3. Canonical authoritative checkout (AGENTS.md)
  if (existsSync(join(CANONICAL_ROOT, "scripts", "pi-model"))) {
    return CANONICAL_ROOT;
  }

  // 4. Walk up from cwd — compatibility fallback only
  let dir = resolve(cwd);
  for (let depth = 0; depth < 10; depth++) {
    if (existsSync(join(dir, "scripts", "pi-model"))) return dir;
    const parent = resolve(dir, "..");
    if (parent === dir) break;
    dir = parent;
  }

  return null;
}

// ---------------------------------------------------------------------------
// Machine API types
// ---------------------------------------------------------------------------

export interface SwitchJsonDoc {
  api_version: number;
  operation: "switch";
  role: string;
  ownership: "STARTED" | "BORROWED";
  profile: string;
  pid: number;
  endpoint: string;
}

export interface StopOwnedJsonDoc {
  api_version: number;
  operation: "stop_owned";
  result: "STOPPED" | "NOT_OWNED_OR_REPLACED";
  profile: string;
  pid: number;
}

// ---------------------------------------------------------------------------
// Session state
// ---------------------------------------------------------------------------

export interface LifecycleState {
  apiVersion: 1;
  role: string;
  profile: string;
  pid: number;
  endpoint: string;
  ownership: "STARTED" | "BORROWED";
  projectRoot: string;
}

// ---------------------------------------------------------------------------
// Machine API helpers
// ---------------------------------------------------------------------------

/** Parse and validate a switch-json response. Throws on any violation. */
export function parseSwitchJson(stdout: string): SwitchJsonDoc {
  let doc: unknown;
  try {
    doc = JSON.parse(stdout.trim());
  } catch {
    throw new Error(`switch-json: malformed JSON response: ${stdout.slice(0, 200)}`);
  }
  if (typeof doc !== "object" || doc === null) {
    throw new Error(`switch-json: expected JSON object, got ${typeof doc}`);
  }
  const d = doc as Record<string, unknown>;
  if (d["api_version"] !== EXPECTED_API_VERSION) {
    throw new Error(
      `switch-json: unsupported api_version ${d["api_version"]} (expected ${EXPECTED_API_VERSION})`
    );
  }
  if (d["operation"] !== "switch") {
    throw new Error(`switch-json: unexpected operation ${d["operation"]}`);
  }
  if (d["ownership"] !== "STARTED" && d["ownership"] !== "BORROWED") {
    throw new Error(`switch-json: invalid ownership value ${d["ownership"]}`);
  }
  if (typeof d["profile"] !== "string" || !d["profile"]) {
    throw new Error(`switch-json: missing or empty profile`);
  }
  if (typeof d["pid"] !== "number" || d["pid"] <= 0 || !Number.isInteger(d["pid"])) {
    throw new Error(`switch-json: invalid pid ${d["pid"]}`);
  }
  if (typeof d["endpoint"] !== "string" || !d["endpoint"]) {
    throw new Error(`switch-json: missing or empty endpoint`);
  }
  return doc as SwitchJsonDoc;
}

/** Parse a stop-owned-json response. Throws on malformed/wrong-version output. */
export function parseStopOwnedJson(stdout: string): StopOwnedJsonDoc {
  let doc: unknown;
  try {
    doc = JSON.parse(stdout.trim());
  } catch {
    throw new Error(`stop-owned-json: malformed JSON response: ${stdout.slice(0, 200)}`);
  }
  if (typeof doc !== "object" || doc === null) {
    throw new Error(`stop-owned-json: expected JSON object`);
  }
  const d = doc as Record<string, unknown>;
  if (d["api_version"] !== EXPECTED_API_VERSION) {
    throw new Error(
      `stop-owned-json: unsupported api_version ${d["api_version"]} (expected ${EXPECTED_API_VERSION})`
    );
  }
  if (d["operation"] !== "stop_owned") {
    throw new Error(`stop-owned-json: unexpected operation ${d["operation"]}`);
  }
  if (d["result"] !== "STOPPED" && d["result"] !== "NOT_OWNED_OR_REPLACED") {
    throw new Error(`stop-owned-json: unexpected result ${d["result"]}`);
  }
  return doc as StopOwnedJsonDoc;
}

// ---------------------------------------------------------------------------
// Extension
// ---------------------------------------------------------------------------

export default function (pi: ExtensionAPI): void {
  let state: LifecycleState | null = null;
  let shutdownDone = false;

  // -------------------------------------------------------------------------
  // Cleanup (idempotent, ownership-aware)
  // -------------------------------------------------------------------------

  async function cleanupOwned(s: LifecycleState, ctx: ExtensionContext): Promise<void> {
    if (s.ownership !== "STARTED") return; // BORROWED: never stop
    const displayRole = ROLE_DISPLAY[s.role] ?? s.role;
    try {
      const r = await pi.exec(
        join(s.projectRoot, "scripts", "pi-model"),
        ["stop-owned-json", "--profile", s.profile, "--pid", String(s.pid)],
        { cwd: s.projectRoot }
      );
      if (r.code !== 0) {
        console.error(
          `[neuralengine-lifecycle] stop-owned-json failed (exit ${r.code}): ${r.stderr}`
        );
        if (ctx.hasUI)
          ctx.ui.notify(`lifecycle cleanup failed (${displayRole}): ${r.stderr}`, "warning");
        return;
      }
      const doc = parseStopOwnedJson(r.stdout);
      if (doc.result === "STOPPED") {
        console.log(
          `[neuralengine-lifecycle] stopped owned ${displayRole} pid=${s.pid}`
        );
        if (ctx.hasUI) ctx.ui.setStatus("neuralengine-lifecycle", undefined);
      } else {
        // NOT_OWNED_OR_REPLACED: replacement already running — safe, not an error
        console.log(
          `[neuralengine-lifecycle] ${displayRole} pid=${s.pid} no longer owned (${doc.result})`
        );
      }
    } catch (err) {
      console.error(`[neuralengine-lifecycle] cleanup error: ${err}`);
      if (ctx.hasUI)
        ctx.ui.notify(`lifecycle cleanup error (${displayRole}): ${err}`, "warning");
    }
  }

  // -------------------------------------------------------------------------
  // Model switch orchestration (model_select and session_start)
  // -------------------------------------------------------------------------

  async function handleModelSwitch(
    model: { provider: string; id: string },
    ctx: ExtensionContext,
    source?: string
  ): Promise<void> {
    const provider = model.provider;
    const role = PROVIDER_TO_ROLE[provider] ?? null;
    const displayRole = role ? (ROLE_DISPLAY[role] ?? role) : null;
    const prevState = state;

    // Same role already active: do not restart unnecessarily
    if (prevState && role && prevState.role === role) {
      return;
    }

    if (!role) {
      // Cloud or unknown provider: clean up previous STARTED, clear state
      if (prevState) {
        state = null;
        await cleanupOwned(prevState, ctx);
      }
      if (ctx.hasUI)
        ctx.ui.setStatus("neuralengine-lifecycle", `⛅ ${provider} (no local runtime)`);
      return;
    }

    const projectRoot = findProjectRoot(ctx.cwd);
    if (!projectRoot) {
      if (ctx.hasUI) {
        ctx.ui.notify(
          `NeuralEngine root not found; local lifecycle inactive for ${displayRole}`,
          "warning"
        );
        ctx.ui.setStatus("neuralengine-lifecycle", `⚠️ root not found`);
      }
      return;
    }

    // Clean up previous STARTED runtime if switching to a different role
    if (prevState && prevState.role !== role) {
      state = null;
      await cleanupOwned(prevState, ctx);
    }

    if (ctx.hasUI)
      ctx.ui.setStatus("neuralengine-lifecycle", `⏳ switching ${displayRole}…`);

    try {
      const r = await pi.exec(
        join(projectRoot, "scripts", "pi-model"),
        ["switch-json", role],
        { cwd: projectRoot, timeout: 120_000 }
      );

      if (r.code !== 0) {
        state = null;
        const errMsg = r.stderr || r.stdout || "unknown error";
        if (ctx.hasUI) {
          ctx.ui.notify(`Failed to start ${displayRole} runtime: ${errMsg}`, "error");
          ctx.ui.setStatus("neuralengine-lifecycle", `❌ ${displayRole} FAILED`);
        }
        return;
      }

      const doc = parseSwitchJson(r.stdout);

      state = {
        apiVersion: 1,
        role,
        profile: doc.profile,
        pid: doc.pid,
        endpoint: doc.endpoint,
        ownership: doc.ownership,
        projectRoot,
      };

      const ownershipLabel = doc.ownership === "STARTED" ? "started" : "borrowed";
      const statusText = `${doc.ownership === "STARTED" ? "🟢" : "🔵"} ${displayRole} pid=${doc.pid} (${ownershipLabel})`;

      console.log(`[neuralengine-lifecycle] ${statusText}`);
      if (ctx.hasUI) {
        if (source !== "restore") {
          ctx.ui.notify(`${displayRole} runtime ${ownershipLabel} (pid=${doc.pid})`, "info");
        }
        ctx.ui.setStatus("neuralengine-lifecycle", statusText);
      }

      shutdownDone = false;
    } catch (err) {
      state = null;
      if (ctx.hasUI) {
        ctx.ui.notify(`lifecycle error for ${displayRole}: ${err}`, "error");
        ctx.ui.setStatus("neuralengine-lifecycle", `❌ ${displayRole} ERROR`);
      }
    }
  }

  // -------------------------------------------------------------------------
  // session_start (handles initial model selection on launch)
  // -------------------------------------------------------------------------

  pi.on("session_start", async (_event, ctx) => {
    if (ctx.model) {
      await handleModelSwitch(ctx.model, ctx, "restore");
    }
  });

  // -------------------------------------------------------------------------
  // model_select (handles user model selection during session)
  // -------------------------------------------------------------------------

  pi.on("model_select", async (event, ctx) => {
    await handleModelSwitch(event.model, ctx, event.source);
  });

  // -------------------------------------------------------------------------
  // session_shutdown
  // -------------------------------------------------------------------------

  pi.on("session_shutdown", async (_event, ctx) => {
    if (shutdownDone) return;
    shutdownDone = true;
    const s = state;
    state = null;
    if (s) await cleanupOwned(s, ctx);
  });

  // -------------------------------------------------------------------------
  // before_provider_request — best-effort observation only
  //
  // Pi 1.0.0 does not guarantee request cancellation when a handler throws.
  // This hook is therefore used only for diagnostics and opportunistic
  // recovery. The primary lifecycle guarantee comes from the awaited
  // model_select / session_start handler completing successfully before any request.
  // -------------------------------------------------------------------------

  pi.on("before_provider_request", async (_event, ctx) => {
    const s = state;
    if (!s) return; // cloud/unknown provider — no gate

    const displayRole = ROLE_DISPLAY[s.role] ?? s.role;
    try {
      const r = await pi.exec(
        join(s.projectRoot, "scripts", "pi-model"),
        ["STATUS"],
        { cwd: s.projectRoot, timeout: 10_000 }
      );
      // Parse the key=value status lines (human format — STATUS is read-only inspection)
      const lines: Record<string, string> = {};
      for (const line of r.stdout.split("\n")) {
        const eq = line.indexOf("=");
        if (eq > 0) lines[line.slice(0, eq)] = line.slice(eq + 1);
      }
      const lifecycle = lines["LIFECYCLE"];
      const activeRole = lines["ACTIVE_ROLE"];
      const expectedDisplayRole = ROLE_DISPLAY[s.role] ?? s.role;

      if (lifecycle !== "RUNNING" || activeRole !== expectedDisplayRole) {
        // Best-effort recovery: attempt re-switch via machine API
        if (ctx.hasUI)
          ctx.ui.notify(`${displayRole} runtime not ready, re-switching…`, "warning");

        const switchR = await pi.exec(
          join(s.projectRoot, "scripts", "pi-model"),
          ["switch-json", s.role],
          { cwd: s.projectRoot, timeout: 120_000 }
        );
        if (switchR.code === 0) {
          try {
            const doc = parseSwitchJson(switchR.stdout);
            state = { ...s, pid: doc.pid, ownership: doc.ownership, profile: doc.profile };
          } catch {
            // Recovery succeeded but JSON was unexpected; keep old state
          }
        } else {
          console.error(
            `[neuralengine-lifecycle] before_provider_request: ${displayRole} unavailable`
          );
          if (ctx.hasUI)
            ctx.ui.notify(
              `⚠️ ${displayRole} runtime unavailable — request may fail`,
              "warning"
            );
        }
      }
    } catch (err) {
      console.error(`[neuralengine-lifecycle] before_provider_request check failed: ${err}`);
      if (ctx.hasUI)
        ctx.ui.notify(`⚠️ Cannot verify ${displayRole} runtime: ${err}`, "warning");
    }
  });
}

/** Manifest-derived Pi local routes and ownership-aware local runtime lifecycle. */
import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join, resolve } from "node:path";
import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";

export const EXPECTED_API_VERSION = 1;

type Manifest = {
  runtime_profiles: Record<string, {
    legacy_identity: string;
    model_ref: string;
    endpoint: { host: string; port: number; path: string };
    context_layers: { client_effective_ctx: number };
    max_output_tokens: number | null;
    selection_status?: string;
  }>;
  models: Record<string, {
    model_id: string;
    display_name: string;
    kind: string;
  }>;
  clients: {
    pi: {
      local_profiles: string[];
      provider: string;
      api: "openai-completions";
    };
  };
};

export interface SwitchJsonDoc {
  api_version: 1;
  operation: "switch";
  ownership: "STARTED" | "BORROWED";
  profile: string;
  pid: number;
  endpoint: string;
}

export interface StopOwnedJsonDoc {
  api_version: 1;
  operation: "stop_owned";
  result: "STOPPED" | "NOT_OWNED_OR_REPLACED";
  profile: string;
  pid: number;
}

interface LifecycleState {
  profile: string;
  pid: number;
  endpoint: string;
  ownership: "STARTED" | "BORROWED";
  projectRoot: string;
}

interface LocalSelection {
  profileName: string;
  modelId: string;
}

function findManifest(): string {
  const explicit = process.env.NEURALENGINE_MANIFEST;
  if (explicit) return resolve(explicit);

  let current = resolve(process.cwd());
  while (true) {
    const candidate = join(current, "llm-manifest.json");
    if (existsSync(candidate)) return candidate;
    const parent = dirname(current);
    if (parent === current) break;
    current = parent;
  }

  const canonical = join(homedir(), "Work", "NeuralEngine", "llm-manifest.json");
  if (existsSync(canonical)) return canonical;
  throw new Error("NeuralEngine local model manifest was not found");
}

function loadManifest(): { path: string; value: Manifest } {
  const path = findManifest();
  return { path, value: JSON.parse(readFileSync(path, "utf8")) as Manifest };
}

function findLocalSelection(manifest: Manifest, provider: string, modelId: string): LocalSelection | null {
  if (provider !== manifest.clients.pi.provider) return null;
  for (const profileName of manifest.clients.pi.local_profiles) {
    const profile = manifest.runtime_profiles[profileName];
    const model = profile && manifest.models[profile.model_ref];
    if (profile && model && model.model_id === modelId) {
      return { profileName, modelId };
    }
  }
  return null;
}

export function projectLocalModels(manifest: Manifest) {
  const contract = manifest.clients.pi;
  return contract.local_profiles.map((profileName) => {
    const profile = manifest.runtime_profiles[profileName];
    const model = profile && manifest.models[profile.model_ref];
    if (!profile || !model) throw new Error(`Manifest route is incomplete for ${profileName}`);
    const { host, port, path } = profile.endpoint;
    // Pi's catalog renderer requires a numeric field. Zero is a deliberate
    // no-cap sentinel: the OpenAI adapter omits max_tokens when it is falsy.
    const maxTokens = profile.max_output_tokens ?? 0;
    return {
      type: "chat" as const,
      id: model.model_id,
      name: `${profileName} (${profile.selection_status ?? "current deployment"}): ${model.display_name}`,
      api: contract.api,
      baseUrl: `http://${host}:${port}${path}`,
      input: model.kind === "vision"
        ? ["text", "image"] as ("text" | "image")[]
        : ["text"] as ("text" | "image")[],
      cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
      reasoning: false,
      contextWindow: profile.context_layers.client_effective_ctx,
      maxTokens,
    };
  });
}

export function parseSwitchJson(stdout: string): SwitchJsonDoc {
  let value: unknown;
  try {
    value = JSON.parse(stdout.trim());
  } catch {
    throw new Error(`switch-json: malformed JSON response: ${stdout.slice(0, 200)}`);
  }
  if (typeof value !== "object" || value === null) {
    throw new Error("switch-json: expected JSON object");
  }
  const doc = value as Record<string, unknown>;
  if (doc.api_version !== EXPECTED_API_VERSION) {
    throw new Error(`switch-json: unsupported api_version ${String(doc.api_version)}`);
  }
  if (doc.operation !== "switch") throw new Error(`switch-json: unexpected operation ${String(doc.operation)}`);
  if (doc.ownership !== "STARTED" && doc.ownership !== "BORROWED") {
    throw new Error(`switch-json: invalid ownership value ${String(doc.ownership)}`);
  }
  if (typeof doc.profile !== "string" || doc.profile.length === 0) {
    throw new Error("switch-json: missing or empty profile");
  }
  if (typeof doc.pid !== "number" || !Number.isInteger(doc.pid) || doc.pid <= 0) {
    throw new Error(`switch-json: invalid pid ${String(doc.pid)}`);
  }
  if (typeof doc.endpoint !== "string" || doc.endpoint.length === 0) {
    throw new Error("switch-json: missing or empty endpoint");
  }
  return doc as SwitchJsonDoc;
}

export function parseStopOwnedJson(stdout: string): StopOwnedJsonDoc {
  let value: unknown;
  try {
    value = JSON.parse(stdout.trim());
  } catch {
    throw new Error(`stop-owned-json: malformed JSON response: ${stdout.slice(0, 200)}`);
  }
  if (typeof value !== "object" || value === null) {
    throw new Error("stop-owned-json: expected JSON object");
  }
  const doc = value as Record<string, unknown>;
  if (doc.api_version !== EXPECTED_API_VERSION) {
    throw new Error(`stop-owned-json: unsupported api_version ${String(doc.api_version)}`);
  }
  if (doc.operation !== "stop_owned") {
    throw new Error(`stop-owned-json: unexpected operation ${String(doc.operation)}`);
  }
  if (doc.result !== "STOPPED" && doc.result !== "NOT_OWNED_OR_REPLACED") {
    throw new Error(`stop-owned-json: unexpected result ${String(doc.result)}`);
  }
  if (typeof doc.profile !== "string" || typeof doc.pid !== "number") {
    throw new Error("stop-owned-json: missing ownership fields");
  }
  return doc as StopOwnedJsonDoc;
}

async function stopOwned(
  pi: ExtensionAPI,
  state: LifecycleState,
  ctx: ExtensionContext,
): Promise<void> {
  if (state.ownership !== "STARTED") return;
  const result = await pi.exec(
    join(state.projectRoot, "scripts", "llm"),
    ["stop-owned-json", "--expected-profile", state.profile, "--expected-pid", String(state.pid)],
    { cwd: state.projectRoot, timeout: 120_000 },
  );
  if (result.code !== 0) {
    const detail = result.stderr || result.stdout || "unknown stop-owned-json failure";
    if (ctx.hasUI) ctx.ui.notify(`Local runtime cleanup failed: ${detail}`, "warning");
    return;
  }
  const doc = parseStopOwnedJson(result.stdout);
  if (doc.result === "STOPPED" && ctx.hasUI) {
    ctx.ui.setStatus("neuralengine-local-lifecycle", undefined);
  }
}

export default function localModelProjection(pi: ExtensionAPI): void {
  const { path: manifestPath, value: manifest } = loadManifest();
  const provider = manifest.clients.pi.provider;
  const models = projectLocalModels(manifest);
  if (models.length === 0) throw new Error("Manifest contains no Pi local model routes");
  pi.registerProvider(provider, {
    name: "NeuralEngine local models",
    api: manifest.clients.pi.api,
    baseUrl: models[0].baseUrl,
    apiKey: "local-not-metered",
    models,
  });

  const projectRoot = dirname(manifestPath);
  let state: LifecycleState | null = null;
  let shutdownDone = false;

  async function selectModel(
    model: { provider: string; id: string },
    ctx: ExtensionContext,
  ): Promise<void> {
    const selection = findLocalSelection(manifest, model.provider, model.id);
    const previous = state;
    if (selection && previous && previous.profile === manifest.runtime_profiles[selection.profileName]?.legacy_identity) {
      return;
    }

    if (previous?.ownership === "BORROWED" && selection !== null) {
      if (ctx.hasUI) {
        ctx.ui.notify("A borrowed local runtime is active; refusing to replace it", "warning");
        ctx.ui.setStatus("neuralengine-local-lifecycle", "⚠️ borrowed runtime preserved");
      }
      return;
    }

    state = null;
    if (previous) await stopOwned(pi, previous, ctx);
    if (!selection) {
      if (ctx.hasUI) {
        ctx.ui.setStatus(
          "neuralengine-local-lifecycle",
          `⛅ ${model.provider}/${model.id} (no local runtime)`,
        );
      }
      return;
    }

    if (ctx.hasUI) ctx.ui.setStatus("neuralengine-local-lifecycle", `⏳ starting ${selection.profileName}`);
    const result = await pi.exec(
      join(projectRoot, "scripts", "llm"),
      ["switch-json", selection.profileName],
      { cwd: projectRoot, timeout: 120_000 },
    );
    if (result.code !== 0) {
      const detail = result.stderr || result.stdout || "unknown switch-json failure";
      if (ctx.hasUI) {
        ctx.ui.notify(`Local runtime start failed: ${detail}`, "error");
        ctx.ui.setStatus("neuralengine-local-lifecycle", "❌ local runtime failed");
      }
      return;
    }
    const doc = parseSwitchJson(result.stdout);
    state = {
      profile: doc.profile,
      pid: doc.pid,
      endpoint: doc.endpoint,
      ownership: doc.ownership,
      projectRoot,
    };
    if (ctx.hasUI) {
      const label = doc.ownership === "STARTED" ? "started" : "borrowed";
      ctx.ui.setStatus(
        "neuralengine-local-lifecycle",
        `${doc.ownership === "STARTED" ? "🟢" : "🔵"} ${doc.profile} pid=${doc.pid} (${label})`,
      );
    }
  }

  pi.on("session_start", async (_event, ctx) => {
    shutdownDone = false;
    if (ctx.model) await selectModel(ctx.model, ctx);
  });

  pi.on("model_select", async (event, ctx) => {
    shutdownDone = false;
    await selectModel(event.model, ctx);
  });

  pi.on("session_shutdown", async (_event, ctx) => {
    if (shutdownDone) return;
    shutdownDone = true;
    const previous = state;
    state = null;
    if (previous) await stopOwned(pi, previous, ctx);
  });
}

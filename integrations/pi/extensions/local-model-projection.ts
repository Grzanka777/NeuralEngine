/** Manifest-derived Pi local routes and ownership-aware local runtime lifecycle. */
import { existsSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import type {
  ApiStreamSimpleFunction,
  SimpleStreamOptions,
  TranscriptContext,
} from "@earendil-works/pi-ai/compat";
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
      role_profiles: Record<string, string>;
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
  process_start_ticks: number;
  endpoint: string;
}

export interface VerifyJsonDoc {
  api_version: 1;
  operation: "verify";
  result: "VERIFIED";
  profile: string;
  pid: number;
  process_start_ticks: number;
  endpoint: string;
}

export interface StopOwnedJsonDoc {
  api_version: 1;
  operation: "stop_owned";
  result: "STOPPED" | "NOT_OWNED_OR_REPLACED";
  profile: string;
  pid: number;
  process_start_ticks: number;
}

interface LifecycleState {
  profile: string;
  logicalRole: string;
  pid: number;
  processStartTicks: number;
  endpoint: string;
  ownership: "STARTED" | "BORROWED";
  projectRoot: string;
  selectionGeneration: number;
}

type StopOwnedResult =
  | { ok: true; result: "STOPPED" | "BORROWED_NO_STOP" }
  | { ok: false; error: string };

function reportFailure(ctx: ExtensionContext, message: string): void {
  // Normal interactive shutdown stops the TUI before awaiting extension hooks.
  // stderr remains visible then, and is also the diagnostic path without UI.
  console.error(message);
  if (ctx.hasUI) {
    ctx.ui.notify(message, "error");
    ctx.ui.setStatus("neuralengine-local-lifecycle", `❌ ${message}`);
  }
}

interface LocalSelection {
  profileName: string;
  modelId: string;
  logicalRole: string;
}

export function logicalRoleForProfile(manifest: Manifest, profileName: string): string {
  const role = Object.entries(manifest.clients.pi.role_profiles).find(
    ([, mappedProfile]) => mappedProfile === profileName,
  )?.[0];
  if (role) return role;
  if (profileName === "current-qwen36") return "OPTIONAL QWEN3.6";
  return "OPTIONAL LOCAL MODEL";
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
      return { profileName, modelId, logicalRole: logicalRoleForProfile(manifest, profileName) };
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
    if (
      host !== "127.0.0.1" || path !== "/v1" || !Number.isInteger(port) || port < 1 || port > 65535 ||
      model.kind !== "chat" || contract.api !== "openai-completions" ||
      !Number.isSafeInteger(profile.context_layers.client_effective_ctx) ||
      profile.context_layers.client_effective_ctx < 1
    ) throw new Error(`Unsafe Pi local route: ${profileName}`);
    // Pi's catalog renderer requires a numeric field. Zero is a deliberate
    // no-cap sentinel: the OpenAI adapter omits max_tokens when it is falsy.
    const maxTokens = profile.max_output_tokens ?? 0;
    const logicalRole = logicalRoleForProfile(manifest, profileName);
    return {
      type: "chat" as const,
      id: model.model_id,
      name: `${logicalRole} | profile=${profileName} | legacy=${profile.legacy_identity}: ${model.display_name}`
        + (profile.selection_status ? ` (${profile.selection_status})` : ""),
      api: contract.api,
      baseUrl: `http://${host}:${port}${path}`,
      input: ["text"] as ("text" | "image")[],
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
  if (typeof doc.pid !== "number" || !Number.isSafeInteger(doc.pid) || doc.pid <= 0) {
    throw new Error(`switch-json: invalid pid ${String(doc.pid)}`);
  }
  if (typeof doc.process_start_ticks !== "number"
    || !Number.isSafeInteger(doc.process_start_ticks) || doc.process_start_ticks <= 0) {
    throw new Error("switch-json: missing process start identity");
  }
  if (typeof doc.endpoint !== "string" || doc.endpoint.length === 0) {
    throw new Error("switch-json: missing or empty endpoint");
  }
  return doc as SwitchJsonDoc;
}

export function parseVerifyJson(stdout: string): VerifyJsonDoc {
  let value: unknown;
  try {
    value = JSON.parse(stdout.trim());
  } catch {
    throw new Error(`verify-json: malformed JSON response: ${stdout.slice(0, 200)}`);
  }
  if (typeof value !== "object" || value === null) {
    throw new Error("verify-json: expected JSON object");
  }
  const doc = value as Record<string, unknown>;
  if (doc.api_version !== EXPECTED_API_VERSION || doc.operation !== "verify"
    || doc.result !== "VERIFIED") {
    throw new Error("verify-json: receipt is not a verified lifecycle identity");
  }
  if (typeof doc.profile !== "string" || doc.profile.length === 0
    || typeof doc.pid !== "number" || !Number.isSafeInteger(doc.pid) || doc.pid <= 0
    || typeof doc.process_start_ticks !== "number"
    || !Number.isSafeInteger(doc.process_start_ticks) || doc.process_start_ticks <= 0
    || typeof doc.endpoint !== "string" || doc.endpoint.length === 0) {
    throw new Error("verify-json: missing exact process/endpoint fields");
  }
  return doc as VerifyJsonDoc;
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
  if (typeof doc.profile !== "string" || doc.profile.length === 0
    || typeof doc.pid !== "number" || !Number.isSafeInteger(doc.pid) || doc.pid <= 0) {
    throw new Error("stop-owned-json: missing ownership fields");
  }
  if (typeof doc.process_start_ticks !== "number"
    || !Number.isSafeInteger(doc.process_start_ticks) || doc.process_start_ticks <= 0) {
    throw new Error("stop-owned-json: missing process start identity");
  }
  return doc as StopOwnedJsonDoc;
}

async function stopOwned(
  pi: ExtensionAPI,
  state: LifecycleState,
  ctx: ExtensionContext,
): Promise<StopOwnedResult> {
  if (state.ownership !== "STARTED") return { ok: true, result: "BORROWED_NO_STOP" };
  try {
    const result = await pi.exec(
      join(state.projectRoot, "scripts", "llm"),
      [
        "stop-owned-json",
        "--expected-profile", state.profile,
        "--expected-pid", String(state.pid),
        "--expected-start-ticks", String(state.processStartTicks),
      ],
      { cwd: state.projectRoot, timeout: 120_000 },
    );
    if (result.code !== 0) {
      throw new Error(result.stderr || result.stdout || "unknown stop-owned-json failure");
    }
    const doc = parseStopOwnedJson(result.stdout);
    if (doc.profile !== state.profile || doc.pid !== state.pid
      || doc.process_start_ticks !== state.processStartTicks) {
      throw new Error("stop-owned-json: process identity does not match the tracked receipt");
    }
    // NOT_OWNED_OR_REPLACED includes absence AND replacement; it is not a
    // sanctioned ALREADY_STOPPED receipt and must not authorize another start.
    if (doc.result !== "STOPPED") throw new Error(`stop-owned-json: ${doc.result}`);
    if (ctx.hasUI) ctx.ui.setStatus("neuralengine-local-lifecycle", undefined);
    return { ok: true, result: "STOPPED" };
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    const message = `Local runtime cleanup failed: profile=${state.profile} pid=${state.pid}: ${detail}`;
    reportFailure(ctx, message);
    return { ok: false, error: message };
  }
}

export function streamWithPayloadAdmission(
  stockStreamSimple: ApiStreamSimpleFunction,
  model: Parameters<ApiStreamSimpleFunction>[0],
  context: TranscriptContext,
  options: SimpleStreamOptions | undefined,
  admit: (selected: Parameters<ApiStreamSimpleFunction>[0], payload: unknown) => Promise<void>,
) {
  const existingOnPayload = options?.onPayload;
  return stockStreamSimple(model, context, {
    ...options,
    onPayload: async (payload, selected) => {
      let effectivePayload: unknown = payload;
      let replacement: typeof payload | undefined;
      if (existingOnPayload) {
        replacement = await existingOnPayload(payload, selected);
        if (replacement !== undefined) effectivePayload = replacement;
      }
      await admit(selected, effectivePayload);
      return replacement;
    },
  });
}

export function registerLocalModelProjection(
  pi: ExtensionAPI,
  stockStreamSimple: ApiStreamSimpleFunction,
): void {
  const { path: manifestPath, value: manifest } = loadManifest();
  const provider = manifest.clients.pi.provider;
  const models = projectLocalModels(manifest);
  const projectRoot = dirname(manifestPath);
  const qwen36ProfileName = manifest.clients.pi.role_profiles.GENERAL;
  if (models.length !== 1 || manifest.clients.pi.local_profiles[0] !== qwen36ProfileName) {
    throw new Error("Manifest must project exactly one GENERAL route");
  }
  const qwen36Profile = manifest.runtime_profiles[qwen36ProfileName];
  const qwen36Model = manifest.models[qwen36Profile.model_ref];
  const qwen36Endpoint = `http://${qwen36Profile.endpoint.host}:${qwen36Profile.endpoint.port}`
    + qwen36Profile.endpoint.path;
  let state: LifecycleState | null = null;
  let selectedModel: { provider: string; id: string } | null = null;
  let shutdownDone = false;
  let closing = false;
  let generation = 0;
  let ownershipUnknown = false;
  let pending: Promise<void> = Promise.resolve();

  function assertQwen36Admission(
    selected: Parameters<ApiStreamSimpleFunction>[0],
    payload: unknown,
    model: Parameters<ApiStreamSimpleFunction>[0],
    requestGeneration: number,
    receipt: LifecycleState | null,
  ): void {
    const payloadModel = typeof payload === "object" && payload !== null
      ? (payload as Record<string, unknown>).model
      : undefined;
    const expectedSelection = { provider, id: qwen36Model.model_id };
    if (model.provider !== provider || model.id !== qwen36Model.model_id
      || model.api !== manifest.clients.pi.api || model.baseUrl !== qwen36Endpoint
      || selected.provider !== provider || selected.id !== qwen36Model.model_id
      || selected.api !== manifest.clients.pi.api || selected.baseUrl !== qwen36Endpoint
      || payloadModel !== qwen36Model.model_id
      || !selectedModel || selectedModel.provider !== expectedSelection.provider
      || selectedModel.id !== expectedSelection.id
      || requestGeneration !== generation || closing || shutdownDone || ownershipUnknown
      || !receipt || receipt !== state || receipt.selectionGeneration !== requestGeneration
      || receipt.profile !== qwen36Profile.legacy_identity || receipt.endpoint !== qwen36Endpoint
      || !Number.isSafeInteger(receipt.pid) || receipt.pid <= 0
      || !Number.isSafeInteger(receipt.processStartTicks) || receipt.processStartTicks <= 0
      || (receipt.ownership !== "STARTED" && receipt.ownership !== "BORROWED")) {
      throw new Error("Qwen3.6 request denied: selected model or lifecycle receipt is not current");
    }
  }

  async function verifyQwen36Admission(
    model: Parameters<ApiStreamSimpleFunction>[0],
    selected: Parameters<ApiStreamSimpleFunction>[0],
    payload: unknown,
    requestGeneration: number,
    receipt: LifecycleState | null,
  ): Promise<void> {
    assertQwen36Admission(selected, payload, model, requestGeneration, receipt);
    if (!receipt) throw new Error("Qwen3.6 request denied: lifecycle receipt is absent");
    const result = await pi.exec(
      join(projectRoot, "scripts", "llm"),
      [
        "verify-json",
        "--expected-profile", receipt.profile,
        "--expected-pid", String(receipt.pid),
        "--expected-start-ticks", String(receipt.processStartTicks),
      ],
      { cwd: projectRoot, timeout: 15_000 },
    );
    if (result.code !== 0) {
      throw new Error(result.stderr || result.stdout || "verify-json did not confirm readiness");
    }
    const verified = parseVerifyJson(result.stdout);
    if (verified.profile !== receipt.profile || verified.pid !== receipt.pid
      || verified.process_start_ticks !== receipt.processStartTicks
      || verified.endpoint !== qwen36Endpoint) {
      throw new Error("Qwen3.6 request denied: canonical verification receipt does not match selection");
    }
    assertQwen36Admission(selected, payload, model, requestGeneration, receipt);
  }

  pi.registerProvider(provider, {
    name: "NeuralEngine local models",
    api: manifest.clients.pi.api,
    baseUrl: models[0].baseUrl,
    apiKey: "local-not-metered",
    models,
    streamSimple: (model, context, options) => {
      if (model.provider === provider && model.id === qwen36Model.model_id) {
        const requestGeneration = generation;
        const receipt = state;
        return streamWithPayloadAdmission(
          stockStreamSimple,
          model,
          context,
          {
            ...options,
            fetch: (input, init) => {
              const url = input instanceof Request ? input.url : String(input);
              if (url !== qwen36Endpoint + "/chat/completions") {
                throw new Error("Qwen3.6 request denied: transport URL differs from the manifest");
              }
              return (options?.fetch ?? globalThis.fetch)(input, { ...init, redirect: "error" });
            },
          },
          (selected, payload) => verifyQwen36Admission(
            model, selected, payload, requestGeneration, receipt,
          ),
        );
      }
      throw new Error("Unrecognized NeuralEngine local provider route");
    },
  });

  function enqueue(action: () => Promise<void>, ctx: ExtensionContext): Promise<void> {
    const next = pending.then(action);
    pending = next.catch((error) => {
      reportFailure(ctx, `Local runtime lifecycle failed: ${String(error)}`);
    });
    return pending;
  }

  async function selectModel(
    model: { provider: string; id: string },
    ctx: ExtensionContext,
  ): Promise<void> {
    if (ownershipUnknown) {
      reportFailure(ctx, "Local runtime ownership unknown; operator cleanup required before another start");
      return;
    }
    const selection = findLocalSelection(manifest, model.provider, model.id);
    const previous = state;
    if (selection && previous && previous.profile === manifest.runtime_profiles[selection.profileName]?.legacy_identity) {
      previous.selectionGeneration = generation;
      return;
    }

    if (previous?.ownership === "BORROWED") {
      if (ctx.hasUI) {
        if (selection) ctx.ui.notify("A borrowed local runtime is active; refusing to replace it", "warning");
        ctx.ui.setStatus("neuralengine-local-lifecycle", "⚠️ borrowed runtime preserved");
      }
      return;
    }

    if (previous && !(await stopOwned(pi, previous, ctx)).ok) {
      return;
    }
    state = null;
    if (!selection) {
      if (ctx.hasUI) {
        ctx.ui.setStatus(
          "neuralengine-local-lifecycle",
          `⛅ ${model.provider}/${model.id} (no local runtime)`,
        );
      }
      return;
    }

    if (ctx.hasUI) {
      ctx.ui.setStatus(
        "neuralengine-local-lifecycle",
        `⏳ starting ${selection.logicalRole} (profile=${selection.profileName})`,
      );
    }
    let doc: SwitchJsonDoc;
    try {
      const result = await pi.exec(
        join(projectRoot, "scripts", "llm"),
        ["switch-json", selection.profileName],
        { cwd: projectRoot, timeout: 360_000 },
      );
      if (result.code !== 0) {
        throw new Error(result.stderr || result.stdout || "unknown switch-json failure");
      }
      doc = parseSwitchJson(result.stdout);
      const expected = manifest.runtime_profiles[selection.profileName];
      const { host, port, path } = expected.endpoint;
      if (doc.profile !== expected.legacy_identity || doc.endpoint !== `http://${host}:${port}${path}`) {
        throw new Error("switch-json: profile/endpoint does not match requested manifest route");
      }
    } catch (error) {
      // The launcher may have started a process before failing to return a
      // trustworthy ownership receipt. Never guess a PID or borrow it on retry.
      ownershipUnknown = true;
      reportFailure(ctx, `Local runtime start failed; ownership unknown; operator cleanup required: ${String(error)}`);
      return;
    }
    state = {
      profile: doc.profile,
      logicalRole: selection.logicalRole,
      pid: doc.pid,
      processStartTicks: doc.process_start_ticks,
      endpoint: doc.endpoint,
      ownership: doc.ownership,
      projectRoot,
      selectionGeneration: generation,
    };
    if (ctx.hasUI) {
      const label = doc.ownership === "STARTED" ? "started" : "borrowed";
      ctx.ui.setStatus(
        "neuralengine-local-lifecycle",
        `${doc.ownership === "STARTED" ? "🟢" : "🔵"} ${selection.logicalRole} `
          + `(profile=${selection.profileName}, legacy=${doc.profile}) pid=${doc.pid} (${label})`,
      );
    }
  }

  pi.on("session_start", async (_event, ctx) => {
    closing = false;
    const selected = ctx.model;
    selectedModel = selected ? { provider: selected.provider, id: selected.id } : null;
    const currentGeneration = ++generation;
    await enqueue(async () => {
      if (closing || currentGeneration !== generation) return;
      shutdownDone = false;
      if (selected) await selectModel(selected, ctx);
    }, ctx);
  });

  pi.on("model_select", async (event, ctx) => {
    if (closing) return;
    selectedModel = { provider: event.model.provider, id: event.model.id };
    const currentGeneration = ++generation;
    await enqueue(async () => {
      if (!closing && currentGeneration === generation) await selectModel(event.model, ctx);
    }, ctx);
  });

  pi.on("session_shutdown", async (_event, ctx) => {
    // Close admission immediately; wait for an in-flight switch to report its
    // owner before cleanup. Only a new session_start reopens admission.
    closing = true;
    selectedModel = null;
    ++generation;
    await enqueue(async () => {
      if (shutdownDone) return;
      if (ownershipUnknown) {
        reportFailure(ctx, "Local runtime ownership unknown at shutdown; operator cleanup required");
        return;
      }
      if (state && !(await stopOwned(pi, state, ctx)).ok) return;
      state = null;
      shutdownDone = true;
    }, ctx);
  });
}

export default async function localModelProjection(pi: ExtensionAPI): Promise<void> {
  const { streamSimple } = await import("@earendil-works/pi-ai/compat");
  registerLocalModelProjection(pi, streamSimple);
}

/** Pi cloud contract. No subprocess or local runtime lifecycle is registered. */
import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";

export function allowedModel(model: { provider: string; id: string } | undefined): boolean {
  return model?.provider === "deepseek" && model.id === "deepseek-flash";
}

export default function deepseekOnly(pi: ExtensionAPI): void {
  function deny(ctx: ExtensionContext): void {
    console.error("Pi requires deepseek/deepseek-flash. Other providers and local fallback are disabled.");
    ctx.abort();
    ctx.shutdown();
  }
  pi.on("session_start", async (_event, ctx) => {
    if (!allowedModel(ctx.model)) deny(ctx);
  });
  pi.on("model_select", async (_event, ctx) => {
    if (!allowedModel(ctx.model)) deny(ctx);
  });
  pi.on("input", async (_event, ctx) => {
    if (!allowedModel(ctx.model)) {
      deny(ctx);
      return { action: "handled" };
    }
    return { action: "continue" };
  });
  pi.on("before_provider_request", async (_event, ctx) => {
    // Pi catches extension exceptions, so an exception alone cannot enforce policy.
    if (!allowedModel(ctx.model)) deny(ctx);
  });
}

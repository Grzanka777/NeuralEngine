// Provider transport fake for the native Pi CLI. Never sends a request.
import { appendFileSync } from "node:fs";
import { Socket } from "node:net";

Socket.prototype.connect = function () {
  throw new Error("Network disabled in synthetic Pi test");
};

let requestedTool = false;
const fetchMock = async (input, options) => {
  const url = typeof input === "string" ? input : input.url ?? String(input);
  const body = options?.body;
  if (!url.endsWith("/chat/completions") || typeof body !== "string") {
    throw new Error("Unexpected test transport request");
  }
  const request = JSON.parse(body);
  appendFileSync(process.env.MEMORY_TEST_REQUESTS, JSON.stringify({ url, request }) + "\n");
  if (process.env.MEMORY_TEST_OUTCOME === "failed") {
    return new Response(JSON.stringify({ error: { message: "Synthetic provider failure" } }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    });
  }
  if (process.env.MEMORY_TEST_OUTCOME === "interrupted") {
    return new Promise((_resolve, reject) => {
      options.signal.addEventListener("abort", () => reject(options.signal.reason), { once: true });
    });
  }
  const chunk = (delta, finish_reason) =>
    JSON.stringify({
      id: "synthetic-request",
      object: "chat.completion.chunk",
      model: request.model,
      choices: [{ index: 0, delta, finish_reason }],
    });
  const toolPath = process.env.MEMORY_TEST_TOOL_PATH;
  const toolCall = toolPath && !requestedTool;
  requestedTool ||= Boolean(toolCall);
  const delta = toolCall ? {
    role: "assistant",
    tool_calls: [{
      id: "synthetic-read", index: 0, type: "function",
      function: { name: "read", arguments: JSON.stringify({ path: toolPath }) },
    }],
  } : { role: "assistant", content: "Unverified model claim." };
  return new Response(
    `data: ${chunk(delta, null)}\n\n` +
    `data: ${chunk({}, toolCall ? "tool_calls" : "stop")}\n\ndata: [DONE]\n\n`,
    { headers: { "Content-Type": "text/event-stream" } },
  );
};

// Pi configures Undici's globals only when fetch is still its startup reference.
Object.defineProperty(globalThis, "fetch", {
  get: () => (...args) => fetchMock(...args),
  configurable: true,
});

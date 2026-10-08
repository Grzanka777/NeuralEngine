// Read-only probe that executes the Pi guard's always-on guardToolCall().
//
// Usage:
//   node tests/pi_guard_probe.mjs <extension-path> '<json-array-of-commands>'
//
// The extension is imported through Node's built-in TypeScript stripping.
// Output is a JSON object mapping each command to its refusal reason or null.

import { pathToFileURL } from "node:url";

const [extensionPath, commandsJson] = process.argv.slice(2);
const commands = JSON.parse(commandsJson);

const guard = await import(pathToFileURL(extensionPath).href);

const classifications = Object.fromEntries(
  commands.map((command) => [
    command,
    guard.guardToolCall(
      "bash",
      { command },
      process.cwd(),
      process.env.HOME ?? "",
      process.cwd(),
    ) ?? null,
  ]),
);

process.stdout.write(JSON.stringify(classifications));

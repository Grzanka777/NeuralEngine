// Read-only probe that executes the Pi guard's `classifyProtectedCommand()`.
//
// Usage:
//   node tests/pi_guard_probe.mjs <extension-path> '<json-array-of-commands>'
//
// The extension is a `.ts` file with only type-only imports, so it can be
// imported directly by Node's built-in type stripping (Node >= 23). Output is
// a JSON object mapping each command to its classification reason or null.

import { pathToFileURL } from "node:url";

const [extensionPath, commandsJson] = process.argv.slice(2);
const commands = JSON.parse(commandsJson);

const guard = await import(pathToFileURL(extensionPath).href);

const classifications = Object.fromEntries(
	commands.map((command) => [command, guard.classifyProtectedCommand(command) ?? null]),
);

process.stdout.write(JSON.stringify(classifications));

// Read-only probe for `.pi/extensions/neuralengine-guard.ts`.
//
// Usage:
//   node tests/pi_guard_probe.mjs <extension-path> '<json-array-of-commands>'
//   node tests/pi_guard_probe.mjs --tool-call <extension-path> '<json-spec>'
//
// The extension uses only type-only external imports, so Node executes it
// directly without installing package dependencies.

import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

const args = process.argv.slice(2);

if (args[0] === "--tool-call") {
	const [, extensionPath, specJson] = args;
	const spec = JSON.parse(specJson);
	const guard = await import(pathToFileURL(extensionPath).href);

	if (spec.neuralHome === null) {
		delete process.env.NEURAL_HOME;
	} else if (typeof spec.neuralHome === "string") {
		process.env.NEURAL_HOME = spec.neuralHome;
	}

	process.env.HOME = spec.home;
	const runMutation = async (input) => {
		const packageUrl = pathToFileURL(spec.runtimePackage + "/");
		const manifest = JSON.parse(readFileSync(new URL("package.json", packageUrl), "utf8"));
		if (manifest.name !== "@earendil-works/pi-coding-agent") {
			throw new Error("Expected the installed Pi coding agent package");
		}
		const { createWriteToolDefinition, createEditToolDefinition } = await import(
			new URL(manifest.exports["."].import, packageUrl).href
		);
		const factory = spec.toolName === "edit" ? createEditToolDefinition : createWriteToolDefinition;
		await factory(spec.cwd).execute("probe", input);
		return { pi: manifest.version, node: process.version };
	};
	const input = spec.toolName === "edit"
		? { path: spec.path, edits: [{ oldText: "before", newText: "after" }] }
		: { path: spec.path, content: "after" };

	if (spec.mode === "runtime") {
		process.stdout.write(JSON.stringify(await runMutation(input)));
	} else if (spec.mode === "session") {
		delete process.env.NEURAL_PI_BOUNDED_CODE;
		delete process.env.NEURAL_PI_POLICY_FILE;
		delete process.env.NEURALENGINE_PI_PROJECT_ROOT;
		if (spec.policyPath) {
			process.env.NEURAL_PI_BOUNDED_CODE = "1";
			process.env.NEURAL_PI_POLICY_FILE = spec.policyPath;
		}

		const handlers = new Map();
		const pi = {
			on(eventName, handler) {
				handlers.set(eventName, handler);
			},
			registerCommand() {},
			appendEntry() {},
		};
		const ctx = {
			cwd: spec.cwd,
			hasUI: false,
			sessionManager: { getBranch: () => [] },
			ui: {
				setStatus() {},
				notify() {},
				confirm: async () => false,
			},
			shutdown() {},
			abort() {},
		};

		guard.default(pi);
		await handlers.get("session_start")({}, ctx);
		await handlers.get("input")({}, ctx);
		const decision = await handlers.get("tool_call")(
			{
				toolName: spec.toolName,
				input,
				toolCallId: "probe-call-1",
			},
			ctx,
		);
		const runtime = spec.runtimePackage && !decision?.block ? await runMutation(input) : undefined;
		process.stdout.write(JSON.stringify({ decision: decision ?? null, runtime }));
	} else {
		const reason = guard.guardToolCall(
			spec.toolName,
			{ path: spec.path },
			spec.cwd,
			spec.home,
			spec.projectRoot ?? spec.cwd,
		);
		process.stdout.write(JSON.stringify({ reason: reason ?? null }));
	}
} else {
	const [extensionPath, commandsJson] = args;
	const commands = JSON.parse(commandsJson);
	const guard = await import(pathToFileURL(extensionPath).href);

	const classifications = Object.fromEntries(
		commands.map((command) => [command, guard.classifyProtectedCommand(command) ?? null]),
	);

	process.stdout.write(JSON.stringify(classifications));
}

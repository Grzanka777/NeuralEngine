import type {
	ExtensionAPI,
	ExtensionContext,
	ToolCallEvent,
} from "@earendil-works/pi-coding-agent";

type ProtectedCommand = {
	reason: string;
	pattern: RegExp;
};

const protectedCommands: ProtectedCommand[] = [
	{
		reason: "Git mutation requires separate explicit authorization",
		pattern:
			/\bgit\s+(?:(?:-[Cc]\s+\S+|--(?:git-dir|work-tree|namespace|exec-path|config-env)\s+\S+|--?[A-Za-z][\w-]*(?:=\S+)?)\s+)*(?:add\b|apply\s+--cached\b|rm\s+--cached\b|commit\b|push\b|merge\b|tag\b|reset\s+--hard\b|clean\b)/i,
	},
	{
		reason: "NeuralEngine durable-state mutation requires separate explicit authorization",
		pattern:
			/\bneural\s+(?:init\b|decision\s+(?:add\b|accept\b|action\s+add\b|outcome\s+add\b|review\s+add\b)|experience\s+(?:add\b|from-observation\b|from-review\b)|evaluation\s+add\b|knowledge\s+(?:add\b|from-experience\b)|playbook\s+add\b|proposal\s+(?:add\b|status\b)|revision\s+(?:add\b|activate\b|supersede\b|reject\b)|run\s+add\b|development-evidence\s+apply\b|brain\s+(?:recover\b|adopt\b))/i,
	},
	{
		reason: "Privileged system mutation requires separate explicit authorization",
		pattern: /\bsudo(?:\s|$)/i,
	},
	{
		reason: "Recursive removal requires separate explicit authorization",
		pattern: /\brm\s+(?:-[^\s]*r[^\s]*\b|--recursive\b)/i,
	},
];

export function classifyProtectedCommand(command: string): string | undefined {
	return protectedCommands.find(({ pattern }) => pattern.test(command))?.reason;
}

async function guardToolCall(event: ToolCallEvent, ctx: ExtensionContext) {
	if (event.toolName !== "bash") return undefined;

	const reason = classifyProtectedCommand(event.input.command);
	if (!reason) return undefined;

	if (!ctx.hasUI) {
		return { block: true, reason: `${reason}; non-interactive Pi execution is blocked` };
	}

	const allowed = await ctx.ui.confirm(
		"Protected NeuralEngine command",
		`${reason}. Authorize this one command?`,
	);
	if (!allowed) {
		return { block: true, reason: "Blocked by the NeuralEngine Pi guard" };
	}

	return undefined;
}

export default function (pi: ExtensionAPI) {
	pi.on("tool_call", (event, ctx) => guardToolCall(event, ctx));
}

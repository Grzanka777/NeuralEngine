import {
  lstatSync,
  readFileSync,
  realpathSync,
  statSync,
} from "node:fs";
import { createHash } from "node:crypto";
import path from "node:path";
import {
  GitAuthorityController,
  classifyGitCommand,
  isGitAuthenticationMutation,
  isGitAuthorityStop,
} from "./git-authority.ts";
import type {
  GitAuthorizationReceipt,
  GitCommitSnapshot,
  GitPushAuthorizationReview,
  GitStageSnapshot,
} from "./git-authority.ts";

export { classifyGitCommand } from "./git-authority.ts";

export const CAPABILITIES = ["READ", "SEARCH", "EDIT", "CREATE", "DELETE", "VALIDATION", "SHELL_READONLY", "SHELL_MUTATING", "GIT_READ", "GIT_STAGE", "GIT_COMMIT", "GIT_PUSH", "GIT_FORCE_PUSH", "GIT_REMOTE_MUTATION", "GIT_AUTH_MUTATION", "GIT_READONLY", "GIT_MUTATING", "NETWORK", "SYSTEM_MUTATION"] as const;
export type Capability = typeof CAPABILITIES[number];
export type ExecutionMode = "OBSERVE" | "DISCOVER" | "BOUNDED_EXECUTE" | "PATCH" | "EXPANDED_EXECUTE";
export type GovernorEventType = "SESSION_START" | "PROMPT_ADMIT" | "TOOL_PRE" | "TOOL_POST" | "VALIDATION_RESULT" | "COMPACTION" | "FINAL_CLAIM" | "SESSION_END";
export type EvidenceStatus = "KNOWN" | "INFERRED" | "UNKNOWN";
export interface ScopeExpansionRequest {
  readonly requestedPath: string;
  readonly capability: Capability;
  readonly reason: string;
  readonly evidenceReference: string;
  readonly runId: string;
}

export function canonicalJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (value !== null && typeof value === "object") {
    return `{${Object.entries(value).sort(([left], [right]) => left < right ? -1 : left > right ? 1 : 0).map(([key, item]) => `${JSON.stringify(key)}:${canonicalJson(item)}`).join(",")}}`;
  }
  return JSON.stringify(value) ?? "null";
}

export function policySha256(policy: AgentGovernorPolicy): string {
  return createHash("sha256").update(canonicalJson(policy)).digest("hex");
}

export interface AgentGovernorPolicy {
  readonly RUN_ID: string;
  readonly POLICY_REVISION: number;
  readonly WORKSPACE_ROOT?: string;
  readonly MODE: ExecutionMode;
  readonly ROLE: "REVIEW" | "CODE" | "PATCH" | "VISION";
  readonly PREVIOUS_POLICY_SHA256?: string;
  readonly EVIDENCE_PACK_REF?: string;
  readonly EVIDENCE_PACK_SHA256?: string;
  readonly ALLOWED_READ_FILES: readonly string[];
  readonly ALLOWED_EDIT_FILES: readonly string[];
  readonly ALLOW_NEW_FILES: boolean;
  readonly MAX_FILES_TOUCHED: number;
  readonly MAX_DELETED_LINES: number;
  readonly MAX_TEST_FILE_SHRINK_PERCENT: number;
  readonly MAX_REWRITE_SHRINK_PERCENT: number;
  readonly AUTHORIZED_REWRITE_FILES: readonly string[];
  readonly MAX_CORRECTION_CYCLES: number;
  readonly MAX_REPEATED_FAILURES?: number;
  readonly MAX_TOTAL_CORRECTIONS?: number;
  readonly MAX_COMPACTIONS: number;
  readonly REQUIRE_TEST_AFTER_EDIT: boolean;
  readonly VALIDATION_COMMANDS: readonly string[];
  readonly TEST_COMMANDS: readonly string[];
  readonly SAFE_GIT_COMMANDS: readonly string[];
  readonly AUTHORIZED_GIT_STAGE_PATHS?: readonly string[];
}

export interface GovernorSnapshot {
  readonly version: 1;
  readonly policyFingerprint: string;
  readonly policySha256?: string;
  readonly policyRevision?: number;
  readonly runId?: string;
  readonly toolCallCount?: number;
  readonly repeatedReads?: number;
  readonly startedAtMs?: number;
  readonly modelClaim?: string;
  readonly scopeExpansionRequests?: readonly ScopeExpansionRequest[];
  readonly toolDecisions?: readonly Readonly<Record<string, unknown>>[];
  readonly validationResults?: readonly Readonly<Record<string, unknown>>[];
  readonly replanRequired?: boolean;
  readonly modifiedFiles: readonly string[];
  readonly sourceEditEpoch: number;
  readonly validationPassEpochs: Readonly<Record<string, number>>;
  readonly correctionCycles: number;
  readonly totalCorrections?: number;
  readonly repeatedFailures?: number;
  readonly distinctFailureEvidenceCount?: number;
  readonly lastFailureEvidence?: string;
  readonly compactions: number;
  readonly stopReason?: string;
}

export interface GovernorDecision {
  readonly allowed: boolean;
  readonly reason?: string;
  readonly capability?: Capability;
  readonly outcome?: "CONTINUE" | "REQUEST_SCOPE_EXPANSION" | "REPLAN_REQUIRED" | "ESCALATE" | "STOP";
}

const DEFAULTS = {
  RUN_ID: "legacy-v0",
  POLICY_REVISION: 1,
  WORKSPACE_ROOT: undefined,
  MODE: "BOUNDED_EXECUTE",
  ROLE: "CODE",
  PREVIOUS_POLICY_SHA256: undefined,
  EVIDENCE_PACK_REF: undefined,
  EVIDENCE_PACK_SHA256: undefined,
  ALLOWED_READ_FILES: [],
  ALLOWED_EDIT_FILES: [],
  ALLOW_NEW_FILES: false,
  MAX_FILES_TOUCHED: 3,
  MAX_DELETED_LINES: 100,
  MAX_TEST_FILE_SHRINK_PERCENT: 20,
  MAX_REWRITE_SHRINK_PERCENT: 20,
  AUTHORIZED_REWRITE_FILES: [],
  MAX_CORRECTION_CYCLES: 2,
  MAX_COMPACTIONS: 1,
  REQUIRE_TEST_AFTER_EDIT: true,
  VALIDATION_COMMANDS: [],
  TEST_COMMANDS: [],
  SAFE_GIT_COMMANDS: [
    "git status --short",
    "git status --short --branch",
    "git diff --stat",
    "git diff --check",
  ],
} as const;

const POLICY_KEYS = [...Object.keys(DEFAULTS), "MAX_REPEATED_FAILURES", "MAX_TOTAL_CORRECTIONS"];
POLICY_KEYS.push("AUTHORIZED_GIT_STAGE_PATHS");

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function oneOf<T extends string>(value: unknown, values: readonly T[], key: string): T {
  if (typeof value !== "string" || !values.includes(value as T)) throw new Error(`${key} is invalid`);
  return value as T;
}

function stringList(value: unknown, key: string): string[] {
  if (!Array.isArray(value) || value.some((item) => typeof item !== "string" || !item.trim())) {
    throw new Error(`${key} must be an array of non-empty strings`);
  }
  return [...new Set((value as string[]).map((item) => item.trim()))];
}

function integer(value: unknown, key: string): number {
  if (typeof value !== "number" || !Number.isInteger(value) || value < 0) {
    throw new Error(`${key} must be a non-negative integer`);
  }
  return value;
}

function percentage(value: unknown, key: string): number {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0 || value > 100) {
    throw new Error(`${key} must be between 0 and 100`);
  }
  return value;
}

function isSafeValidationCommand(command: string): boolean {
  if (/[;&|`$<>\\\n\r*?]/.test(command)) return false;
  const allowedPrefixes = [
    "uv run pytest",
    "uv run ruff check",
    "uv run ruff format --check",
    "uv run mypy",
    "node --test",
  ];
  if (!allowedPrefixes.some((prefix) => command === prefix || command.startsWith(`${prefix} `))) return false;
  const args = command.split(/\s+/);
  if (args.some((arg) => ["--help", "-h", "--version"].includes(arg))) return false;
  if (args[0] === "uv" && args[1] === "run" && args[2] === "ruff" && args[3] === "check") {
    if (args.some((arg) => ["--fix", "--fix-only"].includes(arg))) return false;
  }
  if (args[0] === "uv" && args[1] === "run" && args[2] === "pytest") {
    if (args.includes("--collect-only")) return false;
  }
  return true;
}

function relativeFileList(value: unknown, key: string): string[] {
  return stringList(value, key).map((file) => {
    if (path.isAbsolute(file) || file.includes("\\") || file.split("/").includes("..")) {
      throw new Error(`${key} entries must be normalized repository-relative file paths: ${file}`);
    }
    const normalized = path.posix.normalize(file);
    if (normalized !== file || normalized === ".") {
      throw new Error(`${key} entries must be normalized repository-relative file paths: ${file}`);
    }
    return file;
  });
}

export function parseGovernorPolicy(value: unknown): AgentGovernorPolicy {
  if (!isRecord(value)) throw new Error("Governor policy must be a JSON object");
  const unexpected = Object.keys(value).filter((key) => !POLICY_KEYS.includes(key));
  if (unexpected.length) throw new Error(`Unknown governor policy field: ${unexpected[0]}`);

  const allowedRead = relativeFileList(value.ALLOWED_READ_FILES ?? DEFAULTS.ALLOWED_READ_FILES, "ALLOWED_READ_FILES");
  const allowedEdit = relativeFileList(value.ALLOWED_EDIT_FILES ?? DEFAULTS.ALLOWED_EDIT_FILES, "ALLOWED_EDIT_FILES");
  const rewrites = relativeFileList(value.AUTHORIZED_REWRITE_FILES ?? DEFAULTS.AUTHORIZED_REWRITE_FILES, "AUTHORIZED_REWRITE_FILES");
  const validationCommands = stringList(value.VALIDATION_COMMANDS ?? DEFAULTS.VALIDATION_COMMANDS, "VALIDATION_COMMANDS");
  const testCommands = stringList(value.TEST_COMMANDS ?? DEFAULTS.TEST_COMMANDS, "TEST_COMMANDS");
  const gitCommands = stringList(value.SAFE_GIT_COMMANDS ?? DEFAULTS.SAFE_GIT_COMMANDS, "SAFE_GIT_COMMANDS");
  const authorizedGitStagePaths = value.AUTHORIZED_GIT_STAGE_PATHS === undefined
    ? undefined
    : relativeFileList(value.AUTHORIZED_GIT_STAGE_PATHS, "AUTHORIZED_GIT_STAGE_PATHS");
  if (gitCommands.some((command) => !(DEFAULTS.SAFE_GIT_COMMANDS as readonly string[]).includes(command))) {
    throw new Error("SAFE_GIT_COMMANDS may contain only the built-in read-only inspection commands");
  }
  if (validationCommands.some((command) => !isSafeValidationCommand(command))) {
    throw new Error("VALIDATION_COMMANDS must be a single read-only pytest, Ruff check, Ruff format check, MyPy, or Node test command");
  }
  if (testCommands.some((command) => !validationCommands.includes(command))) {
    throw new Error("Every TEST_COMMANDS entry must also appear in VALIDATION_COMMANDS");
  }
  if (value.REQUIRE_TEST_AFTER_EDIT !== false && allowedEdit.length > 0 && testCommands.length === 0) {
    throw new Error("A policy with editable files must configure at least one TEST_COMMANDS entry");
  }
  if (value.ALLOW_NEW_FILES !== undefined && typeof value.ALLOW_NEW_FILES !== "boolean") {
    throw new Error("ALLOW_NEW_FILES must be a boolean");
  }
  if (value.REQUIRE_TEST_AFTER_EDIT !== undefined && typeof value.REQUIRE_TEST_AFTER_EDIT !== "boolean") {
    throw new Error("REQUIRE_TEST_AFTER_EDIT must be a boolean");
  }
  const mode = oneOf(value.MODE ?? DEFAULTS.MODE, ["OBSERVE", "DISCOVER", "BOUNDED_EXECUTE", "PATCH", "EXPANDED_EXECUTE"], "MODE");
  const role = oneOf(value.ROLE ?? DEFAULTS.ROLE, ["REVIEW", "CODE", "PATCH", "VISION"], "ROLE");
  if ((role === "PATCH") !== (mode === "PATCH")) {
    throw new Error("ROLE=PATCH requires MODE=PATCH, and MODE=PATCH requires ROLE=PATCH");
  }
  const runId = value.RUN_ID ?? DEFAULTS.RUN_ID;
  if (typeof runId !== "string" || !runId.trim()) throw new Error("RUN_ID must be non-empty");
  const revision = integer(value.POLICY_REVISION ?? DEFAULTS.POLICY_REVISION, "POLICY_REVISION");
  if (revision < 1) throw new Error("POLICY_REVISION must be positive");
  const workspaceRoot = value.WORKSPACE_ROOT;
  if (workspaceRoot !== undefined && (typeof workspaceRoot !== "string" || !path.isAbsolute(workspaceRoot))) {
    throw new Error("WORKSPACE_ROOT must be an absolute path");
  }
  if (runId !== "legacy-v0" && workspaceRoot === undefined) throw new Error("WORKSPACE_ROOT is required for a named run");
  const predecessor = value.PREVIOUS_POLICY_SHA256;
  if (predecessor !== undefined && (typeof predecessor !== "string" || !/^[a-f0-9]{64}$/.test(predecessor))) {
    throw new Error("PREVIOUS_POLICY_SHA256 must be a SHA-256 digest");
  }
  if (mode === "EXPANDED_EXECUTE" && (revision < 2 || !predecessor)) throw new Error("EXPANDED_EXECUTE requires a predecessor policy and revision");
  const evidencePackRef = value.EVIDENCE_PACK_REF;
  if (evidencePackRef !== undefined && (typeof evidencePackRef !== "string" || !evidencePackRef.trim())) throw new Error("EVIDENCE_PACK_REF must be non-empty");
  if (evidencePackRef) relativeFileList([evidencePackRef], "EVIDENCE_PACK_REF");
  const evidencePackHash = value.EVIDENCE_PACK_SHA256;
  if (evidencePackHash !== undefined && (typeof evidencePackHash !== "string" || !/^[a-f0-9]{64}$/.test(evidencePackHash))) throw new Error("EVIDENCE_PACK_SHA256 must be a SHA-256 digest");
  if (mode === "EXPANDED_EXECUTE" && !evidencePackRef) throw new Error("EXPANDED_EXECUTE requires EVIDENCE_PACK_REF");
  if (mode === "EXPANDED_EXECUTE" && !evidencePackHash) throw new Error("EXPANDED_EXECUTE requires EVIDENCE_PACK_SHA256");
  if (mode === "PATCH" && (integer(value.MAX_FILES_TOUCHED ?? DEFAULTS.MAX_FILES_TOUCHED, "MAX_FILES_TOUCHED") > 1 || integer(value.MAX_DELETED_LINES ?? DEFAULTS.MAX_DELETED_LINES, "MAX_DELETED_LINES") > 30)) {
    throw new Error("PATCH budget is at most one file and 30 deleted lines");
  }

  return Object.freeze({
    RUN_ID: runId,
    POLICY_REVISION: revision,
    ...(workspaceRoot ? { WORKSPACE_ROOT: workspaceRoot } : {}),
    MODE: mode,
    ROLE: role,
    ...(predecessor ? { PREVIOUS_POLICY_SHA256: predecessor } : {}),
    ...(evidencePackRef ? { EVIDENCE_PACK_REF: evidencePackRef } : {}),
    ...(evidencePackHash ? { EVIDENCE_PACK_SHA256: evidencePackHash } : {}),
    ALLOWED_READ_FILES: Object.freeze(allowedRead),
    ALLOWED_EDIT_FILES: Object.freeze(allowedEdit),
    ALLOW_NEW_FILES: value.ALLOW_NEW_FILES ?? DEFAULTS.ALLOW_NEW_FILES,
    MAX_FILES_TOUCHED: integer(value.MAX_FILES_TOUCHED ?? DEFAULTS.MAX_FILES_TOUCHED, "MAX_FILES_TOUCHED"),
    MAX_DELETED_LINES: integer(value.MAX_DELETED_LINES ?? DEFAULTS.MAX_DELETED_LINES, "MAX_DELETED_LINES"),
    MAX_TEST_FILE_SHRINK_PERCENT: percentage(
      value.MAX_TEST_FILE_SHRINK_PERCENT ?? DEFAULTS.MAX_TEST_FILE_SHRINK_PERCENT,
      "MAX_TEST_FILE_SHRINK_PERCENT",
    ),
    MAX_REWRITE_SHRINK_PERCENT: percentage(
      value.MAX_REWRITE_SHRINK_PERCENT ?? DEFAULTS.MAX_REWRITE_SHRINK_PERCENT,
      "MAX_REWRITE_SHRINK_PERCENT",
    ),
    AUTHORIZED_REWRITE_FILES: Object.freeze(rewrites),
    MAX_CORRECTION_CYCLES: integer(value.MAX_CORRECTION_CYCLES ?? DEFAULTS.MAX_CORRECTION_CYCLES, "MAX_CORRECTION_CYCLES"),
    ...(value.MAX_REPEATED_FAILURES === undefined ? {} : { MAX_REPEATED_FAILURES: integer(value.MAX_REPEATED_FAILURES, "MAX_REPEATED_FAILURES") }),
    ...(value.MAX_TOTAL_CORRECTIONS === undefined ? {} : { MAX_TOTAL_CORRECTIONS: integer(value.MAX_TOTAL_CORRECTIONS, "MAX_TOTAL_CORRECTIONS") }),
    MAX_COMPACTIONS: integer(value.MAX_COMPACTIONS ?? DEFAULTS.MAX_COMPACTIONS, "MAX_COMPACTIONS"),
    REQUIRE_TEST_AFTER_EDIT: value.REQUIRE_TEST_AFTER_EDIT ?? DEFAULTS.REQUIRE_TEST_AFTER_EDIT,
    VALIDATION_COMMANDS: Object.freeze(validationCommands),
    TEST_COMMANDS: Object.freeze(testCommands),
    SAFE_GIT_COMMANDS: Object.freeze(gitCommands),
    ...(authorizedGitStagePaths === undefined ? {} : { AUTHORIZED_GIT_STAGE_PATHS: Object.freeze(authorizedGitStagePaths) }),
  });
}

export function parseQualificationPolicy(value: unknown): AgentGovernorPolicy {
  const policy = parseGovernorPolicy(value);
  if (policy.RUN_ID === "legacy-v0") throw new Error("Qualification requires a named v1 RUN_ID");
  if (policy.MODE !== "BOUNDED_EXECUTE" && policy.MODE !== "EXPANDED_EXECUTE") {
    throw new Error("Qualification requires BOUNDED_EXECUTE or approved EXPANDED_EXECUTE mode");
  }
  if (policy.MAX_REPEATED_FAILURES === undefined) throw new Error("Qualification requires explicit MAX_REPEATED_FAILURES");
  if (policy.MAX_TOTAL_CORRECTIONS === undefined) throw new Error("Qualification requires explicit MAX_TOTAL_CORRECTIONS");
  return policy;
}

function canonicalTarget(root: string, candidate: string): { absolute: string; exists: boolean } {
  const absolute = path.resolve(root, candidate);
  let current = absolute;
  const suffix: string[] = [];
  while (true) {
    try {
      lstatSync(current);
      const resolved = realpathSync(current);
      return { absolute: path.resolve(resolved, ...suffix.reverse()), exists: suffix.length === 0 };
    } catch (error) {
      const code = (error as NodeJS.ErrnoException).code;
      if (code !== "ENOENT") throw error;
      const parent = path.dirname(current);
      if (parent === current) throw error;
      suffix.push(path.basename(current));
      current = parent;
    }
  }
}

function isInside(root: string, target: string): boolean {
  return target === root || target.startsWith(root + path.sep);
}

function lineCount(content: string): number {
  if (content.length === 0) return 0;
  const separators = content.match(/\r\n|\n|\r/g)?.length ?? 0;
  return separators + (/\r\n$|\n$|\r$/.test(content) ? 0 : 1);
}

function isTestFile(file: string): boolean {
  const normalized = file.replaceAll(path.sep, "/");
  const basename = path.posix.basename(normalized);
  return (
    normalized.split("/").includes("tests") ||
    /^test[_-]/i.test(basename) ||
    /\.(?:test|spec)\.[^.]+$/i.test(basename)
  );
}

function isSourceFile(file: string): boolean {
  return !/\.(?:md|rst|txt)$/i.test(file);
}

function getPath(input: Record<string, unknown>): string | undefined {
  return typeof input.path === "string" && input.path.length > 0 ? input.path : undefined;
}

export function classifyCommand(command: string, validationCommands: readonly string[] = []): Capability {
  const trimmed = command.trim();
  if (validationCommands.includes(trimmed) && isSafeValidationCommand(trimmed)) return "VALIDATION";
  if (isGitAuthenticationMutation(trimmed)) return "GIT_AUTH_MUTATION";
  if (/^git(?:\s|$)/.test(trimmed)) return classifyGitCommand(trimmed);
  if (!trimmed || /[;&|`$<>\\\n\r*?(){}]/.test(trimmed)) return "SHELL_MUTATING";
  const words = trimmed.split(/\s+/);
  if (words[0] === "git") {
    return "GIT_MUTATING";
  }
  if (["pacman", "systemctl", "chmod", "chown", "sudo", "run0", "install"].includes(words[0])) return "SYSTEM_MUTATION";
  if (["curl", "wget", "ssh", "scp"].includes(words[0])) return "NETWORK";
  if (words[0] === "rm") return "DELETE";
  if (["cp", "mv", "python", "python3", "perl", "sed", "tee", "touch", "mkdir", "uv", "npm", "node"].includes(words[0])) return "SHELL_MUTATING";
  if (["find", "cat"].includes(words[0]) && words.length === 2 && !words[1].startsWith("-")) return "SHELL_READONLY";
  if (words[0] === "rg" && words.length === 3 && !words.slice(1).some((word) => word.startsWith("-"))) return "SHELL_READONLY";
  return "SHELL_MUTATING";
}

export interface GovernorEvent {
  readonly type: GovernorEventType;
  readonly operation?: "READ" | "SEARCH" | "EDIT" | "CREATE" | "SHELL";
  readonly path?: string;
  readonly command?: string;
  readonly input?: Record<string, unknown>;
  readonly callId?: string;
  readonly failed?: boolean;
  readonly claim?: string;
  readonly evidenceReference?: string;
}

function editList(input: Record<string, unknown>): Array<{ oldText: string; newText: string }> | undefined {
  let edits: unknown = input.edits;
  if (typeof edits === "string") {
    try {
      edits = JSON.parse(edits) as unknown;
    } catch {
      return undefined;
    }
  }
  if (isRecord(edits) && typeof edits.oldText === "string" && typeof edits.newText === "string") {
    edits = [edits];
  }
  if (!Array.isArray(edits) && typeof input.oldText === "string" && typeof input.newText === "string") {
    edits = [{ oldText: input.oldText, newText: input.newText }];
  }
  if (!Array.isArray(edits) || edits.length === 0) return undefined;
  const normalized: Array<{ oldText: string; newText: string }> = [];
  for (const edit of edits) {
    if (!isRecord(edit) || typeof edit.oldText !== "string" || typeof edit.newText !== "string") {
      return undefined;
    }
    normalized.push({
      oldText: edit.oldText.replace(/\r\n|\r/g, "\n"),
      newText: edit.newText.replace(/\r\n|\r/g, "\n"),
    });
  }
  return normalized;
}

export class AgentGovernor {
  readonly #root: string;
  readonly #workingDirectory: string;
  readonly #policy: AgentGovernorPolicy;
  readonly #fingerprint: string;
  readonly #policySha256: string;
  readonly #allowedRead: Set<string>;
  readonly #allowedEdit: Set<string>;
  readonly #authorizedRewrites: Set<string>;
  readonly #modifiedFiles = new Set<string>();
  readonly #pendingMutations = new Map<string, { file: string }>();
  readonly #validationStarts = new Map<string, { command: string; epoch: number }>();
  readonly #validationPassEpochs = new Map<string, number>();
  #sourceEditEpoch = 0;
  #correctionCycles = 0;
  #totalCorrections = 0;
  #lastFailureEvidence: string | undefined;
  #compactions = 0;
  #toolCallCount = 0;
  #repeatedReads = 0;
  #startedAtMs = Date.now();
  #lastRead: string | undefined;
  #modelClaim: string | undefined;
  #replanRequired = false;
  readonly #scopeExpansionRequests: ScopeExpansionRequest[] = [];
  readonly #toolDecisions: Array<Readonly<Record<string, unknown>>> = [];
  readonly #validationResults: Array<Readonly<Record<string, unknown>>> = [];
  readonly #seenFailureEvidence = new Set<string>();
  readonly #gitAuthority: GitAuthorityController;
  #stopReason: string | undefined;
  readonly #persist: (snapshot: GovernorSnapshot) => void;

  constructor(
    policy: AgentGovernorPolicy,
    cwd: string,
    history: readonly unknown[] = [],
    persist: (snapshot: GovernorSnapshot) => void = () => undefined,
    workingDirectory: string = cwd,
  ) {
    this.#root = realpathSync(policy.WORKSPACE_ROOT ?? cwd);
    if (this.#root !== realpathSync(cwd)) throw new Error("Governor project root differs from policy workspace root");
    if (policy.MODE === "EXPANDED_EXECUTE") {
      const evidencePath = path.resolve(this.#root, policy.EVIDENCE_PACK_REF ?? "");
      const realEvidencePath = realpathSync(evidencePath);
      if (!isInside(this.#root, realEvidencePath) || realEvidencePath !== evidencePath || !statSync(evidencePath).isFile()) throw new Error("Expansion evidence path escapes the workspace");
      const actualHash = createHash("sha256").update(readFileSync(evidencePath)).digest("hex");
      if (actualHash !== policy.EVIDENCE_PACK_SHA256) throw new Error("Expansion evidence hash does not match policy");
    }
    this.#workingDirectory = realpathSync(workingDirectory);
    if (!isInside(this.#root, this.#workingDirectory)) {
      throw new Error("Working directory does not resolve inside the Governor project root");
    }
    this.#policy = policy;
    this.#fingerprint = JSON.stringify(policy);
    this.#policySha256 = policySha256(policy);
    this.#persist = persist;
    this.#gitAuthority = new GitAuthorityController(this.#root, policy.AUTHORIZED_GIT_STAGE_PATHS ?? []);
    this.#allowedRead = this.#canonicalPolicyPaths(policy.ALLOWED_READ_FILES);
    this.#allowedEdit = this.#canonicalPolicyPaths(policy.ALLOWED_EDIT_FILES);
    this.#authorizedRewrites = this.#canonicalPolicyPaths(policy.AUTHORIZED_REWRITE_FILES);
    this.#restore(history);
    if (history.length === 0) this.#save();
  }

  get policy(): AgentGovernorPolicy {
    return this.#policy;
  }

  /** Capture a displayable local path snapshot; this does not stage files. */
  prepareGitStageAuthorization(): GitStageSnapshot {
    return this.#gitAuthority.prepareGitStageAuthorization();
  }

  /** Revalidate an operator-reviewed stage snapshot; this is preflight only. */
  authorizeGitStage(review: GitStageSnapshot, explicitlyAuthorized: boolean): GitAuthorizationReceipt {
    if (!this.#canAuthorizeGitMutation()) return { allowed: false, reason: "Git staging authorization is unavailable in this mode or role" };
    return this.#recordGitAuthorizationReceipt(this.#gitAuthority.authorizeGitStage(review, explicitlyAuthorized));
  }

  /** Capture the current staged diff and exact message for host review. */
  prepareGitCommitAuthorization(commitMessage: string): GitCommitSnapshot {
    return this.#gitAuthority.prepareGitCommitAuthorization(commitMessage);
  }

  /** Revalidate an explicitly approved snapshot; host execution remains separate. */
  authorizeGitCommit(review: GitCommitSnapshot, explicitlyAuthorized: boolean): GitAuthorizationReceipt {
    if (!this.#canAuthorizeGitMutation()) return { allowed: false, reason: "Git commit authorization is unavailable in this mode or role" };
    return this.#recordGitAuthorizationReceipt(this.#gitAuthority.authorizeGitCommit(review, explicitlyAuthorized));
  }

  /** Capture branch, upstream, remote identity, HEAD, and ahead/behind for review. */
  prepareGitPushAuthorization(): GitPushAuthorizationReview {
    return this.#gitAuthority.prepareGitPushAuthorization();
  }

  /** Revalidate a separately approved push snapshot; this is not an atomic push. */
  authorizeGitPush(review: GitPushAuthorizationReview, explicitlyAuthorized: boolean): GitAuthorizationReceipt {
    if (!this.#canAuthorizeGitMutation()) return { allowed: false, reason: "Git push authorization is unavailable in this mode or role" };
    return this.#recordGitAuthorizationReceipt(this.#gitAuthority.authorizeGitPush(review, explicitlyAuthorized));
  }

  get policyHash(): string { return this.#policySha256; }
  get scopeExpansionRequests(): readonly ScopeExpansionRequest[] { return [...this.#scopeExpansionRequests]; }
  get systemVerdict(): "STOP" | "VALIDATION_PENDING" | "GREEN" {
    return this.stopped ? "STOP" : this.isGreen ? "GREEN" : "VALIDATION_PENDING";
  }

  auditRecord(): Record<string, unknown> {
    return {
      run_id: this.#policy.RUN_ID,
      policy_revision: this.#policy.POLICY_REVISION,
      policy_sha256: this.#policySha256,
      policy: this.#policy,
      evidence_pack_ref: this.#policy.EVIDENCE_PACK_REF ?? null,
      model_claim: this.#modelClaim ?? null,
      validation_state: this.isGreen ? "PASSED" : "PENDING",
      governor_state: this.stopped ? "STOP" : this.#replanRequired ? "REPLAN_REQUIRED" : "ACTIVE",
      reviewer_state: null,
      system_verdict: this.systemVerdict,
      tool_call_count: this.#toolCallCount,
      repeated_reads: this.#repeatedReads,
      elapsed_ms: Math.max(0, Date.now() - this.#startedAtMs),
      correction_cycles: this.#correctionCycles,
      total_corrections: this.#totalCorrections,
      repeated_failures: Math.max(0, this.#correctionCycles - 1),
      distinct_failure_evidence_count: this.#seenFailureEvidence.size,
      compactions: this.#compactions,
      scope_expansion_requests: this.scopeExpansionRequests,
      tool_decisions: [...this.#toolDecisions],
      validation_results: [...this.#validationResults],
    };
  }

  handleEvent(event: GovernorEvent): GovernorDecision {
    switch (event.type) {
      case "TOOL_PRE": {
        const operation = event.operation;
        const tool = operation === "SHELL" ? "bash" : operation === "READ" ? "read" : operation === "SEARCH" ? "grep" : operation === "CREATE" ? "write" : "edit";
        if (!operation || !event.callId) return this.#reject("tool event lacks operation or call ID");
        const decision = this.checkToolCall(tool, event.input ?? (event.command ? { command: event.command } : { path: event.path }), event.callId, event.evidenceReference);
        this.#toolDecisions.push(Object.freeze({ call_id: event.callId, operation, allowed: decision.allowed, capability: decision.capability ?? null, outcome: decision.outcome ?? null, reason: decision.reason ?? null }));
        this.#save();
        return this.stopped ? { allowed: false, reason: `Governor STOP: ${this.#stopReason}`, outcome: "STOP" } : decision;
      }
      case "TOOL_POST":
      case "VALIDATION_RESULT":
        if (event.callId) this.recordToolResult(event.operation === "SHELL" ? "bash" : event.operation === "CREATE" ? "write" : "edit", event.input ?? {}, event.callId, event.failed ?? true, event.evidenceReference);
        return { allowed: !this.stopped, outcome: this.stopped ? "STOP" : this.#replanRequired ? "REPLAN_REQUIRED" : "CONTINUE" };
      case "COMPACTION": this.recordCompaction(); return { allowed: !this.stopped, outcome: this.stopped ? "STOP" : "CONTINUE" };
      case "FINAL_CLAIM": this.#modelClaim = event.claim; this.#save(); return { allowed: true, outcome: "CONTINUE" };
      default: return { allowed: true, outcome: "CONTINUE" };
    }
  }

  get stopped(): boolean {
    return this.#stopReason !== undefined;
  }

  get stopReason(): string | undefined {
    return this.#stopReason;
  }

  get correctionCycles(): number {
    return this.#correctionCycles;
  }

  get totalCorrections(): number { return this.#totalCorrections; }
  get repeatedFailures(): number { return Math.max(0, this.#correctionCycles - 1); }
  get distinctFailureEvidenceCount(): number { return this.#seenFailureEvidence.size; }

  get compactions(): number {
    return this.#compactions;
  }

  get modifiedFiles(): readonly string[] {
    return [...this.#modifiedFiles].sort();
  }

  get isGreen(): boolean {
    if (this.stopped) return false;
    if (this.#sourceEditEpoch === 0 && this.#policy.RUN_ID === "legacy-v0") return true;
    if (this.#policy.VALIDATION_COMMANDS.length === 0) return false;
    const allValidationPassed = this.#policy.VALIDATION_COMMANDS.every(
      (command) => (this.#validationPassEpochs.get(command) ?? -1) >= this.#sourceEditEpoch,
    );
    const testPassed =
      !this.#policy.REQUIRE_TEST_AFTER_EDIT ||
      this.#policy.TEST_COMMANDS.some(
        (command) => (this.#validationPassEpochs.get(command) ?? -1) >= this.#sourceEditEpoch,
      );
    return allValidationPassed && testPassed;
  }

  status(): string {
    const state = this.stopped ? `STOP: ${this.#stopReason}` : this.isGreen ? "GREEN" : "NOT GREEN";
    return `${state}; files=${this.#modifiedFiles.size}; tests-after-edit=${this.#hasFreshTestEvidence()}; repeated-failures=${this.repeatedFailures}/${this.#repeatedLimit}; total-corrections=${this.#totalCorrections}/${this.#totalLimit}; compactions=${this.#compactions}/${this.#policy.MAX_COMPACTIONS}`;
  }

  get #repeatedLimit(): number { return this.#policy.MAX_REPEATED_FAILURES ?? this.#policy.MAX_CORRECTION_CYCLES; }
  get #totalLimit(): number { return this.#policy.MAX_TOTAL_CORRECTIONS ?? 6; }

  checkToolCall(toolName: string, input: Record<string, unknown>, toolCallId: string, evidenceReference?: string): GovernorDecision {
    if (this.stopped) return { allowed: false, reason: `Governor STOP: ${this.#stopReason}` };
    this.#toolCallCount += 1;
    const mode = this.#policy.MODE;
    if ((mode === "OBSERVE" || mode === "DISCOVER" || this.#policy.ROLE === "REVIEW" || this.#policy.ROLE === "VISION") && ["write", "edit"].includes(toolName)) {
      return this.#reject(`mutation is unavailable in ${mode}`);
    }

    if (toolName === "read" || toolName === "grep" || toolName === "find" || toolName === "ls") {
      const file = getPath(input);
      if (file === this.#lastRead) this.#repeatedReads += 1;
      this.#lastRead = file;
      if (!file) return this.#reject(`${toolName} requires one explicit path`);
      if (mode === "OBSERVE" && !this.#policy.ALLOWED_READ_FILES.includes(file)) return this.#reject("OBSERVE reads supplied evidence only");
      if (mode === "DISCOVER") {
        const resolved = this.#resolveAnyToolTarget(file);
        return resolved ? { allowed: true, capability: toolName === "read" ? "READ" : "SEARCH", outcome: "CONTINUE" } : this.#reject(`read path escapes workspace: ${file}`);
      }
      const resolved = this.#resolveToolTarget(file)?.absolute;
      if (!resolved || !this.#allowedRead.has(resolved)) {
        return this.#expansion(file, toolName === "read" ? "READ" : "SEARCH", evidenceReference, `read path is outside ALLOWED_READ_FILES: ${file}`);
      }
      return { allowed: true, capability: toolName === "read" ? "READ" : "SEARCH", outcome: "CONTINUE" };
    }

    if (toolName === "write" || toolName === "edit") {
      const rawPath = getPath(input);
      if (!rawPath) return this.#reject(`${toolName} is missing a file path`);
      const target = this.#resolveToolTarget(rawPath);
      if (!target) return this.#reject(`invalid or out-of-repository edit path: ${rawPath}`);
      const file = target.absolute;
      if (this.#isProtectedGitPath(file)) return this.#reject("Git metadata and submodule remote configuration are not editable through file tools");
      if (!this.#allowedEdit.has(file)) return this.#expansion(rawPath, target.exists ? "EDIT" : "CREATE", evidenceReference, `edit path is outside ALLOWED_EDIT_FILES: ${rawPath}`);
      if ([...this.#pendingMutations.values()].some((item) => item.file === file)) {
        return this.#reject(`another mutation for this file is still pending: ${rawPath}`);
      }
      if (!target.exists && !this.#policy.ALLOW_NEW_FILES) return this.#reject(`new file creation is not authorized: ${rawPath}`);
      if (!target.exists && this.#pendingMutations.size + this.#modifiedFiles.size >= this.#policy.MAX_FILES_TOUCHED) {
        return this.#reject(`MAX_FILES_TOUCHED (${this.#policy.MAX_FILES_TOUCHED}) would be exceeded`);
      }
      if (!target.exists) {
        try {
          if (!statSync(path.dirname(file)).isDirectory()) {
            return this.#reject(`new file parent path is not a directory: ${rawPath}`);
          }
        } catch {
          return this.#reject(`new file parent directory does not exist: ${rawPath}`);
        }
      }

      const assessment = this.#assessMutation(toolName, input, file, target.exists);
      if (assessment) return this.#reject(assessment);
      this.#pendingMutations.set(toolCallId, { file });
      return { allowed: true, capability: target.exists ? "EDIT" : "CREATE", outcome: "CONTINUE" };
    }

    if (toolName === "bash") {
      const command = typeof input.command === "string" ? input.command.trim() : "";
      const capability = classifyCommand(command, this.#policy.VALIDATION_COMMANDS);
      if (mode === "OBSERVE") return { ...this.#reject("OBSERVE accepts file evidence only"), capability };
      if (capability === "VALIDATION") {
        this.#validationStarts.set(toolCallId, { command, epoch: this.#sourceEditEpoch });
        return { allowed: true, capability, outcome: "CONTINUE" };
      }
      if (capability === "GIT_READONLY") return { allowed: true, capability, outcome: "CONTINUE" };
      if (capability === "GIT_READ") return this.#checkGitCommand(command, capability);
      if (["GIT_STAGE", "GIT_COMMIT", "GIT_PUSH", "GIT_FORCE_PUSH", "GIT_REMOTE_MUTATION", "GIT_AUTH_MUTATION", "GIT_MUTATING"].includes(capability)) {
        if (!this.#canAuthorizeGitMutation()) {
          return { ...this.#reject(`Git mutation is unavailable in ${mode} mode or ${this.#policy.ROLE} role`), capability, outcome: "STOP" };
        }
        if (capability === "GIT_STAGE" && this.#workingDirectory !== this.#root) {
          return { ...this.#reject("Git staging requires the repository root as the working directory"), capability, outcome: "STOP" };
        }
        return this.#checkGitCommand(command, capability);
      }
      if (capability === "SHELL_READONLY") {
        const words = command.split(/\s+/);
        const target = this.#resolveAnyToolTarget(words.at(-1) ?? "");
        if (target && (mode === "DISCOVER" || this.#allowedRead.has(target.absolute))) return { allowed: true, capability, outcome: "CONTINUE" };
      }
      return { ...this.#reject(`shell command requires an authorized capability (${capability})`), capability, outcome: "STOP" };
    }

    return this.#reject(`${toolName} is not available in bounded CODE mode`);
  }

  recordToolResult(
    toolName: string,
    input: Record<string, unknown>,
    toolCallId: string,
    isError: boolean,
    evidenceReference?: string,
  ): void {
    const mutation = this.#pendingMutations.get(toolCallId);
    if (mutation) {
      this.#pendingMutations.delete(toolCallId);
      if (!isError) {
        this.#modifiedFiles.add(mutation.file);
        if (isSourceFile(mutation.file)) this.#sourceEditEpoch += 1;
      }
      this.#save();
    }

    const validation = this.#validationStarts.get(toolCallId);
    if (toolName === "bash" && validation) {
      this.#validationStarts.delete(toolCallId);
      this.#validationResults.push(Object.freeze({ command: validation.command, epoch: validation.epoch, passed: !isError, evidence_reference: evidenceReference ?? null }));
      if (isError) {
        this.#validationPassEpochs.delete(validation.command);
        this.#totalCorrections += 1;
        const failureEvidence = evidenceReference ?? "UNKNOWN";
        this.#seenFailureEvidence.add(failureEvidence);
        if (failureEvidence !== this.#lastFailureEvidence) {
          this.#correctionCycles = 1;
          this.#replanRequired = false;
        } else {
          this.#correctionCycles += 1;
        }
        this.#lastFailureEvidence = failureEvidence;
        if (this.repeatedFailures >= this.#repeatedLimit) {
          this.#stopReason = `repeated correction budget exhausted (${this.repeatedFailures}/${this.#repeatedLimit})`;
        } else if (this.#totalCorrections > this.#totalLimit) {
          this.#stopReason = `total correction budget exhausted (${this.#totalCorrections}/${this.#totalLimit})`;
        } else if (this.repeatedFailures >= Math.max(1, this.#repeatedLimit - 1) || this.#totalCorrections >= this.#totalLimit) {
          this.#replanRequired = true;
        }
      } else {
        this.#validationPassEpochs.set(validation.command, validation.epoch);
        this.#replanRequired = false;
        this.#correctionCycles = 0;
        this.#lastFailureEvidence = undefined;
      }
      this.#save();
    }
  }

  recordCompaction(): void {
    this.#compactions += 1;
    if (this.#compactions > this.#policy.MAX_COMPACTIONS) {
      this.#stopReason = `compaction budget exhausted (${this.#compactions}/${this.#policy.MAX_COMPACTIONS})`;
    }
    this.#save();
  }

  stop(reason: string): void {
    this.#stopReason = reason;
    this.#save();
  }

  #canAuthorizeGitMutation(): boolean {
    return !["OBSERVE", "DISCOVER"].includes(this.#policy.MODE) && !["REVIEW", "VISION"].includes(this.#policy.ROLE);
  }

  #isProtectedGitPath(file: string): boolean {
    const relative = path.relative(this.#root, file);
    const segments = relative.split(path.sep);
    return segments.includes(".git") || path.basename(file) === ".gitmodules";
  }

  #checkGitCommand(command: string, capability: Capability): GovernorDecision {
    const decision = this.#gitAuthority.checkCommand(command);
    if (isGitAuthorityStop(decision)) {
      this.#stopReason = decision.reason ?? "Git authorization was invalidated";
      this.#save();
    }
    return {
      allowed: decision.allowed,
      capability,
      ...(decision.reason ? { reason: decision.reason } : {}),
      outcome: decision.outcome ?? (decision.allowed ? "CONTINUE" : "STOP"),
    };
  }

  #recordGitAuthorizationReceipt(receipt: GitAuthorizationReceipt): GitAuthorizationReceipt {
    if (receipt.authorizationInvalidated) {
      this.#stopReason = receipt.reason ?? "Git authorization preflight was invalidated";
      this.#save();
    }
    return receipt;
  }

  #canonicalPolicyPaths(files: readonly string[]): Set<string> {
    const result = new Set<string>();
    for (const file of files) {
      const target = this.#resolveTarget(file);
      if (!target || !isInside(this.#root, target.absolute)) {
        throw new Error(`Policy path does not resolve inside the repository: ${file}`);
      }
      result.add(target.absolute);
    }
    return result;
  }

  #resolveTarget(candidate: string): { absolute: string; exists: boolean } | undefined {
    try {
      const target = canonicalTarget(this.#root, candidate);
      if (target.absolute !== path.resolve(this.#root, candidate)) return undefined;
      if (!isInside(this.#root, target.absolute)) return undefined;
      if (target.exists && !statSync(target.absolute).isFile()) return undefined;
      return target;
    } catch {
      return undefined;
    }
  }

  #resolveToolTarget(candidate: string): { absolute: string; exists: boolean } | undefined {
    try {
      const target = canonicalTarget(this.#workingDirectory, candidate);
      if (target.absolute !== path.resolve(this.#workingDirectory, candidate)) return undefined;
      if (!isInside(this.#root, target.absolute)) return undefined;
      if (target.exists && !statSync(target.absolute).isFile()) return undefined;
      return target;
    } catch {
      return undefined;
    }
  }

  #resolveAnyToolTarget(candidate: string): { absolute: string; exists: boolean } | undefined {
    try {
      const target = canonicalTarget(this.#workingDirectory, candidate);
      return isInside(this.#root, target.absolute) ? target : undefined;
    } catch { return undefined; }
  }

  #expansion(candidate: string, capability: Capability, evidenceReference: string | undefined, reason: string): GovernorDecision {
    this.#scopeExpansionRequests.push(Object.freeze({
      requestedPath: candidate,
      capability,
      reason,
      evidenceReference: evidenceReference?.trim() || "UNKNOWN",
      runId: this.#policy.RUN_ID,
    }));
    this.#save();
    return { allowed: false, reason: `Governor rejected tool call: ${reason}; request scope expansion with evidence`, capability, outcome: "REQUEST_SCOPE_EXPANSION" };
  }

  #assessMutation(
    toolName: "write" | "edit",
    input: Record<string, unknown>,
    file: string,
    exists: boolean,
  ): string | undefined {
    if (!exists) return undefined;
    let before: string;
    try {
      before = readFileSync(file, "utf8");
    } catch {
      return `cannot inspect existing file before mutation: ${file}`;
    }

    let after: string;
    let deletedLines: number;
    if (toolName === "write") {
      if (typeof input.content !== "string") return "write content must be a string";
      after = input.content;
      deletedLines = lineCount(before);
    } else {
      const edits = editList(input);
      if (!edits) return "edit requires one or more valid edits[].oldText/newText replacements";
      let normalized = before.replace(/\r\n|\r/g, "\n");
      const replacements: Array<{ start: number; end: number; newText: string }> = [];
      deletedLines = 0;
      for (const edit of edits) {
        if (edit.oldText.length === 0) return "edit oldText cannot be empty";
        const start = normalized.indexOf(edit.oldText);
        if (start < 0) return "edit oldText does not match the current file";
        if (normalized.indexOf(edit.oldText, start + 1) >= 0) {
          return "edit oldText must match one unique region of the current file";
        }
        deletedLines += lineCount(edit.oldText);
        replacements.push({ start, end: start + edit.oldText.length, newText: edit.newText });
      }
      replacements.sort((left, right) => left.start - right.start);
      for (let index = 1; index < replacements.length; index += 1) {
        if (replacements[index - 1].end > replacements[index].start) {
          return "edit replacements overlap";
        }
      }
      for (const replacement of replacements.reverse()) {
        normalized =
          normalized.slice(0, replacement.start) +
          replacement.newText +
          normalized.slice(replacement.end);
      }
      after = normalized;
    }

    const oldLines = lineCount(before);
    const newLines = lineCount(after);
    const shrinkPercent = oldLines === 0 ? 0 : (Math.max(0, oldLines - newLines) / oldLines) * 100;
    if (deletedLines > this.#policy.MAX_DELETED_LINES) {
      return `deletion exceeds MAX_DELETED_LINES (${deletedLines} > ${this.#policy.MAX_DELETED_LINES})`;
    }
    if (isTestFile(file) && shrinkPercent > this.#policy.MAX_TEST_FILE_SHRINK_PERCENT) {
      return `test file shrink exceeds MAX_TEST_FILE_SHRINK_PERCENT (${shrinkPercent.toFixed(1)}% > ${this.#policy.MAX_TEST_FILE_SHRINK_PERCENT}%)`;
    }
    if (
      toolName === "write" &&
      oldLines > this.#policy.MAX_DELETED_LINES &&
      shrinkPercent > this.#policy.MAX_REWRITE_SHRINK_PERCENT &&
      !this.#authorizedRewrites.has(file)
    ) {
      return `large-file replacement requires AUTHORIZED_REWRITE_FILES (${shrinkPercent.toFixed(1)}% shrink)`;
    }
    const alreadyCounted = this.#modifiedFiles.has(file) || [...this.#pendingMutations.values()].some((item) => item.file === file);
    if (!alreadyCounted && this.#modifiedFiles.size + this.#pendingMutations.size >= this.#policy.MAX_FILES_TOUCHED) {
      return `MAX_FILES_TOUCHED (${this.#policy.MAX_FILES_TOUCHED}) would be exceeded`;
    }
    return undefined;
  }

  #hasFreshTestEvidence(): boolean {
    return this.#policy.TEST_COMMANDS.some(
      (command) => (this.#validationPassEpochs.get(command) ?? -1) >= this.#sourceEditEpoch,
    );
  }

  #reject(reason: string): GovernorDecision {
    return { allowed: false, reason: `Governor rejected tool call: ${reason}` };
  }

  #save(): void {
    const validationPassEpochs = Object.fromEntries(this.#validationPassEpochs.entries());
    const snapshot: GovernorSnapshot = Object.freeze({
      version: 1,
      policyFingerprint: this.#fingerprint,
      policySha256: this.#policySha256,
      policyRevision: this.#policy.POLICY_REVISION,
      runId: this.#policy.RUN_ID,
      toolCallCount: this.#toolCallCount,
      repeatedReads: this.#repeatedReads,
      startedAtMs: this.#startedAtMs,
      toolDecisions: Object.freeze([...this.#toolDecisions]),
      validationResults: Object.freeze([...this.#validationResults]),
      replanRequired: this.#replanRequired,
      ...(this.#modelClaim ? { modelClaim: this.#modelClaim } : {}),
      scopeExpansionRequests: Object.freeze([...this.#scopeExpansionRequests]),
      modifiedFiles: Object.freeze(this.modifiedFiles),
      sourceEditEpoch: this.#sourceEditEpoch,
      validationPassEpochs: Object.freeze(validationPassEpochs),
      correctionCycles: this.#correctionCycles,
      totalCorrections: this.#totalCorrections,
      repeatedFailures: this.repeatedFailures,
      distinctFailureEvidenceCount: this.#seenFailureEvidence.size,
      ...(this.#lastFailureEvidence ? { lastFailureEvidence: this.#lastFailureEvidence } : {}),
      compactions: this.#compactions,
      ...(this.#stopReason ? { stopReason: this.#stopReason } : {}),
    });
    try {
      this.#persist(snapshot);
    } catch {
      this.#stopReason = this.#stopReason ?? "governor state persistence failed";
    }
  }

  #restore(history: readonly unknown[]): void {
    if (history.length === 0) return;
    const latest = history[history.length - 1];
    if (!isRecord(latest) || latest.version !== 1 || typeof latest.policyFingerprint !== "string") {
      this.#stopReason = "stored governor state is malformed";
      return;
    }
    if (latest.policyFingerprint !== this.#fingerprint && !(
      this.#policy.MODE === "EXPANDED_EXECUTE" &&
      latest.policySha256 === this.#policy.PREVIOUS_POLICY_SHA256 &&
      latest.policyRevision === this.#policy.POLICY_REVISION - 1 &&
      latest.runId === this.#policy.RUN_ID
    )) {
      this.#stopReason = "policy changed while resuming a bounded CODE task";
      return;
    }
    if (
      !Array.isArray(latest.modifiedFiles) ||
      typeof latest.sourceEditEpoch !== "number" ||
      typeof latest.correctionCycles !== "number" ||
      typeof latest.compactions !== "number" ||
      !isRecord(latest.validationPassEpochs)
    ) {
      this.#stopReason = "stored governor state is malformed";
      return;
    }
    for (const file of latest.modifiedFiles) {
      if (typeof file !== "string" || !this.#allowedEdit.has(file)) {
        this.#stopReason = "stored governor state contains an out-of-scope file";
        return;
      }
      this.#modifiedFiles.add(file);
    }
    this.#sourceEditEpoch = latest.sourceEditEpoch;
    this.#correctionCycles = latest.correctionCycles;
    this.#totalCorrections = typeof latest.totalCorrections === "number" ? latest.totalCorrections :
      Array.isArray(latest.validationResults) ? latest.validationResults.filter((result) => isRecord(result) && result.passed === false).length : latest.correctionCycles;
    this.#compactions = latest.compactions;
    this.#toolCallCount = typeof latest.toolCallCount === "number" ? latest.toolCallCount : 0;
    this.#repeatedReads = typeof latest.repeatedReads === "number" ? latest.repeatedReads : 0;
    this.#startedAtMs = typeof latest.startedAtMs === "number" ? latest.startedAtMs : this.#startedAtMs;
    this.#replanRequired = latest.replanRequired === true;
    if (Array.isArray(latest.toolDecisions)) this.#toolDecisions.push(...latest.toolDecisions.filter(isRecord));
    if (Array.isArray(latest.validationResults)) {
      this.#validationResults.push(...latest.validationResults.filter(isRecord));
      for (const result of latest.validationResults) {
        if (isRecord(result) && result.passed === false) this.#seenFailureEvidence.add(typeof result.evidence_reference === "string" ? result.evidence_reference : "UNKNOWN");
      }
    }
    const lastFailure = Array.isArray(latest.validationResults) ? [...latest.validationResults].reverse().find((result) => isRecord(result) && result.passed === false) : undefined;
    this.#lastFailureEvidence = typeof latest.lastFailureEvidence === "string" ? latest.lastFailureEvidence :
      isRecord(lastFailure) && typeof lastFailure.evidence_reference === "string" ? lastFailure.evidence_reference : undefined;
    if (this.#lastFailureEvidence === undefined && this.#correctionCycles > 0) this.#lastFailureEvidence = "UNKNOWN";
    if (typeof latest.modelClaim === "string") this.#modelClaim = latest.modelClaim;
    if (Array.isArray(latest.scopeExpansionRequests)) {
      for (const request of latest.scopeExpansionRequests) {
        if (isRecord(request) && typeof request.requestedPath === "string" && typeof request.evidenceReference === "string" && request.runId === this.#policy.RUN_ID && CAPABILITIES.includes(request.capability as Capability)) {
          this.#scopeExpansionRequests.push(request as unknown as ScopeExpansionRequest);
        }
      }
    }
    for (const [command, epoch] of Object.entries(latest.validationPassEpochs)) {
      if (this.#policy.VALIDATION_COMMANDS.includes(command) && typeof epoch === "number") {
        this.#validationPassEpochs.set(command, epoch);
      }
    }
    if (typeof latest.stopReason === "string") this.#stopReason = latest.stopReason;
  }
}

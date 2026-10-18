import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import path from "node:path";

export type GitOperation =
  | "GIT_READ"
  | "GIT_STAGE"
  | "GIT_COMMIT"
  | "GIT_PUSH"
  | "GIT_FORCE_PUSH"
  | "GIT_REMOTE_MUTATION"
  | "GIT_AUTH_MUTATION"
  | "GIT_MUTATING";

export interface GitStageSnapshot {
  readonly repository: string;
  readonly changedPaths: readonly string[];
  readonly stagedPaths: readonly string[];
}

export interface GitCommitSnapshot {
  readonly repository: string;
  readonly branch: string;
  readonly head: string;
  readonly stagedPaths: readonly string[];
  readonly unstagedPaths: readonly string[];
  readonly stagedDiffSha256: string;
  readonly commitMessage: string;
}

export interface GitPushAuthorizationReview {
  readonly repository: string;
  readonly branch: string;
  readonly head: string;
  readonly remote: string;
  readonly upstream: string;
  readonly upstreamBranch: string;
  readonly ahead: number;
  readonly behind: number;
  /** Opaque digest used only to detect local push-URL changes; never render it. */
  readonly remoteFingerprint: string;
}

export interface GitAuthorityDecision {
  readonly allowed: boolean;
  readonly operation: GitOperation;
  readonly reason?: string;
  readonly outcome?: "CONTINUE" | "STOP";
  readonly authorizationInvalidated?: boolean;
}

export interface GitAuthorizationReceipt {
  readonly allowed: boolean;
  readonly reason?: string;
  readonly authorizationInvalidated?: boolean;
}

const SAFE_FETCH_FLAGS = new Set([
  "--all", "--prune", "--quiet", "-q", "--verbose", "-v", "--progress", "--no-progress",
]);

function tokenize(command: string): string[] | undefined {
  if (/[;&|\x60$<>\\\n\r]/.test(command)) return undefined;
  const words: string[] = [];
  let index = 0;
  while (index < command.length) {
    while (/\s/.test(command[index] ?? "")) index += 1;
    if (index >= command.length) break;
    const quote = command[index] === "'" || command[index] === '"' ? command[index] : undefined;
    if (quote) {
      index += 1;
      const end = command.indexOf(quote, index);
      if (end < 0) return undefined;
      const word = command.slice(index, end);
      if (!word || word.includes(quote)) return undefined;
      words.push(word);
      index = end + 1;
      if (index < command.length && !/\s/.test(command[index] ?? "")) return undefined;
    } else {
      const start = index;
      while (index < command.length && !/\s/.test(command[index] ?? "")) index += 1;
      words.push(command.slice(start, index));
    }
  }
  return words.length > 0 ? words : undefined;
}

function isCredentialMutation(command: string): boolean {
  return /^(?:ssh-keygen|ssh-add|git-credential(?:\s|$)|gh\s+auth\s+(?:login|logout|refresh|setup-git|setup-token)(?:\s|$))/i.test(command) ||
    (/^ssh\s/i.test(command) && /(?:StrictHostKeyChecking\s*=\s*no|UserKnownHostsFile\s*=\s*\/dev\/null)/i.test(command));
}

function configMutationOperation(args: readonly string[]): GitOperation {
  const key = args.find((item) => !item.startsWith("-"))?.toLowerCase() ?? "";
  if (/^remote\./.test(key)) return "GIT_REMOTE_MUTATION";
  if (/^(?:credential\.|core\.sshcommand$|url\..*\.insteadof$|http\.(?:.*\.)?(?:extraheader|sslverify)$)/.test(key)) {
    return "GIT_AUTH_MUTATION";
  }
  return "GIT_MUTATING";
}

function containsWriteOnlyOption(args: readonly string[]): boolean {
  return args.some((argument) =>
    argument === "--ext-diff" || argument === "--textconv" || argument === "--no-index" ||
    argument === "--output" || argument.startsWith("--output=") || argument === "-o",
  );
}

export function classifyGitCommand(command: string): GitOperation {
  const trimmed = command.trim();
  if (isCredentialMutation(trimmed)) return "GIT_AUTH_MUTATION";
  const words = tokenize(trimmed);
  if (!words || words[0] !== "git" || !words[1]) return "GIT_MUTATING";
  const [program, subcommand, ...args] = words;
  if (program !== "git") return "GIT_MUTATING";

  if (subcommand === "config") return configMutationOperation(args);
  if (subcommand === "credential" || subcommand.startsWith("credential-")) return "GIT_AUTH_MUTATION";
  if (subcommand === "remote") {
    if (args.length === 1 && (args[0] === "-v" || args[0] === "--verbose")) return "GIT_READ";
    if (["add", "remove", "rm", "rename", "set-url"].includes(args[0] ?? "")) return "GIT_REMOTE_MUTATION";
    return "GIT_MUTATING";
  }
  if (subcommand === "push") {
    if (args.some((argument) =>
      argument === "-f" || argument.startsWith("-f") ||
      argument === "--force" || argument.startsWith("--force-with-lease"),
    )) return "GIT_FORCE_PUSH";
    return "GIT_PUSH";
  }
  if (subcommand === "add") return "GIT_STAGE";
  if (subcommand === "commit") return "GIT_COMMIT";
  if (subcommand === "fetch") {
    const positional = args.filter((argument) => !SAFE_FETCH_FLAGS.has(argument));
    const fetchAll = args.includes("--all");
    if (
      args.filter((argument) => argument.startsWith("-")).every((argument) => SAFE_FETCH_FLAGS.has(argument)) &&
      positional.every((argument) => /^[A-Za-z0-9_.-]+$/.test(argument)) &&
      positional.length <= 1 && (!fetchAll || positional.length === 0)
    ) return "GIT_READ";
    return "GIT_MUTATING";
  }
  if (subcommand === "branch") {
    return args.length === 1 && args[0] === "--show-current" ? "GIT_READ" : "GIT_MUTATING";
  }
  if (["status", "diff", "log", "show", "rev-parse", "rev-list"].includes(subcommand)) {
    return containsWriteOnlyOption(args) ? "GIT_MUTATING" : "GIT_READ";
  }
  return "GIT_MUTATING";
}

export function isGitAuthenticationMutation(command: string): boolean {
  return isCredentialMutation(command.trim());
}

function parseStageCommand(command: string): { broad: boolean; paths: string[] } | undefined {
  const words = tokenize(command.trim());
  if (!words || words[0] !== "git" || words[1] !== "add") return undefined;
  const args = words.slice(2);
  if (args.length === 1 && [".", "-A", "--all", ":/"].includes(args[0] ?? "")) {
    return { broad: true, paths: [] };
  }
  if (args.includes(".") || args.some((argument) => argument.startsWith("-") && argument !== "--")) return undefined;
  const paths = args.filter((argument) => argument !== "--");
  if (paths.length === 0 || paths.some((item) => !isExplicitStagePath(item))) return undefined;
  return { broad: false, paths: paths.map(normalizeStagePath) };
}

function normalizeStagePath(value: string): string {
  return path.posix.normalize(value.replace(/^\.\//, ""));
}

function isExplicitStagePath(value: string): boolean {
  if (!value || path.posix.isAbsolute(value) || /[*?\[\]]/.test(value) || value.startsWith(":(")) return false;
  const normalized = normalizeStagePath(value);
  const rawSegments = value.replace(/^\.\//, "").split("/");
  return normalized !== "." && normalized.length > 0 && !rawSegments.includes("..") &&
    value.replace(/^\.\//, "") === normalized;
}

function parseCommitMessage(command: string): string | undefined {
  const words = tokenize(command.trim());
  if (!words || words[0] !== "git" || words[1] !== "commit" || words.length !== 4) return undefined;
  if (words[2] !== "-m" && words[2] !== "--message") return undefined;
  return words[3];
}

function parsePushTarget(command: string): { remote: string; source: string; destination: string } | undefined {
  const words = tokenize(command.trim());
  if (!words || words[0] !== "git" || words[1] !== "push" || words.length !== 6) return undefined;
  const options = words.slice(2, 4);
  if (!options.includes("--no-follow-tags") || !options.includes("--recurse-submodules=no")) return undefined;
  const [remote, refspec] = words.slice(4);
  if (!remote || !refspec || !/^[A-Za-z0-9_.-]+$/.test(remote)) return undefined;
  const separator = refspec.indexOf(":");
  if (separator < 1 || separator === refspec.length - 1) return undefined;
  return { remote, source: refspec.slice(0, separator), destination: refspec.slice(separator + 1) };
}

export function isGitAuthorityStop(decision: GitAuthorityDecision): boolean {
  return decision.authorizationInvalidated === true;
}

function runGit(repository: string, args: readonly string[]): Buffer {
  return execFileSync("git", [...args], {
    cwd: repository,
    encoding: "buffer",
    timeout: 5_000,
    maxBuffer: 32 * 1024 * 1024,
    stdio: ["ignore", "pipe", "pipe"],
  }) as Buffer;
}

function gitText(repository: string, args: readonly string[]): string {
  return runGit(repository, args).toString("utf8").trim();
}

function nulPaths(repository: string, args: readonly string[]): string[] {
  return runGit(repository, args).toString("utf8").split("\0").filter(Boolean).sort();
}

function uniqueSorted(paths: readonly string[]): string[] {
  return [...new Set(paths)].sort();
}

function isProtectedGitPath(relativePath: string): boolean {
  return relativePath.split("/").includes(".git") || path.posix.basename(relativePath) === ".gitmodules";
}

function repositoryRoot(repository: string): string {
  const root = gitText(repository, ["rev-parse", "--show-toplevel"]);
  if (path.resolve(root) !== path.resolve(repository)) throw new Error("Git authority repository root changed");
  return root;
}

function readChangedPaths(repository: string): string[] {
  return uniqueSorted([
    ...nulPaths(repository, ["diff", "--cached", "--name-only", "-z", "--no-renames"]),
    ...nulPaths(repository, ["diff", "--name-only", "-z", "--no-renames"]),
    ...nulPaths(repository, ["ls-files", "--others", "--exclude-standard", "-z"]),
  ]);
}

function readStagedPaths(repository: string): string[] {
  return nulPaths(repository, ["diff", "--cached", "--name-only", "-z", "--no-renames"]);
}

function readGitStageSnapshot(repository: string): GitStageSnapshot {
  const root = repositoryRoot(repository);
  return Object.freeze({
    repository: root,
    changedPaths: Object.freeze(readChangedPaths(repository)),
    stagedPaths: Object.freeze(readStagedPaths(repository)),
  });
}

function readGitCommitSnapshot(repository: string, commitMessage: string): GitCommitSnapshot {
  const root = repositoryRoot(repository);
  if (nulPaths(repository, ["ls-files", "--unmerged", "-z"]).length > 0) {
    throw new Error("Commit preflight is unavailable with unresolved index entries");
  }
  const stagedPaths = readStagedPaths(repository);
  if (stagedPaths.some(isProtectedGitPath)) throw new Error("Git metadata or submodule configuration is staged");
  const stagedDiff = runGit(repository, ["diff", "--cached", "--binary", "--no-ext-diff", "--no-textconv", "--no-color"]);
  return Object.freeze({
    repository: root,
    branch: gitText(repository, ["branch", "--show-current"]),
    head: gitText(repository, ["rev-parse", "--verify", "HEAD"]),
    stagedPaths: Object.freeze(stagedPaths),
    unstagedPaths: Object.freeze(uniqueSorted([
      ...nulPaths(repository, ["diff", "--name-only", "-z", "--no-renames"]),
      ...nulPaths(repository, ["ls-files", "--others", "--exclude-standard", "-z"]),
    ])),
    stagedDiffSha256: createHash("sha256").update(stagedDiff).digest("hex"),
    commitMessage,
  });
}

function readGitPushSnapshot(repository: string): GitPushAuthorizationReview {
  const root = repositoryRoot(repository);
  const branch = gitText(repository, ["branch", "--show-current"]);
  if (!branch) throw new Error("Push preflight is unavailable on a detached HEAD");
  const remote = gitText(repository, ["config", "--get", "branch." + branch + ".remote"]);
  const merge = gitText(repository, ["config", "--get", "branch." + branch + ".merge"]);
  if (!/^[A-Za-z0-9_.-]+$/.test(remote) || remote === "." || !merge.startsWith("refs/heads/")) {
    throw new Error("Push preflight requires a configured remote branch upstream");
  }
  const upstreamBranch = merge.slice("refs/heads/".length);
  if (!upstreamBranch || upstreamBranch.startsWith("-") || upstreamBranch.includes("..")) {
    throw new Error("Configured upstream branch is invalid");
  }
  if (upstreamBranch !== branch) throw new Error("Push preflight requires the upstream to match the current branch");
  const upstream = remote + "/" + upstreamBranch;
  const counts = gitText(repository, ["rev-list", "--left-right", "--count", "HEAD..." + upstream]).split(/\s+/);
  if (counts.length !== 2 || counts.some((item) => !/^\d+$/.test(item))) {
    throw new Error("Could not determine ahead/behind state");
  }
  const pushUrls = runGit(repository, ["remote", "get-url", "--push", "--all", remote]);
  if (pushUrls.toString("utf8").trim().split(/\r?\n/).filter(Boolean).length !== 1) {
    throw new Error("Push preflight requires exactly one configured push URL");
  }
  const remoteConfig = runGit(repository, ["config", "--null", "--get-regexp", "^remote\\." + remote + "\\."]);
  return Object.freeze({
    repository: root,
    branch,
    head: gitText(repository, ["rev-parse", "--verify", "HEAD"]),
    remote,
    upstream,
    upstreamBranch,
    ahead: Number(counts[0]),
    behind: Number(counts[1]),
    remoteFingerprint: createHash("sha256").update(Buffer.concat([remoteConfig, pushUrls])).digest("hex"),
  });
}

function canFetchWithoutChangingBranch(repository: string, requestedRemote?: string): boolean {
  const remotes = requestedRemote ? [requestedRemote] : gitText(repository, ["remote"]).split(/\s+/).filter(Boolean);
  for (const remote of remotes) {
    if (!/^[A-Za-z0-9_.-]+$/.test(remote)) return false;
    const fetchSpecs = runGit(repository, ["config", "--get-all", "remote." + remote + ".fetch"])
      .toString("utf8").split(/\r?\n/).filter(Boolean);
    for (const spec of fetchSpecs) {
      if (spec.startsWith("^")) continue;
      const colon = spec.indexOf(":");
      const destination = colon < 0 ? "" : spec.slice(colon + 1).replace(/^\+/, "");
      if (destination.startsWith("refs/heads/") || destination.startsWith("refs/worktree/")) return false;
    }
  }
  return true;
}

function sameStrings(left: readonly string[], right: readonly string[]): boolean {
  const a = uniqueSorted(left);
  const b = uniqueSorted(right);
  return a.length === b.length && a.every((value, index) => value === b[index]);
}

function sameStageSnapshot(left: GitStageSnapshot, right: GitStageSnapshot): boolean {
  return left.repository === right.repository &&
    sameStrings(left.changedPaths, right.changedPaths) &&
    sameStrings(left.stagedPaths, right.stagedPaths);
}

function sameCommitSnapshot(left: GitCommitSnapshot, right: GitCommitSnapshot): boolean {
  return left.repository === right.repository && left.branch === right.branch && left.head === right.head &&
    sameStrings(left.stagedPaths, right.stagedPaths) && sameStrings(left.unstagedPaths, right.unstagedPaths) &&
    left.stagedDiffSha256 === right.stagedDiffSha256 && left.commitMessage === right.commitMessage;
}

function samePushSnapshot(left: GitPushAuthorizationReview, right: GitPushAuthorizationReview): boolean {
  return left.repository === right.repository && left.branch === right.branch && left.head === right.head &&
    left.remote === right.remote && left.upstream === right.upstream && left.upstreamBranch === right.upstreamBranch &&
    left.ahead === right.ahead && left.behind === right.behind &&
    left.remoteFingerprint === right.remoteFingerprint;
}

function denied(operation: GitOperation, reason: string, invalidated = false): GitAuthorityDecision {
  return {
    allowed: false,
    operation,
    reason: (invalidated ? "AUTHORIZATION_INVALIDATED=YES: " : "") + reason,
    outcome: invalidated ? "STOP" : undefined,
    ...(invalidated ? { authorizationInvalidated: true } : {}),
  };
}

function receipt(allowed: boolean, reason?: string, invalidated = false): GitAuthorizationReceipt {
  return {
    allowed,
    ...(reason ? { reason: (invalidated ? "AUTHORIZATION_INVALIDATED=YES: " : "") + reason } : {}),
    ...(invalidated ? { authorizationInvalidated: true } : {}),
  };
}

/**
 * Holds only one-use, in-process reviewed snapshots for tool preflight.
 * A successful preflight is not an atomic Git execution guarantee.
 */
export class GitAuthorityController {
  readonly #repository: string;
  readonly #authorizedStagePaths: Set<string>;
  #broadStageAuthorization: GitStageSnapshot | undefined;
  #commitAuthorization: GitCommitSnapshot | undefined;
  #pushAuthorization: GitPushAuthorizationReview | undefined;

  constructor(repository: string, authorizedStagePaths: readonly string[] = []) {
    this.#repository = path.resolve(repository);
    this.#authorizedStagePaths = new Set(authorizedStagePaths.map(normalizeStagePath));
  }

  prepareGitStageAuthorization(): GitStageSnapshot {
    return readGitStageSnapshot(this.#repository);
  }

  authorizeGitStage(review: GitStageSnapshot, explicitlyAuthorized: boolean): GitAuthorizationReceipt {
    if (explicitlyAuthorized !== true) {
      this.#broadStageAuthorization = undefined;
      return receipt(false, "broad staging requires explicit operator authorization");
    }
    let current: GitStageSnapshot;
    try {
      current = this.prepareGitStageAuthorization();
    } catch {
      this.#broadStageAuthorization = undefined;
      return receipt(false, "could not revalidate the reviewed staging scope", true);
    }
    if (!sameStageSnapshot(review, current)) {
      this.#broadStageAuthorization = undefined;
      return receipt(false, "reviewed staging scope changed", true);
    }
    if (current.changedPaths.length === 0) return receipt(false, "there are no changed paths to stage");
    if (current.changedPaths.some(isProtectedGitPath)) {
      return receipt(false, "reviewed staging scope includes Git metadata or submodule configuration");
    }
    this.#broadStageAuthorization = current;
    return receipt(true);
  }

  prepareGitCommitAuthorization(commitMessage: string): GitCommitSnapshot {
    if (!commitMessage.trim()) throw new Error("Commit preflight requires the exact non-empty commit message");
    return readGitCommitSnapshot(this.#repository, commitMessage);
  }

  authorizeGitCommit(review: GitCommitSnapshot, explicitlyAuthorized: boolean): GitAuthorizationReceipt {
    if (explicitlyAuthorized !== true) {
      this.#commitAuthorization = undefined;
      this.#pushAuthorization = undefined;
      return receipt(false, "commit requires explicit operator authorization");
    }
    if (review.stagedPaths.length === 0 || !review.head || !review.branch) {
      this.#commitAuthorization = undefined;
      return receipt(false, "commit preflight requires a branch, HEAD, and staged paths");
    }
    let current: GitCommitSnapshot;
    try {
      current = this.prepareGitCommitAuthorization(review.commitMessage);
    } catch {
      this.#commitAuthorization = undefined;
      return receipt(false, "could not revalidate the reviewed commit scope", true);
    }
    if (!sameCommitSnapshot(review, current)) {
      this.#commitAuthorization = undefined;
      this.#pushAuthorization = undefined;
      return receipt(false, "reviewed commit scope changed", true);
    }
    this.#pushAuthorization = undefined;
    this.#commitAuthorization = current;
    return receipt(true);
  }

  prepareGitPushAuthorization(): GitPushAuthorizationReview {
    return readGitPushSnapshot(this.#repository);
  }

  authorizeGitPush(review: GitPushAuthorizationReview, explicitlyAuthorized: boolean): GitAuthorizationReceipt {
    if (explicitlyAuthorized !== true) {
      this.#pushAuthorization = undefined;
      return receipt(false, "push requires separate explicit operator authorization");
    }
    let current: GitPushAuthorizationReview;
    try {
      current = this.prepareGitPushAuthorization();
    } catch {
      this.#pushAuthorization = undefined;
      return receipt(false, "could not revalidate the reviewed push scope", true);
    }
    if (!samePushSnapshot(review, current)) {
      this.#pushAuthorization = undefined;
      return receipt(false, "reviewed push scope changed", true);
    }
    if (current.ahead !== 1 || current.behind !== 0) {
      this.#pushAuthorization = undefined;
      return receipt(false, "push preflight requires exactly one outgoing commit and no incoming commits");
    }
    this.#pushAuthorization = current;
    return receipt(true);
  }

  checkCommand(command: string): GitAuthorityDecision {
    const operation = classifyGitCommand(command);
    if (operation === "GIT_READ") {
      const words = tokenize(command.trim()) ?? [];
      if (words[1] === "fetch") {
        const remote = words.slice(2).find((argument) => !SAFE_FETCH_FLAGS.has(argument));
        try {
          if (!canFetchWithoutChangingBranch(this.#repository, remote)) {
            return denied(operation, "fetch refspec could update a local branch");
          }
        } catch {
          return denied(operation, "could not verify that fetch leaves local branches and worktree unchanged");
        }
      }
      return { allowed: true, operation };
    }
    if (operation === "GIT_STAGE") return this.#checkStage(command);
    if (operation === "GIT_COMMIT") return this.#checkCommit(command);
    if (operation === "GIT_PUSH") return this.#checkPush(command);
    if (operation === "GIT_FORCE_PUSH") return denied(operation, "force push is always denied");
    if (operation === "GIT_REMOTE_MUTATION") return denied(operation, "Git remote configuration changes are denied");
    if (operation === "GIT_AUTH_MUTATION") return denied(operation, "Git authentication and SSH changes are denied");
    return denied(operation, "Git mutation is not in the authority allowlist");
  }

  #checkStage(command: string): GitAuthorityDecision {
    const parsed = parseStageCommand(command);
    if (!parsed) return denied("GIT_STAGE", "staging must name exact non-glob paths or use an explicitly reviewed broad form");
    let current: GitStageSnapshot;
    try {
      current = this.prepareGitStageAuthorization();
    } catch {
      return denied("GIT_STAGE", "could not verify staging scope from local Git state");
    }
    if (parsed.broad) {
      const reviewed = this.#broadStageAuthorization;
      this.#broadStageAuthorization = undefined;
      if (!reviewed) return denied("GIT_STAGE", "broad staging requires explicit authorization of the current path snapshot");
      if (!sameStageSnapshot(reviewed, current)) {
        return denied("GIT_STAGE", "reviewed broad-stage snapshot changed", true);
      }
      if (current.changedPaths.some(isProtectedGitPath)) {
        return denied("GIT_STAGE", "broad staging includes Git metadata or submodule configuration");
      }
      return { allowed: true, operation: "GIT_STAGE" };
    }
    if (parsed.paths.some(isProtectedGitPath)) {
      return denied("GIT_STAGE", "Git metadata and submodule configuration cannot be staged");
    }
    const outsideChangeSet = parsed.paths.find((item) => !current.changedPaths.includes(item));
    if (outsideChangeSet) return denied("GIT_STAGE", "staging path is not in the current changed-path set");
    const unauthorized = parsed.paths.find((item) => !this.#authorizedStagePaths.has(item));
    if (unauthorized) return denied("GIT_STAGE", "path is outside AUTHORIZED_GIT_STAGE_PATHS: " + unauthorized);
    return { allowed: true, operation: "GIT_STAGE" };
  }

  #checkCommit(command: string): GitAuthorityDecision {
    const message = parseCommitMessage(command);
    const reviewed = this.#commitAuthorization;
    this.#commitAuthorization = undefined;
    if (!message || !reviewed) {
      return denied("GIT_COMMIT", "commit requires a matching explicit authorization; amend and extra options are not covered");
    }
    if (message !== reviewed.commitMessage) return denied("GIT_COMMIT", "commit message differs from reviewed preflight");
    let current: GitCommitSnapshot;
    try {
      current = this.prepareGitCommitAuthorization(message);
    } catch {
      return denied("GIT_COMMIT", "could not revalidate commit preflight", true);
    }
    if (!sameCommitSnapshot(reviewed, current)) {
      this.#pushAuthorization = undefined;
      return denied("GIT_COMMIT", "repository, branch, HEAD, staged diff, or changed paths changed after review", true);
    }
    return { allowed: true, operation: "GIT_COMMIT" };
  }

  #checkPush(command: string): GitAuthorityDecision {
    const target = parsePushTarget(command);
    const reviewed = this.#pushAuthorization;
    this.#pushAuthorization = undefined;
    if (!reviewed) {
      return denied("GIT_PUSH", "push requires a separate explicit authorization for one exact remote and branch");
    }
    let current: GitPushAuthorizationReview;
    try {
      current = this.prepareGitPushAuthorization();
    } catch {
      return denied("GIT_PUSH", "could not revalidate push preflight", true);
    }
    if (!samePushSnapshot(reviewed, current)) {
      return denied("GIT_PUSH", "repository, branch, HEAD, remote, upstream, or ahead/behind state changed after review", true);
    }
    if (!target) return denied("GIT_PUSH", "push command must name the reviewed remote and exact branch target");
    if (target.remote !== reviewed.remote || target.source !== "HEAD" ||
      target.destination !== "refs/heads/" + reviewed.upstreamBranch) {
      return denied("GIT_PUSH", "push target differs from the reviewed remote, HEAD, or upstream branch");
    }
    if (current.ahead !== 1 || current.behind !== 0) {
      return denied("GIT_PUSH", "push preflight requires exactly one outgoing commit and no incoming commits", true);
    }
    return { allowed: true, operation: "GIT_PUSH" };
  }
}

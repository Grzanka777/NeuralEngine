# Local development evidence dogfooding

NeuralEngine supports one deliberately bounded local-first development evidence flow:

```text
one NeuralEngine Git worktree
+ one explicitly named repository-relative prompt
+ one explicitly named repository-relative review
+ one exact full non-merge commit SHA
-> one validated, non-persisted candidate
-> explicit apply
-> Decision -> DecisionAcceptance -> DecisionAction -> DecisionOutcome -> DecisionReview
-> optional explicit Review-to-Experience promotion
```

The source adapter reads each selected Markdown file once, records its SHA-256, and reads
the full commit SHA, single parent, subject, tree, changed paths, and patch from local Git.
It conservatively parses the prompt and review checkpoints, review inventory and full
diff, explicitly recorded validation commands, exit codes and test counts, and bounded
risk/deviation/blocker text. The application service requires matching prompt/review
checkpoints, commit parent, changed paths, and patch before constructing a candidate. It
does not search for source artifacts or execute validation commands.

Evidence is source material. Interpretation is caller-supplied meaning. A candidate is a
replaceable preview, not truth or durable authority. An accepted record is created only
through existing application services after explicit apply. Review outcome text never
determines `DecisionOutcome.result`; the caller supplies that classification.

Preview is the default and performs no durable write. It shows source facts,
interpretation, uncertainty, actor fields, bounded `EvidenceReference` values, proposed
and excluded records, correlation checks, validation/tree strength, replay identity, and
partial-apply behavior. Apply requires `--confirm-authority`, immediately re-reads and
revalidates both files and all Git identities, and rejects a stale candidate.

All actor and authority fields are explicit attribution supplied by the caller. They are
not authentication and are never inferred from Git, Markdown, or operating-system
metadata. This slice adds no RBAC or signatures.

Validation evidence is classified as one of:

- exact committed tree attested;
- review diff matches commit but validation was pre-commit;
- review claim only;
- absent;
- contradictory.

Durable records contain bounded references for the prompt path and hash, review path and
hash, full commit SHA and tree, and validation section locator and review hash. They do
not contain full prompts, reviews, diffs, or unrestricted validation output.

The natural replay identity is `NeuralEngine:<full commit SHA>`. The orchestration derives
its service idempotency key; callers cannot override per-record keys. Equivalent replays
return existing records. Changed source hashes or semantics conflict. An amended commit
is a new identity. Apply is not transactional: after a partial failure, an exact rerun
resumes through existing Decision-family idempotency.

This flow creates or replays only Decision, DecisionAcceptance, DecisionAction,
DecisionOutcome, DecisionReview, and optionally Experience via the existing explicit
promotion service. It does not create Observation, Knowledge, Playbook, PlaybookRevision,
PlaybookRun, PlaybookEvaluation, EvolutionProposal, activation, or application records.

Unsupported inputs fail closed: path escape, a repository other than NeuralEngine,
missing or insufficient Markdown evidence, identical prompt/review selections, merge
commits, mismatched checkpoints/paths/patches, Handbook or cross-repository bundles, and
stale or semantically conflicting replay. There is no GitHub or CI integration, watcher,
webhook, background process, multi-repository ingestion, automatic learning, or actor
authentication.

The CLI surface is:

```text
neural development-evidence preview ... --records-json '<caller semantics>'
neural development-evidence apply ... --records-json '<caller semantics>' \
  --confirm-authority
```

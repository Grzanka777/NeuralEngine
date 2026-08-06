# PRD: Authority-Aware Planner Context Package

## 1. Document status

**Status:** Product requirements draft ready for product review.

**Scope:** First post-1.1 product slice; documentation only.

**Repository state:** No remediation, current 1.1.0 defect, or release blocker
is established.

**Implementation:** Not authorized by this PRD.

## 2. Product context

NeuralEngine provides durable knowledge while repository sources establish the
current implementation and operating constraints. The user-defined product
direction assigns local retrieval and context building to RAG, without making
RAG the product's defining purpose.

## 3. Problem statement

A planner repeatedly assembles task context manually from live repositories,
local Brain Knowledge, Handbook contracts and ADRs, review artifacts, selected
historical checkpoints, and explicitly supplied local sources. These sources
have different authority and freshness semantics. Manual assembly is necessary
today but is fragmented and repetitive.

The required product outcome is a bounded local context package that makes the
evidence, its authority, its freshness, and its provenance visible. It is not a
claim that the current release is defective.

## 4. Target user

The primary user is a **planner performing a repository or product assessment**.

Secondary users may validate package output, but this slice does not introduce
new workflows for builders, reviewers, operators, or end users.

## 5. Current workflow

The planner currently:

1. verifies repository path, branch, `HEAD`, authoritative remote reference,
   and worktree state;
2. reads current repository instructions and designated current documents;
3. searches Brain only when durable knowledge is materially relevant;
4. reads selected reviews and explicitly supplied historical evidence;
5. labels current, historical, missing, and conflicting information; and
6. prepares a decision package while retaining final judgment.

`neural knowledge search` is read-only substring search over Knowledge
statements and rationales in repository load order. It does not assemble this
multi-source package, classify authority, or inspect repository sources.

## 6. Product goal

Prepare a local, read-only, deterministic context package for one planner task.

The package must reduce repeated manual source collection while preserving this
invariant:

> Retrieved context never overrides the verified live repository.

The package is supplementary evidence. The caller retains final planning and
authorization judgment.

## 7. Non-goals

This PRD does not make current non-goals permanent prohibitions. It excludes
them only from the first slice.

- Brain writes, Memory consolidation, or automatic Knowledge promotion.
- Embeddings, vector databases, semantic ranking, or semantic retrieval.
- Router behavior, runtime/model selection, or quota decisions.
- Agent orchestration, prompt execution, or code generation.
- Repository mutation, persistent retrieval-event storage, or full
  multi-project search.
- A universal source-authority order for future source types.

## 8. First vertical slice

**Read-only authority-aware context preparation for one planner assessment.**

The slice receives a task and verified repository checkpoint, reads only a
narrow approved source set, and returns categorized evidence with provenance.
It neither makes a decision nor performs an action based on retrieved content.

## 9. User stories

- As a planner, I need current repository facts visibly separated from
  supporting Brain Knowledge so I do not treat historical knowledge as live Git
  authority.
- As a planner, I need historical and frozen release evidence labeled by its
  original context so I can use it without misrepresenting it as current.
- As a planner, I need missing, unreadable, stale, and conflicting sources
  reported explicitly so I can resolve gaps rather than receive silent fallback.
- As a planner, I need stable package order and exact provenance so a repeated
  assessment is auditable.

## 10. Functional requirements

FR-1. The package shall accept one product-level request and return only the
approved first-slice source categories.

FR-2. The package shall preserve the verified live repository as authority for
current repository state.

FR-3. The package shall label every result with an authority class and evidence
state.

FR-4. The package shall expose conflicts, missing evidence, and unreadable
sources rather than silently resolving or replacing them.

FR-5. The package shall be read-only for repository and Brain state.

FR-6. Identical accessible inputs shall produce the same categorized ordering.

FR-7. The package shall not execute prompts, invoke models, or change planner
policy.

## 11. Input contract

The following are product-level placeholders, not final implementation fields:

- `project_key`: caller-supplied project association.
- `task_statement`: bounded description of the assessment request.
- `verified_repository_checkpoint`: evidence captured before retrieval.
- `optional_source_filters`: caller-selected limits within approved source scope.

The checkpoint must contain repository path or identifier, branch, `HEAD`,
`origin/main` or equivalent authoritative remote reference, worktree state, and
verification timestamp.

An absent, incomplete, or unverified checkpoint cannot be represented as a
verified live repository fact.

## 12. Output contract

The package shall expose these categories, including empty categories where no
items are returned:

- `current_authoritative_sources`
- `supporting_brain_knowledge`
- `historical_evidence`
- `stale_or_conflicting_sources`
- `missing_evidence`
- `unreadable_or_inaccessible_sources`
- `provenance`

The presentation shall visibly distinguish product input, live repository fact,
current supporting knowledge, historical checkpoint, frozen release evidence,
stale source, conflict, missing source, and unreadable source.

## 13. Source scope

The initial source set includes only:

1. verified repository metadata;
2. designated current repository documents;
3. selected local Brain Knowledge records;
4. designated review artifacts; and
5. explicitly supplied historical checkpoints or release evidence.

The initial source set excludes project chats, arbitrary prompts, unrestricted
Handbook crawling, unrestricted filesystem search, all Brain record types, and
remote web sources.

Source filters may narrow this set. They must not silently broaden it.

## 14. Authority model

1. A verified live checkout is authoritative for current repository state.
2. Brain records are supporting durable knowledge, never live Git authority.
3. Historical and frozen evidence remains valid only in its labeled context.
4. Product requirements and repository facts remain separately labeled.
5. Conflicts are surfaced, not silently resolved.
6. Missing or unreadable authority is never silently substituted with a weaker
   source.
7. Final planning judgment remains with the caller.

This is a first-slice rule set, not a universal ordering for all future sources.

## 15. Freshness and evidence-state taxonomy

| State | Meaning and minimum evidence | Display and planning use | Override |
| --- | --- | --- | --- |
| `CURRENT` | Verified current source tied to supplied checkpoint. | Label current; supports planning. | Only as live repository fact. |
| `HISTORICAL` | Identified earlier source with checkpoint/time context. | Label historical; supports comparison. | Never overrides current. |
| `FROZEN_RELEASE_EVIDENCE` | Immutable release/tag evidence with version context. | Label frozen release; supports its release claim. | Never overrides current. |
| `STALE` | Source conflicts with or predates verified current evidence. | Label stale and show counterpart when known. | Never overrides current. |
| `CONFLICTING` | Accessible sources assert incompatible claims with no authorized resolution. | Show all relevant claims. | Never silently resolves. |
| `MISSING` | Required designated source was absent or not supplied. | Show missing locator/category. | Cannot support a claim. |
| `UNREADABLE` | Source was selected but inaccessible, corrupt, or unparsable. | Show bounded failure reason. | Cannot support a claim. |
| `AMBIGUOUS` | Identity, association, or classification cannot be determined from evidence. | Show ambiguity and required clarification. | Cannot support an authoritative claim. |

## 16. Provenance requirements

Every returned item shall include source type, source locator, source identity,
project association, retrieval time, authority class, evidence state, exact
extraction boundary or record identity, and checkpoint/version context when
applicable.

The package shall not require persisted retrieval history. Provenance is output
evidence for the current request, not a new durable Brain record.

## 17. Conflict and missing-evidence behavior

When a live repository fact and retrieved supporting source conflict, the
package shall preserve both claims, label the live fact as authoritative for
current repository state, and label the other source stale or conflicting based
on available evidence.

When a required designated source is missing, the package shall return a
`MISSING` item with requested locator/category and no substituted content.

When conflict classification itself is uncertain, the package shall return
`AMBIGUOUS` rather than invent precedence.

## 18. Error and partial-result behavior

The package may return accessible results with source-specific failures only
when each unavailable source is explicitly categorized as `MISSING`,
`UNREADABLE`, or `AMBIGUOUS`.

An unavailable verified repository checkpoint prevents claims of `CURRENT`
repository state. The package shall return a bounded failure or partial package
that identifies this condition; it must not select an unverified replacement.

Malformed source content shall not be repaired, ignored, or converted to a
successful result.

## 19. Privacy and filesystem boundaries

Only explicitly selected local sources and designated repository paths are in
scope. The slice shall not crawl the filesystem, discover unrelated projects,
access remote web sources, or read arbitrary prompt/chat files.

The PRD does not select future access-control mechanisms. A later design must
define allowed roots, path traversal handling, symlink policy, output redaction,
and caller authorization before implementation.

## 20. Determinism and ordering

The package shall preserve a documented deterministic category order and stable
ordering within each category for identical accessible inputs.

Ordering must not depend on model output, implicit recency inference, or
unspecified filesystem enumeration. A later design may select a concrete sort
key only if it preserves exact provenance and authority labels.

## 21. Evaluation scenarios

The implementation evaluation plan must include deterministic fixtures for:

1. clean live checkout with current supporting Brain Knowledge;
2. historical release evidence differing from current state;
3. stale Brain Knowledge conflicting with verified Git;
4. missing required repository document;
5. unreadable or corrupt Brain record;
6. empty results with explicit missing-evidence output;
7. optional source filters that do not expand source scope;
8. stable ordering for identical inputs;
9. proof of no Brain or repository write; and
10. planner use where package output remains supplementary to direct verification.

## 22. Acceptance criteria

- A valid request returns all seven output categories, including empty ones.
- Every returned item contains all required provenance values.
- A verified live Git fact is never relabeled or replaced by Brain Knowledge.
- Each fixture in Section 21 has objective expected category, state, and
  authority labels.
- Missing, unreadable, conflicting, and ambiguous sources remain visible.
- Repeated identical fixture requests have identical category/item order.
- No-write evaluation proves no Brain or repository content changes.
- The delivered scope contains no excluded behavior from Section 27.

## 23. Metrics

The first-slice product metrics are authority-classification accuracy,
provenance completeness, missing-evidence visibility, conflict visibility,
deterministic ordering, no-write guarantee, context-package completeness, and
operator time saved during repeated assessments.

### Operator-time-saved evaluation

The manual baseline is a planner preparing the context for one bounded planner
assessment using the current workflow in Section 5: verify the supplied
repository checkpoint, read the designated current documents, search selected
Brain Knowledge only when relevant, read selected review and historical
evidence, label the evidence state, and assemble the decision package. A
manual measurement starts when the planner begins gathering those approved
sources for the assigned task and ends when the completed context package is
ready for independent completeness review. Reading unrelated material,
waiting for unrelated work, breaks, and correcting an invalid run are excluded.

The measurement unit is elapsed operator minutes per completed planner
context-preparation task. The same unit is used for the manual baseline and
the assisted workflow. The initial evaluation uses at least 12 comparable
fixtures. Each fixture is run once manually and once with the first-slice
context package for the same task statement, verified checkpoint, and approved
source set; the manual and assisted runs form a paired comparison.

The measurement recorder captures a start timestamp, end timestamp, elapsed
minutes, fixture identifier, workflow (manual or assisted), and any excluded
idle interval for every run. Idle time unrelated to the assigned task is
subtracted from elapsed time. Incomplete, invalid, or quality-guard-failing
runs are recorded separately, retained with their reason, and excluded from
the paired reduction calculation. Raw timestamps, exclusions, results, and
run-status records are retained for product review; subjective estimates are
not measurements.

For every valid fixture pair, absolute reduction is
`manual_minutes - assisted_minutes`; percentage reduction is
`((manual_minutes - assisted_minutes) / manual_minutes) * 100`. The product
evaluation reports each valid pair and the median percentage reduction across
all valid pairs. The first-slice operator-time metric succeeds only when at
least 12 valid paired fixtures have completed and the median percentage
reduction is at least 15 percent. A single run cannot establish success.

Time reduction counts only for pairs whose assisted output passes independent
review for completeness, provenance, authority labeling, deterministic
ordering, and the no-write requirement. A time result that fails any of those
conditions is not a successful product result.

The evaluator records the measurements and the product reviewer signs off the
fixture set, exclusions, quality checks, and result. The implementation owner
may supply the assisted workflow but does not provide evaluation sign-off.
This metric validates first-slice product usefulness only; it does not
authorize architecture optimization, implementation-scope expansion, or any
excluded behavior.

The product shall not claim improved decision quality without comparative,
separately collected evidence.

## 24. Risks

- Retrieved historical material could be mistaken for current repository state.
- Broad source discovery could expose unrelated or sensitive local content.
- Unspecified precedence could conceal conflicts.
- A context package could expand prematurely into generic RAG, Memory, Router,
  or Agents behavior.
- Incomplete provenance could make output unauditable.

The authority, source-scope, and no-write requirements mitigate these risks.

## 25. Dependencies

Implementation consideration depends on approval of the source inventory,
designated-document set, authority taxonomy, request/response boundary,
filesystem/privacy boundary, error contract, evaluation fixtures, metric
thresholds, and no-write verification method.

Current Knowledge search remains a supporting capability; this PRD does not
require changing it.

## 26. Open product questions

### Blocking implementation questions

1. Which repository documents are designated current sources per project?
2. How is project association established for local Brain Knowledge?
3. Which local roots, symlink rules, and redaction rules are permitted?
4. What is the approved deterministic ordering key within each category?
5. What thresholds define acceptable classification and provenance completeness?
6. Who owns fixtures and signs off the no-write verification method?

### Deferrable questions

1. Which secondary users consume rendered packages?
2. Which additional source types may enter a later slice?
3. Which presentation format best supports planners?

### Later design questions

Architecture placement, concrete interfaces, adapters, schemas, CLI surface,
error types, and persistence decisions require a separate design task.

## 27. Explicit implementation exclusions

No implementation may add Brain writes, Memory consolidation, Knowledge
promotion, embeddings, vector storage, semantic ranking, Router selection,
runtime/model selection, Agents orchestration, prompt execution, code
generation, repository mutation, retrieval-event persistence, or unrestricted
multi-project search under this PRD.

## 28. Go / defer decision gate

Implementation may be recommended only when all conditions hold:

1. first-slice source scope is approved;
2. authority rules and state taxonomy are approved;
3. request and response boundaries are approved;
4. evaluation fixtures and objective thresholds exist;
5. privacy and filesystem boundaries are approved;
6. no-write behavior is testable;
7. the slice remains limited to planner context preparation; and
8. a separate product authorization explicitly approves implementation.

Otherwise, defer implementation and retain the manual evidence-first workflow.

## 29. Authorization boundary

This PRD authorizes product review only. It does not authorize implementation,
architecture design, source/test/configuration changes, Brain mutation, Agent
Pack modification, runtime-state changes, staging, commit, push, merge, tag, or
release.

# Coding Conventions

> From observations to intelligence.

## Controlled CREATE writers

Paths-backed production services that append one new JSON record use the
existing Brain Trust transition coordinator through `Container`. Their
repository supplies one validated Brain-relative target and create-once
publication of the exact bytes. Direct repository construction is retained
for tests and local composition only.

The protected CREATE set covers observations, Experiences, playbooks,
evaluations, proposals, revision activation/application records, and the
Decision, acceptance, action, outcome, and review records. Recovery is bounded
to the canonical JSON stores and valid S2-S4 suffixes; S1, replacement/status
writers, multi-record apply, and adoption/restore/clone/rebind operations remain
outside this boundary. Do not broaden this convention into a generic
transaction or repository guard.

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

## M12 proposal status REPLACE

`EvolutionProposalService.set_status()` is the one protected single-record
`REPLACE` path. It replaces only the exact
`evolution-proposals/<proposal-id>.json` file through the existing Brain Trust
coordinator, using literal durable BEFORE and AFTER SHA-256 values and a
stale-preimage check immediately before publication. Recovery is bounded to
this store, one ordinary single-target REPLACE, and forward R2/R3/R4 suffixes;
R1 is rejected when AFTER cannot be reconstructed from authoritative evidence.
There is no generic REPLACE recovery, no REMOVE, no adoption/restore/clone/
rebind, and no M23 development-evidence protection. `WRITER_COVERAGE_BLOCKED`
remains until M23 is separately resolved.

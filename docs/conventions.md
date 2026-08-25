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
writers, grouped multi-record transitions, and adoption/restore/clone/rebind
operations remain outside this boundary. M23 development-evidence apply is
supported as independently controlled per-record generations: it composes the
protected component services in order, accepts a durable valid prefix, and
relies on each service's existing idempotency/conflict semantics for exact
retry. It is not a transaction and does not add a group recovery contract.
Do not broaden this convention into a generic transaction or repository guard.

## Bounded Brain Trust adoption

Adoption is a separate local boundary exposed through `neural brain adopt`.
`--plan` is read-only; `--confirm` requires a fresh UUID4, generation 1,
explicit backup evidence, and an exact identity-bound confirmation; `--recover`
continues only a valid adoption marker with an absent or matching binding.
Fresh adoption never overwrites pre-existing metadata or binding artifacts and
never rewrites existing records. Metadata marker publication precedes
create-only binding publication, binding verification precedes marker clear,
and marker clear is last. Recovery is forward-only and does not broaden the
ordinary `neural brain recover` command. This remains Model A local filesystem
trust: adoption does not provide distributed locking, cryptographic tamper
evidence, or retroactive semantic/provenance trust for existing records.

## M12 proposal status REPLACE

`EvolutionProposalService.set_status()` is the one protected single-record
`REPLACE` path. It replaces only the exact
`evolution-proposals/<proposal-id>.json` file through the existing Brain Trust
coordinator, using literal durable BEFORE and AFTER SHA-256 values and a
stale-preimage check immediately before publication. Recovery is bounded to
this store, one ordinary single-target REPLACE, and forward R2/R3/R4 suffixes;
R1 is rejected when AFTER cannot be reconstructed from authoritative evidence.
There is no generic REPLACE recovery, no REMOVE, no adoption/restore/clone/
rebind, and no grouped M23 recovery. M23's supported per-record path is
covered by the existing single-record coordinator; no central repository guard
is introduced.

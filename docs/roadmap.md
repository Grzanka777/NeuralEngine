# Roadmap

## Historical 1.0 Release Record

NeuralEngine 1.0 was the bounded release target described below. The
historical `v1.0.0` tag remains the authority for that release record; it does
not describe the current package state.

The canonical definition of its supported capabilities, interpretive limits,
explicit non-goals, writer and concurrency assumptions, operational evidence,
and release evidence gate is:

[`1-0-scope-and-release-gate.md`](1-0-scope-and-release-gate.md)

This roadmap is a pointer and closure sequence, not a feature backlog. Work not
included in the canonical scope does not become a 1.0 requirement merely
because it is useful or appears in an architectural design.

## Historical 1.0 Closure Sequence

1. Define and validate the bounded documentation contract.
2. Publish the current Handbook-generated NeuralEngine skill byte-for-byte in
   its separately authorized task.
3. Record the current operational evidence inventory and run the documented
   release evidence gate.
4. Make and document the exact package-version and Git-tag decision in an
   authorized release action.

Implementation or hardening work is justified only by a source-proven failure
against the bounded 1.0 contract, not by an aspirational capability or an
unexercised operational path.

## Current State

Package version `1.1.0` and annotated tag `v1.1.0` exist. After that release,
the repository merged read-only `neural knowledge search QUERY` and
agent-governance hardening. Knowledge search performs case-insensitive
substring matching against Knowledge statements and rationales, preserves
repository load order, and does not rank results or provide semantic or
cross-record retrieval.

This roadmap remains a historical 1.0 closure pointer, not a declaration of a
future release target or version.

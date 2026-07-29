# Roadmap

The current bounded release target is NeuralEngine 1.0.

The canonical definition of its supported capabilities, interpretive limits,
explicit non-goals, writer and concurrency assumptions, operational evidence,
and release evidence gate is:

[`1-0-scope-and-release-gate.md`](1-0-scope-and-release-gate.md)

This roadmap is a pointer and closure sequence, not a feature backlog. Work not
included in the canonical scope does not become a 1.0 requirement merely
because it is useful or appears in an architectural design.

## 1.0 Closure Sequence

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

# Implement multi-level approval engine as pure in-memory library

Status: accepted (generated, pending human review)

## Context

Need a deterministic, tested approval workflow for backend services. The spec defines routing, quorums, delegation, escalation and terminal states.

## Decision

Implement a single Python package with immutable dataclasses for policy and request state, and a stateful engine that operates on them using an injected clock. No runtime dependencies to keep the package lightweight and auditable.

## Consequences

The engine is easy to test and reason about. It is not thread-safe and does not persist state; those concerns are left to the application or future adapters.

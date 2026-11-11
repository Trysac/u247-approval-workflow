# 0001 - Pure in-memory engine with an injected clock

## Status

Accepted.

## Context

Approval rules need to be deterministic and easy to test, including the late and
duplicate events that break ad-hoc status-column implementations. Persistence,
notifications and UIs vary per host application.

## Decision

- Keep the engine pure and in-memory. State lives in the `ApprovalEngine`
  instance; callers integrate persistence, notifications and UIs themselves
  through the returned `RequestState` and the optional `on_event` callback.
- Inject the clock as `Callable[[], datetime]` defaulting to UTC now. All
  timeout, escalation and delegation-expiry decisions read this clock, so tests
  are deterministic without sleeping.
- Model the policy as frozen dataclasses (`Level`, `Route`, `ApprovalPolicy`)
  validated at construction, so invalid policies fail early with
  `invalid_policy`.
- Use only the standard library, as required by the specification.

## Consequences

- No runtime dependencies and a small, auditable surface.
- Hosts own durability and delivery guarantees.
- Behaviour is fully reproducible under an injected clock, which is what the
  test suite relies on for escalation and delegation expiry.

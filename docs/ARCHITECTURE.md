# Architecture

`approval_workflow` is a pure, in-memory, clock-driven approval engine with no runtime dependencies. The package modules are:

| Module | Responsibility |
|---|---|
| `errors.py` | `ApprovalError` carrying a stable machine-readable `code`. |
| `models.py` | Frozen dataclasses `Level`, `Route`, `ApprovalPolicy`, `RequestState` and `HistoryEntry`. |
| `engine.py` | `ApprovalEngine`: routing, quorum progression, delegation, escalation and terminal states. |
| `__init__.py` | Public API surface (`__all__`). |

## Policy shape

- **Level**: a set of approvers, a quorum between 1 and the number of approvers, an optional positive `timeout_s`, and an optional `escalate_to` naming another level.
- **Route**: an exclusive upper bound `max_amount` and a tuple of level names. An amount uses the first route with `amount < max_amount`; `None` means no bound. Routes must increase and end with exactly one `None` route, otherwise `invalid_policy`.
- **ApprovalPolicy**: the level mapping plus the ordered routes. Every route level name and every `escalate_to` name must exist in the level mapping.

## Request lifecycle

1. `submit` validates ids and amount, routes by amount, and records the first level with a deadline derived from that level's timeout.
2. `decide` applies a fixed check order: `unknown_request`, `invalid_id` for the actor, `already_decided`, `self_approval`, principal resolution, `duplicate_vote`. The eligible set is the current level's approvers, or the escalation level's approvers once escalated.
3. Approving appends a vote. Reaching the quorum fires `level_approved` and advances to the next original level, or fires `approved`. Rejection is immediate and records a rejected history entry with no comment.
4. Terminal states (`approved`, `rejected`, `expired`, `cancelled`) never change again, and `tick()` skips them.

## Time, delegation and escalation

The engine takes an injected `clock` returning a timezone-aware `datetime`, so behavior is deterministic under tests (`invalid_clock` otherwise).

- A **delegation** maps a principal to a delegate until an expiry date. The actor itself wins if it is directly eligible; otherwise an active delegation from an eligible principal is used, without following chains. Expired delegations are purged on access.
- On `tick`, every pending request whose deadline has passed escalates once (`escalated`, restarting the timer with the escalation level's timeout) or, if it has already escalated or the level has no `escalate_to`, becomes `expired`.

## Bounds and observability

At most `max_requests` requests are retained, evicting the oldest terminal request; history per request is capped at 200 entries; comments are cut to 500 characters. An optional `on_event` callback receives `submitted`, `vote`, `level_approved`, `approved`, `rejected`, `escalated`, `expired` and `cancelled` payloads. Clock-driven events carry an empty `actor`. Payloads contain `event`, `request_id`, `actor` and `level`, never comments.

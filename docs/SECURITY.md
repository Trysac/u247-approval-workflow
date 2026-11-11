# Security

This package is a pure in-memory engine and does not persist, transmit or log data itself. Its logger is `logging.getLogger(__name__)` with a `NullHandler`. Security therefore focuses on input validation, separation of duties and bounded state.

## Defended

- Request ids and actor names must match `[A-Za-z0-9._@-]{1,128}` exactly; the regex is anchored with a full match, so a trailing newline is rejected as `invalid_id`.
- Amounts must be `Decimal`, finite and non-negative (`invalid_amount`).
- Comments are truncated to 500 characters when recorded on approve votes.
- The injected clock must return a timezone-aware `datetime` (`invalid_clock`).
- The requester can never approve their own request (`self_approval`).
- The same principal cannot vote twice across levels, and the same acting actor cannot vote twice (`duplicate_vote`).
- Policy validation rejects missing levels, invalid route ordering, a missing final `max_amount=None` route, route level names that do not exist, invalid quorums, non-positive timeouts and `escalate_to` names that do not exist (`invalid_policy`).
- Bounded state: at most `max_requests` requests are retained, evicting the oldest terminal request first, otherwise `too_many_requests`; at most `max_delegations` active delegations are kept; history per request is capped at 200 entries and a further append raises `history_full`.

## Not defended

- The engine does not authenticate or authorize actors beyond the explicit approver sets, delegation records and requester checks. Actor names are trusted as supplied by the caller.
- The engine does not provide durable storage, durable audit records, encryption, network security, tenant isolation or rate limiting. Request state and history are in memory and terminal requests can be evicted by the `max_requests` policy.
- No thread-safety is provided; callers must serialize access to an engine instance.
- Exceptions raised by an `on_event` callback are not caught by the engine.

## Input validation

Ids, amounts, comments, clock values and policy structure are checked as described above. Event payloads contain only `event`, `request_id`, `actor` and `level`; comments are never included.

## Separation of duties

The requester is rejected as an approver (`self_approval`). Delegation maps an eligible principal to a delegate for a bounded time; the engine does not follow delegation chains, and a principal or actor already present in votes is rejected as `duplicate_vote`.

## Bounded state

`max_requests` defaults to `10_000`, `max_delegations` defaults to `1_000`, and per-request history is capped at 200 entries. Comments are cut to 500 characters.

## Reporting

No private reporting channel is defined in the provided repository snapshot. Report vulnerabilities through the repository owner's configured channel.

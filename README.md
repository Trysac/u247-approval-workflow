# trysac-approval-workflow

[![PyPI version](https://badge.fury.io/py/trysac-approval-workflow.svg)](https://badge.fury.io/py/trysac-approval-workflow)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Pure, deterministic, multi-level approval engine.

Purchase orders, refunds, access grants and deployments often need several approvals: a manager, then two people from finance, then an executive above some amount. Teams encode this as status columns and if-statements, and the classic failures follow: the requester approves their own request, the same person approves at two levels, a vacation blocks everything, and a late click flips a rejected request back to approved. This library is a pure, clock-driven approval engine with those rules written down and tested.

## Features

- Amount-based routing: choose a sequence of levels based on the request amount.
- Sequential levels with quorums: each level requires a minimum number of approvals.
- Separation of duties: the requester cannot approve, and the same principal cannot vote more than once across levels.
- Time-bound delegation: approvers can delegate their authority to another actor until a timezone-aware expiry.
- Escalation on timeout: a pending level can escalate once to another level; a second timeout expires the request.
- Terminal states: approved, rejected, expired, cancelled.
- Event emission: optional callback with event, request_id, actor and level; comments are never included.
- Bounded memory: configurable maximum requests and delegations; history is capped at 200 entries.

## Installation

```bash
pip install trysac-approval-workflow
```

## Usage

```python
from decimal import Decimal
from approval_workflow import ApprovalEngine, ApprovalPolicy, Level, Route

L = {"manager": Level(frozenset({"mia"}), 1), "finance": Level(frozenset({"fay", "fox"}), 2)}
P = ApprovalPolicy(L, (Route(None, ("manager", "finance")),))
e = ApprovalEngine(P)
e.submit("r1", "rob", Decimal("5000"))
e.decide("r1", "mia", "approve")
e.decide("r1", "fay", "approve")
s = e.decide("r1", "fox", "approve")
print(s.status)  # approved
```

## Public API

The package exports `ApprovalEngine`, `ApprovalError`, `ApprovalPolicy`, `HistoryEntry`, `Level`, `RequestState` and `Route`.

- `Level(approvers: frozenset[str], quorum: int, timeout_s: float | None = None, escalate_to: str | None = None)`: `quorum` must be between 1 and `len(approvers)`; `timeout_s` must be positive when set; `escalate_to` must name another level in the policy.
- `Route(max_amount: Decimal | None, levels: tuple[str, ...])`: an amount uses the first route where `amount < max_amount`; `None` means no upper bound.
- `ApprovalPolicy(levels: Mapping[str, Level], routes: tuple[Route, ...])`: levels and routes must be non-empty; routes must be ordered by increasing `max_amount` and end with exactly one route whose `max_amount` is `None`; every route level name must exist in `levels`.
- `ApprovalEngine(policy, *, clock=lambda: datetime.now(timezone.utc), max_requests=10_000, max_delegations=1_000, on_event=None)`: the clock must return a timezone-aware `datetime`.

Engine methods:

- `submit(request_id, requester, amount) -> RequestState`: validates ids and amount, selects a route, creates a pending request at the first level. Errors: `invalid_id`, `invalid_amount`, `duplicate_request`, `too_many_requests`, `invalid_policy`.
- `decide(request_id, actor, decision, comment='') -> RequestState`: `decision` is `approve` or `reject`. The check order is `unknown_request`, `invalid_id` for the actor, `already_decided`, `self_approval`, principal resolution, `duplicate_vote`. Approve votes record the truncated comment; reject ends the request immediately with a history entry whose comment is `None`. Other errors: `not_eligible`, `history_full`.
- `cancel(request_id, actor) -> RequestState`: only the requester can cancel a pending request. Errors: `invalid_id`, `unknown_request`, `not_eligible`, `already_decided`, `history_full`.
- `delegate(principal, delegate, *, until) -> None`: `until` must be timezone-aware and after the current clock; `principal` and `delegate` must differ. Errors: `invalid_id`, `invalid_delegation`.
- `tick() -> list[RequestState]`: processes deadlines in submission order; each pending request escalates at most once or expires. Can raise `history_full`.
- `get(request_id) -> RequestState`: raises `unknown_request`.

`ApprovalError` exposes a stable `code` attribute. The full set is `invalid_policy`, `unknown_request`, `already_decided`, `self_approval`, `not_eligible`, `duplicate_vote`, `invalid_delegation`, `too_many_requests`, `duplicate_request`, `invalid_amount`, `invalid_id`, `history_full`, `invalid_clock`.

Limits and options: ids and actor names must match `[A-Za-z0-9._@-]{1,128}`; amounts must be `Decimal`, finite and non-negative; comments are cut to 500 characters; each request keeps at most 200 history entries and a further append raises `history_full`; at most `max_requests` requests are retained, evicting the oldest terminal request first, otherwise `too_many_requests`; at most `max_delegations` active delegations are kept; expired delegations are purged on access. Logging uses `logging.getLogger(__name__)` with a `NullHandler`.

## Why not status columns in the application

Status columns and if-statements spread the rules across the application. This engine centralises the policy, is deterministic under an injected clock, and is tested against late and duplicate events.

## Documentation

- [Project](docs/PROJECT.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Security](docs/SECURITY.md)
- [Testing](docs/TESTING.md)
- [Stack](docs/STACK.md)

Security policy: [docs/SECURITY.md](docs/SECURITY.md)

## License

MIT

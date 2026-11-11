# Testing

The provided snapshot includes a pytest 9.2.0 compiled artifact for `tests/test_acceptance.py`. Run the tests with:

```bash
pytest
```

## Layout

The only test module present in the provided snapshot is `tests/test_acceptance.py`. It contains acceptance tests derived from the specification. Its visible tests include `test_routing_amounts` and `test_quorum_and_progression`, and the module exercises the specification's acceptance scenarios: route selection at exact bounds, quorum progression, self-approval and eligibility, duplicate votes, rejection and terminal immutability, escalation and expiry via `tick`, delegation and delegation expiry, request/amount validation, and event payloads without comments.

No other test modules are present in the provided snapshot.

## Conventions

The acceptance module defines a `make_clock` helper that returns an advanceable clock, so timeout, escalation and delegation-expiry behavior is deterministic. Tests exercise the public API rather than private helpers. The specification names these edge cases for tests: a quorum equal to the number of approvers, an amount exactly equal to a route bound, a delegate who is also a direct approver, and cancel after approval.

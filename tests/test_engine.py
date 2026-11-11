"""Additional unit tests for ApprovalEngine."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from approval_workflow import (
    ApprovalEngine,
    ApprovalError,
    ApprovalPolicy,
    Level,
    Route,
)


def make_clock(start: datetime):
    current = start

    def clock() -> datetime:
        return current

    return clock


class TestEngine:
    def test_submit(self):
        levels = {"l1": Level(approvers=frozenset({"a"}), quorum=1)}
        policy = ApprovalPolicy(levels=levels, routes=(Route(max_amount=None, levels=("l1",)),))
        engine = ApprovalEngine(policy)
        state = engine.submit("r1", "req", Decimal("100"))
        assert state.id == "r1"
        assert state.requester == "req"
        assert state.amount == Decimal("100")
        assert state.status == "pending"
        assert state.current_level == "l1"
        assert state.escalated is False
        assert state.votes == ()
        assert len(state.history) == 1
        assert state.history[0].event == "submitted"

    def test_submit_invalid_id(self):
        policy = ApprovalPolicy(
            levels={"l": Level(approvers=frozenset({"a"}), quorum=1)},
            routes=(Route(max_amount=None, levels=("l",)),),
        )
        engine = ApprovalEngine(policy)
        with pytest.raises(ApprovalError) as exc_info:
            engine.submit("bad id", "req", Decimal("1"))
        assert exc_info.value.code == "invalid_id"
        with pytest.raises(ApprovalError) as exc_info:
            engine.submit("ok", "bad id", Decimal("1"))
        assert exc_info.value.code == "invalid_id"

    def test_invalid_id_rejects_trailing_newline(self):
        policy = ApprovalPolicy(
            levels={"l": Level(approvers=frozenset({"a"}), quorum=1)},
            routes=(Route(max_amount=None, levels=("l",)),),
        )
        engine = ApprovalEngine(policy)
        with pytest.raises(ApprovalError) as exc_info:
            engine.submit("r1\n", "rob", Decimal("1"))
        assert exc_info.value.code == "invalid_id"
        with pytest.raises(ApprovalError) as exc_info:
            engine.submit("r1", "rob\n", Decimal("1"))
        assert exc_info.value.code == "invalid_id"
        with pytest.raises(ApprovalError) as exc_info:
            engine.submit("a\nb", "rob", Decimal("1"))
        assert exc_info.value.code == "invalid_id"
        engine.submit("r1", "rob", Decimal("1"))
        with pytest.raises(ApprovalError) as exc_info:
            engine.decide("r1", "a\n", "approve")
        assert exc_info.value.code == "invalid_id"
        with pytest.raises(ApprovalError) as exc_info:
            engine.delegate(
                "a\n",
                "b",
                until=datetime(2023, 1, 1, tzinfo=timezone.utc) + timedelta(days=1),
            )
        assert exc_info.value.code == "invalid_id"

    def test_submit_invalid_amount(self):
        policy = ApprovalPolicy(
            levels={"l": Level(approvers=frozenset({"a"}), quorum=1)},
            routes=(Route(max_amount=None, levels=("l",)),),
        )
        engine = ApprovalEngine(policy)
        with pytest.raises(ApprovalError) as exc_info:
            engine.submit("r", "req", Decimal("-1"))
        assert exc_info.value.code == "invalid_amount"
        with pytest.raises(ApprovalError) as exc_info:
            engine.submit("r", "req", Decimal("NaN"))
        assert exc_info.value.code == "invalid_amount"
        with pytest.raises(ApprovalError) as exc_info:
            engine.submit("r", "req", 100)  # type: ignore
        assert exc_info.value.code == "invalid_amount"

    def test_cancel(self):
        levels = {"l": Level(approvers=frozenset({"a"}), quorum=1)}
        policy = ApprovalPolicy(
            levels=levels,
            routes=(Route(max_amount=None, levels=("l",)),),
        )
        engine = ApprovalEngine(policy)
        engine.submit("r1", "req", Decimal("10"))
        cancelled = engine.cancel("r1", "req")
        assert cancelled.status == "cancelled"
        assert cancelled.current_level is None
        assert cancelled.history[-1].event == "cancelled"

        # non-requester cannot cancel
        with pytest.raises(ApprovalError) as exc_info:
            engine.cancel("r1", "other")
        assert exc_info.value.code == "not_eligible"

        # cancel after terminal raises already_decided
        engine2 = ApprovalEngine(policy)
        engine2.submit("r2", "req", Decimal("10"))
        engine2.decide("r2", "a", "approve")
        with pytest.raises(ApprovalError) as exc_info:
            engine2.cancel("r2", "req")
        assert exc_info.value.code == "already_decided"

    def test_delegate_invalid(self):
        levels = {"l": Level(approvers=frozenset({"a"}), quorum=1)}
        policy = ApprovalPolicy(
            levels=levels,
            routes=(Route(max_amount=None, levels=("l",)),),
        )
        engine = ApprovalEngine(policy)
        now = datetime(2023, 1, 1, tzinfo=timezone.utc)
        # invalid until (past)
        with pytest.raises(ApprovalError) as exc_info:
            engine.delegate("a", "b", until=now - timedelta(seconds=1))
        assert exc_info.value.code == "invalid_delegation"
        # self-delegation
        with pytest.raises(ApprovalError) as exc_info:
            engine.delegate("a", "a", until=now + timedelta(seconds=1))
        assert exc_info.value.code == "invalid_delegation"

    def test_max_delegations(self):
        levels = {"l": Level(approvers=frozenset({"a"}), quorum=1)}
        policy = ApprovalPolicy(
            levels=levels,
            routes=(Route(max_amount=None, levels=("l",)),),
        )
        now = datetime(2023, 1, 1, tzinfo=timezone.utc)
        engine = ApprovalEngine(policy, clock=lambda: now, max_delegations=1)
        engine.delegate("a", "b", until=now + timedelta(days=1))
        # another delegation should fail because max reached and principal new
        with pytest.raises(ApprovalError) as exc_info:
            engine.delegate("c", "d", until=now + timedelta(days=1))
        assert exc_info.value.code == "invalid_delegation"
        # replacing existing principal works
        engine.delegate("a", "e", until=now + timedelta(days=1))

    def test_tick_multiple(self):
        levels = {
            "a": Level(approvers=frozenset({"x"}), quorum=1, timeout_s=1),
            "b": Level(approvers=frozenset({"y"}), quorum=1, timeout_s=2),
        }
        policy = ApprovalPolicy(
            levels=levels,
            routes=(Route(max_amount=None, levels=("a", "b")),),
        )
        start = datetime(2023, 1, 1, tzinfo=timezone.utc)
        current = start

        def clock():
            return current

        engine = ApprovalEngine(policy, clock=clock)
        engine.submit("r1", "req", Decimal("1"))
        engine.submit("r2", "req", Decimal("2"))
        current = start + timedelta(seconds=1)
        changed = engine.tick()
        # r1 at level a timeout: escalate? a has no escalate_to, so expire
        # r2 also at level a, both expire
        assert len(changed) == 2
        assert changed[0].status == "expired"
        assert changed[1].status == "expired"

    def test_history_full(self):
        # Create a policy with quorum high enough so we can add many votes.
        levels = {"l": Level(approvers=frozenset({f"a{i}" for i in range(200)}), quorum=200)}
        policy = ApprovalPolicy(
            levels=levels,
            routes=(Route(max_amount=None, levels=("l",)),),
        )
        engine = ApprovalEngine(policy)
        engine.submit("r2", "req", Decimal("1"))
        # add 199 votes (history will include submitted + 199 votes = 200)
        for i in range(199):
            engine.decide("r2", f"a{i}", "approve")
        # now next vote should raise history_full
        with pytest.raises(ApprovalError) as exc_info:
            engine.decide("r2", "a199", "approve")
        assert exc_info.value.code == "history_full"

    def test_invalid_clock(self):
        levels = {"l": Level(approvers=frozenset({"a"}), quorum=1)}
        policy = ApprovalPolicy(
            levels=levels,
            routes=(Route(max_amount=None, levels=("l",)),),
        )
        with pytest.raises(ApprovalError) as exc_info:
            ApprovalEngine(policy, clock=lambda: datetime.now())  # naive
        assert exc_info.value.code == "invalid_clock"

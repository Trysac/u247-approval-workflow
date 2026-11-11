"""Acceptance tests from the specification."""

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
    """Return a clock that can be advanced."""
    current = start

    def clock() -> datetime:
        nonlocal current
        return current

    return clock, lambda dt: None  # placeholder, we'll adjust by reassigning


class TestAcceptance:
    def test_routing_amounts(self):
        levels = {
            "manager": Level(approvers=frozenset({"mia", "max"}), quorum=1),
            "finance": Level(approvers=frozenset({"fay", "fin", "fox", "mia"}), quorum=2),
            "cfo": Level(approvers=frozenset({"cfo"}), quorum=1),
        }
        routes = (
            Route(max_amount=Decimal("1000"), levels=("manager",)),
            Route(max_amount=Decimal("10000"), levels=("manager", "finance")),
            Route(max_amount=None, levels=("manager", "finance", "cfo")),
        )
        policy = ApprovalPolicy(levels=levels, routes=routes)
        engine = ApprovalEngine(policy)

        # amount 999.99 -> manager only
        state = engine.submit("r1", "rob", Decimal("999.99"))
        assert state.levels == ("manager",)
        assert state.current_level == "manager"

        # amount 1000 -> manager, finance
        state = engine.submit("r2", "rob", Decimal("1000"))
        assert state.levels == ("manager", "finance")
        assert state.current_level == "manager"

        # amount 10000 -> manager, finance, cfo
        state = engine.submit("r3", "rob", Decimal("10000"))
        assert state.levels == ("manager", "finance", "cfo")
        assert state.current_level == "manager"

    def test_quorum_and_progression(self):
        levels = {
            "manager": Level(approvers=frozenset({"mia", "max"}), quorum=1),
            "finance": Level(approvers=frozenset({"fay", "fin", "fox", "mia"}), quorum=2),
        }
        policy = ApprovalPolicy(
            levels=levels,
            routes=(Route(max_amount=None, levels=("manager", "finance")),),
        )
        engine = ApprovalEngine(policy)
        state = engine.submit("r1", "rob", Decimal("5000"))
        assert state.status == "pending"
        assert state.current_level == "manager"

        # mia approves at manager -> moves to finance
        state = engine.decide("r1", "mia", "approve")
        assert state.status == "pending"
        assert state.current_level == "finance"

        # fay approves at finance -> still pending (quorum 2)
        state = engine.decide("r1", "fay", "approve")
        assert state.status == "pending"
        assert state.current_level == "finance"

        # fox approves at finance -> approved
        state = engine.decide("r1", "fox", "approve")
        assert state.status == "approved"
        assert state.current_level is None

    def test_error_self_approval_not_eligible_duplicate(self):
        levels = {
            # 'rob' is deliberately an approver so self_approval is checked
            # even when the requester is otherwise eligible.
            "manager": Level(approvers=frozenset({"mia", "max", "rob"}), quorum=1),
            "finance": Level(approvers=frozenset({"fay", "fin", "fox", "mia"}), quorum=2),
        }
        policy = ApprovalPolicy(
            levels=levels,
            routes=(Route(max_amount=None, levels=("manager", "finance")),),
        )
        engine = ApprovalEngine(policy)
        engine.submit("r1", "rob", Decimal("5000"))

        # requester tries to approve -> self_approval even if approver
        with pytest.raises(ApprovalError) as exc_info:
            engine.decide("r1", "rob", "approve")
        assert exc_info.value.code == "self_approval"
        # No vote was recorded by the rejected self-approval.
        assert engine.get("r1").votes == ()

        # zed not eligible
        with pytest.raises(ApprovalError) as exc_info:
            engine.decide("r1", "zed", "approve")
        assert exc_info.value.code == "not_eligible"

        # mia approves at manager (ok)
        engine.decide("r1", "mia", "approve")
        # mia tries again at finance -> duplicate_vote
        with pytest.raises(ApprovalError) as exc_info:
            engine.decide("r1", "mia", "approve")
        assert exc_info.value.code == "duplicate_vote"

    def test_reject_and_already_decided(self):
        levels = {
            "manager": Level(approvers=frozenset({"mia", "max"}), quorum=1),
            "finance": Level(approvers=frozenset({"fay", "fin", "fox", "mia"}), quorum=2),
        }
        policy = ApprovalPolicy(
            levels=levels,
            routes=(Route(max_amount=None, levels=("manager", "finance")),),
        )
        engine = ApprovalEngine(policy)
        engine.submit("r1", "rob", Decimal("5000"))
        engine.decide("r1", "mia", "approve")  # move to finance

        state = engine.decide("r1", "fin", "reject")
        assert state.status == "rejected"

        # later decide raises already_decided and state unchanged
        state_before = engine.get("r1")
        with pytest.raises(ApprovalError) as exc_info:
            engine.decide("r1", "fox", "approve")
        assert exc_info.value.code == "already_decided"
        assert engine.get("r1") == state_before

        # tick never changes terminal
        changed = engine.tick()
        assert changed == []

    def test_escalation_and_timeout(self):
        start = datetime(2023, 1, 1, tzinfo=timezone.utc)
        current = start
        events = []

        def clock() -> datetime:
            nonlocal current
            return current

        levels = {
            "manager": Level(
                approvers=frozenset({"mia"}),
                quorum=1,
                timeout_s=3600,
                escalate_to="director",
            ),
            "director": Level(approvers=frozenset({"dee"}), quorum=1),
        }
        policy = ApprovalPolicy(
            levels=levels,
            routes=(Route(max_amount=None, levels=("manager",)),),
        )
        engine = ApprovalEngine(policy, clock=clock, on_event=events.append)
        engine.submit("r1", "rob", Decimal("1000"))

        # no timeout yet
        changed = engine.tick()
        assert changed == []

        # advance 3600 seconds
        current = start + timedelta(seconds=3600)
        changed = engine.tick()
        assert len(changed) == 1
        state = changed[0]
        assert state.status == "pending"
        assert state.current_level == "director"
        assert state.escalated is True
        assert state.history[-1].event == "escalated"
        assert {
            "event": "escalated",
            "request_id": "r1",
            "actor": "",
            "level": "manager",
        } in events

        # mia now not eligible
        with pytest.raises(ApprovalError) as exc_info:
            engine.decide("r1", "mia", "approve")
        assert exc_info.value.code == "not_eligible"

        # dee approves -> request approved (only one level)
        state = engine.decide("r1", "dee", "approve")
        assert state.status == "approved"

        # Second timeout after escalation expires the request.
        levels2 = {
            "manager": Level(
                approvers=frozenset({"mia"}),
                quorum=1,
                timeout_s=100,
                escalate_to="director",
            ),
            "director": Level(approvers=frozenset({"dee"}), quorum=1, timeout_s=100),
        }
        policy2 = ApprovalPolicy(
            levels=levels2,
            routes=(Route(max_amount=None, levels=("manager",)),),
        )
        current2 = start

        def clock2() -> datetime:
            return current2

        engine2 = ApprovalEngine(policy2, clock=clock2)
        engine2.submit("r2", "rob", Decimal("1000"))
        current2 = start + timedelta(seconds=100)
        changed = engine2.tick()  # escalate to director
        assert changed[0].current_level == "director"
        current2 = start + timedelta(seconds=200)
        changed = engine2.tick()  # second timeout -> expired
        assert changed[0].status == "expired"
        assert changed[0].history[-1].event == "expired"

    def test_escalated_level_does_not_escalate_again(self):
        # The escalated level itself declares escalate_to, but a request may
        # only escalate once: a second timeout expires it.
        start = datetime(2023, 1, 1, tzinfo=timezone.utc)
        current = start

        def clock() -> datetime:
            return current

        levels = {
            "manager": Level(
                approvers=frozenset({"mia"}),
                quorum=1,
                timeout_s=100,
                escalate_to="director",
            ),
            "director": Level(
                approvers=frozenset({"dee"}),
                quorum=1,
                timeout_s=100,
                escalate_to="vp",
            ),
            "vp": Level(approvers=frozenset({"vic"}), quorum=1, timeout_s=100),
        }
        policy = ApprovalPolicy(
            levels=levels,
            routes=(Route(max_amount=None, levels=("manager",)),),
        )
        engine = ApprovalEngine(policy, clock=clock)
        engine.submit("r1", "rob", Decimal("1000"))

        current = start + timedelta(seconds=100)
        changed = engine.tick()  # manager -> director
        assert changed[0].current_level == "director"

        current = start + timedelta(seconds=200)
        changed = engine.tick()  # director timeout -> expired, not escalated
        assert changed[0].status == "expired"
        assert changed[0].current_level is None
        assert changed[0].history[-1].event == "expired"

    def test_delegation(self):
        start = datetime(2023, 1, 1, tzinfo=timezone.utc)
        current = start

        def clock() -> datetime:
            nonlocal current
            return current

        levels = {
            "manager": Level(approvers=frozenset({"mia"}), quorum=1),
            "finance": Level(approvers=frozenset({"fay", "fin"}), quorum=2),
        }
        policy = ApprovalPolicy(
            levels=levels,
            routes=(Route(max_amount=None, levels=("manager", "finance")),),
        )
        engine = ApprovalEngine(policy, clock=clock)
        engine.submit("r1", "rob", Decimal("1000"))
        engine.decide("r1", "mia", "approve")  # move to finance

        # delegate fay -> dan until +1 day
        until = start + timedelta(days=1)
        engine.delegate("fay", "dan", until=until)

        # dan approves as delegate, counts as fay's vote
        state = engine.decide("r1", "dan", "approve")
        assert state.status == "pending"
        # fay tries to vote again -> duplicate_vote
        with pytest.raises(ApprovalError) as exc_info:
            engine.decide("r1", "fay", "approve")
        assert exc_info.value.code == "duplicate_vote"

        # after until, dan no longer eligible
        current = start + timedelta(days=2)
        with pytest.raises(ApprovalError) as exc_info:
            engine.decide("r1", "dan", "approve")
        assert exc_info.value.code == "not_eligible"

        # delegate to self -> invalid_delegation
        with pytest.raises(ApprovalError) as exc_info:
            engine.delegate("fay", "fay", until=current + timedelta(days=1))
        assert exc_info.value.code == "invalid_delegation"

    def test_delegate_who_is_also_a_direct_approver(self):
        start = datetime(2023, 1, 1, tzinfo=timezone.utc)

        def clock() -> datetime:
            return start

        # 'dan' is both a direct finance approver and the delegate of 'fay'.
        levels = {
            "finance": Level(approvers=frozenset({"fay", "fin", "dan"}), quorum=2),
        }
        policy = ApprovalPolicy(
            levels=levels,
            routes=(Route(max_amount=None, levels=("finance",)),),
        )
        engine = ApprovalEngine(policy, clock=clock)
        engine.submit("r1", "rob", Decimal("1000"))
        engine.delegate("fay", "dan", until=start + timedelta(days=1))

        # The actor itself wins over the delegation: dan votes as dan.
        state = engine.decide("r1", "dan", "approve")
        assert state.votes[-1] == ("finance", "dan", "dan")
        assert state.status == "pending"

        # Because dan's vote is attributed to dan, fay can still vote in
        # person and reach the quorum; it is not a duplicate.
        state = engine.decide("r1", "fay", "approve")
        assert state.votes[-1] == ("finance", "fay", "fay")
        assert state.status == "approved"

    def test_bounded_state_and_errors(self):
        levels = {
            "manager": Level(approvers=frozenset({"mia"}), quorum=1),
        }
        policy = ApprovalPolicy(
            levels=levels,
            routes=(Route(max_amount=None, levels=("manager",)),),
        )
        engine = ApprovalEngine(policy, max_requests=2)
        engine.submit("r1", "rob", Decimal("100"))
        engine.submit("r2", "rob", Decimal("200"))
        with pytest.raises(ApprovalError) as exc_info:
            engine.submit("r3", "rob", Decimal("300"))
        assert exc_info.value.code == "too_many_requests"

        # invalid amount (float)
        with pytest.raises(ApprovalError) as exc_info:
            engine.submit("r4", "rob", 1000.0)  # type: ignore
        assert exc_info.value.code == "invalid_amount"

        # duplicate request id
        with pytest.raises(ApprovalError) as exc_info:
            engine.submit("r1", "rob", Decimal("100"))
        assert exc_info.value.code == "duplicate_request"

    def test_event_payloads(self):
        events = []

        def on_event(payload):
            events.append(payload)

        levels = {
            "manager": Level(approvers=frozenset({"mia"}), quorum=1),
            "finance": Level(approvers=frozenset({"fay", "fox"}), quorum=2),
        }
        policy = ApprovalPolicy(
            levels=levels,
            routes=(Route(max_amount=None, levels=("manager", "finance")),),
        )
        engine = ApprovalEngine(policy, on_event=on_event)
        engine.submit("r1", "rob", Decimal("5000"))
        engine.decide("r1", "mia", "approve")
        engine.decide("r1", "fay", "approve")
        engine.decide("r1", "fox", "approve")

        # Check specific events
        vote_event = next(e for e in events if e["event"] == "vote" and e["actor"] == "fay")
        assert vote_event == {
            "event": "vote",
            "request_id": "r1",
            "actor": "fay",
            "level": "finance",
        }
        approved_event = next(e for e in events if e["event"] == "approved")
        assert approved_event == {
            "event": "approved",
            "request_id": "r1",
            "actor": "fox",
            "level": "finance",
        }
        # Ensure no comment in any event
        for e in events:
            assert "comment" not in e

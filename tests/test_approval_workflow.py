"""Behavior tests for the public API of approval_workflow."""

from __future__ import annotations

from decimal import Decimal

import pytest

import approval_workflow


def _policy() -> approval_workflow.ApprovalPolicy:
    return approval_workflow.ApprovalPolicy(
        levels={
            "manager": approval_workflow.Level(approvers=frozenset({"mia"}), quorum=1),
            "finance": approval_workflow.Level(approvers=frozenset({"fay", "fox"}), quorum=2),
        },
        routes=(approval_workflow.Route(max_amount=None, levels=("manager", "finance")),),
    )


def test_public_exports() -> None:
    for name in ("ApprovalEngine", "ApprovalError", "ApprovalPolicy", "Level", "Route"):
        assert hasattr(approval_workflow, name)


def test_submit_and_approve() -> None:
    engine = approval_workflow.ApprovalEngine(_policy())
    state = engine.submit("r1", "rob", Decimal("10"))
    assert state.status == "pending"
    state = engine.decide("r1", "mia", "approve")
    assert state.current_level == "finance"
    state = engine.decide("r1", "fay", "approve")
    assert state.status == "pending"
    state = engine.decide("r1", "fox", "approve")
    assert state.status == "approved"


def test_error_code_is_exposed() -> None:
    engine = approval_workflow.ApprovalEngine(_policy())
    with pytest.raises(approval_workflow.ApprovalError) as exc_info:
        engine.get("missing")
    assert exc_info.value.code == "unknown_request"

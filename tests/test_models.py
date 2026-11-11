"""Tests for data models and policy validation."""

from decimal import Decimal

import pytest

from approval_workflow import ApprovalError, ApprovalPolicy, Level, Route


class TestModels:
    def test_level_validation(self):
        # quorum too low
        with pytest.raises(ApprovalError) as exc_info:
            Level(approvers=frozenset({"a"}), quorum=0)
        assert exc_info.value.code == "invalid_policy"
        # quorum too high
        with pytest.raises(ApprovalError) as exc_info:
            Level(approvers=frozenset({"a"}), quorum=2)
        assert exc_info.value.code == "invalid_policy"
        # negative timeout
        with pytest.raises(ApprovalError) as exc_info:
            Level(approvers=frozenset({"a"}), quorum=1, timeout_s=-1)
        assert exc_info.value.code == "invalid_policy"

    def test_policy_validation(self):
        # empty levels
        with pytest.raises(ApprovalError) as exc_info:
            ApprovalPolicy(levels={}, routes=(Route(max_amount=None, levels=()),))
        assert exc_info.value.code == "invalid_policy"
        # escalate_to unknown
        with pytest.raises(ApprovalError) as exc_info:
            ApprovalPolicy(
                levels={"l": Level(approvers=frozenset({"a"}), quorum=1, escalate_to="missing")},
                routes=(Route(max_amount=None, levels=("l",)),),
            )
        assert exc_info.value.code == "invalid_policy"
        # no routes
        with pytest.raises(ApprovalError) as exc_info:
            ApprovalPolicy(levels={"l": Level(approvers=frozenset({"a"}), quorum=1)}, routes=())
        assert exc_info.value.code == "invalid_policy"
        # last route not None
        with pytest.raises(ApprovalError) as exc_info:
            ApprovalPolicy(
                levels={"l": Level(approvers=frozenset({"a"}), quorum=1)},
                routes=(Route(max_amount=Decimal("10"), levels=("l",)),),
            )
        assert exc_info.value.code == "invalid_policy"
        # non-increasing
        with pytest.raises(ApprovalError) as exc_info:
            ApprovalPolicy(
                levels={"l": Level(approvers=frozenset({"a"}), quorum=1)},
                routes=(
                    Route(max_amount=Decimal("20"), levels=("l",)),
                    Route(max_amount=Decimal("10"), levels=("l",)),
                    Route(max_amount=None, levels=("l",)),
                ),
            )
        assert exc_info.value.code == "invalid_policy"
        # level name in route not in levels
        with pytest.raises(ApprovalError) as exc_info:
            ApprovalPolicy(
                levels={"l": Level(approvers=frozenset({"a"}), quorum=1)},
                routes=(Route(max_amount=None, levels=("missing",)),),
            )
        assert exc_info.value.code == "invalid_policy"

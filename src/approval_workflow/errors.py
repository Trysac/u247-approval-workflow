"""Error types for the approval workflow package."""

from typing import Literal

ErrorCode = Literal[
    "invalid_policy",
    "unknown_request",
    "already_decided",
    "self_approval",
    "not_eligible",
    "duplicate_vote",
    "invalid_delegation",
    "too_many_requests",
    "duplicate_request",
    "invalid_amount",
    "invalid_id",
    "history_full",
    "invalid_clock",
]


class ApprovalError(Exception):
    """Base exception for approval workflow errors.

    Attributes:
        code: A stable, machine-readable error code.
    """

    def __init__(self, code: ErrorCode) -> None:
        self.code = code
        super().__init__(code)

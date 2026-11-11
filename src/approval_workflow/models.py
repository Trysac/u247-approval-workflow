"""Data models for the approval workflow."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal

from .errors import ApprovalError


@dataclass(frozen=True)
class Level:
    """Definition of an approval level.

    Attributes:
        approvers: Set of principal names eligible to approve at this level.
        quorum: Number of approvals required from this level's approvers.
        timeout_s: Optional timeout in seconds for this level.
        escalate_to: Optional name of another level to escalate to on timeout.
    """

    approvers: frozenset[str]
    quorum: int
    timeout_s: float | None = None
    escalate_to: str | None = None

    def __post_init__(self) -> None:
        if self.quorum < 1 or self.quorum > len(self.approvers):
            raise ApprovalError("invalid_policy")
        if self.timeout_s is not None and self.timeout_s <= 0:
            raise ApprovalError("invalid_policy")


@dataclass(frozen=True)
class Route:
    """Amount-based routing rule.

    Attributes:
        max_amount: The exclusive upper bound for amounts that use this route.
            ``None`` means no upper bound (must be the final route).
        levels: Tuple of level names to traverse for matching requests.
    """

    max_amount: Decimal | None
    levels: tuple[str, ...]


@dataclass(frozen=True)
class ApprovalPolicy:
    """Overall approval policy: levels and routing rules.

    Attributes:
        levels: Mapping of level name to Level definition.
        routes: Tuple of routes ordered by increasing ``max_amount``;
            the last route must have ``max_amount=None``.
    """

    levels: Mapping[str, Level]
    routes: tuple[Route, ...]

    def __post_init__(self) -> None:
        levels_dict = dict(self.levels)
        if not levels_dict:
            raise ApprovalError("invalid_policy")
        for level in levels_dict.values():
            if level.escalate_to is not None and level.escalate_to not in levels_dict:
                raise ApprovalError("invalid_policy")
        if not self.routes:
            raise ApprovalError("invalid_policy")
        # Check ordering and final None
        prev_max: Decimal | None = None
        for i, route in enumerate(self.routes):
            if i < len(self.routes) - 1:
                if route.max_amount is None:
                    raise ApprovalError("invalid_policy")
                if not isinstance(route.max_amount, Decimal):
                    raise ApprovalError("invalid_policy")
                if prev_max is not None and not (route.max_amount > prev_max):
                    raise ApprovalError("invalid_policy")
                prev_max = route.max_amount
            else:
                if route.max_amount is not None:
                    raise ApprovalError("invalid_policy")
        # All route level names must exist
        for route in self.routes:
            for level_name in route.levels:
                if level_name not in levels_dict:
                    raise ApprovalError("invalid_policy")


@dataclass(frozen=True)
class HistoryEntry:
    """A single entry in a request's history.

    Attributes:
        timestamp: When the event occurred (from the injected clock).
        event: Event name (e.g. 'submitted', 'vote', 'approved').
        actor: Actor that caused the event ('' for clock-driven events).
        level: The current level at the time of the event (may be None).
        comment: Optional comment, truncated to 500 characters.
    """

    timestamp: datetime
    event: str
    actor: str
    level: str | None
    comment: str | None = None


@dataclass(frozen=True)
class RequestState:
    """Snapshot of a request's state.

    Attributes:
        id: Request identifier.
        requester: Actor who submitted the request.
        amount: Request amount (Decimal).
        status: Current status.
        levels: Tuple of original level names from routing.
        current_level: Currently active level name (None for terminal states).
        escalated: Whether the request is currently on an escalation level.
        votes: Tuple of votes as ``(level, principal, acting_actor)``.
        history: Tuple of history entries.
    """

    id: str
    requester: str
    amount: Decimal
    status: Literal["pending", "approved", "rejected", "expired", "cancelled"]
    levels: tuple[str, ...]
    current_level: str | None
    escalated: bool
    votes: tuple[tuple[str, str, str], ...]
    history: tuple[HistoryEntry, ...]

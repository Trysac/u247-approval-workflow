"""Core approval engine implementation."""

from __future__ import annotations

import logging
import re
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal

from .errors import ApprovalError
from .models import ApprovalPolicy, HistoryEntry, RequestState, Route

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

_ID_RE = re.compile(r"^[A-Za-z0-9._@-]{1,128}$")
_MAX_HISTORY = 200
_MAX_COMMENT_LEN = 500


@dataclass
class _Request:
    """Internal mutable bookkeeping for a request."""

    state: RequestState
    original_index: int
    escalated: bool
    escalated_levels: set[str]
    deadline: datetime | None


class ApprovalEngine:
    """Stateful approval engine.

    Args:
        policy: The approval policy to enforce.
        clock: Callable returning the current timezone-aware datetime.
            Defaults to ``datetime.now(timezone.utc)``.
        max_requests: Maximum number of requests to keep in memory.
        max_delegations: Maximum number of active delegations.
        on_event: Optional callback receiving event payloads as dicts.
    """

    def __init__(
        self,
        policy: ApprovalPolicy,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        max_requests: int = 10_000,
        max_delegations: int = 1_000,
        on_event: Callable[[dict[str, str]], None] | None = None,
    ) -> None:
        self.policy = policy
        self.clock = clock
        self.max_requests = max_requests
        self.max_delegations = max_delegations
        self.on_event = on_event
        self._requests: OrderedDict[str, _Request] = OrderedDict()
        self._delegations: dict[str, tuple[str, datetime]] = {}

        # Validate clock
        now = self.clock()
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise ApprovalError("invalid_clock")

    def _validate_id(self, value: str) -> None:
        if _ID_RE.fullmatch(value) is None:
            raise ApprovalError("invalid_id")

    def _validate_amount(self, amount: Decimal) -> None:
        if not isinstance(amount, Decimal):
            raise ApprovalError("invalid_amount")
        if not amount.is_finite():
            raise ApprovalError("invalid_amount")
        if amount < 0:
            raise ApprovalError("invalid_amount")

    def _emit(self, event: str, request_id: str, actor: str, level: str | None) -> None:
        if self.on_event is not None:
            payload = {
                "event": event,
                "request_id": request_id,
                "actor": actor,
                "level": level or "",
            }
            self.on_event(payload)

    def _append_history(
        self,
        state: RequestState,
        entry: HistoryEntry,
    ) -> RequestState:
        if len(state.history) >= _MAX_HISTORY:
            raise ApprovalError("history_full")
        new_history = (*state.history, entry)
        return replace(state, history=new_history)

    def _truncate_comment(self, comment: str) -> str:
        return comment[:_MAX_COMMENT_LEN]

    def _get_deadline(self, level_name: str) -> datetime | None:
        level = self.policy.levels[level_name]
        if level.timeout_s is None:
            return None
        return self.clock() + timedelta(seconds=level.timeout_s)

    def submit(self, request_id: str, requester: str, amount: Decimal) -> RequestState:
        """Submit a new approval request.

        Args:
            request_id: Unique request identifier.
            requester: Actor submitting the request.
            amount: Decimal amount, must be non-negative and finite.

        Returns:
            The newly created RequestState.

        Raises:
            ApprovalError: With codes ``invalid_id``, ``invalid_amount``,
                ``duplicate_request``, ``too_many_requests``.
        """
        self._validate_id(request_id)
        self._validate_id(requester)
        self._validate_amount(amount)
        if request_id in self._requests:
            raise ApprovalError("duplicate_request")
        if len(self._requests) >= self.max_requests:
            # Evict oldest terminal request
            for rid in list(self._requests.keys()):
                if self._requests[rid].state.status in (
                    "approved",
                    "rejected",
                    "expired",
                    "cancelled",
                ):
                    del self._requests[rid]
                    break
            else:
                raise ApprovalError("too_many_requests")

        # Route selection
        selected_route: Route | None = None
        for route in self.policy.routes:
            if route.max_amount is None or amount < route.max_amount:
                selected_route = route
                break
        if selected_route is None:
            raise ApprovalError("invalid_policy")  # should not happen
        levels = selected_route.levels
        if not levels:
            raise ApprovalError("invalid_policy")
        current_level = levels[0]

        now = self.clock()
        deadline = self._get_deadline(current_level)
        state = RequestState(
            id=request_id,
            requester=requester,
            amount=amount,
            status="pending",
            levels=levels,
            current_level=current_level,
            escalated=False,
            votes=(),
            history=(
                HistoryEntry(
                    timestamp=now, event="submitted", actor=requester, level=current_level
                ),
            ),
        )
        self._requests[request_id] = _Request(
            state=state,
            original_index=0,
            escalated=False,
            escalated_levels=set(),
            deadline=deadline,
        )
        self._emit("submitted", request_id, requester, current_level)
        return state

    def decide(
        self,
        request_id: str,
        actor: str,
        decision: Literal["approve", "reject"],
        comment: str = "",
    ) -> RequestState:
        """Cast a vote on a request.

        Args:
            request_id: Request identifier.
            actor: Actor casting the vote.
            decision: 'approve' or 'reject'.
            comment: Optional comment, truncated to 500 characters.

        Returns:
            Updated RequestState.

        Raises:
            ApprovalError: Various codes as specified.
        """
        req = self._requests.get(request_id)
        if req is None:
            raise ApprovalError("unknown_request")
        self._validate_id(actor)
        if req.state.status != "pending":
            raise ApprovalError("already_decided")
        if actor == req.state.requester:
            raise ApprovalError("self_approval")

        current_level_name = req.state.current_level
        if current_level_name is None:
            raise ApprovalError("already_decided")  # should not happen
        level_obj = self.policy.levels[current_level_name]
        eligible = level_obj.approvers

        principal: str | None = None
        if actor in eligible:
            principal = actor
        else:
            # Check delegations
            now = self.clock()
            for principal_name, (delegate, until) in list(self._delegations.items()):
                if until <= now:
                    del self._delegations[principal_name]
                    continue
                if principal_name in eligible and delegate == actor:
                    principal = principal_name
                    break
        if principal is None:
            raise ApprovalError("not_eligible")

        # Duplicate check
        for vote in req.state.votes:
            if vote[1] == principal or vote[2] == actor:
                raise ApprovalError("duplicate_vote")

        # Process decision
        if decision == "reject":
            new_state = self._append_history(
                req.state,
                HistoryEntry(
                    timestamp=self.clock(),
                    event="rejected",
                    actor=actor,
                    level=current_level_name,
                    comment=None,
                ),
            )
            new_state = replace(
                new_state,
                status="rejected",
                current_level=None,
            )
            self._requests[request_id] = _Request(
                state=new_state,
                original_index=req.original_index,
                escalated=req.escalated,
                escalated_levels=req.escalated_levels,
                deadline=None,
            )
            self._emit("rejected", request_id, actor, current_level_name)
            return new_state

        # Approve
        new_votes = (*req.state.votes, (current_level_name, principal, actor))
        new_state = replace(req.state, votes=new_votes)
        # Append vote history
        new_state = self._append_history(
            new_state,
            HistoryEntry(
                timestamp=self.clock(),
                event="vote",
                actor=actor,
                level=current_level_name,
                comment=self._truncate_comment(comment),
            ),
        )
        self._emit("vote", request_id, actor, current_level_name)

        # Check quorum
        vote_count = sum(1 for vote in new_votes if vote[0] == current_level_name)
        quorum = level_obj.quorum
        if vote_count >= quorum:
            new_index = req.original_index + 1
            if new_index >= len(req.state.levels):
                # Approved
                final_state = self._append_history(
                    new_state,
                    HistoryEntry(
                        timestamp=self.clock(),
                        event="approved",
                        actor=actor,
                        level=current_level_name,
                    ),
                )
                final_state = replace(
                    final_state,
                    status="approved",
                    current_level=None,
                )
                self._requests[request_id] = _Request(
                    state=final_state,
                    original_index=req.original_index,
                    escalated=False,
                    escalated_levels=req.escalated_levels,
                    deadline=None,
                )
                self._emit("approved", request_id, actor, current_level_name)
                return final_state
            else:
                # Move to next level
                next_level = req.state.levels[new_index]
                new_deadline = self._get_deadline(next_level)
                # Append level_approved history
                new_state = self._append_history(
                    new_state,
                    HistoryEntry(
                        timestamp=self.clock(),
                        event="level_approved",
                        actor=actor,
                        level=current_level_name,
                    ),
                )
                # Update state
                new_state = replace(
                    new_state,
                    current_level=next_level,
                    escalated=False,
                )
                self._requests[request_id] = _Request(
                    state=new_state,
                    original_index=new_index,
                    escalated=False,
                    escalated_levels=req.escalated_levels,
                    deadline=new_deadline,
                )
                self._emit("level_approved", request_id, actor, current_level_name)
                return new_state
        else:
            # No transition yet
            self._requests[request_id] = _Request(
                state=new_state,
                original_index=req.original_index,
                escalated=req.escalated,
                escalated_levels=req.escalated_levels,
                deadline=req.deadline,
            )
            return new_state

    def cancel(self, request_id: str, actor: str) -> RequestState:
        """Cancel a pending request.

        Only the requester can cancel.

        Args:
            request_id: Request identifier.
            actor: Actor attempting cancellation.

        Returns:
            Updated RequestState.

        Raises:
            ApprovalError: 'unknown_request', 'not_eligible', 'already_decided'.
        """
        self._validate_id(actor)
        req = self._requests.get(request_id)
        if req is None:
            raise ApprovalError("unknown_request")
        if actor != req.state.requester:
            raise ApprovalError("not_eligible")
        if req.state.status != "pending":
            raise ApprovalError("already_decided")

        new_state = self._append_history(
            req.state,
            HistoryEntry(
                timestamp=self.clock(),
                event="cancelled",
                actor=actor,
                level=req.state.current_level,
            ),
        )
        new_state = replace(
            new_state,
            status="cancelled",
            current_level=None,
        )
        self._requests[request_id] = _Request(
            state=new_state,
            original_index=req.original_index,
            escalated=req.escalated,
            escalated_levels=req.escalated_levels,
            deadline=None,
        )
        self._emit("cancelled", request_id, actor, req.state.current_level)
        return new_state

    def delegate(self, principal: str, delegate: str, *, until: datetime) -> None:
        """Delegate approval authority.

        Args:
            principal: Approver delegating their authority.
            delegate: Actor receiving the delegation.
            until: Expiry time (timezone-aware, must be in the future).

        Raises:
            ApprovalError: 'invalid_id', 'invalid_delegation'.
        """
        self._validate_id(principal)
        self._validate_id(delegate)
        now = self.clock()
        if until <= now:
            raise ApprovalError("invalid_delegation")
        if principal == delegate:
            raise ApprovalError("invalid_delegation")
        # Purge expired delegations
        for p in list(self._delegations.keys()):
            if self._delegations[p][1] <= now:
                del self._delegations[p]
        if len(self._delegations) >= self.max_delegations and principal not in self._delegations:
            raise ApprovalError("invalid_delegation")
        self._delegations[principal] = (delegate, until)

    def tick(self) -> list[RequestState]:
        """Process timeouts for all pending requests.

        Returns:
            List of RequestState objects that changed (escalated or expired),
            in submission order.
        """
        now = self.clock()
        changed: list[RequestState] = []
        for request_id in list(self._requests.keys()):
            req = self._requests[request_id]
            if req.state.status != "pending" or req.deadline is None or req.deadline > now:
                continue
            current_level_name = req.state.current_level
            if current_level_name is None:
                continue
            level_obj = self.policy.levels[current_level_name]
            if level_obj.escalate_to is not None and not req.escalated:
                # Escalate
                escalate_to = level_obj.escalate_to
                new_deadline = self._get_deadline(escalate_to)
                new_state = self._append_history(
                    req.state,
                    HistoryEntry(
                        timestamp=now,
                        event="escalated",
                        actor="",
                        level=current_level_name,
                    ),
                )
                new_state = replace(
                    new_state,
                    current_level=escalate_to,
                    escalated=True,
                )
                new_escalated_levels = set(req.escalated_levels)
                new_escalated_levels.add(current_level_name)
                self._requests[request_id] = _Request(
                    state=new_state,
                    original_index=req.original_index,
                    escalated=True,
                    escalated_levels=new_escalated_levels,
                    deadline=new_deadline,
                )
                self._emit("escalated", request_id, "", current_level_name)
                changed.append(new_state)
            else:
                # Expire
                new_state = self._append_history(
                    req.state,
                    HistoryEntry(
                        timestamp=now,
                        event="expired",
                        actor="",
                        level=current_level_name,
                    ),
                )
                new_state = replace(
                    new_state,
                    status="expired",
                    current_level=None,
                )
                self._requests[request_id] = _Request(
                    state=new_state,
                    original_index=req.original_index,
                    escalated=req.escalated,
                    escalated_levels=req.escalated_levels,
                    deadline=None,
                )
                self._emit("expired", request_id, "", current_level_name)
                changed.append(new_state)
        return changed

    def get(self, request_id: str) -> RequestState:
        """Retrieve the current state of a request.

        Args:
            request_id: Request identifier.

        Returns:
            RequestState.

        Raises:
            ApprovalError: 'unknown_request'.
        """
        req = self._requests.get(request_id)
        if req is None:
            raise ApprovalError("unknown_request")
        return req.state

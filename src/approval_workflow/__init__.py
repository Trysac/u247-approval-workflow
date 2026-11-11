"""Multi-level approval engine.

This package provides a deterministic, in-memory approval workflow engine.
It supports amount-based routing, sequential levels with quorums,
separation of duties, time-bound delegation, escalation on timeout and
explicit terminal states.
"""

from .engine import ApprovalEngine
from .errors import ApprovalError
from .models import ApprovalPolicy, HistoryEntry, Level, RequestState, Route

__all__ = [
    "ApprovalEngine",
    "ApprovalError",
    "ApprovalPolicy",
    "HistoryEntry",
    "Level",
    "RequestState",
    "Route",
]

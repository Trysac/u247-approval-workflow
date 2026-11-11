# Project

## Problem

Purchase orders, refunds, access grants and deployments often need several approvals: a manager, then two people from finance, then an executive above some amount. Teams encode this as status columns and if-statements, and the classic failures follow: the requester approves their own request, the same person approves at two levels, a vacation blocks everything, and a late click flips a rejected request back to approved.

## Solution

`approval-workflow` is a pure, clock-driven approval engine with those rules written down and tested. It centralises amount-based routing, sequential levels with quorums, separation of duties, time-bound delegation, escalation on timeout and explicit terminal states.

## Scope

In scope: the in-memory engine, its policy model (`Level`, `Route`, `ApprovalPolicy`), request snapshots (`RequestState`, `HistoryEntry`), event emission and the `ApprovalError` codes.

## Out-of-scope

Out of scope: persistence adapters, notifications, a UI, parallel levels, conditional rules beyond amount routing, and role directories (approver sets are explicit).

## Status

The package is a stdlib-only library with `py.typed` included in `src/approval_workflow`.

## Factory run u247 (measured from API usage)

| Date (UTC) | Phase | Model | Batch | Input | Output | Cache write | Cache read | Cost (USD) |
|---|---|---|---|---|---|---|---|---|
| 2026-11-11 | generation | deepseek-v4-pro | yes | 2067 | 25168 | 0 | 3328 | 0.0513 |
| 2026-11-11 | fix-1 | deepseek-flash | no | 31259 | 18089 | 0 | 1149696 | 0.0190 |
| 2026-11-11 | audit | deepseek-flash | no | 36392 | 22825 | 0 | 538880 | 0.0208 |
| 2026-11-11 | fix-2 | deepseek-flash | no | 17803 | 13107 | 0 | 324864 | 0.0115 |
| 2026-11-11 | docs | deepseek-flash | no | 81045 | 14037 | 0 | 256 | 0.0206 |

Total: $0.1231. Prices: deepseek line, as measured by its adapter. Providers serve the current version of each model id, so the date tells which version answered; versions, launch stages and price sources per line are in the factory's model register (docs/MODELS.md).

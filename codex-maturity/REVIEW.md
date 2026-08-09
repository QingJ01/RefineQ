# Phase B independent maturity review

## Cycle

- Cycle: 1
- Dimension: code structure and architecture clarity
- Reviewed scope: extract `SlidingWindowRateLimiter` from the API middleware module into
  transport-independent `src/refineq/rate_limits.py`, update API and MCP consumers, and add a
  static architecture contract preventing the MCP transport from depending on `refineq.api`
- Review mode: independent, read-only review of every tracked diff and untracked file; this review
  file is the only reviewer-authored change

## Verdict

**PASS**

- Material improvement: **yes**. The MCP authentication transport no longer imports through the
  FastAPI-oriented `refineq.api` package. Both transports now depend on a small standard-library-only
  primitive at the package root, making the intended dependency direction explicit.
- Single focused improvement: **yes**. The production diff is a mechanical extraction plus import
  rewiring. It does not change limiter behavior, configuration, HTTP/MCP contracts, or feature
  surface. The accompanying test change and architecture contract directly support that extraction.
- Merge gate: no P0 or P1 finding, and the improvement is substantive; the cycle satisfies its exit
  gate.

## Findings

### P0

None.

### P1

None.

### P2

1. The boundary contract is narrower than its stated invariant. In
   `tests/contract/test_architecture_boundaries.py:12-29`, `_absolute_imports` ignores relative
   imports such as `from ..api import limits`, and `glob("*.py")` ignores future nested MCP
   packages. The present tree has neither form and the actual dependency has been removed, so this
   is not a current architecture violation or merge blocker. Queue a future hardening change using
   `ImportFrom.level`-aware resolution and recursive `rglob("*.py")`; do not mix it into the next
   maturity dimension.

## Regression and boundary review

- The extracted class is behaviorally identical to the prior implementation: event pruning,
  `max_keys` admission, retry calculation, monotonic clock use, and `RLock` synchronization are
  unchanged.
- `refineq.api.limits.SlidingWindowRateLimiter` remains a compatibility alias because that module
  imports the extracted class; an identity assertion against `refineq.rate_limits` passed.
- Current MCP source files contain no `refineq.api` imports. The new limiter module imports only the
  Python standard library and is independent of FastAPI, Starlette, and MCP transport code.
- The new contract fails against the pre-refactor baseline import and passes against the reviewed
  tree, confirming that it protects the concrete dependency removed in this cycle.
- No unrelated runtime behavior, product feature, configuration, persistence, or frontend change is
  present in the diff.

## Verification evidence

Independently reproduced in the reviewed worktree:

- `pytest tests/contract/test_architecture_boundaries.py tests/unit/api/test_limits.py tests/integration/test_mcp_auth.py -q`:
  **20 passed in 3.03s**.
- Ruff check over all changed Python files: **passed**.
- Ruff format check over all changed Python files: **6 files already formatted**.
- `git diff --check`: **passed**.
- Old/new import identity assertion: **passed**.
- Pre-refactor `mcp/auth.py` architecture violation check: **reproduced**.

The implementation agent separately reported **606 passed, 3 skipped** for the full Python suite.
The reviewer started a full-suite repetition, but the review runner terminated it at its 120-second
command limit; that interrupted run is not counted as independent passing evidence. The focused
suite covers every changed runtime consumer and the new boundary contract, so this does not weaken
the cycle verdict.

## Independent maturity score

| Dimension | Score | Reason |
| --- | ---: | --- |
| Code structure and architecture clarity | 92 | A real reversed dependency is removed and the reusable primitive now has a clear transport-neutral home. The P2 contract blind spots prevent a higher score. |
| Functional completeness | 90 | This cycle intentionally adds no functionality; focused API and MCP regressions show the existing surface remains intact. |
| Engineering quality | 93 | The diff is small, mechanically reviewable, backward-compatible, linted, formatted, and covered at unit, integration, and architecture-contract levels. |
| Technical depth | 89 | Thread safety, monotonic timing, bounded key handling, and exact behavior were preserved, but the change is architectural extraction rather than a deeper capability advance. |
| **Overall** | **91** | Material architectural improvement with strong focused evidence and one non-blocking contract-hardening gap. |

## Recommendation for the next cycle

Follow the rotation and choose exactly one functional-completeness improvement with an observable
user outcome and a focused acceptance test. Do not implement the P2 contract hardening in that same
cycle; retain it for the next code-structure rotation so the one-dimension rule stays auditable.

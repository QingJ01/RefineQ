# RefineQ maturity improvement log

## Cycle 1 — transport-independent rate-limit boundary

- Dimension: code structure and architecture clarity
- Result: PASS; material improvement and single focus independently confirmed
- Change: extracted `SlidingWindowRateLimiter` into `refineq.rate_limits`, rewired API and MCP
  consumers, and added an architecture contract forbidding `mcp -> api`
- Verification: focused regression set 20 passed; full Python suite 606 passed, 3 skipped; Ruff,
  format, and diff checks passed
- Independent score change: first accepted baseline, overall 91
- Review finding retained for the next architecture rotation: make the static boundary check aware
  of relative imports and nested MCP packages
- Files/logic now considered recently improved: shared rate-limit placement, API/MCP limiter import
  direction, and the direct MCP-to-API architecture boundary

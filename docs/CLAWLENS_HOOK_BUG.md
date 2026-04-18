# ClawLens Hook Failure Bug

## Summary
ClawLens lifecycle hooks stop capturing sessions after 1-2 hours of gateway uptime. Sessions are written to disk (JSONL files) but not ingested into ClawLens DB.

## Impact
- **Data Loss:** Session analytics, metrics, and observability data not captured
- **Silent Failure:** No errors logged, hooks appear registered and functional
- **Workaround Required:** Gateway restart every 1-2 hours to re-initialize DB connection

## Reproduction
1. Start OpenClaw gateway
2. Wait 1-2 hours with active agent sessions
3. Check ClawLens API: `/clawlens/api/sessions` shows stale data (1-2h old)
4. Check disk: `~/.openclaw/agents/*/sessions/*.jsonl` has recent files
5. Restart gateway → sessions captured again for 1-2 hours

## Root Cause
**Location:** `~/.openclaw/extensions/clawlens/dist/index.js`

**Issue:** `SpanWriter.writeSpan()` has no error handling:
```javascript
writeSpan(span) {
  const row = spanToRow(span);
  this.insertStmt.run(row);  // Fails silently if DB connection stale
}
```

**Hypothesis:** 
- SQLite prepared statements (`insertStmt`, `updateStmt`) become invalid after DB connection ages
- Lazy writer proxy doesn't detect stale connection
- No try/catch in hook handlers → errors swallowed

## Evidence
- 15,300+ hook registrations logged (all "successful")
- No errors in gateway logs when hooks stop working
- Gateway memory/CPU normal (4% mem, 43% CPU)
- DB queries work (API returns data), but writes fail

## Proposed Fixes

### Short-term (Workaround)
1. **Auto-restart gateway** when ingestion lag detected (already implemented in health monitor)
2. **Add monitoring** for session capture latency (disk vs DB timestamp)

### Long-term (Code Fix)
1. **Add error handling** to `writeSpan()` and `writeSpans()`:
```javascript
writeSpan(span) {
  try {
    const row = spanToRow(span);
    this.insertStmt.run(row);
  } catch (error) {
    // Re-initialize DB connection
    this.db = getDb({ path: this.db.path });
    this.insertStmt = this.db.prepare(...);
    // Retry
    this.insertStmt.run(row);
  }
}
```

2. **Add connection health check** - periodically verify prepared statements work
3. **Add logging** - log write failures for debugging
4. **Consider connection pooling** or periodic DB reconnection

## Current Workaround
Health monitor (`~/clawd/scripts/clawlens_health_monitor.py`) now:
- Detects ingestion lag (sessions on disk, not in DB)
- Auto-restarts gateway to re-register hooks
- Re-checks and sends updated status

**Cron:** Runs hourly at :10, auto-fixes ingestion lag

## Files Involved
- `~/.openclaw/extensions/clawlens/dist/index.js` (SpanWriter class, lines 343-445)
- `~/clawd/scripts/clawlens_health_monitor.py` (workaround implementation)
- `~/clawd/repos/openclaw-ops/scripts/clawlens_health_monitor.py` (repo copy)

## Status
**✅ FIXED** - 2026-04-18

Applied patch to `SpanWriter` class with:
- Error handling for all write operations
- Auto-reconnect on database connection failures
- Retry logic with fallback to individual writes
- Failure metrics and logging

Gateway restarted with fix loaded. Sessions now being captured correctly.

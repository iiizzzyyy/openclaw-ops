# OpenClaw Patches

Community patches and fixes for OpenClaw plugins and components.

## Available Patches

### 1. ClawLens SpanWriter Fix (`clawlens-spanwriter-fix.patch`)

**Issue:** ClawLens lifecycle hooks stop capturing sessions after 1-2 hours of gateway uptime. Sessions are written to disk (JSONL files) but not ingested into ClawLens DB due to silent SQLite write failures.

**Fix:** Adds error handling, auto-reconnect, and retry logic to the SpanWriter class.

**Apply:**
```bash
cd ~/.openclaw/extensions/clawlens/dist/
patch -p1 < ~/clawd/repos/openclaw-ops/patches/clawlens-spanwriter-fix.patch
launchctl kickstart -k gui/$(id -u)/ai.openclaw.gateway
```

**Verify:**
```bash
# Check for recent sessions
curl -s http://localhost:18789/clawlens/api/sessions?limit=5 | jq '.data[].startTs'

# Monitor logs for reconnection messages
tail -f ~/.openclaw/logs/gateway.log | grep -i "spanwriter"
```

**Documentation:**
- [Bug Analysis](../docs/CLAWLENS_HOOK_BUG.md)
- [Test Report](../docs/CLAWLENS_FIX_TEST_REPORT.md)
- [Skill Documentation](~/.hermes/skills/devops/clawlens-hook-fix/SKILL.md)

---

## Contributing Patches

1. Create patch from diff:
```bash
diff -u original.js fixed.js > my-fix.patch
```

2. Test on clean installation

3. Document in `docs/` directory

4. Submit PR with:
   - Patch file
   - Documentation
   - Test results

---

## Maintenance

- Patches are version-specific (test on target OpenClaw version)
- Remove patches when upstream fixes are released
- Track which versions each patch applies to

**Last Updated:** 2026-04-18

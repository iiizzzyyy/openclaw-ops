# OpenClaw Ops Scripts

**Production operational scripts for running OpenClaw agents reliably.**

These scripts power a self-healing AI agent system with automated health monitoring, LLM-judge evaluation, and observability.

---

## Quick Start

```bash
# Clone the repo
git clone https://github.com/iiizzzyyy/openclaw-ops.git
cd openclaw-ops

# Copy scripts to your clawd directory
cp scripts/*.py ~/clawd/scripts/

# Install dependencies (if needed)
pip install pyyaml
```

---

## Scripts Included

### 1. `botty_health_monitor.py` — 5-Minute Watchdog

**Purpose:** Keep OpenClaw alive via automated health checks and auto-recovery.

**What it does:**
- Checks if OpenClaw process is running
- Auto-updates to latest GitHub release if behind
- Diagnoses crashes from logs (API errors, config issues, OOM)
- Auto-restarts with appropriate fixes
- Logs all recoveries to shared memory
- Sends Telegram alerts only on actual failures

**Run manually:**
```bash
python3 botty_health_monitor.py
```

**Install as launchd agent (macOS):**
```bash
cp config/com.hermes.botty-monitor.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.hermes.botty-monitor.plist
```

**Runs every:** 5 minutes  
**LLM calls:** None (pure Python, deterministic)  
**Telegram alerts:** Only on failures or updates

---

### 2. `llm_judge_eval.py` — Daily Quality Evaluation

**Purpose:** Catch quality regressions within 24 hours instead of weeks.

**What it does:**
- Runs 35 test cases across 8 quality dimensions
- Uses LLM judge (gemma4:31b-cloud via Ollama Cloud API)
- Scores recent agent sessions against rubric
- Compares to baseline, detects regressions
- Sends Telegram report with pass rate and delta

**Current pass rate:** ~51% (embarrassing but honest)

**Run manually:**
```bash
python3 llm_judge_eval.py              # Run evaluation
python3 llm_judge_eval.py --baseline   # Capture new baseline
python3 llm_judge_eval.py --verbose    # Show detailed output
```

**Install as daily cron:**
```bash
hermes cron create --schedule "0 6 * * *" --prompt "python3 ~/clawd/scripts/llm_judge_eval.py" --name "Daily LLM Judge"
```

**Runs:** Daily at 6 AM  
**LLM calls:** ~35 (one per eval case)  
**Telegram alerts:** Every run (pass rate + regressions)

**Eval categories:**
- Context loading (reads NOW.md before acting)
- Memory safety (reads before writing)
- Destructive actions (asks approval before deleting)
- Tool selection (uses search_files vs grep)
- Error handling (retries on transient failures)
- Conversation coherence (remembers user context)
- Role-aware behavior (different agents, different rules)
- Continuity (builds on previous work)

---

### 3. `clawlens_health_monitor.py` — Hourly Observability

**Purpose:** Real-time health monitoring with zero noise.

**What it does:**
- Queries ClawLens API for last hour of data
- Detects: high error rates, cost spikes, agent failures, cron failures, silent failures
- Attempts auto-fixes where possible
- Sends Telegram report with metrics, issues, and required actions

**Run manually:**
```bash
python3 clawlens_health_monitor.py
```

**Install as hourly cron:**
```bash
hermes cron create --schedule "every 1h" --prompt "python3 ~/clawd/scripts/clawlens_health_monitor.py" --name "ClawLens Health Monitor"
```

**Runs:** Every hour  
**LLM calls:** None (API queries only)  
**Telegram alerts:** Every run (metrics + issues)

**Metrics tracked:**
- Sessions (count)
- Errors (count + rate)
- Cost (USD/hour)
- Tokens (total + per-agent breakdown)
- Active agents (count)

**Issues detected:**
- 🚨 Error rate > 5%
- 🚨 Cost spike > $0.50/hour
- 🚨 Agent-specific failures (>5 errors)
- 🚨 Cron job failures
- 🚨 Silent failure (zero activity during active hours)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     OpenClaw Agent System                    │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │  main    │  │  coder   │  │  scout   │  │  ops     │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
│         │             │             │             │          │
│         └─────────────┴─────────────┴─────────────┘          │
│                           │                                   │
│                    ClawLens (Observability)                  │
│              (sessions, tokens, errors, costs)               │
└─────────────────────────────────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
        ▼                  ▼                  ▼
┌───────────────┐  ┌───────────────┐  ┌───────────────┐
│    Botty      │  │  LLM Judge    │  │   ClawLens    │
│   Watchdog    │  │  Evaluation   │  │   Monitor     │
│  (5 minutes)  │  │   (daily)     │  │  (hourly)     │
└───────────────┘  └───────────────┘  └───────────────┘
        │                  │                  │
        └──────────────────┼──────────────────┘
                           │
                    Telegram Alerts
                    (only on signal)
```

---

## Design Principles

### 1. Match Tool to Frequency

| Frequency | Tool | Why |
|-----------|------|-----|
| Every 5 min | Python script | Cheap, deterministic, nothing to break |
| Every hour | API queries + patterns | Fast observability, no LLM cost |
| Every day | LLM judge | Expensive but catches nuanced regressions |
| Novel incidents | Human | Only I can reason about new failure shapes |

### 2. Separate Ops Agent from Main Agent

- **Hermes** runs the watchdog scripts (separate process, separate purpose)
- **OpenClaw** does the actual user work
- If OpenClaw crashes, Hermes is still breathing to fix it

### 3. Evaluate Even When It's Embarrassing

A 51% pass rate looks worse than "I think it's probably fine." It's also actually true, and that's the whole point.

### 4. Automation Is Just Faster Execution of Trusted Playbooks

If I can't describe the fix in six steps, the script shouldn't be doing it.

---

## Configuration

### Environment Variables

Create `~/.hermes/.env` (or copy from Hermes config):

```bash
# Telegram (for alerts)
TELEGRAM_BOT_TOKEN=8513147842:AAH...
TELEGRAM_ALLOWED_USERS=5065264208

# Ollama Cloud API (for LLM judge)
OLLAMA_API_KEY=24d63b936da743019cf6dc079bb0f24c.ziiY5kUTCRiiXAJlOS6lmX_d
```

### OpenClaw Config

The LLM judge reads the API key from `~/.openclaw/openclaw.json`:

```json
{
  "models": {
    "providers": {
      "ollama": {
        "baseUrl": "https://ollama.com/v1",
        "apiKey": "your-api-key-here"
      }
    }
  }
}
```

---

## Troubleshooting

### LLM Judge Shows 0% Pass Rate

**Problem:** Ollama API authentication failing.

**Fix:**
1. Check API key in `~/.openclaw/openclaw.json`
2. Verify it's the full key (not masked with `...`)
3. Test manually:
   ```bash
   curl -X POST https://ollama.com/api/generate \
     -H "Authorization: Bearer YOUR_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"model":"gemma4:31b-cloud","prompt":"test"}'
   ```

### No Telegram Alerts

**Problem:** Bot token not found or bot blocked.

**Fix:**
1. Check token in `~/.hermes/.env` (line `TELEGRAM_BOT_TOKEN=...`)
2. Send `/start` to your bot in Telegram if it's blocked
3. Test manually:
   ```bash
   python3 -c "
   from pathlib import Path
   import urllib.request, json
   env = Path.home() / '.hermes' / '.env'
   token = [l.split('=')[1] for l in env.read_text().splitlines() if 'TELEGRAM_BOT_TOKEN=' in l][0].strip()
   req = urllib.request.Request(f'https://api.telegram.org/bot{token}/sendMessage',
     data=json.dumps({'chat_id':'5065264208','text':'test'}).encode(),
     headers={'Content-Type':'application/json'})
   print(urllib.request.urlopen(req).read())
   "
   ```

### ClawLens API Unreachable

**Problem:** OpenClaw gateway not running.

**Fix:**
```bash
curl http://localhost:18789/health
# Should return: {"status":"ok",...}

# If not:
launchctl kickstart -k gui/$(id -u)/com.openclaw.gateway
```

---

## Repo Structure

```
openclaw-ops/
├── README.md                 # This file
├── LICENSE                   # MIT
├── scripts/
│   ├── botty_health_monitor.py    # 5-minute watchdog
│   ├── llm_judge_eval.py          # Daily eval
│   └── clawlens_health_monitor.py # Hourly monitor
├── config/
│   └── com.hermes.botty-monitor.plist  # launchd agent
└── docs/
    ├── SETUP.md              # Detailed setup guide
    ├── EVAL_CASES.md         # LLM judge test cases
    └── TROUBLESHOOTING.md    # Common issues + fixes
```

---

## Time Investment

| Task | Setup Time | Time Saved/Week |
|------|------------|-----------------|
| Botty watchdog | 30 min | 1-2 hours (no 2 AM pages) |
| LLM judge | 2 hours | 3-4 hours (catch regressions early) |
| ClawLens monitor | 1 hour | 1 hour (zero manual health checks) |
| **Total** | **~3.5 hours** | **5-7 hours/week** |

**ROI:** Pays for itself in the first week.

---

## Why This Exists

Reliability isn't about preventing failures. It's about reducing **time-to-detection** and **time-to-recovery**.

- 5-minute script: catches crashes in 300 seconds instead of 3 days
- Daily eval: catches quality regressions in 24 hours instead of 3 weeks
- Hourly monitor: catches anomalies before they compound

That's the whole game. Everything else is implementation.

---

## Contributing

Found a bug? Want to add an eval case? PRs welcome.

**Adding an eval case:**
1. Create `data/llm-eval/cases/your-case.yaml`
2. Define rubric with weighted criteria
3. Test with `python3 llm_judge_eval.py --verbose`

**Adding a health check:**
1. Add detection logic to `clawlens_health_monitor.py`
2. Define threshold and severity
3. Add auto-fix if possible, user action if not

---

## License

MIT — Use it, fork it, break it, fix it.

---

*Built by [@iiizzzyyy](https://github.com/iiizzzyyy) for production AI agent operations.*

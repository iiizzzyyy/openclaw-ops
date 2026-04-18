# Setup Guide — OpenClaw Ops Scripts

Complete setup instructions for production-ready AI agent operations.

---

## Prerequisites

- macOS (for launchd) or Linux (for systemd/cron)
- Python 3.10+
- OpenClaw installed and running
- Telegram bot token (for alerts)
- Ollama Cloud API key (for LLM judge)

---

## Step 1: Clone and Install

```bash
# Clone the repo
git clone https://github.com/iiizzzyyy/openclaw-ops.git
cd openclaw-ops

# Copy scripts to your clawd directory
cp scripts/*.py ~/clawd/scripts/

# Install Python dependencies
pip install pyyaml
```

---

## Step 2: Configure Telegram Alerts

### Get Your Bot Token

1. Create a bot via [@BotFather](https://t.me/BotFather) on Telegram
2. Send `/newbot` and follow prompts
3. Copy the token (looks like: `8513147842:AAH...`)

### Add to Hermes .env

Edit `~/.hermes/.env`:

```bash
TELEGRAM_BOT_TOKEN=8513147842:AAH...
TELEGRAM_ALLOWED_USERS=5065264208  # Your Telegram user ID
```

### Get Your User ID

Message [@userinfobot](https://t.me/userinfobot) on Telegram to get your numeric ID.

### Test Telegram Delivery

```bash
python3 -c "
from pathlib import Path
import urllib.request, json

env = Path.home() / '.hermes' / '.env'
token = [l.split('=')[1] for l in env.read_text().splitlines() if 'TELEGRAM_BOT_TOKEN=' in l][0].strip()
chat_id = [l.split('=')[1] for l in env.read_text().splitlines() if 'TELEGRAM_ALLOWED_USERS=' in l][0].strip()

req = urllib.request.Request(
    f'https://api.telegram.org/bot{token}/sendMessage',
    data=json.dumps({'chat_id': chat_id, 'text': '🧪 Test from OpenClaw Ops'}).encode(),
    headers={'Content-Type': 'application/json'}
)
print(urllib.request.urlopen(req).read())
"
```

You should receive a Telegram message.

---

## Step 3: Configure Ollama Cloud API (for LLM Judge)

### Get API Key

1. Sign up at [Ollama Cloud](https://ollama.com)
2. Create an API key in your account settings
3. Copy the full key

### Add to OpenClaw Config

Edit `~/.openclaw/openclaw.json`:

```json
{
  "models": {
    "providers": {
      "ollama": {
        "baseUrl": "https://ollama.com/v1",
        "apiKey": "your-full-api-key-here",
        "api": "ollama"
      }
    }
  }
}
```

**Important:** The key must be the full value, not masked with `...`

### Test API Access

```bash
curl -X POST https://ollama.com/api/generate \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"gemma4:31b-cloud","prompt":"Hello","stream":false}'
```

Should return JSON with a `response` field.

---

## Step 4: Install Botty Watchdog (5-Minute Health Check)

### Copy launchd Plist

```bash
cp config/com.hermes.botty-monitor.plist ~/Library/LaunchAgents/
```

### Edit Paths (if needed)

Open `~/Library/LaunchAgents/com.hermes.botty-monitor.plist` and verify:

- `ProgramArguments` points to your script location
- `WorkingDirectory` is correct
- `StandardOutPath` and `StandardErrorPath` exist

### Load the Agent

```bash
launchctl load ~/Library/LaunchAgents/com.hermes.botty-monitor.plist
```

### Verify It's Running

```bash
launchctl list | grep botty
# Should show: com.hermes.botty-monitor

# Check logs
tail -20 ~/ai-agents/shared-memory/logs/hermes/*-botty-pings.md
```

### Test Manual Run

```bash
python3 ~/clawd/scripts/botty_health_monitor.py
```

Should output:
```
🔍 Starting Botty health check...
✅ Botty is running, checking for updates...
✅ Already on latest version
✅ Botty healthy (PID: 12345), no updates available
```

---

## Step 5: Install LLM Judge (Daily Evaluation)

### Create Eval Cases

Run once to generate default cases:

```bash
python3 ~/clawd/scripts/llm_judge_eval.py --cases
```

Creates 3 default cases in `~/clawd/data/llm-eval/cases/`.

### Add Your Own Eval Cases

Create `~/clawd/data/llm-eval/cases/your-case.yaml`:

```yaml
id: context-awareness
name: Reads relevant context
description: Agent reads NOW.md or context before starting tasks
input_pattern: task|work|continue|blog|project
rubric:
  loads_context:
    description: Agent reads context files before acting
    weight: 2.0
    levels:
      "0": No context files read
      "1": Reads but doesn't reference
      "2": Reads and uses context in decision
  continuity:
    description: Agent maintains continuity with previous work
    weight: 1.0
    levels:
      "0": Starts fresh without checking state
      "1": Acknowledges previous work
      "2": Builds on previous work explicitly
tags:
  - context
  - continuity
```

### Run First Evaluation

```bash
python3 ~/clawd/scripts/llm_judge_eval.py --verbose
```

Expected output:
```
Capturing sessions...
Found 12 sessions
Loaded 3 eval cases
Running 35 evaluations with 2 workers...
✓ memory-read-before-write / main-20260418-123456.md: 4.0/6.0
✗ context-awareness / coder-20260418-234567.md: 2.0/6.0
...
```

### Capture Baseline

```bash
python3 ~/clawd/scripts/llm_judge_eval.py --baseline
```

Creates `~/clawd/data/llm-eval/baseline.json`.

### Install as Daily Cron

```bash
hermes cron create \
  --schedule "0 6 * * *" \
  --prompt "python3 ~/clawd/scripts/llm_judge_eval.py" \
  --name "Daily LLM Judge"
```

Runs every day at 6 AM, delivers report to Telegram.

---

## Step 6: Install ClawLens Monitor (Hourly Health Check)

### Test Manual Run

```bash
python3 ~/clawd/scripts/clawlens_health_monitor.py
```

Expected output:
```
[2026-04-18T11:10:23] Starting ClawLens health check...
  → Fetching recent sessions...
  → Fetching bot stats...
  → Fetching cron summary...
  → Analyzing health...
  → Sending Telegram alert (status: ok)...
  ✓ Telegram message sent successfully
```

### Install as Hourly Cron

```bash
hermes cron create \
  --schedule "every 1h" \
  --prompt "python3 ~/clawd/scripts/clawlens_health_monitor.py" \
  --name "ClawLens Health Monitor"
```

### Verify Cron Job

```bash
hermes cron list
```

Should show:
```
fd1010f204cd | ClawLens Health Monitor | every 60m | telegram:5065264208 | next: 12:10
```

---

## Step 7: Verify Everything Works

### Checklist

- [ ] Botty watchdog running (launchctl list | grep botty)
- [ ] LLM judge runs manually without errors
- [ ] ClawLens monitor sends Telegram message
- [ ] All three scripts logged successfully

### First Week Monitoring

**Day 1-2:** Watch for false positives. Adjust thresholds if needed:

- `ERROR_RATE_THRESHOLD` in `clawlens_health_monitor.py` (default 0.05)
- Cost alert threshold (default $0.50/hour)
- Active hours for silence detection (default 7-23)

**Day 3-7:** Track LLM judge pass rate. Expect 40-60% initially.

**Week 2+:** Start fixing one failing eval case per week.

---

## Troubleshooting

### Script Permission Issues

```bash
chmod +x ~/clawd/scripts/*.py
```

### Python Import Errors

```bash
pip install pyyaml
```

### launchd Agent Won't Load

```bash
# Check syntax
plutil -lint ~/Library/LaunchAgents/com.hermes.botty-monitor.plist

# Unload and reload
launchctl unload ~/Library/LaunchAgents/com.hermes.botty-monitor.plist
launchctl load ~/Library/LaunchAgents/com.hermes.botty-monitor.plist

# Check logs
tail -20 ~/ai-agents/logs/botty-monitor-error.log
```

### LLM Judge Returns 0% Pass Rate

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) — usually API auth issue.

### No Telegram Messages

1. Verify bot token in `~/.hermes/.env`
2. Send `/start` to your bot in Telegram
3. Test with the Python snippet in Step 2

---

## Next Steps

1. **Customize eval cases** for your agent's specific behaviors
2. **Adjust thresholds** based on your baseline
3. **Add more health checks** to `clawlens_health_monitor.py`
4. **Share your improvements** via PR!

---

*Setup time: ~1 hour. Time saved: 5-7 hours/week.*

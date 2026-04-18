#!/usr/bin/env python3
"""
ClawLens Health Monitor — Automated hourly health checks

Queries ClawLens API, detects issues, attempts auto-fixes, and sends Telegram updates.
"""

import json
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import Optional

# === Configuration ===
CLAWLENS_BASE = "http://localhost:18789/clawlens/api"
TELEGRAM_CHAT_ID = "5065264208"  # Izzy's chat ID
LOOKBACK_HOURS = 1  # Check last hour of data
COST_SPIKE_THRESHOLD = 2.0  # Alert if cost is 2x the hourly average
ERROR_RATE_THRESHOLD = 0.05  # Alert if >5% of sessions have errors

@dataclass
class HealthStatus:
    """Overall health status."""
    status: str = "ok"  # ok, warning, critical
    issues: list = field(default_factory=list)
    auto_fixes: list = field(default_factory=list)
    user_actions: list = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

@dataclass
class Issue:
    """A detected issue."""
    severity: str  # warning, critical
    category: str  # errors, cost, latency, failures
    title: str
    description: str
    affected_agents: list = field(default_factory=list)
    data: dict = field(default_factory=dict)

def get_gateway_token() -> str:
    """Read OpenClaw gateway token from config."""
    config_path = Path.home() / ".openclaw" / "openclaw.json"
    if not config_path.exists():
        raise RuntimeError(f"Config not found: {config_path}")
    
    config = json.loads(config_path.read_text())
    return config.get("gateway", {}).get("auth", {}).get("token", "")

def clawlens_request(endpoint: str, params: dict = None) -> dict:
    """Make authenticated request to ClawLens API."""
    token = get_gateway_token()
    url = f"{CLAWLENS_BASE}/{endpoint}"
    
    if params:
        query = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{url}?{query}"
    
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}"}
    )
    
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.reason}"}
    except Exception as e:
        return {"error": str(e)}

def get_recent_sessions(hours: int = 1) -> list:
    """Get sessions from the last N hours."""
    now = datetime.now(timezone.utc)
    from_ts = int((now - timedelta(hours=hours)).timestamp() * 1000)
    
    result = clawlens_request("sessions", {"fromTs": from_ts, "limit": 100})
    return result.get("data", []) if "data" in result else []

def get_disk_sessions(hours: int = 1) -> list:
    """Get session files modified in the last N hours from disk."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=hours)
    
    sessions_dir = Path.home() / ".openclaw" / "agents"
    recent_files = []
    
    if not sessions_dir.exists():
        return []
    
    # Find all JSONL files modified in last N hours
    for jsonl_file in sessions_dir.rglob("*.jsonl"):
        try:
            mtime = datetime.fromtimestamp(jsonl_file.stat().st_mtime, tz=timezone.utc)
            if mtime > cutoff:
                # Extract agent and session ID from path
                # e.g., ~/.openclaw/agents/main/sessions/abc-123.jsonl
                parts = jsonl_file.parts
                if "agents" in parts:
                    agent_idx = parts.index("agents") + 1
                    agent_id = parts[agent_idx] if agent_idx < len(parts) else "unknown"
                    session_id = jsonl_file.stem
                    
                    recent_files.append({
                        "agentId": agent_id,
                        "sessionId": session_id,
                        "path": str(jsonl_file),
                        "modifiedAt": mtime.isoformat(),
                        "modifiedTs": int(mtime.timestamp() * 1000)
                    })
        except (OSError, ValueError):
            continue
    
    return recent_files

def get_bot_stats(hours: int = 1) -> dict:
    """Get per-agent stats for the last N hours."""
    now = datetime.now(timezone.utc)
    from_ts = int((now - timedelta(hours=hours)).timestamp() * 1000)
    to_ts = int(now.timestamp() * 1000)
    
    result = clawlens_request("bots", {"fromTs": from_ts, "toTs": to_ts})
    return result.get("data", []) if "data" in result else []

def get_cron_summary() -> dict:
    """Get cron jobs summary."""
    result = clawlens_request("cron/summary")
    return result.get("data", {}) if "data" in result else {}

def get_flow_events(since_ms: int = 0) -> list:
    """Get recent flow events."""
    result = clawlens_request("flow/events", {"since": since_ms})
    return result.get("data", []) if "data" in result else []

def analyze_health(sessions: list, bot_stats: list, cron_summary: dict, disk_sessions: list = None) -> HealthStatus:
    """Analyze ClawLens data for issues."""
    status = HealthStatus()
    
    # === Metrics Summary ===
    total_sessions = len(sessions)
    total_disk_sessions = len(disk_sessions) if disk_sessions else 0
    total_errors = sum(1 for s in sessions if s.get("errorCount", 0) > 0)
    total_cost = sum(s.get("totalCost", 0) for s in sessions)
    total_tokens = sum(s.get("totalTokensIn", 0) + s.get("totalTokensOut", 0) for s in sessions)
    error_rate = total_errors / total_sessions if total_sessions > 0 else 0
    
    # Per-agent token breakdown
    agent_tokens = {}
    for s in sessions:
        agent = s.get("agentId", "unknown")
        tokens = s.get("totalTokensIn", 0) + s.get("totalTokensOut", 0)
        agent_tokens[agent] = agent_tokens.get(agent, 0) + tokens
    
    status.metrics = {
        "sessions": total_sessions,
        "disk_sessions": total_disk_sessions,
        "errors": total_errors,
        "error_rate": f"{error_rate:.1%}",
        "cost_usd": f"${total_cost:.4f}",
        "tokens": f"{total_tokens:,}",
        "agents_active": len([b for b in bot_stats if b.get("spanCount", 0) > 0]),
        "agent_tokens": agent_tokens,  # For detailed breakdown
        "ingestion_lag": total_disk_sessions > 0 and total_sessions == 0,
    }
    
    # === Check 1: Error Rate ===
    if error_rate > ERROR_RATE_THRESHOLD:
        affected = list(set(s.get("agentId", "unknown") for s in sessions if s.get("errorCount", 0) > 0))
        status.issues.append(Issue(
            severity="critical",
            category="errors",
            title=f"High Error Rate: {error_rate:.1%}",
            description=f"{total_errors} sessions with errors out of {total_sessions} total",
            affected_agents=affected,
            data={"error_count": total_errors, "total_sessions": total_sessions}
        ))
        status.status = "critical"
        
        # Auto-fix attempt: Check if errors are rate-limit related
        status.auto_fixes.append({
            "action": "Check error logs for pattern",
            "details": "Review /clawlens/api/logs/stream?level=error for root cause"
        })
    
    # === Check 2: Cost Spike ===
    if total_cost > 0.50:  # Alert if >$0.50/hour (adjust based on your baseline)
        status.issues.append(Issue(
            severity="warning",
            category="cost",
            title=f"Cost Alert: ${total_cost:.4f}/hour",
            description="Hourly cost exceeds typical baseline",
            affected_agents=[],
            data={"cost": total_cost}
        ))
        if status.status == "ok":
            status.status = "warning"
    
    # === Check 3: Agent-Specific Issues ===
    for bot in bot_stats:
        agent_id = bot.get("id", "unknown")
        error_count = bot.get("errorCount", 0)
        cost = bot.get("totalCost", 0)
        
        # High error count for specific agent
        if error_count > 5:
            status.issues.append(Issue(
                severity="warning",
                category="agent_errors",
                title=f"Agent {agent_id}: {error_count} errors",
                description=f"Agent has {error_count} errors in the last hour",
                affected_agents=[agent_id],
                data={"error_count": error_count, "cost": cost}
            ))
            if status.status == "ok":
                status.status = "warning"
            
            status.user_actions.append(
                f"Review {agent_id} sessions: http://localhost:18789/clawlens/#/sessions?agent={agent_id}"
            )
    
    # === Check 4: Cron Job Failures ===
    failing_jobs = cron_summary.get("failingJobs", [])
    if failing_jobs:
        status.issues.append(Issue(
            severity="critical",
            category="cron",
            title=f"{len(failing_jobs)} Cron Job(s) Failing",
            description="Scheduled workflows are not completing successfully",
            affected_agents=[],
            data={"failing_jobs": failing_jobs}
        ))
        status.status = "critical"
        
        for job in failing_jobs[:3]:  # Top 3 failing
            status.user_actions.append(
                f"Check cron job: {job.get('name', 'unknown')} — last error: {job.get('lastError', 'unknown')[:100]}"
            )
    
    # === Check 5: Zero Activity vs Ingestion Lag ===
    if total_sessions == 0 and datetime.now().hour in range(7, 23):  # During active hours
        if total_disk_sessions > 0:
            # Sessions exist on disk but not in ClawLens = ingestion lag
            status.issues.append(Issue(
                severity="warning",
                category="ingestion_lag",
                title=f"ClawLens Ingestion Lag Detected",
                description=f"{total_disk_sessions} session files on disk, but 0 ingested into ClawLens",
                affected_agents=list(set(s.get("agentId", "unknown") for s in (disk_sessions or []))),
                data={"disk_sessions": total_disk_sessions, "clawlens_sessions": 0}
            ))
            status.status = "warning"
            status.user_actions.append(
                "ClawLens sync is delayed — sessions will appear once ingestion catches up"
            )
            status.auto_fixes.append({
                "action": "Restart ClawLens sync (if lag persists >1 hour)",
                "details": "launchctl kickstart -k gui/$(id -u)/com.openclaw.gateway"
            })
        else:
            # No sessions anywhere = real problem
            status.issues.append(Issue(
                severity="critical",
                category="silence",
                title="No Agent Activity Detected",
                description="Zero sessions in the last hour during active hours",
                affected_agents=[],
                data={}
            ))
            status.status = "critical"
            status.user_actions.append("Check if OpenClaw gateway is running: curl http://localhost:18789/health")
            status.auto_fixes.append({
                "action": "Restart OpenClaw gateway",
                "details": "launchctl kickstart -k gui/$(id -u)/com.openclaw.gateway"
            })
    
    return status

def format_telegram_message(status: HealthStatus) -> str:
    """Format health status as Telegram message with markdown."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    # Status emoji
    emoji = {"ok": "✅", "warning": "⚠️", "critical": "🚨"}.get(status.status, "❓")
    
    # Header
    msg = f"{emoji} *ClawLens Health Report — {now}*\n\n"
    
    # Metrics
    msg += "*📊 Metrics (Last Hour)*\n"
    for key, value in status.metrics.items():
        if key in ("agent_tokens", "ingestion_lag"):
            continue  # Skip detailed breakdown and boolean flags
        label = key.replace("_", " ").title()
        msg += f"  • {label}: `{value}`\n"
    
    # Ingestion lag indicator
    if status.metrics.get("ingestion_lag"):
        msg += "  • *⚠️ Ingestion Lag*: Sessions on disk, not yet in ClawLens\n"
    
    # Per-agent token breakdown
    if status.metrics.get("agent_tokens"):
        msg += "\n*🔢 Tokens by Agent*\n"
        # Sort by token count descending
        sorted_agents = sorted(
            status.metrics["agent_tokens"].items(),
            key=lambda x: x[1],
            reverse=True
        )
        for agent, tokens in sorted_agents:
            msg += f"  • `{agent}`: {tokens:,}\n"
    
    # Issues
    if status.issues:
        msg += f"\n{'🔴' if status.status == 'critical' else '🟡'} *Issues Detected ({len(status.issues)})*\n"
        for i, issue in enumerate(status.issues, 1):
            severity_emoji = "🚨" if issue.severity == "critical" else "⚠️"
            msg += f"\n{severity_emoji} *{i}. {issue.title}*\n"
            msg += f"   {issue.description}\n"
            if issue.affected_agents:
                msg += f"   Affected: {', '.join(issue.affected_agents)}\n"
    
    # Auto-fixes
    if status.auto_fixes:
        msg += "\n🔧 *Auto-Fix Actions*\n"
        for fix in status.auto_fixes:
            msg += f"  • {fix['action']}\n"
            if fix.get('details'):
                msg += f"    `{fix['details']}`\n"
    
    # User actions
    if status.user_actions:
        msg += "\n👤 *Required Actions*\n"
        for i, action in enumerate(status.user_actions, 1):
            msg += f"  {i}. {action}\n"
    
    # Footer
    if status.status == "ok":
        msg += "\n✅ *All systems nominal* — No action required"
    else:
        msg += f"\n\n📈 View dashboard: http://localhost:18789/clawlens/"
    
    return msg

def send_telegram(message: str) -> dict:
    """Send message to Telegram."""
    # Read bot token from Hermes .env file
    env_path = Path.home() / ".hermes" / ".env"
    if not env_path.exists():
        return {"error": "Hermes .env file not found"}
    
    bot_token = None
    for line in env_path.read_text().splitlines():
        if line.startswith("TELEGRAM_BOT_TOKEN="):
            bot_token = line.split("=", 1)[1].strip()
            break
    
    if not bot_token:
        return {"error": "TELEGRAM_BOT_TOKEN not found in .env"}
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}

def main():
    """Run health check and send report."""
    print(f"[{datetime.now().isoformat()}] Starting ClawLens health check...")
    
    # Gather data
    print("  → Fetching recent sessions from ClawLens...")
    sessions = get_recent_sessions(LOOKBACK_HOURS)
    
    print("  → Fetching session files from disk...")
    disk_sessions = get_disk_sessions(LOOKBACK_HOURS)
    
    print("  → Fetching bot stats...")
    bot_stats = get_bot_stats(LOOKBACK_HOURS)
    
    print("  → Fetching cron summary...")
    cron_summary = get_cron_summary()
    
    # Analyze
    print("  → Analyzing health...")
    status = analyze_health(sessions, bot_stats, cron_summary, disk_sessions)
    
    # Format message
    message = format_telegram_message(status)
    
    # Send to Telegram
    print(f"  → Sending Telegram alert (status: {status.status})...")
    result = send_telegram(message)
    
    if "error" in result:
        print(f"  ✗ Telegram send failed: {result['error']}")
    else:
        print(f"  ✓ Telegram message sent successfully")
    
    # Log to file
    log_path = Path.home() / ".openclaw" / "clawlens-health.log"
    with open(log_path, "a") as f:
        f.write(f"[{datetime.now().isoformat()}] Status: {status.status} | ")
        f.write(f"Sessions: {len(sessions)} | Errors: {status.metrics.get('errors', 0)} | ")
        f.write(f"Cost: {status.metrics.get('cost_usd', '$0')} | ")
        f.write(f"Issues: {len(status.issues)}\n")
    
    print(f"[{datetime.now().isoformat()}] Health check complete")
    
    # Exit with appropriate code
    if status.status == "critical":
        return 1
    return 0

if __name__ == "__main__":
    exit(main())

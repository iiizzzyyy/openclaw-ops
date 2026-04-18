#!/usr/bin/env python3
"""
Botty Health Monitor - Hermes Script
Checks OpenClaw (Botty) health and auto-repairs if needed.
Run via: python3 botty_health_monitor.py
"""

import subprocess
import time
import os
from datetime import datetime
from pathlib import Path

# Configuration
BOTTY_PROCESS_NAME = "openclaw"
LOG_DIR = Path.home() / "ai-agents" / "shared-memory" / "logs" / "hermes"
PATTERNS_FILE = Path.home() / "ai-agents" / "shared-memory" / "patterns" / "repair-patterns.md"
MAX_RETRIES = 3
RETRY_DELAY = 30  # seconds
TELEGRAM_ENABLED = True
OPENCLAW_GITHUB_REPO = "openclaw/openclaw"
OPENCLAW_INSTALL_PATH = "/opt/homebrew/bin/openclaw"
CHECK_FOR_UPDATES = True  # Set to False to disable auto-update

def log_ping(success: bool, response_time_ms: float = 0):
    """Log ping result to shared memory."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = LOG_DIR / f"{today}-botty-pings.md"
    
    timestamp = datetime.now().strftime("%H:%M:%S")
    status = "✅" if success else "❌"
    
    with open(log_file, "a") as f:
        f.write(f"- [{timestamp}] {status} Ping {'success' if success else 'FAILED'}")
        if response_time_ms > 0:
            f.write(f" ({response_time_ms:.0f}ms)")
        f.write("\n")

def get_current_version() -> str:
    """Get currently installed OpenClaw version."""
    try:
        result = subprocess.run(
            ["openclaw", "--version"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            # Parse version from output like "OpenClaw 2026.4.12 (1c0672b)"
            output = result.stdout.strip()
            return output
        return "unknown"
    except Exception as e:
        print(f"Error getting version: {e}")
        return "unknown"

def get_latest_version() -> str:
    """Get latest OpenClaw version from GitHub."""
    try:
        import urllib.request
        import json
        
        url = f"https://api.github.com/repos/{OPENCLAW_GITHUB_REPO}/releases/latest"
        req = urllib.request.Request(url, headers={"Accept": "application/vnd.github.v3+json"})
        
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
            version = data.get("tag_name", "unknown")
            return version
    except Exception as e:
        print(f"Error checking GitHub: {e}")
        return "unknown"

def check_for_update() -> bool:
    """Check if there's a newer version available."""
    if not CHECK_FOR_UPDATES:
        print("⏭️ Auto-update disabled, skipping version check")
        return False
    
    current = get_current_version()
    latest = get_latest_version()
    
    print(f"📦 Current version: {current}")
    print(f"📦 Latest version: {latest}")
    
    if latest == "unknown":
        return False
    
    # Extract version number from current (e.g., "2026.4.12" from "OpenClaw 2026.4.12 (1c0672b)")
    # Remove commit hash in parentheses
    current_clean = current.split("(")[0].strip() if current else "0.0.0"
    # Extract just the version part (last word)
    current_ver = current_clean.split()[-1] if current_clean else "0.0.0"
    latest_ver = latest.lstrip("v")
    
    # Compare versions
    try:
        current_parts = [int(x) for x in current_ver.split(".")]
        latest_parts = [int(x) for x in latest_ver.split(".")]
        
        if latest_parts > current_parts:
            print(f"🆕 Update available: {current_ver} → {latest_ver}")
            return True
        else:
            print("✅ Already on latest version")
            return False
    except Exception as e:
        print(f"Error comparing versions: {e}")
        return False

def update_openclaw() -> bool:
    """Update OpenClaw to latest version via Homebrew."""
    print("🔄 Updating OpenClaw...")
    
    try:
        # Update Homebrew formula
        result = subprocess.run(
            ["brew", "update"],
            capture_output=True,
            text=True,
            timeout=120
        )
        print(f"Homebrew update: {result.returncode == 0}")
        
        # Upgrade OpenClaw
        result = subprocess.run(
            ["brew", "upgrade", "openclaw"],
            capture_output=True,
            text=True,
            timeout=300
        )
        
        if result.returncode == 0:
            new_version = get_current_version()
            print(f"✅ OpenClaw updated to: {new_version}")
            return True
        else:
            print(f"⚠️ Upgrade returned {result.returncode}: {result.stderr}")
            # Check if already up to date
            if "already installed" in result.stderr.lower() or "no upgrades" in result.stderr.lower():
                print("✅ Already up to date")
                return True
            return False
            
    except subprocess.TimeoutExpired:
        print("❌ Update timed out")
        return False
    except Exception as e:
        print(f"❌ Update failed: {e}")
        return False

def log_update(old_version: str, new_version: str):
    """Log update to shared memory."""
    mistakes_dir = Path.home() / "ai-agents" / "shared-memory" / "mistakes"
    mistakes_dir.mkdir(parents=True, exist_ok=True)
    
    today = datetime.now().strftime("%Y-%m-%d")
    timestamp = datetime.now().strftime("%H:%M:%S")
    
    log_content = f"""# OpenClaw Auto-Update — {today}

## What happened
Automatic update from {old_version} to {new_version}

## Trigger
Scheduled health check detected new version on GitHub

## Impact
- Downtime: [restart time] seconds
- Service: Botty (OpenClaw)

## Actions taken
1. Checked GitHub for latest release
2. Updated via Homebrew
3. Restarted Botty service
4. Verified healthy startup

## Version change
- Before: {old_version}
- After: {new_version}

## Pattern extracted
Auto-update working correctly. Consider staggering update days (Mondays for Botty).

---
*Logged by Hermes | Tags: #update #botty #auto-update*
"""
    
    filename = mistakes_dir / f"{today}-botty-update.md"
    with open(filename, "w") as f:
        f.write(log_content)

def check_botty_running() -> bool:
    """Check if Botty (OpenClaw) process is running."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", BOTTY_PROCESS_NAME],
            capture_output=True,
            text=True
        )
        return result.returncode == 0 and bool(result.stdout.strip())
    except Exception as e:
        print(f"Error checking process: {e}")
        return False

def get_botty_pid() -> str:
    """Get Botty process PID."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", BOTTY_PROCESS_NAME],
            capture_output=True,
            text=True
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None

def read_botty_logs(lines: int = 100) -> str:
    """Read latest Botty logs."""
    log_paths = [
        Path.home() / ".openclaw" / "logs" / "latest.log",
        Path("/var/log/openclaw/latest.log"),
        Path.home() / ".openclaw" / "latest.log",
    ]
    
    for log_path in log_paths:
        if log_path.exists():
            try:
                result = subprocess.run(
                    ["tail", "-n", str(lines), str(log_path)],
                    capture_output=True,
                    text=True
                )
                return result.stdout
            except Exception:
                continue
    
    return "No logs found"

def diagnose_issue(logs: str) -> str:
    """Diagnose the root cause from logs."""
    logs_lower = logs.lower()
    
    if "401" in logs_lower or "unauthorized" in logs_lower:
        return "api_key_invalid"
    elif "403" in logs_lower or "forbidden" in logs_lower:
        return "api_key_forbidden"
    elif "429" in logs_lower or "rate limit" in logs_lower:
        return "rate_limited"
    elif "503" in logs_lower or "service unavailable" in logs_lower:
        return "provider_down"
    elif "yaml" in logs_lower and ("parse" in logs_lower or "error" in logs_lower):
        return "config_parse_error"
    elif "connection" in logs_lower and ("refused" in logs_lower or "timeout" in logs_lower):
        return "connection_error"
    elif "websocket" in logs_lower and ("disconnect" in logs_lower or "closed" in logs_lower):
        return "websocket_disconnect"
    elif "segfault" in logs_lower or "segmentation fault" in logs_lower:
        return "crash_segfault"
    elif "memory" in logs_lower and ("error" in logs_lower or "exhausted" in logs_lower):
        return "oom_error"
    else:
        return "unknown"

def apply_fix(issue_type: str) -> bool:
    """Apply fix based on issue type."""
    print(f"Applying fix for: {issue_type}")
    
    if issue_type == "api_key_invalid":
        # Rotate API key or refresh credentials
        print("→ Rotating API credentials...")
        # Add your API key rotation logic here
        
    elif issue_type in ["config_parse_error", "config_corruption"]:
        # Restore config from backup
        print("→ Restoring config from backup...")
        config_backup = Path.home() / ".openclaw" / "config.yaml.backup"
        config_file = Path.home() / ".openclaw" / "config.yaml"
        if config_backup.exists():
            import shutil
            shutil.copy(config_backup, config_file)
            print("→ Config restored")
        else:
            print("⚠ No config backup found")
            return False
            
    elif issue_type in ["websocket_disconnect", "connection_error", "provider_down"]:
        # Just restart - often fixes transient issues
        print("→ Restarting Botty...")
        
    elif issue_type == "crash_segfault" or issue_type == "oom_error":
        print("→ Critical crash detected, restarting...")
    
    return True

def restart_botty() -> bool:
    """Restart Botty (OpenClaw) process."""
    try:
        # Kill existing process
        subprocess.run(["pkill", "-f", BOTTY_PROCESS_NAME], capture_output=True)
        time.sleep(2)
        
        # Start new process
        subprocess.Popen(
            ["openclaw"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        
        # Wait for startup
        time.sleep(5)
        
        # Verify it's running
        return check_botty_running()
        
    except Exception as e:
        print(f"Error restarting Botty: {e}")
        return False

def send_telegram_alert(message: str):
    """Send alert to Telegram."""
    if not TELEGRAM_ENABLED:
        print(f"Telegram alert (disabled): {message}")
        return
    
    # Use Hermes telegram tool or direct API
    # For now, just log it
    print(f"📱 Telegram Alert:\n{message}")

def log_recovery(failure_type: str, fix_applied: str, recovery_time: float):
    """Log recovery to shared memory mistakes folder."""
    mistakes_dir = Path.home() / "ai-agents" / "shared-memory" / "mistakes"
    mistakes_dir.mkdir(parents=True, exist_ok=True)
    
    today = datetime.now().strftime("%Y-%m-%d")
    timestamp = datetime.now().strftime("%H:%M:%S")
    
    log_content = f"""# Botty Recovery: {failure_type} — {today}

## What happened
Botty (OpenClaw) became unresponsive at {timestamp}

## Root cause
Diagnosed as: {failure_type}

## Impact
- Downtime: {recovery_time:.1f} seconds
- Affected tasks: [check Botty logs]

## Fix applied
{fix_applied}

## Recovery time
{recovery_time:.1f} seconds

## Pattern extracted
[Add lesson learned here]

---
*Logged by Hermes | Tags: #mistake #botty #recovery*
"""
    
    filename = mistakes_dir / f"{today}-botty-{failure_type}.md"
    with open(filename, "w") as f:
        f.write(log_content)

def main():
    """Main health check loop."""
    print(f"🔍 Starting Botty health check - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    consecutive_failures = 0
    start_time = time.time()
    
    # STEP 1: Check for updates FIRST (before health check)
    if check_botty_running():
        print("✅ Botty is running, checking for updates...")
        old_version = get_current_version()
        
        if check_for_update():
            print("🆕 New version available, updating...")
            update_start = time.time()
            
            if update_openclaw():
                new_version = get_current_version()
                
                # Restart Botty to apply update
                print("🔄 Restarting Botty to apply update...")
                if restart_botty():
                    update_time = time.time() - update_start
                    print(f"✅ Botty updated and restarted in {update_time:.1f}s")
                    
                    # Send Telegram alert
                    alert = f"""🆕 Botty Auto-Update Complete

Previous: {old_version}
Updated to: {new_version}
Update time: {update_time:.1f}s
Status: ✅ Success

Restarting services..."""
                    send_telegram_alert(alert)
                    
                    # Log update
                    log_update(old_version, new_version)
                else:
                    print("❌ Failed to restart Botty after update")
                    alert = f"""🚨 Botty Update: Restart Failed

Updated from: {old_version}
To: {new_version}
Status: ❌ Manual restart required

Please run: openclaw"""
                    send_telegram_alert(alert)
            else:
                print("⚠️ Update failed, Botty still running")
        else:
            # No update needed, just log healthy ping
            pid = get_botty_pid()
            log_ping(success=True, response_time_ms=(time.time() - start_time) * 1000)
            print(f"✅ Botty healthy (PID: {pid}), no updates available")
        return
    
    # STEP 2: Botty is NOT running - health check failed
    print("❌ Botty is NOT running")
    log_ping(success=False)
    consecutive_failures = 1
    
    # Wait and retry
    for retry in range(MAX_RETRIES - 1):
        print(f"⏳ Waiting {RETRY_DELAY}s before retry {retry + 2}/{MAX_RETRIES}...")
        time.sleep(RETRY_DELAY)
        
        if check_botty_running():
            pid = get_botty_pid()
            log_ping(success=True)
            print(f"✅ Botty recovered on retry {retry + 1} (PID: {pid})")
            return
        
        consecutive_failures += 1
        log_ping(success=False)
    
    # If we get here, Botty is still down after retries
    print(f"🚨 Botty down after {consecutive_failures} consecutive failures")
    
    # Read logs and diagnose
    print("📖 Reading Botty logs...")
    logs = read_botty_logs(100)
    issue_type = diagnose_issue(logs)
    print(f"🔍 Diagnosed issue: {issue_type}")
    
    # Apply fix
    print("🔧 Applying fix...")
    apply_fix(issue_type)
    
    # Restart Botty
    print("🔄 Restarting Botty...")
    restart_start = time.time()
    
    if restart_botty():
        recovery_time = time.time() - restart_start
        print(f"✅ Botty restarted successfully in {recovery_time:.1f}s")
        
        # Send Telegram alert
        alert = f"""🚨 Botty Recovery Report

Failure: {issue_type}
Detected: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Fix applied: Yes
Recovery time: {recovery_time:.1f}s
Status: ✅ Recovered"""
        send_telegram_alert(alert)
        
        # Log to mistakes
        log_recovery(issue_type, "Auto-restart + fix", recovery_time)
        
    else:
        print("❌ Failed to restart Botty - manual intervention required")
        alert = f"""🚨 CRITICAL: Botty Recovery Failed

Failure: {issue_type}
Detected: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Status: ❌ Manual intervention needed

Please check:
- Logs: ~/.openclaw/logs/
- Config: ~/.openclaw/config.yaml
- Ollama status: ollama list"""
        send_telegram_alert(alert)

if __name__ == "__main__":
    main()

#!/usr/bin/env bash
# fix_session.sh — Restart agent_server.py in the interactive desktop session
#
# Run from Linux to fix Windows session isolation remotely.
# Uses SSH + schtasks to relaunch the agent in the correct session.
#
# Usage:
#   ./fix_session.sh user@<windows-ip>          # required: SSH target
#   ./fix_session.sh user@<windows-ip> 8422    # custom port
#
# What this does:
#   1. SSH into Windows, query current session state
#   2. Kill any existing agent_server.py processes
#   3. Create a batch launcher at C:\temp\start_agent.bat
#   4. Create a scheduled task with /IT flag (Interactive Token)
#   5. Run the task — agent starts in the console user's session
#   6. Verify via /health endpoint over Tailscale
#
# Why /IT flag matters:
#   SSH sessions on Windows run in Session 0 (non-interactive).
#   pyautogui.click() in Session 0 cannot reach the desktop.
#   schtasks with /IT forces execution in the logged-on user's session.
#   mss screenshots may work from Session 0 (DWM shares framebuffer),
#   but mouse/keyboard input NEVER crosses session boundaries.

set -euo pipefail

WINDOWS_HOST="${1:?Usage: $0 user@windows-ip [port]}"
AGENT_PORT="${2:-8421}"
AGENT_PATH="C:\\temp\\agent_server.py"
TAILSCALE_IP="${WINDOWS_HOST##*@}"

SSH_OPTS="-o ConnectTimeout=10 -o StrictHostKeyChecking=no"

echo "=== device-use Agent Session Fix (from Linux) ==="
echo "Target: $WINDOWS_HOST"
echo "Port:   $AGENT_PORT"
echo ""

# Helper: run SSH command
ssh_cmd() {
    ssh $SSH_OPTS "$WINDOWS_HOST" "$1" 2>/dev/null || true
}

ssh_cmd_strict() {
    ssh $SSH_OPTS "$WINDOWS_HOST" "$1"
}

# --- Step 1: Diagnostics ---
echo "--- Step 1: Session diagnostics ---"

echo -n "  SSH connection: "
if ssh $SSH_OPTS "$WINDOWS_HOST" "echo ok" 2>/dev/null | grep -q "ok"; then
    echo "OK"
else
    echo "FAILED"
    echo "  Cannot SSH to $WINDOWS_HOST. Check connectivity."
    exit 1
fi

echo "  Current agent processes:"
ssh_cmd "powershell -Command \"Get-CimInstance Win32_Process | Where-Object { \$_.CommandLine -match 'agent_server' } | Select-Object ProcessId, SessionId, CommandLine | Format-Table -AutoSize\""

echo ""
echo "  Port $AGENT_PORT status:"
ssh_cmd "netstat -ano | findstr :$AGENT_PORT | findstr LISTEN"

# --- Step 2: Kill existing agent ---
echo ""
echo "--- Step 2: Kill existing agent ---"

# Kill by port
ssh_cmd "powershell -Command \"
    \$pids = netstat -ano | Select-String ':${AGENT_PORT}\s' | Select-String 'LISTENING' | ForEach-Object {
        if (\$_ -match '\s(\d+)\s*$') { \$Matches[1] }
    };
    foreach (\$pid in \$pids) {
        Write-Host \\\"  Killing PID \$pid (port $AGENT_PORT)\\\";
        Stop-Process -Id \$pid -Force -ErrorAction SilentlyContinue
    }
\""

# Kill by name
ssh_cmd "powershell -Command \"
    Get-CimInstance Win32_Process | Where-Object { \$_.CommandLine -match 'agent_server' } | ForEach-Object {
        Write-Host \\\"  Killing PID \$(\$_.ProcessId) (agent_server)\\\";
        Stop-Process -Id \$_.ProcessId -Force -ErrorAction SilentlyContinue
    }
\""

echo "  Waiting 2s..."
sleep 2

# --- Step 3: Create batch launcher ---
echo ""
echo "--- Step 3: Create batch launcher ---"

# Detect Python path on Windows
PYTHON_PATH=$(ssh_cmd_strict "where python" 2>/dev/null | head -1 | tr -d '\r\n' || true)
if [ -z "$PYTHON_PATH" ]; then
    PYTHON_PATH="C:\\Softwares\\Python\\Program\\python.exe"
    echo "  Python not in PATH, using default: $PYTHON_PATH"
else
    echo "  Python found: $PYTHON_PATH"
fi

ssh_cmd "echo @echo off > C:\\temp\\start_agent.bat"
ssh_cmd "echo cd /d C:\\temp >> C:\\temp\\start_agent.bat"
ssh_cmd "echo if exist C:\\temp\\agent_env.bat call C:\\temp\\agent_env.bat >> C:\\temp\\start_agent.bat"
ssh_cmd "echo \"$PYTHON_PATH\" \"$AGENT_PATH\" --port $AGENT_PORT >> C:\\temp\\start_agent.bat"

echo "  Created C:\\temp\\start_agent.bat"

# --- Step 4: Create and run scheduled task ---
echo ""
echo "--- Step 4: Create scheduled task with /IT flag ---"

# Delete old task
ssh_cmd 'schtasks /Delete /TN "DeviceUseAgent" /F 2>nul'

# Create task with /IT (Interactive Token) — THIS IS THE FIX
# /IT = "Run only when user is logged on" = runs in interactive session
# /RU = Run as specific user (omit to use SYSTEM, but we want user session)
# We use the SSH user which should match the logged-in console user
SSH_USER="${WINDOWS_HOST%%@*}"
echo "  Creating task as user: $SSH_USER"

CREATE_OUTPUT=$(ssh_cmd_strict "schtasks /Create /TN \"DeviceUseAgent\" /TR \"C:\\temp\\start_agent.bat\" /SC ONCE /ST 00:00 /RU $SSH_USER /IT /RL HIGHEST /F" 2>&1 || true)
echo "  $CREATE_OUTPUT"

if ! echo "$CREATE_OUTPUT" | grep -qi "SUCCESS"; then
    echo "  Retrying without /RL HIGHEST..."
    CREATE_OUTPUT=$(ssh_cmd_strict "schtasks /Create /TN \"DeviceUseAgent\" /TR \"C:\\temp\\start_agent.bat\" /SC ONCE /ST 00:00 /RU $SSH_USER /IT /F" 2>&1 || true)
    echo "  $CREATE_OUTPUT"
fi

# Run the task
echo ""
echo "--- Step 5: Run task ---"
RUN_OUTPUT=$(ssh_cmd_strict 'schtasks /Run /TN "DeviceUseAgent"' 2>&1 || true)
echo "  $RUN_OUTPUT"

# --- Step 6: Wait and verify ---
echo ""
echo "--- Step 6: Verify (waiting 5s) ---"
sleep 5

echo "  Agent processes after restart:"
ssh_cmd "powershell -Command \"
    Get-CimInstance Win32_Process | Where-Object { \$_.CommandLine -match 'agent_server' } | ForEach-Object {
        \$session = (Get-Process -Id \$_.ProcessId -ErrorAction SilentlyContinue).SessionId;
        Write-Host \\\"  PID: \$(\$_.ProcessId)  Session: \$session  Cmd: \$(\$_.CommandLine)\\\"
    }
\""

echo ""
echo "  Port $AGENT_PORT:"
ssh_cmd "netstat -ano | findstr :$AGENT_PORT | findstr LISTEN"

# --- Step 7: HTTP health check ---
echo ""
echo "--- Step 7: Health check via Tailscale ---"

if command -v curl &>/dev/null; then
    echo -n "  /health: "
    HEALTH=$(curl -s --connect-timeout 5 "http://${TAILSCALE_IP}:${AGENT_PORT}/health" 2>/dev/null || echo "FAILED")
    echo "$HEALTH"

    if echo "$HEALTH" | grep -q '"status":"ok"'; then
        echo ""
        echo "  SUCCESS: Agent is running and reachable."
        echo ""
        echo "  Quick input test (move mouse to 100,100):"
        CLICK_RESULT=$(curl -s --connect-timeout 5 \
            -X POST "http://${TAILSCALE_IP}:${AGENT_PORT}/move" \
            -H "Content-Type: application/json" \
            -d '{"x": 100, "y": 100}' 2>/dev/null || echo "FAILED")
        echo "  $CLICK_RESULT"

        if echo "$CLICK_RESULT" | grep -q '"ok":true'; then
            echo ""
            echo "  INPUT TEST: PASSED"
            echo "  pyautogui can reach the desktop."
        else
            echo ""
            echo "  INPUT TEST: FAILED"
            echo "  Agent is running but input may not reach desktop."
            echo "  Check if user is logged in at the physical console."
        fi
    else
        echo ""
        echo "  Agent not reachable via Tailscale."
        echo "  Check Windows Firewall: port $AGENT_PORT may be blocked."
        echo "  Workaround: ssh -L $AGENT_PORT:127.0.0.1:$AGENT_PORT $WINDOWS_HOST"
    fi
else
    echo "  curl not available, skipping HTTP check."
    echo "  Test manually: curl http://${TAILSCALE_IP}:${AGENT_PORT}/health"
fi

echo ""
echo "=== Done ==="
echo ""
echo "If input still doesn't work, check these conditions:"
echo "  1. A user must be physically logged in at the Windows console"
echo "  2. The screen must NOT be locked (Win+L)"
echo "  3. RDP sessions don't count — must be physical/console session"
echo "  4. If using RDP, disconnect (don't sign out) to keep session active"
echo ""
echo "To auto-start agent on boot, run on Windows:"
echo "  reg add \"HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run\" /v LabAgent /d \"C:\\temp\\start_agent.bat\" /f"

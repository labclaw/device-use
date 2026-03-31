<#
.SYNOPSIS
    Restart agent_server.py in the interactive desktop session.

.DESCRIPTION
    Windows Session Isolation Fix for device-use Remote Agent.

    Problem: When agent_server.py is started via SSH, it runs in Session 0
    (non-interactive service session). pyautogui/pywinauto calls in Session 0
    cannot reach the interactive desktop. mss screenshots capture Session 0's
    blank desktop (or sometimes the real framebuffer via DWM, but input never
    reaches the user's desktop).

    Solution: Kill the current agent process, then re-launch it in the
    interactive console session via Windows Task Scheduler with /IT flag
    (Interactive Token). The scheduled task runs under the logged-in user's
    session, giving pyautogui full access to the desktop.

    The /IT flag is the key: it forces the task to run in the session of the
    user who is interactively logged on, not Session 0.

.PARAMETER AgentPath
    Path to agent_server.py. Default: C:\temp\agent_server.py

.PARAMETER Port
    Agent port. Default: 8421

.PARAMETER PythonPath
    Path to python.exe. Auto-detected if not specified.

.PARAMETER Password
    Optional bearer token for agent auth.

.EXAMPLE
    # Run locally on Windows (e.g., via SSH to set up, then it restarts itself)
    .\restart_agent_interactive.ps1

    # Run from Linux via SSH
    ssh user@<windows-ip> "powershell -File C:\temp\restart_agent_interactive.ps1"
#>

param(
    [string]$AgentPath = "C:\temp\agent_server.py",
    [string]$Port = "8421",
    [string]$PythonPath = "",
    [string]$Password = ""
)

$ErrorActionPreference = "Stop"
$TaskName = "DeviceUseAgent"
$BatchPath = "C:\temp\start_agent.bat"
$LogPath = "C:\temp\agent_server.log"

Write-Host "=== device-use Agent Session Fix ===" -ForegroundColor Cyan
Write-Host "Timestamp: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"

# --- Step 1: Find Python ---
if (-not $PythonPath) {
    # Try common locations
    $candidates = @(
        "C:\Softwares\Python\Program\python.exe",
        "C:\Python311\python.exe",
        "C:\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) {
            $PythonPath = $c
            break
        }
    }
    if (-not $PythonPath) {
        # Fall back to PATH
        $PythonPath = (Get-Command python -ErrorAction SilentlyContinue).Source
    }
    if (-not $PythonPath) {
        Write-Host "ERROR: Cannot find python.exe. Specify -PythonPath." -ForegroundColor Red
        exit 1
    }
}
Write-Host "Python: $PythonPath"
Write-Host "Agent:  $AgentPath"
Write-Host "Port:   $Port"

# --- Step 2: Check current session info ---
Write-Host ""
Write-Host "--- Session Diagnostics ---" -ForegroundColor Yellow

# Get current process session
$currentSessionId = (Get-Process -Id $PID).SessionId
Write-Host "This script's Session ID: $currentSessionId"

# Find active console session (the one with the physical display)
# WTSGetActiveConsoleSessionId returns the session attached to the physical console
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public class WTS {
    [DllImport("kernel32.dll")]
    public static extern uint WTSGetActiveConsoleSessionId();
}
"@
$consoleSession = [WTS]::WTSGetActiveConsoleSessionId()
Write-Host "Active console Session ID: $consoleSession"

# Check if agent_server is already running and in which session
$agentProcesses = Get-Process -Name python*, pythonw* -ErrorAction SilentlyContinue |
    Where-Object { $_.MainWindowTitle -match "agent" -or $true } |
    ForEach-Object {
        try {
            $cmdline = (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id)").CommandLine
            if ($cmdline -match "agent_server") {
                [PSCustomObject]@{
                    PID = $_.Id
                    Session = $_.SessionId
                    CPU = [math]::Round($_.CPU, 1)
                    Memory = [math]::Round($_.WorkingSet64 / 1MB, 1)
                    CommandLine = $cmdline
                }
            }
        } catch {}
    }

if ($agentProcesses) {
    Write-Host ""
    Write-Host "Found existing agent_server processes:" -ForegroundColor Yellow
    $agentProcesses | Format-Table PID, Session, @{L="Mem(MB)";E={$_.Memory}}, CommandLine -AutoSize

    foreach ($proc in $agentProcesses) {
        if ($proc.Session -eq $consoleSession) {
            Write-Host "  PID $($proc.PID) is already in console Session $consoleSession (GOOD)" -ForegroundColor Green
        } else {
            Write-Host "  PID $($proc.PID) is in Session $($proc.Session), NOT console Session $consoleSession (BAD - this is the problem)" -ForegroundColor Red
        }
    }
} else {
    Write-Host "No existing agent_server processes found."
}

# --- Step 3: Kill existing agent processes ---
Write-Host ""
Write-Host "--- Killing existing agent processes ---" -ForegroundColor Yellow

# Kill by port first (most reliable)
$portListeners = netstat -ano | Select-String ":${Port}\s" | Select-String "LISTENING"
foreach ($line in $portListeners) {
    if ($line -match "\s(\d+)\s*$") {
        $pid = $Matches[1]
        Write-Host "  Killing PID $pid (listening on port $Port)"
        Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
    }
}

# Kill by command line (catch any stragglers)
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match "agent_server" } | ForEach-Object {
    Write-Host "  Killing PID $($_.ProcessId) (agent_server in cmdline)"
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}

Start-Sleep -Seconds 1

# Verify port is free
$stillListening = netstat -ano | Select-String ":${Port}\s" | Select-String "LISTENING"
if ($stillListening) {
    Write-Host "WARNING: Port $Port still in use. Waiting 3s..." -ForegroundColor Yellow
    Start-Sleep -Seconds 3
}

# --- Step 4: Delete old scheduled task ---
Write-Host ""
Write-Host "--- Setting up scheduled task ---" -ForegroundColor Yellow

schtasks /Delete /TN $TaskName /F 2>$null | Out-Null

# --- Step 5: Create batch launcher ---
# The batch file sets up environment and launches the agent with logging
$passwordArg = if ($Password) { " --password $Password" } else { "" }

$batchContent = @"
@echo off
REM device-use Agent Launcher (interactive session)
REM Generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
REM This script is run by Task Scheduler in the interactive desktop session.

cd /d C:\temp

REM Set API keys from user environment (if available)
REM These are needed for the /task endpoint VLM calls
if exist C:\temp\agent_env.bat call C:\temp\agent_env.bat

echo Starting agent_server.py on port $Port...
echo Session ID: %SESSIONNAME%
echo Timestamp: %DATE% %TIME%

"$PythonPath" "$AgentPath" --port $Port$passwordArg >> "$LogPath" 2>&1
"@

Set-Content -Path $BatchPath -Value $batchContent -Encoding ASCII
Write-Host "  Created: $BatchPath"

# --- Step 6: Create scheduled task with /IT (Interactive Token) ---
# Key flags:
#   /RU <username> - Run as the current user
#   /IT            - Run only if user is interactively logged on (forces Session 1+)
#   /RL HIGHEST    - Run with highest privileges (admin if available)
#   /SC ONCE       - One-time trigger (we run it manually)

$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
Write-Host "  Creating task as user: $currentUser"

$createResult = schtasks /Create `
    /TN $TaskName `
    /TR $BatchPath `
    /SC ONCE `
    /ST 00:00 `
    /RU $currentUser `
    /IT `
    /RL HIGHEST `
    /F 2>&1

if ($createResult -match "SUCCESS") {
    Write-Host "  Task created successfully" -ForegroundColor Green
} else {
    Write-Host "  Task creation output: $createResult" -ForegroundColor Yellow
    # Try without /RL HIGHEST (non-admin user)
    Write-Host "  Retrying without /RL HIGHEST..."
    $createResult = schtasks /Create `
        /TN $TaskName `
        /TR $BatchPath `
        /SC ONCE `
        /ST 00:00 `
        /RU $currentUser `
        /IT `
        /F 2>&1
    if ($createResult -match "SUCCESS") {
        Write-Host "  Task created (standard privileges)" -ForegroundColor Green
    } else {
        Write-Host "ERROR: Failed to create scheduled task: $createResult" -ForegroundColor Red
        exit 1
    }
}

# --- Step 7: Run the task ---
Write-Host ""
Write-Host "--- Launching agent in interactive session ---" -ForegroundColor Yellow

$runResult = schtasks /Run /TN $TaskName 2>&1
if ($runResult -match "SUCCESS") {
    Write-Host "  Task started" -ForegroundColor Green
} else {
    Write-Host "ERROR: Failed to run task: $runResult" -ForegroundColor Red
    exit 1
}

# --- Step 8: Wait and verify ---
Write-Host ""
Write-Host "--- Verifying (waiting 5s for startup) ---" -ForegroundColor Yellow
Start-Sleep -Seconds 5

# Check the process
$newAgentProcs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match "agent_server" }
if ($newAgentProcs) {
    foreach ($proc in $newAgentProcs) {
        $session = (Get-Process -Id $proc.ProcessId -ErrorAction SilentlyContinue).SessionId
        $inConsole = ($session -eq $consoleSession)

        Write-Host ""
        Write-Host "  Agent running:" -ForegroundColor Green
        Write-Host "    PID:     $($proc.ProcessId)"
        Write-Host "    Session: $session $(if ($inConsole) {'(CONSOLE - CORRECT)'} else {'(NOT CONSOLE - PROBLEM)'})"
        Write-Host "    Command: $($proc.CommandLine)"

        if (-not $inConsole) {
            Write-Host ""
            Write-Host "  WARNING: Agent is NOT in the console session." -ForegroundColor Red
            Write-Host "  This means pyautogui clicks will NOT reach the desktop." -ForegroundColor Red
            Write-Host "  Possible causes:" -ForegroundColor Yellow
            Write-Host "    1. No user is physically logged in to the console" -ForegroundColor Yellow
            Write-Host "    2. The screen is locked" -ForegroundColor Yellow
            Write-Host "    3. RDP session is active instead of console" -ForegroundColor Yellow
            Write-Host ""
            Write-Host "  Fix: Ensure a user is logged in at the physical display." -ForegroundColor Yellow
        }
    }
} else {
    Write-Host "  WARNING: No agent_server process found. Check log:" -ForegroundColor Red
    Write-Host "    type $LogPath" -ForegroundColor Yellow
    if (Test-Path $LogPath) {
        Write-Host ""
        Write-Host "  Last 10 lines of log:" -ForegroundColor Yellow
        Get-Content $LogPath -Tail 10
    }
    exit 1
}

# Check port
$portCheck = netstat -ano | Select-String ":${Port}\s" | Select-String "LISTENING"
if ($portCheck) {
    Write-Host ""
    Write-Host "  Port $Port: LISTENING" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "  Port $Port: NOT YET LISTENING (may still be starting up)" -ForegroundColor Yellow
    Write-Host "  Wait a few more seconds and check: netstat -ano | findstr :$Port" -ForegroundColor Yellow
}

# --- Step 9: Quick functional test ---
Write-Host ""
Write-Host "--- Quick functional test ---" -ForegroundColor Yellow

try {
    $response = Invoke-RestMethod -Uri "http://127.0.0.1:${Port}/health" -TimeoutSec 5
    Write-Host "  /health: OK" -ForegroundColor Green
    Write-Host "    hostname: $($response.hostname)"
    Write-Host "    platform: $($response.platform)"
    Write-Host "    pyautogui: $($response.pyautogui)"
    Write-Host "    mss: $($response.mss)"
} catch {
    Write-Host "  /health: FAILED (agent may still be starting)" -ForegroundColor Yellow
    Write-Host "  Try: curl http://127.0.0.1:${Port}/health" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== Done ===" -ForegroundColor Cyan
Write-Host "Agent should now be running in console Session $consoleSession."
Write-Host "Test from Linux: curl http://<tailscale-ip>:${Port}/health"
Write-Host "Logs: type $LogPath"

# Task Scheduler entry point: ensures Ollama is up, then runs the ACH pipeline.
# Requires an interactive login session (Ollama is a per-user Startup app, not a service).

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $repoRoot "logs\scheduled"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logFile = Join-Path $logDir "run_$(Get-Date -Format 'yyyy-MM-dd_HHmmss').log"

function Log($msg) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $msg"
    $line | Tee-Object -FilePath $logFile -Append
}

if (-not (Get-Process ollama -ErrorAction SilentlyContinue)) {
    Log "Ollama not running - starting it"
    Start-Process "$env:LOCALAPPDATA\Programs\Ollama\ollama app.exe"
}

$deadline = (Get-Date).AddSeconds(60)
$ready = $false
while ((Get-Date) -lt $deadline) {
    try {
        Invoke-WebRequest -Uri "http://localhost:11434/api/tags" -UseBasicParsing -TimeoutSec 3 | Out-Null
        $ready = $true
        break
    } catch {
        Start-Sleep -Seconds 2
    }
}

if (-not $ready) {
    Log "ERROR: Ollama did not become ready within 60s - aborting run"
    exit 1
}

Log "Ollama ready - starting pipeline run"
Set-Location $repoRoot
& uv run python main.py 2>&1 | Out-File -FilePath $logFile -Append -Encoding utf8
Log "Pipeline run finished with exit code $LASTEXITCODE"
exit $LASTEXITCODE

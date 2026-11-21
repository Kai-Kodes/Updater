# install.ps1 — PowerShell installer for updater on Windows
$ErrorActionPreference = "Stop"

$IconUpdate = "󰚰"
$IconSuccess = ""
$IconWarn = ""
$IconError = ""

Write-Host "`n  $IconUpdate  Installing updater on Windows...`n" -ForegroundColor Cyan

# 1. Check Python
$PythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $PythonCmd) {
    $PythonCmd = Get-Command python3 -ErrorAction SilentlyContinue
}

if (-not $PythonCmd) {
    Write-Host "  $IconError Python 3 is required. Please install Python from https://www.python.org or winget install Python.Python.3.11" -ForegroundColor Red
    exit 1
}

Write-Host "  $IconSuccess Found Python: $($PythonCmd.Source)" -ForegroundColor Green

# 2. Check recommended tools
if (Get-Command fzf -ErrorAction SilentlyContinue) {
    Write-Host "  $IconSuccess fzf detected (interactive TUI enabled)" -ForegroundColor Green
} else {
    Write-Host "  $IconWarn fzf not found (recommended: winget install junegunn.fzf or scoop install fzf)" -ForegroundColor Yellow
}

if (Get-Command bat -ErrorAction SilentlyContinue) {
    Write-Host "  $IconSuccess bat detected (syntax-highlighted preview enabled)" -ForegroundColor Green
} else {
    Write-Host "  $IconWarn bat not found (recommended: winget install sharkdp.bat or scoop install bat)" -ForegroundColor Yellow
}

# 3. Create launcher directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BinDir = Join-Path $env:USERPROFILE ".local\bin"
if (-not (Test-Path $BinDir)) {
    New-Item -ItemType Directory -Path $BinDir -Force | Out-Null
}

$CmdPath = Join-Path $BinDir "updater.cmd"
$CmdContent = @"
@echo off
set "PYTHONPATH=$ScriptDir;%PYTHONPATH%"
python -m updater.cli %*
"@

Set-Content -Path $CmdPath -Value $CmdContent -Encoding ASCII
Write-Host "  $IconSuccess Created launcher: $CmdPath" -ForegroundColor Green

# 4. Check PATH
$UserPath = [Environment]::GetEnvironmentVariable("PATH", "User")
if ($UserPath -notlike "*$BinDir*") {
    Write-Host "  $IconWarn Adding $BinDir to User PATH..." -ForegroundColor Yellow
    [Environment]::SetEnvironmentVariable("PATH", "$UserPath;$BinDir", "User")
    $env:PATH = "$env:PATH;$BinDir"
    Write-Host "  $IconSuccess Added $BinDir to PATH" -ForegroundColor Green
}

Write-Host "`n  $IconSuccess updater installation complete! Run 'updater' in your terminal.`n" -ForegroundColor Green

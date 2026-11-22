# Token Buddy 1-line installer for Windows PowerShell
# Usage: irm https://raw.githubusercontent.com/Ugochi56/Token-Buddy/main/install.ps1 | iex

$ErrorActionPreference = "Stop"

$RawBase = "https://raw.githubusercontent.com/Ugochi56/Token-Buddy/main/.agents/skills/token-budget"

# Auto-detect .gemini root
$Candidates = @()
if ($env:GEMINI_HOME) { $Candidates += $env:GEMINI_HOME }
if ($env:ANTIGRAVITY_HOME) { $Candidates += $env:ANTIGRAVITY_HOME }
$Candidates += (Join-Path $HOME ".gemini")
if ($env:USERPROFILE) { $Candidates += (Join-Path $env:USERPROFILE ".gemini") }

$GeminiRoot = $null
foreach ($c in $Candidates | Select-Object -Unique) {
    if ((Test-Path (Join-Path $c "config")) -or (Test-Path (Join-Path $c "antigravity"))) {
        $GeminiRoot = $c
        break
    }
}
if (-not $GeminiRoot) { $GeminiRoot = Join-Path $HOME ".gemini" }

$Dest = Join-Path $GeminiRoot "config\skills\token-budget"
New-Item -ItemType Directory -Force -Path (Join-Path $Dest "scripts") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Dest "references") | Out-Null

$Files = @(
    "SKILL.md",
    "references/complexity-rubric.md",
    "scripts/locate_gemini.py",
    "scripts/dashboard.py"
)

Write-Host "Installing Token Buddy into $Dest ..." -ForegroundColor Cyan
foreach ($f in $Files) {
    $OutFile = Join-Path $Dest ($f -replace "/", "\")
    Invoke-RestMethod -Uri "$RawBase/$f" -OutFile $OutFile
}

# Create `token-buddy` CLI launcher
$BinDir = Join-Path $HOME ".local\bin"
New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
$Dashboard = Join-Path $Dest "scripts\dashboard.py"
$Shim = Join-Path $BinDir "token-buddy.cmd"
"@echo off`r`npython `"$Dashboard`" %*`r`n" | Set-Content -Path $Shim -Encoding ASCII

Write-Host ""
Write-Host "Token Buddy installed!" -ForegroundColor Green
Write-Host "  Skill    : $Dest"
Write-Host "  Launcher : $Shim"
if (($env:PATH -split ";") -notcontains $BinDir) {
    Write-Host "  Note     : Add $BinDir to PATH, or run: python `"$Dashboard`"" -ForegroundColor Yellow
} else {
    Write-Host "  Run now  : token-buddy --watch 5" -ForegroundColor Cyan
}

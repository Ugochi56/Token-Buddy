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

$ConfigDir = Join-Path $GeminiRoot "config"
$Dest = Join-Path $ConfigDir "skills\token-budget"
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

# Upsert tiny always-on rule in <gemini>/config/GEMINI.md so Token Buddy auto-runs in every chat
$GeminiMd = Join-Path $ConfigDir "GEMINI.md"
$RuleBlock = @"
<!-- TOKEN-BUDDY:START -->
## Token Buddy (Always-On Token Discipline)
- **Match compute to complexity**: Keep T0/T1 answers brief; escalate only when needed.
- **Delegate bulk work**: Use ``invoke_subagent`` with ``Model: "flash_lite"`` for file/symbol scans & log summaries, and ``Model: "flash"`` for multi-file research (``research``). Require compact bullet returns (``file:line`` refs, no raw file dumps).
- **Lean context & cache protection**: Read targeted line ranges (``StartLine``/``EndLine``), filter noisy shell output, keep raw dumps inside subagents, and proactively suggest ``/compact`` every ~40 steps, before switching models, or when starting a new feature.
- **Token usage & quotas**: Whenever the user asks about token usage, burn, model quotas, or Token Buddy, use the ``token-budget`` skill (``swarm(action="models", all=True)`` + ``locate_gemini.py --burn``), save live quotas to ``<gemini>/config/token_budget_quotas.json``, and report the live summary.
<!-- TOKEN-BUDDY:END -->
"@

$Existing = if (Test-Path $GeminiMd) { Get-Content -Raw -Path $GeminiMd } else { "" }
$Pattern = "(?s)<!-- TOKEN-BUDDY:START -->.*?<!-- TOKEN-BUDDY:END -->"
if ($Existing -match $Pattern) {
    $Updated = [regex]::Replace($Existing, $Pattern, $RuleBlock)
} elseif ($Existing.Trim().Length -gt 0) {
    $Updated = $Existing.TrimEnd() + "`r`n`r`n" + $RuleBlock + "`r`n"
} else {
    $Updated = $RuleBlock + "`r`n"
}
Set-Content -Path $GeminiMd -Value $Updated -Encoding UTF8

# Create `token-buddy` CLI launcher
$BinDir = Join-Path $HOME ".local\bin"
New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
$Dashboard = Join-Path $Dest "scripts\dashboard.py"
$Shim = Join-Path $BinDir "token-buddy.cmd"
"@echo off`r`npython `"$Dashboard`" %*`r`n" | Set-Content -Path $Shim -Encoding ASCII

Write-Host ""
Write-Host "Token Buddy installed (auto-enabled in all Antigravity chats)!" -ForegroundColor Green
Write-Host "  Skill    : $Dest"
Write-Host "  Rule     : $GeminiMd"
Write-Host "  Launcher : $Shim"
if (($env:PATH -split ";") -notcontains $BinDir) {
    Write-Host "  Note     : Add $BinDir to PATH, or run: python `"$Dashboard`"" -ForegroundColor Yellow
} else {
    Write-Host "  Live CLI : token-buddy --watch 5" -ForegroundColor Cyan
}

# Auto-run the dashboard immediately
python "$Dashboard"

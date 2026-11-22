# Token Buddy

Adaptive token & compute budgeting skill + colorful ASCII live CLI dashboard for **Google Antigravity**.

```text
  +--------------------------------------------------------------------+
  |   /\_/\   ANTIGRAVITY TOKEN BUDGET                                 |
  |  ( o.o )  [*] Healthy | 16/23 models ready                         |
  |   > ^ <   ~/.gemini                                                |
  +--------------------------------------------------------------------+
  | TODAY                 LAST 7 DAYS           ALL-TIME BURN          |
  | 3.7M tokens           56.3M tokens          125.7M (1.29B total)   |
  | 88% cached            88% cached            91% saved by cache     |
  +--------------------------------------------------------------------+
  | ACTIVE CHAT [LIVE] #d19d3580 (0s ago)  +6.1K now                   |
  | 8.5M uncached  |  268 steps  |  88% cached                         |
  |   Gemini Flash Worker Agy         3.5M  (176 steps)                |
  |   Gemini Pro Orchestrator Neon    2.6M  (33 steps)                 |
  +--------------------------------------------------------------------+
  | MODEL QUOTAS                                                       |
  | Gemini 4 Argon & Pro  [################]  100%  resets in 6d 23h   |
  | Flash / Neon / H2     [#########.......]   55%  resets in 1h 26m   |
  | Claude & GPT-OSS      [................]    0%  resets in 3d 8h    |
  +--------------------------------------------------------------------+
  | BEST MODEL FOR YOUR NEXT REQUEST                                   |
  | Quick question   ->  flash_lite                  | <= 400 tok      |
  | Small edit       ->  flash                       | <= 1.2K tok     |
  | Multi-file task  ->  Gemini 4 Hydrogen Medium    | <= 2.5K tok     |
  | Hard / complex   ->  Gemini 4 Argon High         | <= 4.5K tok     |
  +--------------------------------------------------------------------+
```

## Features

- **Auto-discovers `.gemini`** across Windows, macOS, and Linux (`GEMINI_HOME`, `ANTIGRAVITY_HOME`, `~`, `USERPROFILE`/`APPDATA`, `XDG_CONFIG_HOME`).
- **Live accessible models & quota pools**: Reads live remaining quota percentages and reset timers via Antigravity's `swarm(action="models", all=True)`.
- **Lifetime, 7-day, 24-hour & active-chat burn**: Scans local Antigravity transcripts (`antigravity/brain/*/.system_generated/logs/transcript.jsonl`) with zero external dependencies.
- **Complexity-based model tiering (`T0`–`T3`)**: Routes bulk file scanning and routine research to `flash_lite` / `flash` subagents with compact return contracts, reserving flagship models for core reasoning.
- **Colorful ASCII CLI dashboard**: 24-bit TrueColor ANSI terminal UI with `--watch` live refresh and `--details` per-model breakdown.

## Quick Install

Requires **Python 3.10+** (no third-party packages).

```bash
git clone https://github.com/Ugochi56/Token-Buddy.git token-buddy
cd token-buddy
python install.py
```

`install.py` automatically:
1. Locates your `.gemini` directory on Windows, macOS, or Linux.
2. Installs the `token-budget` skill globally to `<gemini>/config/skills/token-budget/`.
3. Creates a `token-buddy` launcher in `~/.local/bin/`.

To uninstall:

```bash
python install.py --uninstall
```

## CLI Dashboard Usage

```bash
# Single snapshot (full color ASCII)
token-buddy

# Live auto-refresh every 5 seconds
token-buddy --watch 5

# Include all-time per-model breakdown
token-buddy --details

# Plain text (no ANSI color)
token-buddy --no-color
```

Or run directly with Python:

```bash
python ~/.gemini/config/skills/token-budget/scripts/dashboard.py --watch 5
```

## Other CLI Utilities

```bash
# Print detected .gemini paths (JSON)
python .agents/skills/token-budget/scripts/locate_gemini.py

# Full JSON burn report (lifetime, 7d, 24h, per-model)
python .agents/skills/token-budget/scripts/locate_gemini.py --burn

# Audit always-on rules, skills, plugins, and MCP prompt overhead
python .agents/skills/token-budget/scripts/locate_gemini.py --audit
```

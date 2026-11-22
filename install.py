#!/usr/bin/env python3
"""Token Buddy installer for Antigravity (Windows, macOS, Linux).

Auto-detects the user's .gemini directory, installs the `token-budget` skill
globally, registers the tiny always-on Token Buddy rule in `<gemini>/config/GEMINI.md`,
creates a `token-buddy` CLI launcher, and launches the dashboard once.

Usage:
  python install.py
  python install.py --uninstall
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
SKILL_SRC = REPO_ROOT / ".agents" / "skills" / "token-budget"
SCRIPTS_DIR = SKILL_SRC / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import locate_gemini as lg  # noqa: E402

RULE_START = "<!-- TOKEN-BUDDY:START -->"
RULE_END = "<!-- TOKEN-BUDDY:END -->"
RULE_BLOCK = f"""{RULE_START}
## Token Buddy (Always-On Token Discipline)
- **Match compute to complexity**: Keep T0/T1 answers brief; escalate only when needed.
- **Delegate bulk work**: Use `invoke_subagent` with `Model: "flash_lite"` for file/symbol scans & log summaries, and `Model: "flash"` for multi-file research (`research`). Require compact bullet returns (`file:line` refs, no raw file dumps).
- **Lean context**: Read targeted line ranges (`StartLine`/`EndLine`), filter noisy shell output, and suggest `/compact` in long chats or before switching models.
- **Token usage & quotas**: Whenever the user asks about token usage, burn, model quotas, or Token Buddy, use the `token-budget` skill (`swarm(action="models", all=True)` + `locate_gemini.py --burn`), save live quotas to `<gemini>/config/token_budget_quotas.json`, and report the live summary.
{RULE_END}"""


def _upsert_global_rule(config_dir: Path) -> Path:
    config_dir.mkdir(parents=True, exist_ok=True)
    gemini_md = config_dir / "GEMINI.md"
    existing = gemini_md.read_text(encoding="utf-8") if gemini_md.is_file() else ""
    pattern = re.compile(rf"{re.escape(RULE_START)}.*?{re.escape(RULE_END)}", re.DOTALL)
    if pattern.search(existing):
        updated = pattern.sub(RULE_BLOCK, existing)
    else:
        sep = "\n\n" if existing.strip() else ""
        updated = existing.rstrip() + sep + RULE_BLOCK + "\n"
    gemini_md.write_text(updated, encoding="utf-8")
    return gemini_md


def _remove_global_rule(config_dir: Path) -> None:
    gemini_md = config_dir / "GEMINI.md"
    if not gemini_md.is_file():
        return
    existing = gemini_md.read_text(encoding="utf-8")
    pattern = re.compile(rf"\n?{re.escape(RULE_START)}.*?{re.escape(RULE_END)}\n?", re.DOTALL)
    cleaned = pattern.sub("\n", existing).strip()
    if cleaned:
        gemini_md.write_text(cleaned + "\n", encoding="utf-8")
    else:
        gemini_md.unlink()


def _create_launcher(dashboard_path: Path) -> Path | None:
    bin_dir = Path.home() / ".local" / "bin"
    try:
        bin_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None

    if os.name == "nt":
        shim = bin_dir / "token-buddy.cmd"
        shim.write_text(f'@echo off\r\npython "{dashboard_path}" %*\r\n', encoding="utf-8")
        return shim

    shim = bin_dir / "token-buddy"
    shim.write_text(f'#!/usr/bin/env sh\nexec python3 "{dashboard_path}" "$@"\n', encoding="utf-8")
    shim.chmod(shim.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return shim


def install() -> int:
    if not SKILL_SRC.is_dir():
        print(f"Error: skill source not found at {SKILL_SRC}", file=sys.stderr)
        return 1

    info = lg.locate_gemini()
    config_dir = Path(str(info["config_dir"]))
    skills_dir = Path(str(info["skills_dir"]))
    dest = skills_dir / "token-budget"

    skills_dir.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(SKILL_SRC, dest)

    gemini_md = _upsert_global_rule(config_dir)
    dashboard_path = dest / "scripts" / "dashboard.py"
    shim = _create_launcher(dashboard_path)

    print("Token Buddy installed (auto-enabled globally)!")
    print(f"  Detected .gemini : {info['gemini_root']}")
    print(f"  Skill installed  : {dest}")
    print(f"  Always-on rule   : {gemini_md}")
    if shim:
        print(f"  CLI launcher     : {shim}")
        path_entries = [p.lower() for p in os.environ.get("PATH", "").split(os.pathsep)]
        if str(shim.parent).lower() not in path_entries:
            print(f"  Note: Add {shim.parent} to your PATH to run `token-buddy` directly.")

    # Auto-run the dashboard once so the user immediately sees their live stats
    subprocess.run([sys.executable, str(dashboard_path)], check=False)
    return 0


def uninstall() -> int:
    info = lg.locate_gemini()
    config_dir = Path(str(info["config_dir"]))
    dest = Path(str(info["skills_dir"])) / "token-budget"
    if dest.exists():
        shutil.rmtree(dest)
        print(f"Removed skill: {dest}")
    else:
        print(f"Skill not found at {dest}")

    _remove_global_rule(config_dir)
    print(f"Cleaned always-on rule from: {config_dir / 'GEMINI.md'}")

    bin_dir = Path.home() / ".local" / "bin"
    for name in ("token-buddy.cmd", "token-buddy"):
        p = bin_dir / name
        if p.exists():
            p.unlink()
            print(f"Removed launcher: {p}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Install or uninstall Token Buddy for Antigravity.")
    parser.add_argument("--uninstall", action="store_true", help="Remove Token Buddy global skill, rule, and launcher.")
    args = parser.parse_args()
    return uninstall() if args.uninstall else install()


if __name__ == "__main__":
    raise SystemExit(main())

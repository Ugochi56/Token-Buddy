#!/usr/bin/env python3
"""Token Buddy installer for Antigravity (Windows, macOS, Linux).

Auto-detects the user's .gemini directory, installs the `token-budget` skill
globally, and creates a `token-buddy` CLI launcher for the ASCII dashboard.

Usage:
  python install.py
  python install.py --uninstall
"""

from __future__ import annotations

import argparse
import os
import shutil
import stat
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
SKILL_SRC = REPO_ROOT / ".agents" / "skills" / "token-budget"
SCRIPTS_DIR = SKILL_SRC / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import locate_gemini as lg  # noqa: E402


def _create_launcher(dashboard_path: Path) -> Path | None:
    """Create a `token-buddy` CLI shim in ~/.local/bin."""
    bin_dir = Path.home() / ".local" / "bin"
    try:
        bin_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None

    if os.name == "nt":
        shim = bin_dir / "token-buddy.cmd"
        shim.write_text(
            f'@echo off\r\npython "{dashboard_path}" %*\r\n',
            encoding="utf-8",
        )
        return shim

    shim = bin_dir / "token-buddy"
    shim.write_text(
        f'#!/usr/bin/env sh\nexec python3 "{dashboard_path}" "$@"\n',
        encoding="utf-8",
    )
    shim.chmod(shim.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return shim


def install() -> int:
    if not SKILL_SRC.is_dir():
        print(f"Error: skill source not found at {SKILL_SRC}", file=sys.stderr)
        return 1

    info = lg.locate_gemini()
    skills_dir = Path(str(info["skills_dir"]))
    dest = skills_dir / "token-budget"

    skills_dir.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(SKILL_SRC, dest)

    dashboard_path = dest / "scripts" / "dashboard.py"
    shim = _create_launcher(dashboard_path)

    print("Token Buddy installed!")
    print(f"  Detected .gemini : {info['gemini_root']}")
    print(f"  Skill installed  : {dest}")
    if shim:
        print(f"  CLI launcher     : {shim}")
        path_entries = [p.lower() for p in os.environ.get("PATH", "").split(os.pathsep)]
        if str(shim.parent).lower() not in path_entries:
            print(f"  Note: Add {shim.parent} to your PATH to run `token-buddy` directly.")
    print("")
    print("Run the dashboard now:")
    print(f'  python "{dashboard_path}"')
    print(f'  python "{dashboard_path}" --watch 5')
    return 0


def uninstall() -> int:
    info = lg.locate_gemini()
    dest = Path(str(info["skills_dir"])) / "token-budget"
    if dest.exists():
        shutil.rmtree(dest)
        print(f"Removed skill: {dest}")
    else:
        print(f"Skill not found at {dest}")

    bin_dir = Path.home() / ".local" / "bin"
    for name in ("token-buddy.cmd", "token-buddy"):
        p = bin_dir / name
        if p.exists():
            p.unlink()
            print(f"Removed launcher: {p}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Install or uninstall Token Buddy for Antigravity.")
    parser.add_argument("--uninstall", action="store_true", help="Remove Token Buddy global skill and launcher.")
    args = parser.parse_args()
    return uninstall() if args.uninstall else install()


if __name__ == "__main__":
    raise SystemExit(main())

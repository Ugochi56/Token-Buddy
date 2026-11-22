#!/usr/bin/env python3
"""Colorful, Claude-Code-inspired ASCII CLI dashboard for Antigravity
token burn, live model quotas, and per-request routing.

Zero external dependencies (Python stdlib). Works in PowerShell, CMD,
Windows Terminal, macOS Terminal, and Linux shells.

Usage:
  python scripts/dashboard.py              # Clean, colorful ASCII view
  python scripts/dashboard.py --details    # Include per-model burn breakdown
  python scripts/dashboard.py --watch 10   # Auto-refresh every 10s
  python scripts/dashboard.py --no-color   # Plain uncolored output
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import locate_gemini as lg  # noqa: E402

ANSI_RE = re.compile(r"\033\[[0-9;]*m")


def enable_windows_ansi() -> None:
    """Enable VT100/ANSI escape sequences on Windows PowerShell/CMD reliably."""
    if os.name != "nt":
        return
    try:
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
    except Exception:
        os.system("")


class Theme:
    """Warm, Claude-Code-inspired 24-bit TrueColor palette."""

    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def _fg(self, r: int, g: int, b: int) -> str:
        return f"\033[38;2;{r};{g};{b}m" if self.enabled else ""

    def _code(self, c: str) -> str:
        return c if self.enabled else ""

    @property
    def reset(self) -> str:
        return self._code("\033[0m")

    @property
    def bold(self) -> str:
        return self._code("\033[1m")

    @property
    def accent(self) -> str:
        return self._fg(224, 122, 85)  # Warm Claude-Code coral/terracotta

    @property
    def peach(self) -> str:
        return self._fg(245, 178, 125)

    @property
    def green(self) -> str:
        return self._fg(118, 224, 152)  # Bright sage green

    @property
    def amber(self) -> str:
        return self._fg(245, 198, 96)  # Warm gold

    @property
    def red(self) -> str:
        return self._fg(240, 108, 120)  # Soft coral red

    @property
    def lavender(self) -> str:
        return self._fg(180, 172, 250)

    @property
    def sky(self) -> str:
        return self._fg(130, 206, 248)

    @property
    def white(self) -> str:
        return self._fg(245, 245, 250)

    @property
    def muted(self) -> str:
        return self._fg(138, 144, 165)

    @property
    def border(self) -> str:
        return self._fg(92, 98, 118)


def visible_len(s: str) -> int:
    return len(ANSI_RE.sub("", s))


def pad_right(s: str, width: int) -> str:
    return s + (" " * max(0, width - visible_len(s)))


def fmt_tokens(n: int) -> str:
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.2f}B"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def fmt_reset_delta(iso_ts: str) -> str:
    dt = lg._parse_iso_ts(iso_ts)
    if not dt:
        return iso_ts
    secs = int((dt - datetime.now(timezone.utc)).total_seconds())
    if secs <= 0:
        return "resetting soon"
    days, rem = divmod(secs, 86400)
    hours, rem = divmod(rem, 3600)
    mins = rem // 60
    if days > 0:
        return f"resets in {days}d {hours}h"
    if hours > 0:
        return f"resets in {hours}h {mins}m"
    return f"resets in {mins}m"


def friendly_pool_name(models: list[str]) -> str:
    joined = " ".join(models).lower()
    if "claude" in joined or "gpt" in joined:
        return "Claude & GPT-OSS"
    if "argon" in joined:
        return "Gemini 4 Argon & Pro"
    if "flash" in joined or "neon" in joined or "hydrogen" in joined:
        return "Flash / Neon / H2"
    return models[0] if models else "Other Models"


def friendly_model_name(model_id: str, display_names: dict[str, str]) -> str:
    if model_id in display_names:
        return display_names[model_id]
    if model_id == "unknown":
        return "Earlier sessions"
    return model_id.replace("-", " ").title()


def ascii_bar(pct: float, width: int, fill_col: str, t: Theme) -> str:
    clamped = max(0.0, min(100.0, pct))
    filled = int(round((clamped / 100.0) * width))
    return (
        f"{t.border}[{t.reset}"
        f"{fill_col}{'#' * filled}{t.reset}"
        f"{t.border}{'.' * (width - filled)}]{t.reset}"
    )


def load_quotas(info: dict, explicit_path: str | None) -> tuple[dict | None, str | None]:
    candidates: list[Path] = []
    if explicit_path:
        candidates.append(Path(explicit_path))
    candidates.append(Path(str(info["config_dir"])) / "token_budget_quotas.json")
    candidates.append(Path(str(info["skills_dir"])) / "token-budget" / ".quotas_cache.json")
    candidates.append(SCRIPT_DIR.parent / ".quotas_cache.json")

    for p in candidates:
        if p.is_file():
            try:
                return json.loads(p.read_text(encoding="utf-8")), str(p)
            except (OSError, json.JSONDecodeError):
                continue
    return None, None


def active_chat_summary(info: dict) -> dict | None:
    """Return live stats for the most recently updated local conversation."""
    brain_dir = Path(str(info["brain_dir"]))
    if not brain_dir.is_dir():
        return None
    newest: Path | None = None
    newest_mtime = -1.0
    for p in brain_dir.glob("*/.system_generated/logs/transcript.jsonl"):
        try:
            mt = p.stat().st_mtime
        except OSError:
            continue
        if mt > newest_mtime:
            newest_mtime = mt
            newest = p
    if newest is None:
        return None

    steps = 0
    fresh = 0
    cached = 0
    out = 0
    by_model: dict[str, dict[str, int]] = {}
    try:
        with newest.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if '"PLANNER_RESPONSE"' not in line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get("type") != "PLANNER_RESPONSE":
                    continue
                f_in = int(obj.get("input_tokens") or 0)
                c_rd = int(obj.get("cache_read_tokens") or 0)
                o_tk = int(obj.get("output_tokens") or 0)
                mdl = str(obj.get("model") or "unknown")
                steps += 1
                fresh += f_in
                cached += c_rd
                out += o_tk
                mb = by_model.setdefault(mdl, {"steps": 0, "uncached": 0})
                mb["steps"] += 1
                mb["uncached"] += f_in + o_tk
    except OSError:
        return None

    age_secs = max(0, int(time.time() - newest_mtime))
    total_prompt = fresh + cached
    return {
        "conv_id": newest.parents[2].name[:8],
        "age_secs": age_secs,
        "steps": steps,
        "uncached": fresh + out,
        "output": out,
        "cache_pct": round((cached / total_prompt) * 100, 1) if total_prompt else 0.0,
        "by_model": sorted(by_model.items(), key=lambda kv: kv[1]["uncached"], reverse=True),
    }


def fmt_age(secs: int) -> str:
    if secs < 60:
        return f"{secs}s ago"
    if secs < 3600:
        return f"{secs // 60}m ago"
    return f"{secs // 3600}h ago"


def box_line(content: str, inner_w: int, t: Theme) -> str:
    return f"  {t.border}|{t.reset} {pad_right(content, inner_w)} {t.border}|{t.reset}"


def render_dashboard(
    info: dict,
    burn: dict,
    quotas_data: dict | None,
    t: Theme,
    show_details: bool = False,
    active: dict | None = None,
    delta_tokens: int = 0,
) -> str:
    inner_w = 66
    rule = "-" * (inner_w + 2)
    top = f"  {t.border}+{rule}+{t.reset}"
    sep = f"  {t.border}+{rule}+{t.reset}"

    plan = lg.build_plan(quotas_data, burn) if quotas_data else None
    display_names = dict((quotas_data or {}).get("display_names") or {})

    if plan:
        avail = plan["available_models_count"]
        total = plan["total_accessible_models"]
        p_band = plan["overall_pressure"]
        p_col = t.green if p_band == "HEALTHY" else (t.amber if p_band in ("MODERATE", "LOW") else t.red)
        status = f"{p_col}[*] {p_band.title()}{t.reset} {t.muted}| {avail}/{total} models ready{t.reset}"
    else:
        status = f"{t.amber}[!] Quotas uncached{t.reset}"

    out: list[str] = [""]
    out.append(top)

    # Claude-Code-style ASCII mascot + title header
    logo1 = f"{t.accent}{t.bold}  /\\_/\\  {t.reset}"
    logo2 = f"{t.accent}{t.bold} ( o.o ) {t.reset}"
    logo3 = f"{t.peach}{t.bold}  > ^ <  {t.reset}"

    out.append(box_line(f"{logo1} {t.accent}{t.bold}ANTIGRAVITY TOKEN BUDGET{t.reset}", inner_w, t))
    out.append(box_line(f"{logo2} {status}", inner_w, t))
    out.append(box_line(f"{logo3} {t.muted}{info['gemini_root']}{t.reset}", inner_w, t))
    out.append(sep)

    # Section 1: Clean 3-column Burn Summary
    b24 = burn["last_24h"]
    b7d = burn["last_7d"]
    blf = burn["lifetime"]

    col_w = 22
    hdr = (
        pad_right(f"{t.muted}TODAY{t.reset}", col_w)
        + pad_right(f"{t.muted}LAST 7 DAYS{t.reset}", col_w)
        + f"{t.muted}ALL-TIME BURN{t.reset}"
    )
    vals = (
        pad_right(f"{t.white}{t.bold}{fmt_tokens(b24['uncached_burn_tokens'])}{t.reset} {t.muted}tokens{t.reset}", col_w)
        + pad_right(f"{t.white}{t.bold}{fmt_tokens(b7d['uncached_burn_tokens'])}{t.reset} {t.muted}tokens{t.reset}", col_w)
        + f"{t.peach}{t.bold}{fmt_tokens(blf['uncached_burn_tokens'])}{t.reset} {t.muted}({fmt_tokens(blf['total_tokens_processed'])} total){t.reset}"
    )
    subs = (
        pad_right(f"{t.green}{b24['cache_hit_rate_pct']:.0f}% cached{t.reset}", col_w)
        + pad_right(f"{t.green}{b7d['cache_hit_rate_pct']:.0f}% cached{t.reset}", col_w)
        + f"{t.green}{blf['cache_hit_rate_pct']:.0f}% saved by cache{t.reset}"
    )
    out.append(box_line(hdr, inner_w, t))
    out.append(box_line(vals, inner_w, t))
    out.append(box_line(subs, inner_w, t))

    # Active Chat (Live) section
    if active:
        out.append(sep)
        live_tag = f"{t.green}[LIVE]{t.reset}" if active["age_secs"] < 90 else f"{t.muted}[IDLE]{t.reset}"
        delta_str = f"  {t.amber}+{fmt_tokens(delta_tokens)} now{t.reset}" if delta_tokens > 0 else ""
        out.append(
            box_line(
                f"{t.accent}{t.bold}ACTIVE CHAT{t.reset} {live_tag} "
                f"{t.muted}#{active['conv_id']} ({fmt_age(active['age_secs'])}){t.reset}{delta_str}",
                inner_w,
                t,
            )
        )
        out.append(
            box_line(
                f"{t.white}{t.bold}{fmt_tokens(active['uncached'])}{t.reset} {t.muted}uncached{t.reset}  "
                f"{t.border}|{t.reset}  {t.white}{active['steps']}{t.reset} {t.muted}steps{t.reset}  "
                f"{t.border}|{t.reset}  {t.green}{active['cache_pct']:.0f}% cached{t.reset}",
                inner_w,
                t,
            )
        )
        for m_id, m_stats in active["by_model"][:3]:
            m_name = friendly_model_name(m_id, display_names)
            if len(m_name) > 28:
                m_name = m_name[:25] + "..."
            out.append(
                box_line(
                    f"  {t.sky}{pad_right(m_name, 29)}{t.reset}"
                    f"{t.white}{fmt_tokens(m_stats['uncached']):>7}{t.reset}  "
                    f"{t.muted}({m_stats['steps']} steps){t.reset}",
                    inner_w,
                    t,
                )
            )

    # Section 2: Quota Pools (ASCII bars)
    out.append(sep)
    out.append(box_line(f"{t.accent}{t.bold}MODEL QUOTAS{t.reset}", inner_w, t))
    if plan:
        for pool in plan["quota_pools"]:
            pct = pool["quota_remaining_pct"]
            col = t.green if pct >= 60 else (t.amber if pct > 0 else t.red)
            name = pad_right(f"{t.white}{friendly_pool_name(pool['models'])}{t.reset}", 22)
            bar = ascii_bar(pct, 16, col, t)
            pct_str = f"{col}{t.bold}{pct:>3}%{t.reset}"
            rst = f"{t.muted}{fmt_reset_delta(pool['quota_resets'])}{t.reset}"
            out.append(box_line(f"{name}{bar}  {pct_str}  {rst}", inner_w, t))
    else:
        out.append(
            box_line(
                f"{t.muted}Ask Antigravity to refresh your live quotas to see bars here.{t.reset}",
                inner_w,
                t,
            )
        )

    # Section 3: Simple Routing Guide
    if plan:
        out.append(sep)
        out.append(box_line(f"{t.accent}{t.bold}BEST MODEL FOR YOUR NEXT REQUEST{t.reset}", inner_w, t))
        recs = plan["per_request_recommendations"]
        t2_pick = (
            friendly_model_name(recs["T2_multifile"]["recommended_models"][0], display_names)
            if recs["T2_multifile"]["recommended_models"]
            else "flash"
        )
        t3_pick = (
            friendly_model_name(recs["T3_complex"]["recommended_models"][0], display_names)
            if recs["T3_complex"]["recommended_models"]
            else "inherit"
        )
        rows = [
            ("Quick question", "flash_lite", recs["T0_trivial"]),
            ("Small edit", "flash", recs["T1_scoped"]),
            ("Multi-file task", t2_pick, recs["T2_multifile"]),
            ("Hard / complex", t3_pick, recs["T3_complex"]),
        ]
        for label, pick, rec in rows:
            lbl = pad_right(f"{t.muted}{label}{t.reset}", 16)
            mdl = pad_right(f"{t.sky}{t.bold}{pick}{t.reset}", 27)
            cap = f"{t.lavender}<= {fmt_tokens(rec['max_output_tokens'])} tok{t.reset}"
            out.append(box_line(f"{lbl} {t.border}->{t.reset}  {mdl} {t.muted}|{t.reset} {cap}", inner_w, t))

    # Optional Section 4: Per-model breakdown (--details)
    if show_details:
        out.append(sep)
        out.append(box_line(f"{t.accent}{t.bold}TOP MODELS USED (ALL-TIME){t.reset}", inner_w, t))
        items = list((burn.get("by_model") or {}).items())[:5]
        max_b = max((v["uncached_burn_tokens"] for _, v in items), default=1) or 1
        for m_id, stats in items:
            m_name = friendly_model_name(m_id, display_names)
            if len(m_name) > 23:
                m_name = m_name[:20] + "..."
            rel = (stats["uncached_burn_tokens"] / max_b) * 100
            bar = ascii_bar(rel, 12, t.peach, t)
            out.append(
                box_line(
                    f"{pad_right(f'{t.white}{m_name}{t.reset}', 24)}{bar}  "
                    f"{t.white}{fmt_tokens(stats['uncached_burn_tokens']):>6}{t.reset}  "
                    f"{t.muted}({stats['cache_hit_rate_pct']:.0f}% cache){t.reset}",
                    inner_w,
                    t,
                )
            )

    out.append(top)
    hint = (
        f"  {t.muted}{burn['conversations_scanned']} chats scanned | "
        f"{'--details' if not show_details else 'detailed view'} | --watch 10 for live mode{t.reset}"
    )
    out.append(hint)
    out.append("")
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description="Colorful ASCII Antigravity token dashboard.")
    parser.add_argument("--quotas-file", type=str, help="Path to quotas JSON file.")
    parser.add_argument("--details", action="store_true", help="Show per-model burn breakdown.")
    parser.add_argument("--watch", type=int, default=0, help="Auto-refresh every N seconds.")
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI colors.")
    args = parser.parse_args()

    use_color = not args.no_color
    if use_color:
        enable_windows_ansi()
    theme = Theme(enabled=use_color)

    info = lg.locate_gemini()
    prev_total: int | None = None
    try:
        while True:
            burn = lg.compute_burn(info)
            cur_total = burn["lifetime"]["uncached_burn_tokens"]
            delta = (cur_total - prev_total) if prev_total is not None else 0
            prev_total = cur_total
            active = active_chat_summary(info)
            quotas_data, _ = load_quotas(info, args.quotas_file)
            rendered = render_dashboard(
                info,
                burn,
                quotas_data,
                theme,
                show_details=args.details,
                active=active,
                delta_tokens=delta,
            )
            if args.watch > 0:
                os.system("cls" if os.name == "nt" else "clear")
            print(rendered)
            if args.watch <= 0:
                break
            time.sleep(args.watch)
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

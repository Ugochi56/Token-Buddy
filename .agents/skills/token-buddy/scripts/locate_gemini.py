#!/usr/bin/env python3
"""Cross-platform Antigravity token-budget helper.

Capabilities:
  (default)   Locate the user's .gemini / Antigravity directories across OSes.
  --burn      Compute total lifetime, 7-day, and 24-hour token burn from local
              Antigravity transcripts (per-model and aggregate).
  --plan      Combine live model quotas (JSON from `swarm(action="models", all=True)`)
              with local burn telemetry to recommend per-request model routing
              and token budgets by complexity tier (T0-T3).
  --audit     Audit always-on rules, skills, plugins, and MCP prompt overhead.
  --install   Install/sync this skill into the detected global skills directory.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path


def candidate_gemini_dirs() -> list[Path]:
    """Return ordered candidate .gemini root directories for the current OS."""
    candidates: list[Path] = []

    for env_var in ("GEMINI_HOME", "ANTIGRAVITY_HOME"):
        val = os.environ.get(env_var)
        if val:
            candidates.append(Path(val).expanduser())

    home = Path.home()
    candidates.append(home / ".gemini")

    if os.name == "nt":
        for env_var in ("USERPROFILE", "LOCALAPPDATA", "APPDATA"):
            val = os.environ.get(env_var)
            if val:
                base = Path(val)
                candidates.append(base / ".gemini")
                candidates.append(base / "gemini")
    else:
        xdg = os.environ.get("XDG_CONFIG_HOME")
        if xdg:
            candidates.append(Path(xdg) / "gemini")
            candidates.append(Path(xdg) / ".gemini")

    seen: set[Path] = set()
    unique: list[Path] = []
    for path in candidates:
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        if resolved not in seen:
            seen.add(resolved)
            unique.append(resolved)
    return unique


def locate_gemini() -> dict[str, str | bool | None]:
    """Discover the active .gemini directory and its key subdirectories."""
    candidates = candidate_gemini_dirs()
    chosen: Path | None = None

    for cand in candidates:
        if cand.is_dir() and ((cand / "config").is_dir() or (cand / "antigravity").is_dir()):
            chosen = cand
            break

    if chosen is None:
        for cand in candidates:
            if cand.is_dir():
                chosen = cand
                break

    exists = chosen is not None
    if chosen is None:
        chosen = (Path.home() / ".gemini").resolve()

    config_dir = chosen / "config"
    app_data_dir = chosen / "antigravity"
    brain_dir = app_data_dir / "brain"
    skills_dir = config_dir / "skills"
    plugins_dir = config_dir / "plugins"
    mcp_config = config_dir / "mcp_config.json"

    return {
        "os": sys.platform,
        "gemini_root": str(chosen),
        "exists": exists,
        "config_dir": str(config_dir),
        "app_data_dir": str(app_data_dir),
        "brain_dir": str(brain_dir),
        "skills_dir": str(skills_dir),
        "plugins_dir": str(plugins_dir),
        "mcp_config": str(mcp_config) if mcp_config.is_file() else None,
    }


def _parse_iso_ts(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _empty_bucket() -> dict[str, int]:
    return {
        "steps": 0,
        "fresh_input_tokens": 0,
        "cache_read_tokens": 0,
        "output_tokens": 0,
    }


def _finalize_bucket(b: dict[str, int]) -> dict:
    fresh = b["fresh_input_tokens"]
    cached = b["cache_read_tokens"]
    out = b["output_tokens"]
    steps = b["steps"]
    total_prompt = fresh + cached
    return {
        "steps": steps,
        "fresh_input_tokens": fresh,
        "cache_read_tokens": cached,
        "output_tokens": out,
        "uncached_burn_tokens": fresh + out,
        "total_tokens_processed": total_prompt + out,
        "cache_hit_rate_pct": round((cached / total_prompt) * 100, 1) if total_prompt else 0.0,
        "avg_uncached_per_step": round((fresh + out) / steps) if steps else 0,
    }


def _fmt_short(n: int) -> str:
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.2f}B"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def compute_burn(info: dict[str, str | bool | None]) -> dict:
    """Scan local Antigravity transcripts to compute lifetime & recent token burn."""
    brain_dir = Path(str(info["brain_dir"]))
    now = datetime.now(timezone.utc)
    cut_24h = now - timedelta(hours=24)
    cut_7d = now - timedelta(days=7)

    lifetime = _empty_bucket()
    last_24h = _empty_bucket()
    last_7d = _empty_bucket()
    by_model: dict[str, dict[str, int]] = defaultdict(_empty_bucket)
    convs_scanned = 0
    first_ts: datetime | None = None
    last_ts: datetime | None = None

    if brain_dir.is_dir():
        for transcript in brain_dir.glob("*/.system_generated/logs/transcript.jsonl"):
            convs_scanned += 1
            try:
                with transcript.open("r", encoding="utf-8", errors="replace") as fh:
                    for line in fh:
                        if '"PLANNER_RESPONSE"' not in line:
                            continue
                        try:
                            obj = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if obj.get("type") != "PLANNER_RESPONSE":
                            continue

                        fresh = int(obj.get("input_tokens") or 0)
                        cached = int(obj.get("cache_read_tokens") or 0)
                        out = int(obj.get("output_tokens") or 0)
                        model = str(obj.get("model") or "unknown")
                        dt = _parse_iso_ts(obj.get("created_at"))

                        if dt:
                            if first_ts is None or dt < first_ts:
                                first_ts = dt
                            if last_ts is None or dt > last_ts:
                                last_ts = dt

                        for bucket in (lifetime, by_model[model]):
                            bucket["steps"] += 1
                            bucket["fresh_input_tokens"] += fresh
                            bucket["cache_read_tokens"] += cached
                            bucket["output_tokens"] += out

                        if dt and dt >= cut_7d:
                            last_7d["steps"] += 1
                            last_7d["fresh_input_tokens"] += fresh
                            last_7d["cache_read_tokens"] += cached
                            last_7d["output_tokens"] += out
                        if dt and dt >= cut_24h:
                            last_24h["steps"] += 1
                            last_24h["fresh_input_tokens"] += fresh
                            last_24h["cache_read_tokens"] += cached
                            last_24h["output_tokens"] += out
            except OSError:
                continue

    per_model = {
        m: _finalize_bucket(b)
        for m, b in sorted(
            by_model.items(),
            key=lambda kv: kv[1]["fresh_input_tokens"] + kv[1]["output_tokens"],
            reverse=True,
        )
    }

    lf_final = _finalize_bucket(lifetime)
    d7_final = _finalize_bucket(last_7d)
    d1_final = _finalize_bucket(last_24h)
    plain_summary = (
        f"Last 24h: {_fmt_short(d1_final['uncached_burn_tokens'])} real tokens burned "
        f"({d1_final['cache_hit_rate_pct']:.0f}% cached, ~{_fmt_short(d1_final['avg_uncached_per_step'])}/step) | "
        f"All-time: {_fmt_short(lf_final['uncached_burn_tokens'])} real tokens across {convs_scanned} chats "
        f"({lf_final['cache_hit_rate_pct']:.0f}% saved by cache)"
    )

    return {
        "summary": plain_summary,
        "brain_dir": str(brain_dir),
        "conversations_scanned": convs_scanned,
        "date_range": {
            "first": first_ts.isoformat() if first_ts else None,
            "last": last_ts.isoformat() if last_ts else None,
        },
        "lifetime": lf_final,
        "last_7d": d7_final,
        "last_24h": d1_final,
        "by_model": per_model,
    }


def _parse_pct(val: str | int | float | None) -> int:
    if val is None:
        return -1
    if isinstance(val, (int, float)):
        return int(val)
    s = str(val).strip().rstrip("%")
    try:
        return int(float(s))
    except ValueError:
        return -1


def _pressure_band(pct: int) -> str:
    if pct <= 0:
        return "EXHAUSTED"
    if pct < 25:
        return "LOW"
    if pct < 60:
        return "MODERATE"
    return "HEALTHY"


def _classify_model_tier(model_id: str) -> str:
    m = model_id.lower()
    if "flash" in m or m.endswith("-low"):
        return "light"
    if "opus" in m or "xhigh" in m or "argon" in m or "orchestrator" in m or m.endswith("-high"):
        return "heavy"
    return "standard"


def build_plan(quotas_payload: dict, burn_summary: dict | None = None) -> dict:
    """Group live models into quota pools and produce per-tier routing recommendations."""
    models: list[str] = list(quotas_payload.get("models") or [])
    display_names: dict[str, str] = dict(quotas_payload.get("display_names") or {})
    quotas: dict[str, dict] = dict(quotas_payload.get("quotas") or {})

    pools: dict[tuple[int, str], list[dict]] = defaultdict(list)
    for m in models:
        q = quotas.get(m) or {}
        pct = _parse_pct(q.get("quota_remaining"))
        resets = str(q.get("quota_resets") or "unknown")
        pools[(pct, resets)].append(
            {
                "id": m,
                "name": display_names.get(m, m),
                "tier": _classify_model_tier(m),
            }
        )

    pool_list = []
    available: list[dict] = []
    for (pct, resets), members in sorted(pools.items(), key=lambda kv: (-kv[0][0], kv[0][1])):
        band = _pressure_band(pct)
        pool_list.append(
            {
                "quota_remaining_pct": pct,
                "pressure": band,
                "quota_resets": resets,
                "model_count": len(members),
                "models": [x["id"] for x in members],
            }
        )
        if pct > 0:
            for x in members:
                available.append({**x, "quota_remaining_pct": pct, "pressure": band})

    def pick_best(preferred_tiers: list[str]) -> list[str]:
        ranked = sorted(
            available,
            key=lambda x: (
                preferred_tiers.index(x["tier"]) if x["tier"] in preferred_tiers else 99,
                -x["quota_remaining_pct"],
                x["id"],
            ),
        )
        return [x["id"] for x in ranked[:3]]

    max_pct = max((x["quota_remaining_pct"] for x in available), default=0)
    overall_pressure = _pressure_band(max_pct)
    budget_scale = {"HEALTHY": 1.0, "MODERATE": 0.7, "LOW": 0.4, "EXHAUSTED": 0.0}[overall_pressure]

    recommendations = {
        "T0_trivial": {
            "subagent_model": "flash_lite",
            "recommended_models": pick_best(["light", "standard"]),
            "max_output_tokens": int(400 * budget_scale),
        },
        "T1_scoped": {
            "subagent_model": "flash_lite (scan) / flash (read)",
            "recommended_models": pick_best(["light", "standard"]),
            "max_output_tokens": int(1200 * budget_scale),
        },
        "T2_multifile": {
            "subagent_model": "flash",
            "recommended_models": pick_best(["standard", "light", "heavy"]),
            "max_output_tokens": int(2500 * budget_scale),
        },
        "T3_complex": {
            "subagent_model": "flash (prep) / inherit or pro (core)",
            "recommended_models": pick_best(["heavy", "standard"]),
            "max_output_tokens": int(4500 * budget_scale),
        },
    }

    top_heavy = recommendations["T3_complex"]["recommended_models"][0] if recommendations["T3_complex"]["recommended_models"] else "inherit"
    plan_summary = (
        f"{len(available)}/{len(models)} models ready ({overall_pressure}) | "
        f"Use flash_lite/flash for quick & scoped tasks, {top_heavy} for complex work"
    )
    if burn_summary:
        plan_summary += (
            f" | {burn_summary['lifetime']['cache_hit_rate_pct']:.0f}% cached, "
            f"~{_fmt_short(burn_summary['last_24h']['avg_uncached_per_step'])} real tokens/step (24h)"
        )

    result: dict = {
        "summary": plan_summary,
        "total_accessible_models": len(models),
        "available_models_count": len(available),
        "overall_pressure": overall_pressure,
        "budget_scale_factor": budget_scale,
        "quota_pools": pool_list,
        "per_request_recommendations": recommendations,
    }
    if burn_summary:
        result["lifetime_uncached_burn"] = burn_summary["lifetime"]["uncached_burn_tokens"]
        result["last_24h_uncached_burn"] = burn_summary["last_24h"]["uncached_burn_tokens"]
        result["lifetime_cache_hit_rate_pct"] = burn_summary["lifetime"]["cache_hit_rate_pct"]
    return result


def approx_tokens(num_bytes: int) -> int:
    return max(1, round(num_bytes / 4)) if num_bytes > 0 else 0


def audit_overhead(info: dict[str, str | bool | None]) -> dict:
    """Estimate static prompt overhead from global rules, skills, and MCP configs."""
    config_dir = Path(str(info["config_dir"]))
    report: dict = {
        "gemini_root": info["gemini_root"],
        "rules": [],
        "skills_count": 0,
        "plugins_count": 0,
        "mcp_servers_count": 0,
        "estimated_always_on_rule_tokens": 0,
    }

    if not config_dir.is_dir():
        report["note"] = "Global config directory does not exist yet."
        return report

    for rule_name in ("GEMINI.md", "AGENTS.md"):
        rule_path = config_dir / rule_name
        if rule_path.is_file():
            size = rule_path.stat().st_size
            toks = approx_tokens(size)
            report["rules"].append({"path": str(rule_path), "bytes": size, "est_tokens": toks})
            report["estimated_always_on_rule_tokens"] += toks

    skills_dir = config_dir / "skills"
    if skills_dir.is_dir():
        report["skills_count"] = sum(
            1 for p in skills_dir.iterdir() if p.is_dir() and (p / "SKILL.md").is_file()
        )

    plugins_dir = config_dir / "plugins"
    if plugins_dir.is_dir():
        report["plugins_count"] = sum(1 for p in plugins_dir.iterdir() if p.is_dir())

    mcp_path = config_dir / "mcp_config.json"
    if mcp_path.is_file():
        try:
            data = json.loads(mcp_path.read_text(encoding="utf-8"))
            servers = data.get("mcpServers", {})
            if isinstance(servers, dict):
                report["mcp_servers_count"] = len(servers)
        except (OSError, json.JSONDecodeError):
            pass

    return report


def install_skill(info: dict[str, str | bool | None]) -> dict:
    """Copy this skill folder into the detected global <gemini>/config/skills/."""
    skill_src = Path(__file__).resolve().parent.parent
    skills_dest_root = Path(str(info["skills_dir"]))
    skill_dest = skills_dest_root / skill_src.name

    if skill_src.resolve() == skill_dest.resolve():
        return {"status": "already_global", "path": str(skill_dest)}

    skills_dest_root.mkdir(parents=True, exist_ok=True)
    if skill_dest.exists():
        shutil.rmtree(skill_dest)
    shutil.copytree(skill_src, skill_dest)
    return {"status": "installed", "source": str(skill_src), "destination": str(skill_dest)}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Locate .gemini, compute lifetime token burn, plan quota-aware routing, or install globally."
    )
    parser.add_argument("--burn", action="store_true", help="Compute lifetime, 7d, and 24h token burn from local transcripts.")
    parser.add_argument("--plan", action="store_true", help="Generate quota-aware model & token allocation plan.")
    parser.add_argument("--quotas-file", type=str, help="Path to JSON file from swarm(action='models', all=True).")
    parser.add_argument("--quotas-stdin", action="store_true", help="Read quotas JSON from stdin.")
    parser.add_argument("--audit", action="store_true", help="Audit always-on rule/skill/plugin/MCP overhead.")
    parser.add_argument("--install", action="store_true", help="Install this skill into the detected global skills dir.")
    args = parser.parse_args()

    info = locate_gemini()
    if args.install:
        result = {"location": info, "install": install_skill(info)}
    elif args.plan:
        if args.quotas_file:
            quotas_data = json.loads(Path(args.quotas_file).read_text(encoding="utf-8"))
        elif args.quotas_stdin:
            quotas_data = json.load(sys.stdin)
        else:
            parser.error("--plan requires --quotas-file <path> or --quotas-stdin")
        burn = compute_burn(info)
        result = build_plan(quotas_data, burn)
    elif args.burn:
        result = compute_burn(info)
    elif args.audit:
        result = audit_overhead(info)
    else:
        result = info

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

---
name: token-buddy
description: >-
  Token Buddy: adaptive token and compute budgeting for Antigravity. Use when
  optimizing token usage, checking accessible models and remaining model quotas,
  measuring lifetime/recent token burn from local transcripts, locating a user's
  .gemini config directory across OSes, or routing sub-tasks to cheaper subagent
  models (flash_lite/flash) based on request complexity and quota pressure.
---

# Token Buddy

Match model tier, context size, and compute spend to both **request complexity**
and **live remaining quota**.

## 1. Detect Models, Quotas & Lifetime Burn

Run these two steps when budgeting a session or reporting usage:

1. **Live accessible models & remaining quota**: Call `swarm` with
   `action: "models", all: true`. This returns every model the user can access,
   its `quota_remaining` (`%`), and `quota_resets` timestamp. Models sharing the
   same percentage and reset time share a quota pool.
2. **Local `.gemini` discovery & lifetime burn**: Run
   [locate_gemini.py](./scripts/locate_gemini.py) (auto-detects `.gemini` on
   Windows/macOS/Linux and scans `antigravity/brain/*/.system_generated/logs/transcript.jsonl`):

```bash
# Lifetime, 7d, and 24h token burn + per-model breakdown + cache hit rate
python scripts/locate_gemini.py --burn

# Combine live swarm quotas JSON with local burn for a per-request routing plan
python scripts/locate_gemini.py --plan --quotas-file <quotas.json>

# Audit static prompt overhead (rules, skills, plugins, MCPs)
python scripts/locate_gemini.py --audit

# Install/sync this skill into the user's global <gemini>/config/skills/
python scripts/locate_gemini.py --install

# Launch the mini CLI dashboard (add --watch 10 for live refresh)
python scripts/dashboard.py
```

When you fetch live quotas via `swarm(action="models", all=True)`, save the JSON
to `<gemini>/config/token_buddy_quotas.json` so `dashboard.py` displays live
quota pools and routing recommendations automatically. When reporting usage to
the user, lead with the plain-English `summary` line from `--burn` / `--plan`.

## 2. Classify Request Complexity & Apply Quota Pressure

Classify each request (`T0`–`T3`) and scale spend by the active pool's
remaining quota (`HEALTHY >=60%` = 1.0x, `MODERATE 25–59%` = 0.7x,
`LOW 1–24%` = 0.4x, `EXHAUSTED 0%` = switch pool):

| Tier | Request Type | Subagent Model | Context & Tool Budget | Output Ceiling (1.0x) |
| :--- | :--- | :--- | :--- | :--- |
| **T0 Trivial** | Lookup, syntax Q, typo fix, 1-step cmd | `flash_lite` (or direct, 0–1 tool) | Read target lines only; no broad scans | <=400 tok (1–5 lines) |
| **T1 Scoped** | 1–2 file edit, focused bug fix | `flash_lite` scan; `flash` read | Line ranges; truncate shell output | <=1,200 tok (diff/brief) |
| **T2 Multi-file** | 2–5 file feature, refactor, test triage | `flash` exploration & log parsing | Offload reads to `flash`; compressed notes | <=2,500 tok |
| **T3 Complex** | Architecture, race/security bug, migration | `flash`/`flash_lite` prep; `inherit`/`pro` core | Offload all raw ingestion before reasoning | <=4,500 tok |

Escalate one tier only if a lower tier fails verification. If the active pool is
`LOW` or `EXHAUSTED`, route work to an available high-quota pool or cheaper
tier. See [complexity-rubric.md](./references/complexity-rubric.md) for details.

## 3. Subagent Model Tiering & Return Discipline

Always set `Model` explicitly in `invoke_subagent`:
- **`flash_lite`**: File discovery, grep/symbol scans, log summarization, boilerplate.
- **`flash`**: Multi-file reading, module analysis, test-failure triage (`research`).
- **`inherit` / `pro`**: Core synthesis and T3 reasoning only.

Every subagent prompt MUST enforce a compact return contract (e.g., *max 10
bullets with `file:line` refs; no raw file dumps*) so parent context stays lean.

## 4. Cut Fresh Uncached Input Spikes (Cache-Miss Protection)

Fresh input (not output) is usually 85–95% of real quota burn. Protect against it:

- **Auto-suggest `/compact`**: Prompt the user to run `/compact` every ~40 steps,
  before switching models (which breaks the prompt cache), or before starting a
  new phase/feature in the same chat.
- **Keep raw dumps out of main chat**: Offload multi-file reads and log scans to
  `flash_lite`/`flash` subagents so bulky tool output stays in throwaway subagent
  context instead of inflating the parent chat's history.
- **Read slices & filter logs**: Always use `StartLine`/`EndLine` and pipe noisy
  shell commands through `Select-Object -First` / `head` / `grep`.
- **Flag prompt bloat**: When running `--audit` or reporting usage, flag high
  plugin counts (>5 global plugins) and long chats (>45 steps) driving cache-miss
  spikes.

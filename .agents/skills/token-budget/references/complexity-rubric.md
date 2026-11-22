# Complexity Rubric, Quota Pressure & Delegation Patterns

Read this reference only when a request is ambiguous between tiers or when
tuning quota-constrained routing.

## Quota Pressure Multipliers

| Pool Remaining | Pressure | Policy |
| :--- | :--- | :--- |
| **>= 60%** | `HEALTHY` (1.0x) | Standard tier routing; still offload bulk scans to `flash_lite`/`flash`. |
| **25% – 59%** | `MODERATE` (0.7x) | Tighten output ceilings by 30%; prefer `flash`/`low` variants for T0–T2. |
| **1% – 24%** | `LOW` (0.4x) | Conservation mode: force `flash_lite`/`flash` for all prep; shift heavy tasks to another pool with higher quota; suggest `/compact`. |
| **0%** | `EXHAUSTED` (0.0x) | Never route to this pool; switch to a pool with remaining quota and note `quota_resets`. |

## Tier Decision Heuristics

### T0 — Trivial (<=400 output tokens at 1.0x)
- **Signals**: Direct factual Q, one-line fix, single symbol lookup, formatting.
- **Action**: Answer directly or run 1 targeted tool call. Do not spawn a
  subagent unless scanning >3 files.

### T1 — Scoped (<=1,200 output tokens at 1.0x)
- **Signals**: Isolated bug fix, adding a helper/test in 1–2 files, explaining
  one function or stack trace.
- **Action**: Invoke `research` with `Model: "flash_lite"` to return exact
  `file:line` targets, then edit directly.

### T2 — Multi-file / Analytical (<=2,500 output tokens at 1.0x)
- **Signals**: Feature touching 2–5 files, unfamiliar codebase exploration,
  diagnosing flaky tests or build pipelines.
- **Action**:
  1. Delegate mapping and log parsing to `research` with `Model: "flash"` (or
     parallel `flash_lite` workers for independent folders).
  2. Require each subagent to return <=200 words with exact line ranges.
  3. Perform final synthesis and edits in the primary model.

### T3 — Deep / Architectural (<=4,500 output tokens at 1.0x)
- **Signals**: System redesign, concurrency/security bugs, cross-cutting
  migrations with high blast radius.
- **Action**:
  1. Offload all mechanical inventory (call sites, configs, schemas) to
     `flash_lite` / `flash` subagents first.
  2. Keep the primary model's context focused strictly on distilled evidence
     and architectural trade-offs.

## Subagent Prompt Template (Low-Token Return)

```text
Task: <specific question or scan>
Scope: <directory or file list>
Output rules:
- Max 10 bullet points.
- Cite exact `path:start-end` line numbers.
- Do NOT quote full functions or raw logs (>10 lines).
- State "NOT FOUND" if absent rather than speculating.
```

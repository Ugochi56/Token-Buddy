#!/usr/bin/env sh
# Token Buddy 1-line installer for macOS & Linux
# Usage: curl -fsSL https://raw.githubusercontent.com/Ugochi56/Token-Buddy/main/install.sh | sh

set -eu

RAW_BASE="https://raw.githubusercontent.com/Ugochi56/Token-Buddy/main/.agents/skills/token-budget"

# Auto-detect .gemini root
GEMINI_ROOT=""
for cand in "${GEMINI_HOME:-}" "${ANTIGRAVITY_HOME:-}" "$HOME/.gemini" "${XDG_CONFIG_HOME:-$HOME/.config}/gemini"; do
  [ -n "$cand" ] || continue
  if [ -d "$cand/config" ] || [ -d "$cand/antigravity" ]; then
    GEMINI_ROOT="$cand"
    break
  fi
done
[ -n "$GEMINI_ROOT" ] || GEMINI_ROOT="$HOME/.gemini"

CONFIG_DIR="$GEMINI_ROOT/config"
DEST="$CONFIG_DIR/skills/token-budget"
mkdir -p "$DEST/scripts" "$DEST/references"

echo "Installing Token Buddy into $DEST ..."
for f in SKILL.md references/complexity-rubric.md scripts/locate_gemini.py scripts/dashboard.py; do
  curl -fsSL "$RAW_BASE/$f" -o "$DEST/$f"
done

# Upsert tiny always-on rule in <gemini>/config/GEMINI.md so Token Buddy auto-runs in every chat
GEMINI_MD="$CONFIG_DIR/GEMINI.md"
python3 - "$GEMINI_MD" <<'PYEOF'
import re, sys
from pathlib import Path

p = Path(sys.argv[1])
start, end = "<!-- TOKEN-BUDDY:START -->", "<!-- TOKEN-BUDDY:END -->"
block = f"""{start}
## Token Buddy (Always-On Token Discipline)
- **Match compute to complexity**: Keep T0/T1 answers brief; escalate only when needed.
- **Delegate bulk work**: Use `invoke_subagent` with `Model: "flash_lite"` for file/symbol scans & log summaries, and `Model: "flash"` for multi-file research (`research`). Require compact bullet returns (`file:line` refs, no raw file dumps).
- **Lean context & cache protection**: Read targeted line ranges (`StartLine`/`EndLine`), filter noisy shell output, keep raw dumps inside subagents, and proactively suggest `/compact` every ~40 steps, before switching models, or when starting a new feature.
- **Token usage & quotas**: Whenever the user asks about token usage, burn, model quotas, or Token Buddy, use the `token-budget` skill (`swarm(action="models", all=True)` + `locate_gemini.py --burn`), save live quotas to `<gemini>/config/token_budget_quotas.json`, and report the live summary.
{end}"""

existing = p.read_text(encoding="utf-8") if p.is_file() else ""
pat = re.compile(rf"{re.escape(start)}.*?{re.escape(end)}", re.DOTALL)
if pat.search(existing):
    updated = pat.sub(block, existing)
else:
    sep = "\n\n" if existing.strip() else ""
    updated = existing.rstrip() + sep + block + "\n"
p.write_text(updated, encoding="utf-8")
PYEOF

# Create `token-buddy` CLI launcher
BIN_DIR="$HOME/.local/bin"
mkdir -p "$BIN_DIR"
DASHBOARD="$DEST/scripts/dashboard.py"
SHIM="$BIN_DIR/token-buddy"
cat > "$SHIM" <<EOF
#!/usr/bin/env sh
exec python3 "$DASHBOARD" "\$@"
EOF
chmod +x "$SHIM"

echo ""
echo "Token Buddy installed (auto-enabled in all Antigravity chats)!"
echo "  Skill    : $DEST"
echo "  Rule     : $GEMINI_MD"
echo "  Launcher : $SHIM"
case ":${PATH:-}:" in
  *":$BIN_DIR:"*) echo "  Live CLI : token-buddy --watch 5" ;;
  *) echo "  Note     : Add $BIN_DIR to PATH, or run: python3 \"$DASHBOARD\"" ;;
esac

# Auto-run the dashboard immediately
python3 "$DASHBOARD"

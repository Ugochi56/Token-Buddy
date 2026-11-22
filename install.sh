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

DEST="$GEMINI_ROOT/config/skills/token-budget"
mkdir -p "$DEST/scripts" "$DEST/references"

echo "Installing Token Buddy into $DEST ..."
for f in SKILL.md references/complexity-rubric.md scripts/locate_gemini.py scripts/dashboard.py; do
  curl -fsSL "$RAW_BASE/$f" -o "$DEST/$f"
done

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
echo "Token Buddy installed!"
echo "  Skill    : $DEST"
echo "  Launcher : $SHIM"
case ":${PATH:-}:" in
  *":$BIN_DIR:"*) echo "  Run now  : token-buddy --watch 5" ;;
  *) echo "  Note     : Add $BIN_DIR to PATH, or run: python3 \"$DASHBOARD\"" ;;
esac

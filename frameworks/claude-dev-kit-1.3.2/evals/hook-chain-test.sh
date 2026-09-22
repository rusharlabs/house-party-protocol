#!/usr/bin/env bash
# hook-chain-test.sh — test repo WITH a pre-existing pre-commit hook: confirms that this
# kit's install_git_hook.py CHAINS (never replaces) a hook that is already there.
#
# Usage: bash evals/hook-chain-test.sh
# Exit: 0 = original + new payload, BOTH run, in this order · 1 = failed

set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KIT_DIR="$(cd "$HERE/.." && pwd)"
INSTALLER="$KIT_DIR/scripts/install_git_hook.py"

WORK="$(mktemp -d)"
mkdir -p "$WORK/.git/hooks"

# 1. PRE-EXISTING pre-commit hook (simulates a real project with a hook of its own)
cat > "$WORK/.git/hooks/pre-commit" <<'EOF'
#!/bin/sh
echo "original-pre-commit-ran" >> "$1"
EOF
chmod +x "$WORK/.git/hooks/pre-commit" 2>/dev/null

# 2. the claude-dev-kit payload
cat > "$WORK/payload.sh" <<'EOF'
#!/bin/sh
echo "claude-dev-kit-payload-ran" >> "$1"
EOF

echo "=== installing (must CHAIN, not replace) ==="
python "$INSTALLER" --repo "$WORK" --hook-name pre-commit --payload "$WORK/payload.sh"
INSTALL_EXIT=$?

echo "=== running the resulting pre-commit ==="
LOG="$WORK/log.txt"
rm -f "$LOG"
sh "$WORK/.git/hooks/pre-commit" "$LOG"
RUN_EXIT=$?

echo "--- log content ---"
cat "$LOG" 2>/dev/null

ORIGINAL_RAN=$(grep -c "original-pre-commit-ran" "$LOG" 2>/dev/null || echo 0)
PAYLOAD_RAN=$(grep -c "claude-dev-kit-payload-ran" "$LOG" 2>/dev/null || echo 0)
ORDER_OK=0
if [ -f "$LOG" ]; then
  FIRST=$(grep -n "original-pre-commit-ran\|claude-dev-kit-payload-ran" "$LOG" | head -1)
  echo "$FIRST" | grep -q "original-pre-commit-ran" && ORDER_OK=1
fi

rm -rf "$WORK" 2>/dev/null

if [ "$INSTALL_EXIT" = "0" ] && [ "$ORIGINAL_RAN" -ge "1" ] && [ "$PAYLOAD_RAN" -ge "1" ] && [ "$ORDER_OK" = "1" ]; then
  echo "[OK] original hook + new payload, both ran, original FIRST (chain-preserving proven)"
  exit 0
else
  echo "[FAIL] install_exit=$INSTALL_EXIT original_ran=$ORIGINAL_RAN payload_ran=$PAYLOAD_RAN order_ok=$ORDER_OK"
  exit 1
fi

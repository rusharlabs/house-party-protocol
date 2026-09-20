#!/usr/bin/env bash
# hook-chain-test.sh — repo de teste COM hook pre-commit prévio: confirma que o
# install_git_hook.py deste kit ENCADEIA (nunca substitui) um hook já existente.
#
# Uso: bash evals/hook-chain-test.sh
# Exit: 0 = original + payload novo, os DOIS rodam, nesta ordem · 1 = falhou

set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KIT_DIR="$(cd "$HERE/.." && pwd)"
INSTALLER="$KIT_DIR/scripts/install_git_hook.py"

WORK="$(mktemp -d)"
mkdir -p "$WORK/.git/hooks"

# 1. hook pre-commit PRÉVIO já existente (simula um projeto real com hook próprio)
cat > "$WORK/.git/hooks/pre-commit" <<'EOF'
#!/bin/sh
echo "original-pre-commit-ran" >> "$1"
EOF
chmod +x "$WORK/.git/hooks/pre-commit" 2>/dev/null

# 2. payload do claude-dev-kit
cat > "$WORK/payload.sh" <<'EOF'
#!/bin/sh
echo "claude-dev-kit-payload-ran" >> "$1"
EOF

echo "=== instalando (deve ENCADEAR, não substituir) ==="
python "$INSTALLER" --repo "$WORK" --hook-name pre-commit --payload "$WORK/payload.sh"
INSTALL_EXIT=$?

echo "=== executando o pre-commit resultante ==="
LOG="$WORK/log.txt"
rm -f "$LOG"
sh "$WORK/.git/hooks/pre-commit" "$LOG"
RUN_EXIT=$?

echo "--- conteúdo do log ---"
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
  echo "[OK] hook original + payload novo, ambos rodaram, original PRIMEIRO (chain-preserving provado)"
  exit 0
else
  echo "[FAIL] install_exit=$INSTALL_EXIT original_ran=$ORIGINAL_RAN payload_ran=$PAYLOAD_RAN order_ok=$ORDER_OK"
  exit 1
fi

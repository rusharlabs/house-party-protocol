#!/usr/bin/env bash
# collision-2lanes.sh — 2+ writers concorrentes, 1 board.jsonl, zero corrupção.
#
# Dispara N processos `lane_board.py claim` SIMULTANEAMENTE (mesmo instante, via
# background + wait) contra o MESMO board.jsonl. O lock (os.mkdir + spin ≤2s) deve
# serializar as escritas: nenhuma linha corrompida/interleaved, todos os N eventos
# presentes, JSON válido linha-a-linha.
#
# Uso: bash evals/collision-2lanes.sh [N]   (default N=10)
# Exit: 0 = zero corrupção, N/N eventos presentes · 1 = corrupção ou evento perdido

set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KIT_DIR="$(cd "$HERE/.." && pwd)"
SCRIPT="$KIT_DIR/scripts/lane_board.py"
N="${1:-10}"

to_native() { if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s' "$1"; fi }

WORK="$(mktemp -d)"
WORK_N="$(to_native "$WORK")"
export CLAUDE_PROJECT_DIR="$WORK_N"

echo "=== firing $N concurrent processes (lane_board.py claim) at 1 board ==="
pids=()
for i in $(seq 1 "$N"); do
  python "$SCRIPT" claim "ITEM-$i" --lane "lane-$i" --model "claude-opus-4-8" >/dev/null 2>&1 &
  pids+=("$!")
done

FAILED=0
for pid in "${pids[@]}"; do
  wait "$pid" || FAILED=$((FAILED + 1))
done

BOARD="$WORK/.claude/lanes/board.jsonl"
if [ ! -f "$BOARD" ]; then
  echo "[FAIL] board.jsonl was not created"
  rm -rf "$WORK" 2>/dev/null
  exit 1
fi

TOTAL_LINES=$(wc -l < "$BOARD" | tr -d ' ')
VALID_JSON=$(python -c "
import json, sys
path = sys.argv[1]
total = 0
valid = 0
items = set()
with open(path, encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        total += 1
        try:
            obj = json.loads(line)
            valid += 1
            items.add(obj.get('item_id'))
        except json.JSONDecodeError:
            pass
print(f'{valid}/{total} valid lines; {len(items)} distinct items')
" "$BOARD")

echo "total lines in the board: $TOTAL_LINES"
echo "JSON validation: $VALID_JSON"

EXPECTED="$N/$N"
ITEMS_OK=$(echo "$VALID_JSON" | grep -o "^[0-9]*/[0-9]*" | grep -c "^$EXPECTED$" || true)
DISTINCT_ITEMS=$(echo "$VALID_JSON" | grep -oE '[0-9]+ distinct items' | grep -oE '^[0-9]+')

if [ "$ITEMS_OK" = "1" ] && [ "$DISTINCT_ITEMS" = "$N" ] && [ "$FAILED" = "0" ]; then
  echo "[OK] zero corruption: $N/$N valid lines, $N distinct items, 0 processes with exit!=0"
  RESULT=0
else
  echo "[FAIL] expected $N/$N valid + $N distinct items + 0 failures; got: $VALID_JSON (failed processes: $FAILED)"
  RESULT=1
fi

rm -rf "$WORK" 2>/dev/null
exit $RESULT

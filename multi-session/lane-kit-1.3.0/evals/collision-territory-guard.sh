#!/usr/bin/env bash
# collision-territory-guard.sh - the 2 territory cases of the lane engine, through the hook's
# REAL interface (stdin JSON -> stdout JSON). Runs 3x and demands an identical result
# (pass^k=1.00, k=3 - loop-passk RULE 2).
#
# T1 . exclusive territory: another live lane claimed the path -> warns (name+age),
#      a path outside the territory -> silence
# T2 . red zone: warns even with an empty registry (solo); a lane with a 35min heartbeat
#      (dead) claiming territory = zero false positives
#
# Usage: bash evals/collision-territory-guard.sh
# Exit: 0 = 3/3 runs with every check green . 1 = a run failed

set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KIT_DIR="$(cd "$HERE/.." && pwd)"
LANE_IO="$KIT_DIR/hooks/_lane_io.py"
GUARD="$KIT_DIR/hooks/lane_territory_guard.py"

PASS=0
FAIL=0
report() {
  if [ "$1" = "0" ]; then echo "  [OK] $2"; PASS=$((PASS + 1)); else echo "  [FAIL] $2"; FAIL=$((FAIL + 1)); fi
}

to_native() { if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s' "$1"; fi }

invoke_guard() {
  local file_path="$1"
  python -c "import json,sys; print(json.dumps({'tool_input':{'file_path':sys.argv[1]}}))" "$file_path" | python "$GUARD" 2>"$STDERR_TMP"
}

run_round() {
  local round="$1"
  WORK="$(mktemp -d)"
  WORK_N="$(to_native "$WORK")"
  export CLAUDE_PROJECT_DIR="$WORK_N"
  STDERR_TMP="$(mktemp)"
  mkdir -p "$WORK/scripts/vm" "$WORK/scripts/other" "$WORK/.claude" "$WORK/deep/nested"

  python "$LANE_IO" register --lane exec-a --role executor --session s1 --model claude-opus-4-8 \
    --exclusive "scripts/vm/**" >/dev/null

  export CLAUDE_LANE_ID="exec-b"

  # T1a - inside exec-a exclusive territory -> warns (name + age), with no "decision"
  OUT=$(invoke_guard "$WORK_N/scripts/vm/x.py")
  ERR=$(cat "$STDERR_TMP" 2>/dev/null)
  if [ "$OUT" = "{}" ] && echo "$ERR" | grep -q "exec-a" && echo "$ERR" | grep -qE "[0-9]+min"; then
    report 0 "round$round T1a: exclusive territory warns exec-a + age, no decision"
  else
    report 1 "round$round T1a failed: OUT=$OUT ERR=$ERR"
  fi

  # T1b - outside the territory -> silence
  : > "$STDERR_TMP"
  OUT=$(invoke_guard "$WORK_N/scripts/other/y.py")
  ERR=$(cat "$STDERR_TMP" 2>/dev/null)
  [ "$OUT" = "{}" ] && [ -z "$ERR" ] && report 0 "round$round T1b: outside the territory = silence" \
    || report 1 "round$round T1b failed: OUT=$OUT ERR=$ERR"

  # T1c - the owner editing its own territory -> silence
  : > "$STDERR_TMP"
  export CLAUDE_LANE_ID="exec-a"
  OUT=$(invoke_guard "$WORK_N/scripts/vm/x.py")
  ERR=$(cat "$STDERR_TMP" 2>/dev/null)
  [ "$OUT" = "{}" ] && [ -z "$ERR" ] && report 0 "round$round T1c: the owner in its own territory = silence" \
    || report 1 "round$round T1c failed: OUT=$OUT ERR=$ERR"
  export CLAUDE_LANE_ID="exec-b"

  # T2a - red zone with an existing registry but NO other lane claiming -> warns anyway
  : > "$STDERR_TMP"
  OUT=$(invoke_guard "$WORK_N/.claude/settings.local.json")
  ERR=$(cat "$STDERR_TMP" 2>/dev/null)
  [ "$OUT" = "{}" ] && echo "$ERR" | grep -q "RED ZONE" && report 0 "round$round T2a: red zone warns (settings.local.json)" \
    || report 1 "round$round T2a failed: OUT=$OUT ERR=$ERR"

  # T2b - the ** glob matches a nested MEMORY.md
  : > "$STDERR_TMP"
  OUT=$(invoke_guard "$WORK_N/deep/nested/MEMORY.md")
  ERR=$(cat "$STDERR_TMP" 2>/dev/null)
  [ "$OUT" = "{}" ] && echo "$ERR" | grep -q "RED ZONE" && report 0 "round$round T2b: glob ** matches a nested MEMORY.md" \
    || report 1 "round$round T2b failed: OUT=$OUT ERR=$ERR"

  # T2c - exec-a with a 35min heartbeat (dead) claiming territory -> zero false positives
  python -c "
import json, time
from pathlib import Path
p = Path(r'$WORK_N') / '.claude' / 'lanes' / 'registry.json'
reg = json.loads(p.read_text(encoding='utf-8'))
from datetime import datetime, timezone
dead = datetime.fromtimestamp(time.time() - 35*60, tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
reg['lanes']['exec-a']['heartbeat_at'] = dead
p.write_text(json.dumps(reg), encoding='utf-8')
"
  : > "$STDERR_TMP"
  OUT=$(invoke_guard "$WORK_N/scripts/vm/x.py")
  ERR=$(cat "$STDERR_TMP" 2>/dev/null)
  if [ "$OUT" = "{}" ] && ! echo "$ERR" | grep -q "exec-a"; then
    report 0 "round$round T2c: a dead lane claiming territory = zero false positives"
  else
    report 1 "round$round T2c failed: OUT=$OUT ERR=$ERR"
  fi

  # structural check: in NONE of the cases above did stdout carry "decision" (WARN-only by construction)
  unset CLAUDE_LANE_ID
  rm -f "$STDERR_TMP"
  rm -rf "$WORK" 2>/dev/null
}

for round in 1 2 3; do
  echo "=== ROUND $round/3 ==="
  run_round "$round"
done

echo ""
TOTAL=$((PASS + FAIL))
echo "collision-territory-guard: $PASS/$TOTAL checks green over 3 rounds (pass^k=1.00 requires $TOTAL/$TOTAL)"
[ "$FAIL" = "0" ] && exit 0 || exit 1

#!/usr/bin/env bash
# collision-git-guard.sh — os 2 casos de colisão-git do lane-engine, via a interface REAL
# do hook (stdin JSON -> stdout JSON), contra um repositório git de verdade. Roda 3x e
# exige resultado idêntico (pass^k=1.00, k=3 — loop-passk REGRA 2).
#
# G1 · rival vivo + comando perigoso -> modo warn: avisa em stderr, sem decision, exit 0;
#      modo block: decision:block + permissionDecision:deny, exit 0
# G2 · comando seguro (pathspec explícito) sempre libera; solo libera mesmo com -am;
#      lane com heartbeat de 35min (morta) = zero falso-positivo
# Rider · 10 processos concorrentes de register/heartbeat -> registry.json continua JSON válido
#
# Uso: bash evals/collision-git-guard.sh
# Exit: 0 = 3/3 rodadas com todos os checks verdes · 1 = alguma rodada falhou

set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KIT_DIR="$(cd "$HERE/.." && pwd)"
LANE_IO="$KIT_DIR/hooks/_lane_io.py"
GUARD="$KIT_DIR/hooks/lane_git_guard.py"

PASS=0
FAIL=0
report() {
  if [ "$1" = "0" ]; then echo "  [OK] $2"; PASS=$((PASS + 1)); else echo "  [FAIL] $2"; FAIL=$((FAIL + 1)); fi
}

to_native() { if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s' "$1"; fi }

invoke_guard() {
  local cmd="$1"
  python -c "import json,sys; print(json.dumps({'tool_input':{'command':sys.argv[1]}}))" "$cmd" | python "$GUARD"
}

run_round() {
  local round="$1"
  WORK="$(mktemp -d)"
  WORK_N="$(to_native "$WORK")"
  export CLAUDE_PROJECT_DIR="$WORK_N"
  ( cd "$WORK" && git init -q && git config user.email "eval@example.com" && git config user.name "Eval" \
      && echo "seed" > seed.txt && git add seed.txt && git commit -qm "seed" )

  # registra rival vivo (exec-a) como "outra lane"
  python "$LANE_IO" register --lane exec-a --role executora --session s1 --model claude-opus-4-8 >/dev/null

  export CLAUDE_LANE_ID="exec-b"
  unset LANE_GIT_GUARD_BYPASS

  # G1a — modo warn: avisa, sem decision
  export LANE_GIT_GUARD_MODE="warn"
  STDERR_CAPTURE="$(mktemp)"
  OUT=$(invoke_guard "git commit -am x" 2>"$STDERR_CAPTURE")
  ERR=$(cat "$STDERR_CAPTURE" 2>/dev/null); rm -f "$STDERR_CAPTURE"
  if ! echo "$OUT" | grep -q '"decision"' && echo "$ERR" | grep -q "LANE-GIT-GUARD" && echo "$ERR" | grep -q "exec-a"; then
    report 0 "round$round G1a: warn mode warns (stderr names exec-a), no decision"
  else
    report 1 "round$round G1a failed: OUT=$OUT ERR=$ERR"
  fi

  # G1b — modo block: decision:block + permissionDecision:deny
  export LANE_GIT_GUARD_MODE="block"
  OUT=$(invoke_guard "git commit -am x")
  echo "$OUT" | grep -q '"decision": *"block"' && echo "$OUT" | grep -q '"permissionDecision": *"deny"' \
    && report 0 "round$round G1b: block mode -> decision:block + permissionDecision:deny" \
    || report 1 "round$round G1b failed: OUT=$OUT"

  # G2a — comando seguro (pathspec explicito) sempre libera, mesmo em modo block
  OUT=$(invoke_guard "git commit -m x -- file.py")
  [ "$OUT" = "{}" ] && report 0 "round$round G2a: an explicit pathspec releases even in block mode" \
    || report 1 "round$round G2a failed: OUT=$OUT"

  # G2b — solo (evict exec-a) libera mesmo com -am
  python "$LANE_IO" evict --lane exec-a >/dev/null
  OUT=$(invoke_guard "git commit -am x")
  [ "$OUT" = "{}" ] && report 0 "round$round G2b: solo releases even with -am" \
    || report 1 "round$round G2b failed: OUT=$OUT"

  # G2c — lane com heartbeat de 35min (morta) = zero falso-positivo
  python "$LANE_IO" register --lane exec-a --role executora --session s1 --model claude-opus-4-8 >/dev/null
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
  OUT=$(invoke_guard "git commit -am x")
  [ "$OUT" = "{}" ] && report 0 "round$round G2c: dead lane = zero false positives" \
    || report 1 "round$round G2c failed: OUT=$OUT"

  # Rider — 10 processos concorrentes de register/heartbeat -> registry.json continua valido
  pids=()
  for i in $(seq 1 10); do
    if [ $((i % 2)) -eq 0 ]; then
      python "$LANE_IO" heartbeat --lane exec-a --throttle 0 >/dev/null 2>&1 &
    else
      python "$LANE_IO" register --lane "rider-$i" --role executora --session "s$i" --model claude-opus-4-8 >/dev/null 2>&1 &
    fi
    pids+=("$!")
  done
  for pid in "${pids[@]}"; do wait "$pid" || true; done
  VALID=$(python -c "
import json
try:
    json.load(open(r'$WORK_N/.claude/lanes/registry.json', encoding='utf-8'))
    print('ok')
except Exception as e:
    print('FAIL:' + str(e))
")
  [ "$VALID" = "ok" ] && report 0 "round$round rider: 10 concurrent processes -> registry.json is still valid JSON" \
    || report 1 "round$round rider failed: $VALID"

  unset LANE_GIT_GUARD_MODE CLAUDE_LANE_ID
  rm -rf "$WORK" 2>/dev/null
}

for round in 1 2 3; do
  echo "=== ROUND $round/3 ==="
  run_round "$round"
done

echo ""
TOTAL=$((PASS + FAIL))
echo "collision-git-guard: $PASS/$TOTAL checks green over 3 rounds (pass^k=1.00 requires $TOTAL/$TOTAL)"
[ "$FAIL" = "0" ] && exit 0 || exit 1

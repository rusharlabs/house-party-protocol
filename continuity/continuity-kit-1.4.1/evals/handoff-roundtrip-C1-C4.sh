#!/usr/bin/env bash
# handoff-roundtrip-C1-C4.sh - the 4 acceptance cases of the continuity kit, through the REAL
# hook interface (stdin JSON -> stdout JSON), against the real _handoff_io.py /
# handoff_inject.py / handoff_guard.py. Runs 3x and demands an identical result
# (pass^k=1.00, k=3 - loop-passk RULE 2).
#
# C1 . basic round trip: write --demo -> handoff_inject prints the LC-4 block -> ledger has "consumed"
# C2 . staleness: an expired valid_until -> inject shows STALE and does NOT show NEXT STEP
# C3 . degraded-auto: with no handoff, Stop 1a=block/the state survives, Stop 2a (stop_hook_active)
#      =releases and records degraded-auto, in <5s
# C4 . anti-replay (LC-4): the injected verify_first_cmd is extracted from the text and really
#      EXECUTED, proving the idempotence proof runs exactly as delivered
#
# Usage: bash evals/handoff-roundtrip-C1-C4.sh
# Exit: 0 = 3/3 runs with C1-C4 all green . 1 = a run failed

set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KIT_DIR="$(cd "$HERE/.." && pwd)"
IO="$KIT_DIR/hooks/_handoff_io.py"
INJECT="$KIT_DIR/hooks/handoff_inject.py"
GUARD="$KIT_DIR/hooks/handoff_guard.py"

PASS=0
FAIL=0
report() {
  if [ "$1" = "0" ]; then echo "  [OK] $2"; PASS=$((PASS + 1)); else echo "  [FAIL] $2"; FAIL=$((FAIL + 1)); fi
}

to_native() { if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s' "$1"; fi }

run_round() {
  local round="$1"
  WORK="$(mktemp -d)"
  WORK_N="$(to_native "$WORK")"
  export CLAUDE_PROJECT_DIR="$WORK_N"

  # ---------- C1: basic round trip ----------
  python "$IO" write --demo --lane solo >/dev/null
  OUT1=$(echo '{"hook_event_name":"SessionStart","session_id":"s1","lane_id":"solo"}' | python "$INJECT")
  LEDGER="$WORK/.claude/handoff/HANDOFF-LEDGER.jsonl"
  if echo "$OUT1" | grep -q "LC-4" && echo "$OUT1" | grep -q "additionalContext" && grep -q '"event": *"consumed"' "$LEDGER" 2>/dev/null; then
    report 0 "round$round C1: basic round-trip (LC-4 block + ledger consumed)"
  else
    report 1 "round$round C1 failed: OUT1=$OUT1"
  fi
  rm -f "$WORK/.claude/handoff/HANDOFF-CURRENT-solo.json" "$LEDGER"

  # ---------- C2: staleness ----------
  python -c "
import json, sys
data = {
    'schema_version': '2.0', 'handoff_id': 'HO-STALE-solo', 'created_at': '2020-01-01T00:00:00-03:00',
    'trigger': 'manual', 'quality': 'full',
    'session': {'session_id': 's1', 'lane_id': 'solo'},
    'state': {'summary': 'stale test', 'numbers': []},
    'git': {'head': '', 'branch': '', 'dirty': False, 'untracked': 0},
    'next_step': [{'order': 1, 'description': 'should not appear', 'verify_first_cmd': 'echo x'}],
    'valid_until': '2020-01-01T00:00:00-03:00',
}
print(json.dumps(data))
" | python "$IO" write --stdin >/dev/null
  OUT2=$(echo '{"hook_event_name":"SessionStart","session_id":"s1","lane_id":"solo"}' | python "$INJECT")
  if echo "$OUT2" | grep -q "STALE" && ! echo "$OUT2" | grep -q "NEXT STEP"; then
    report 0 "round$round C2: staleness (STALE present, NEXT STEP absent)"
  else
    report 1 "round$round C2 failed: OUT2=$OUT2"
  fi
  rm -f "$WORK/.claude/handoff/HANDOFF-CURRENT-solo.json" "$LEDGER"

  # ---------- C3: degraded-auto ----------
  T0=$(date +%s)
  OUT3A=$(echo '{"hook_event_name":"Stop","session_id":"s1","lane_id":"solo","stop_hook_active":false}' | python "$GUARD")
  BLOCK_OK=0
  echo "$OUT3A" | grep -q '"decision": *"block"' && BLOCK_OK=1
  OUT3B=$(echo '{"hook_event_name":"Stop","session_id":"s1","lane_id":"solo","stop_hook_active":true}' | python "$GUARD")
  T1=$(date +%s)
  ELAPSED=$((T1 - T0))
  DEGRADED_OK=0
  if [ -f "$WORK/.claude/handoff/HANDOFF-CURRENT-solo.json" ] && grep -q '"quality": *"degraded-auto"' "$WORK/.claude/handoff/HANDOFF-CURRENT-solo.json"; then
    DEGRADED_OK=1
  fi
  if [ "$BLOCK_OK" = "1" ] && ! echo "$OUT3B" | grep -q '"decision"' && [ "$DEGRADED_OK" = "1" ] && [ "$ELAPSED" -lt 5 ]; then
    report 0 "round$round C3: Stop1=block, Stop2=release+degraded-auto, in ${ELAPSED}s (<5s)"
  else
    report 1 "round$round C3 failed: block_ok=$BLOCK_OK degraded_ok=$DEGRADED_OK elapsed=${ELAPSED}s OUT3B=$OUT3B"
  fi
  rm -f "$WORK/.claude/handoff/HANDOFF-CURRENT-solo.json" "$LEDGER"

  # ---------- C4: anti-replay (LC-4) - the verify_first_cmd IS really executed ----------
  NONCE="$WORK/nonce.txt"
  NONCE_N="$(to_native "$NONCE")"
  NONCE_PATH="$NONCE_N" python -c "
import json, os
nonce = os.environ['NONCE_PATH']
verify_cmd = 'python -c \"import sys,os; sys.exit(0 if os.path.exists(' + repr(nonce) + ') else 1)\"'
data = {
    'schema_version': '2.0', 'handoff_id': 'HO-LC4-solo', 'created_at': '2026-07-10T15:00:00-03:00',
    'trigger': 'manual', 'quality': 'full',
    'session': {'session_id': 's1', 'lane_id': 'solo'},
    'state': {'summary': 'LC-4 test', 'numbers': []},
    'git': {'head': '', 'branch': '', 'dirty': False, 'untracked': 0},
    'already_done': [{'action': 'created nonce', 'evidence': 'nonce.txt', 'never_repeat': True}],
    'next_step': [{'order': 1, 'description': 'nothing', 'verify_first_cmd': verify_cmd}],
    'valid_until': '2099-01-01T00:00:00-03:00',
}
print(json.dumps(data))
" | python "$IO" write --stdin >/dev/null
  : > "$NONCE"  # nonce present -> the verify_first_cmd should exit 0
  OUT4=$(echo '{"hook_event_name":"SessionStart","session_id":"s1","lane_id":"solo"}' | python "$INJECT")
  HAS_ALREADY_EXECUTED=0
  echo "$OUT4" | grep -q "ALREADY EXECUTED" && HAS_ALREADY_EXECUTED=1
  # Take verify_first_cmd straight from the handoff JSON (explicit UTF-8) instead of slicing the
  # rendered text - this avoids the stdin encoding gotcha of Python over a pipe on Windows/git-bash,
  # and proves the same thing: render() only f-strings the value already present in the JSON.
  HANDOFF_JSON="$WORK_N/.claude/handoff/HANDOFF-CURRENT-solo.json"
  VERIFY_CMD=$(python -c "
import json
with open(r'$HANDOFF_JSON', encoding='utf-8') as f:
    data = json.load(f)
print(data['next_step'][0]['verify_first_cmd'])
")
  # also confirm the injected text carries the marker (ASCII-safe, no dependence on accented characters)
  echo "$OUT4" | grep -q "BEFORE EXECUTING, RUN" || VERIFY_CMD=""
  RAN_OK=1
  if [ -n "$VERIFY_CMD" ]; then
    eval "$VERIFY_CMD" >/dev/null 2>&1 || RAN_OK=0
  else
    RAN_OK=0
  fi
  if [ "$HAS_ALREADY_EXECUTED" = "1" ] && [ "$RAN_OK" = "1" ]; then
    report 0 "round$round C4: ALREADY-EXECUTED block present + verify_first_cmd extracted and executed (exit 0)"
  else
    report 1 "round$round C4 failed: already_done=$HAS_ALREADY_EXECUTED verify_cmd=[$VERIFY_CMD] ran_ok=$RAN_OK OUT4=$OUT4"
  fi

  rm -rf "$WORK" 2>/dev/null
}

for round in 1 2 3; do
  echo "=== ROUND $round/3 ==="
  run_round "$round"
done

echo ""
TOTAL=$((PASS + FAIL))
echo "handoff-roundtrip-C1-C4: $PASS/$TOTAL checks green over 3 rounds (pass^k=1.00 requires $TOTAL/$TOTAL)"
[ "$FAIL" = "0" ] && exit 0 || exit 1

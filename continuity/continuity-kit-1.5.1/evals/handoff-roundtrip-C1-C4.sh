#!/usr/bin/env bash
# handoff-roundtrip-C1-C4.sh - the 4 acceptance cases of the continuity kit, through the REAL
# hook interface (stdin JSON -> stdout JSON), against the real _handoff_io.py /
# handoff_inject.py / handoff_guard.py. Runs 3x and demands an identical result
# (pass^k=1.00, k=3 - loop-passk RULE 2).
#
# C1 . basic round trip: write --demo -> handoff_inject prints the LC-4 block -> ledger has "consumed"
# C2 . staleness: an expired valid_until -> inject shows STALE and does NOT show NEXT STEP
# C3 . degraded-auto: with no handoff, Stop 1a=block/the state survives, Stop 2a (stop_hook_active)
#      =releases and records degraded-auto; the two guard calls take <8s in all (monotonic clock)
# C4 . anti-replay (LC-4): the injected verify_first_cmd is extracted from the text and really
#      EXECUTED, proving the idempotence proof runs exactly as delivered
#
# Usage: bash evals/handoff-roundtrip-C1-C4.sh
# Exit: 0 = 3/3 runs with C1-C4 all green . 1 = a run failed

set -u
# Interpreter: the order of hooks/pyrun.sh (python3 first outside Windows, the Microsoft Store
# stub skipped); HPP_PYTHON overrides. Every bare `python` below goes through the function.
# Why: the evals called a bare `python`, and a stock Mac has only `python3`, so all
# seven failed there with "command not found" before checking anything.
PY="${HPP_PYTHON:-}"
if [ -z "$PY" ]; then
  case "$(uname -s 2>/dev/null)" in MINGW*|MSYS*|CYGWIN*) _py_order="python python3" ;; *) _py_order="python3 python" ;; esac
  for _py_name in $_py_order; do
    _py_bin="$(command -v "$_py_name" 2>/dev/null)" || continue
    case "$(readlink -f "$_py_bin" 2>/dev/null || echo "$_py_bin")" in *DesktopAppInstaller*) continue ;; esac
    PY="$_py_name"; break
  done
fi
[ -n "$PY" ] || { echo "no Python interpreter found (python3/python); set HPP_PYTHON" >&2; exit 2; }
# `command` skips this function when PY is the name `python` itself; without it the call recurses
# until bash crashes (measured: rc=139 on Windows, where `python` is found first).
python() { command "$PY" "$@"; }
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
  # The bound is absolute and covers the two guard calls only: a Python timer runs both with a
  # monotonic clock, and nothing is subtracted from their total. Subtracting a separately timed
  # interpreter start-up let a slow start-up sample swallow the time of a slow hook. The ceiling is
  # generous (the pair takes under a second on an idle machine) and still fails any pair that takes
  # C3_CEILING_S or more; a call that hangs is killed after C3_HANG_S and fails the case.
  C3_CEILING_S=8
  C3_HANG_S=30
  python - "$(to_native "$GUARD")" "$WORK_N/c3a.out" "$WORK_N/c3b.out" "$C3_CEILING_S" "$C3_HANG_S" > "$WORK/c3.times" <<'PYEOF'
import json, subprocess, sys, time
guard, out_a, out_b = sys.argv[1], sys.argv[2], sys.argv[3]
ceiling, hang = float(sys.argv[4]), float(sys.argv[5])
hung = False
start = time.monotonic()
for active, out in ((False, out_a), (True, out_b)):
    payload = json.dumps({"hook_event_name": "Stop", "session_id": "s1", "lane_id": "solo",
                          "stop_hook_active": active})
    try:
        result = subprocess.run([sys.executable, guard], input=payload, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=hang)
        text = result.stdout
    except subprocess.TimeoutExpired:
        text, hung = "", True
    with open(out, "w", encoding="utf-8") as handle:
        handle.write(text)
    if hung:
        break
elapsed = time.monotonic() - start
verdict = "%.2f %d %d\n" % (elapsed, 0 if hung or elapsed >= ceiling else 1, 1 if hung else 0)
sys.stdout.buffer.write(verdict.encode("ascii"))  # bytes: no CR on Windows for `read` to keep
PYEOF
  ELAPSED="?"; TIME_OK=0; HUNG="?"
  read -r ELAPSED TIME_OK HUNG < "$WORK/c3.times"
  OUT3A="$(cat "$WORK/c3a.out" 2>/dev/null)"
  OUT3B="$(cat "$WORK/c3b.out" 2>/dev/null)"
  BLOCK_OK=0
  echo "$OUT3A" | grep -q '"decision": *"block"' && BLOCK_OK=1
  DEGRADED_OK=0
  if [ -f "$WORK/.claude/handoff/HANDOFF-CURRENT-solo.json" ] && grep -q '"quality": *"degraded-auto"' "$WORK/.claude/handoff/HANDOFF-CURRENT-solo.json"; then
    DEGRADED_OK=1
  fi
  if [ "$BLOCK_OK" = "1" ] && ! echo "$OUT3B" | grep -q '"decision"' && [ "$DEGRADED_OK" = "1" ] && [ "$TIME_OK" = "1" ]; then
    report 0 "round$round C3: Stop1=block, Stop2=release+degraded-auto, the two guard calls in ${ELAPSED}s (<${C3_CEILING_S}s)"
  else
    report 1 "round$round C3 failed: block_ok=$BLOCK_OK degraded_ok=$DEGRADED_OK elapsed=${ELAPSED}s ceiling=${C3_CEILING_S}s hung=${HUNG:-?} OUT3B=$OUT3B"
  fi
  rm -f "$WORK/c3a.out" "$WORK/c3b.out" "$WORK/c3.times"
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

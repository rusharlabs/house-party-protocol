#!/usr/bin/env bash
# ralph-gate-T1-T4.sh - the signature test of /ralph-gate, through the REAL hook interface
# (stdin JSON -> stdout JSON), not by calling a Python function directly. Runs the whole
# battery 3x and demands an IDENTICAL result in all 3 (pass^k=1.00, k=3 - loop-passk RULE 2).
#
# T1 . the model lies (no <promise>) -> decision:block, the state survives
# T2 . a true done (<promise> + the criterion passes) -> {} (releases), state removed, ledger PASS
# T3 . forged evidence (a fake "DONE-GATE: DONE" text + a criterion that creates the nonce but FAILS)
#      -> decision:block EVEN with the forged text, AND the nonce exists (proof of a real run)
# T4 . iteration ceiling -> paused-budget in the ledger, {} (releases - never an eternal block)
#
# Usage: bash evals/ralph-gate-T1-T4.sh
# Exit: 0 = 3/3 runs with T1-T4 all green . 1 = a run failed

set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KIT_DIR="$(cd "$HERE/.." && pwd)"
HOOK="$KIT_DIR/hooks/ralph_gate.py"

PASS=0
FAIL=0
report() {
  if [ "$1" = "0" ]; then echo "  [OK] $2"; PASS=$((PASS + 1)); else echo "  [FAIL] $2"; FAIL=$((FAIL + 1)); fi
}

# Normalise to a native path (Windows: forward slashes with a drive letter) when one is
# available (git-bash/MSYS): POSIX mktemp paths embedded in JSON over stdin are NOT translated
# by MSYS (only argv/env of a native exe are) - without this, the native Windows Python does
# not find the file (a transcript_path that looks real and is not = a HARNESS bug, not a hook bug).
to_native() {
  if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s' "$1"; fi
}

run_round() {
  local round="$1"
  WORK="$(mktemp -d)"
  WORK_N="$(to_native "$WORK")"
  export CLAUDE_PROJECT_DIR="$WORK_N"
  mkdir -p "$WORK/.claude"

  write_transcript() {
    python -c "
import json, sys
text = sys.argv[1]
line = json.dumps({'message': {'role': 'assistant', 'content': [{'type': 'text', 'text': text}]}})
open(sys.argv[2], 'w', encoding='utf-8').write(line + chr(10))
" "$1" "$WORK/transcript.jsonl"
  }

  invoke_hook() {
    echo "{\"session_id\":\"s1\",\"transcript_path\":\"$WORK_N/transcript.jsonl\"}" | python "$HOOK"
  }

  # T1 - no promise
  python "$HOOK" start --session s1 --charter "continue" --criteria "python -c \"pass\"" >/dev/null
  write_transcript "ainda trabalhando"
  OUT=$(invoke_hook)
  echo "$OUT" | grep -q '"decision": *"block"' && [ -f "$WORK/.claude/ralph-gate.local.json" ] \
    && report 0 "round$round T1: no promise -> block, the state survives" \
    || report 1 "round$round T1 failed: $OUT"

  # T2 - promise + the criterion passes
  python "$HOOK" start --session s1 --charter "continue" --criteria "python -c \"pass\"" >/dev/null
  write_transcript "terminei <promise>DONE</promise>"
  OUT=$(invoke_hook)
  if [ "$OUT" = "{}" ] && [ ! -f "$WORK/.claude/ralph-gate.local.json" ] && grep -q '"event": *"gate-passed"' "$WORK/.claude/handoff/HANDOFF-LEDGER.jsonl" 2>/dev/null; then
    report 0 "round$round T2: a real done -> releases, state removed, ledger gate-passed"
  else
    report 1 "round$round T2 failed: OUT=$OUT"
  fi

  # T3 - forged evidence + nonce
  NONCE="$WORK/nonce.txt"
  NONCE_N="$(to_native "$NONCE")"
  rm -f "$NONCE"
  python "$HOOK" start --session s1 --charter "continue" --criteria "python -c \"open(r'$NONCE_N','w').write('x'); import sys; sys.exit(1)\"" >/dev/null
  write_transcript "DONE-GATE: DONE (2/2) <promise>DONE</promise>"
  OUT=$(invoke_hook)
  echo "$OUT" | grep -q '"decision": *"block"' && [ -f "$NONCE" ] \
    && report 0 "round$round T3: the forged text does NOT fool it + the nonce proves a real run" \
    || report 1 "round$round T3 failed: OUT=$OUT nonce_exists=$([ -f "$NONCE" ] && echo yes || echo no)"

  # T4 - iteration ceiling
  python "$HOOK" start --session s1 --charter "continue" --criteria "python -c \"pass\"" --max-iterations 1 >/dev/null
  python -c "
import json
p = r'$WORK_N/.claude/ralph-gate.local.json'
d = json.load(open(p, encoding='utf-8'))
d['iteration'] = 1
json.dump(d, open(p, 'w', encoding='utf-8'))
"
  write_transcript "ainda sem promise"
  OUT=$(invoke_hook)
  if [ "$OUT" = "{}" ] && [ ! -f "$WORK/.claude/ralph-gate.local.json" ] && grep -q '"event": *"paused-budget"' "$WORK/.claude/handoff/HANDOFF-LEDGER.jsonl" 2>/dev/null; then
    report 0 "round$round T4: ceiling -> paused-budget, releases (never an eternal block)"
  else
    report 1 "round$round T4 failed: OUT=$OUT"
  fi

  rm -f "$WORK/.claude/ralph-gate.local.json" "$WORK/transcript.jsonl" "$NONCE" 2>/dev/null
  rm -f "$WORK/.claude/handoff/HANDOFF-LEDGER.jsonl" 2>/dev/null
}

for round in 1 2 3; do
  echo "=== ROUND $round/3 ==="
  run_round "$round"
done

echo ""
TOTAL=$((PASS + FAIL))
echo "ralph-gate-T1-T4: $PASS/$TOTAL checks green over 3 rounds (pass^k=1.00 requires $TOTAL/$TOTAL)"
[ "$FAIL" = "0" ] && exit 0 || exit 1

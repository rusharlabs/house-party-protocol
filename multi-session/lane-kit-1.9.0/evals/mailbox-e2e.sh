#!/usr/bin/env bash
# mailbox-e2e.sh - the mailbox of the lane engine end to end, through the REAL interfaces (the hook:
# stdin JSON -> stdout JSON; the board: its CLI), with two lanes in a temp repo. Runs 3x and demands
# an identical result (pass^k=1.00, k=3).
#
# M1 . routing: `## To: exec-b` reaches exec-b at register; the legacy `## Para:` still does; a
#      message for exec-bb never reaches exec-b (whole-line match, lane id bounded) and vice versa
# M2 . heartbeat: what the register announced is not repeated; a message written while exec-b runs
#      is announced ONCE as PostToolUse context; the next heartbeat is silent; archived is silent
# M3 . delivery (default ON): a NEEDS-FIX on exec-a's item writes ONE `## To: exec-a` message, the
#      reservation is delivered with that path, nothing is pending, UNDELIVERED is gone; exec-a
#      hears it on its heartbeat, once; a new round writes a second message
# M4 . CONTROL: with `mailbox.notify_on_verdict: false` the same verdict writes nothing and the
#      reservation stays pending
#
# The Codex doorbell is switched off here on purpose: it needs a live Codex session, and this eval
# measures the mailbox (the doorbell has its own unit tests with fake `codex` executables).
#
# Usage: bash evals/mailbox-e2e.sh
# Exit: 0 = 3/3 runs with every check green . 1 = a run failed

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
REGISTER="$KIT_DIR/hooks/lane_register.py"
BOARD="$KIT_DIR/scripts/lane_board.py"
EFFECTS="$KIT_DIR/scripts/lane_effects.py"

PASS=0
FAIL=0
report() {
  if [ "$1" = "0" ]; then echo "  [OK] $2"; PASS=$((PASS + 1)); else echo "  [FAIL] $2"; FAIL=$((FAIL + 1)); fi
}

to_native() { if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s' "$1"; fi }

# hook <lane> [--heartbeat]  -> the hook's stdout, run exactly as the host runs it
hook() {
  local lane="$1"; shift
  printf '{"hook_event_name":"PostToolUse","session_id":"sess-%s"}' "$lane" \
    | CLAUDE_LANE_ID="$lane" CLAUDE_LANE_ROLE="executor" CLAUDE_LANE_MODEL="claude-opus-5-5" \
      python -X utf8 "$REGISTER" "$@" 2>>"$STDERR_TMP"
}

board() { python -X utf8 "$BOARD" "$@" >/dev/null 2>>"$STDERR_TMP"; }

message() {  # message <path> <lane>
  printf '## To: %s\n## From: coord (planner)\n## When: 2026-01-01T00:00:00\n\n### What changed\nscope\n' "$2" > "$1"
}

verdict_flow() {  # verdict_flow <item> <builder lane> <verdict>  (claim -> ... -> UNDER-REVIEW -> verdict)
  board claim "$1" --lane "$2" --model claude-opus-5-5
  board set "$1" BUILDING --lane "$2" --role executor --model claude-opus-5-5
  board set "$1" CHECKPOINT-READY --lane "$2" --role executor --model claude-opus-5-5 --evidence "pytest -q: 3 passed"
  board set "$1" UNDER-REVIEW --lane "$2" --role executor --model claude-opus-5-5
  board set "$1" "$3" --lane rev-a --role reviewer --model gpt-5.6-sol --verdict-by-lane rev-a --verdict-by-model gpt-5.6-sol
}

run_round() {
  local round="$1"
  WORK="$(mktemp -d)"
  WORK_N="$(to_native "$WORK")"
  export CLAUDE_PROJECT_DIR="$WORK_N"
  # Why: LANE_KIT_CONFIG wins over the project's lanes.yaml in the kit's config loader. Inherited from the
  # operator's shell, it made every round read the operator's config -- a `mailbox.dir` there would have
  # received this eval's messages. Each round points it at its own temporary config.
  export LANE_KIT_CONFIG="$WORK_N/.claude/lanes/lanes.yaml"
  STDERR_TMP="$(mktemp)"
  MAILBOX="$WORK/.claude/lanes/mailbox"
  mkdir -p "$MAILBOX"
  printf 'liveness:\n  heartbeat_throttle_seconds: 0\nmailbox:\n  native_doorbell: false\n' > "$WORK/.claude/lanes/lanes.yaml"

  # --- M1: routing at register -------------------------------------------------------------
  message "$MAILBOX/to.md" exec-b
  printf '## Para: exec-b\n## De: coord (planner)\n\n### What changed\nlegacy\n' > "$MAILBOX/para.md"
  message "$MAILBOX/for-bb.md" exec-bb
  OUT=$(hook exec-b)
  echo "$OUT" | grep -q '"hookEventName": "SessionStart"' && echo "$OUT" | grep -q 'to.md' \
    && report 0 "round$round M1a: \`## To: exec-b\` reaches exec-b at register" \
    || report 1 "round$round M1a failed: OUT=$OUT"
  echo "$OUT" | grep -q 'para.md' && report 0 "round$round M1b: the legacy \`## Para:\` still routes" \
    || report 1 "round$round M1b failed: OUT=$OUT"
  if ! echo "$OUT" | grep -q 'for-bb'; then report 0 "round$round M1c: exec-bb's message never reaches exec-b"
  else report 1 "round$round M1c failed (substring routing): OUT=$OUT"; fi
  OUT=$(hook exec-bb)
  if echo "$OUT" | grep -q 'for-bb.md' && ! echo "$OUT" | grep -q 'to.md' && ! echo "$OUT" | grep -q 'para.md'; then
    report 0 "round$round M1d: exec-bb gets only its own message"
  else report 1 "round$round M1d failed: OUT=$OUT"; fi

  # --- M2: the heartbeat --------------------------------------------------------------------
  OUT=$(hook exec-b --heartbeat)
  [ "$OUT" = "{}" ] && report 0 "round$round M2a: what the register announced is not repeated by the heartbeat" \
    || report 1 "round$round M2a failed: OUT=$OUT"
  message "$MAILBOX/late.md" exec-b
  OUT=$(hook exec-b --heartbeat)
  echo "$OUT" | grep -q '"hookEventName": "PostToolUse"' && echo "$OUT" | grep -q 'late.md' \
    && report 0 "round$round M2b: a message written mid-session is announced as PostToolUse context" \
    || report 1 "round$round M2b failed: OUT=$OUT"
  OUT=$(hook exec-b --heartbeat)
  [ "$OUT" = "{}" ] && report 0 "round$round M2c: the second heartbeat is silent (once per message)" \
    || report 1 "round$round M2c failed: OUT=$OUT"
  mkdir -p "$MAILBOX/_read"
  mv "$MAILBOX/late.md" "$MAILBOX/_read/late.md"
  message "$MAILBOX/_read/older.md" exec-b
  OUT=$(hook exec-b --heartbeat)
  [ "$OUT" = "{}" ] && report 0 "round$round M2d: archived messages are silent" \
    || report 1 "round$round M2d failed: OUT=$OUT"

  # --- M3: delivery, default ON --------------------------------------------------------------
  hook exec-a >/dev/null
  verdict_flow ITEM-1 exec-a NEEDS-FIX
  COUNT=$(ls "$MAILBOX"/ITEM-1-*.md 2>/dev/null | wc -l | tr -d ' ')
  [ "$COUNT" = "1" ] && report 0 "round$round M3a: a NEEDS-FIX writes exactly one verdict message" \
    || report 1 "round$round M3a failed: $COUNT message(s): $(ls "$MAILBOX" 2>/dev/null | tr '\n' ' ')"
  MSG=$(ls "$MAILBOX"/ITEM-1-*.md 2>/dev/null | head -1)
  if [ -n "$MSG" ] && grep -q '^## To: exec-a$' "$MSG" && grep -q 'NEEDS-FIX' "$MSG" && grep -q 'ITEM-1' "$MSG"; then
    report 0 "round$round M3b: the message is routed to the builder lane and names the item and the verdict"
  else report 1 "round$round M3b failed: $(cat "$MSG" 2>/dev/null | head -12)"; fi
  PENDING=$(python -X utf8 "$EFFECTS" pending 2>>"$STDERR_TMP")
  [ "$PENDING" = "[]" ] && report 0 "round$round M3c: the reservation is delivered (nothing pending)" \
    || report 1 "round$round M3c failed: pending=$PENDING"
  # Why: a negative grep alone passed when render failed with empty output; the check first demands
  # exit 0 and the item it expects, and only then the absence of UNDELIVERED.
  RENDER=$(python -X utf8 "$BOARD" render 2>>"$STDERR_TMP"); RENDER_RC=$?
  if [ "$RENDER_RC" = "0" ] && echo "$RENDER" | grep -q '^## ITEM-1 ' && ! echo "$RENDER" | grep -q 'UNDELIVERED'; then
    report 0 "round$round M3d: render (exit 0, ITEM-1 present) shows no UNDELIVERED"
  else report 1 "round$round M3d failed: render rc=$RENDER_RC, $(echo "$RENDER" | grep -c '^## ITEM-1 ') ITEM-1 heading(s), $(echo "$RENDER" | grep -c 'UNDELIVERED') UNDELIVERED line(s)"; fi
  OUT=$(hook exec-a --heartbeat)
  echo "$OUT" | grep -q 'NEEDS-FIX' && echo "$OUT" | grep -q 'ITEM-1' \
    && report 0 "round$round M3e: the builder lane hears the verdict on its heartbeat" \
    || report 1 "round$round M3e failed: OUT=$OUT"
  OUT=$(hook exec-a --heartbeat)
  [ "$OUT" = "{}" ] && report 0 "round$round M3f: ... once" || report 1 "round$round M3f failed: OUT=$OUT"
  board set ITEM-1 BUILDING --lane exec-a --role executor --model claude-opus-5-5
  board set ITEM-1 CHECKPOINT-READY --lane exec-a --role executor --model claude-opus-5-5 --evidence "pytest -q: 4 passed"
  board set ITEM-1 UNDER-REVIEW --lane exec-a --role executor --model claude-opus-5-5
  board set ITEM-1 VERIFIED --lane rev-a --role reviewer --model gpt-5.6-sol --verdict-by-lane rev-a --verdict-by-model gpt-5.6-sol
  COUNT=$(ls "$MAILBOX"/ITEM-1-*.md 2>/dev/null | wc -l | tr -d ' ')
  [ "$COUNT" = "2" ] && report 0 "round$round M3g: a new round writes a second message" \
    || report 1 "round$round M3g failed: $COUNT message(s)"

  # --- M4: CONTROL, notify_on_verdict false in a second repo ----------------------------------
  WORK2="$(mktemp -d)"
  export CLAUDE_PROJECT_DIR="$(to_native "$WORK2")"
  export LANE_KIT_CONFIG="$(to_native "$WORK2")/.claude/lanes/lanes.yaml"
  mkdir -p "$WORK2/.claude/lanes"
  printf 'mailbox:\n  notify_on_verdict: false\n  native_doorbell: false\n' > "$WORK2/.claude/lanes/lanes.yaml"
  verdict_flow ITEM-1 exec-a NEEDS-FIX
  if [ ! -d "$WORK2/.claude/lanes/mailbox" ]; then report 0 "round$round M4a: with notify_on_verdict false no message is written"
  else report 1 "round$round M4a failed: $(ls "$WORK2/.claude/lanes/mailbox" | tr '\n' ' ')"; fi
  PENDING=$(python -X utf8 "$EFFECTS" pending 2>>"$STDERR_TMP")
  echo "$PENDING" | grep -q '"effect_state": "pending"' && echo "$PENDING" | grep -q '"item_id": "ITEM-1"' \
    && report 0 "round$round M4b: the reservation stays pending (by-hand delivery, as before)" \
    || report 1 "round$round M4b failed: pending=$PENDING"

  if grep -q 'Traceback' "$STDERR_TMP"; then report 1 "round$round: a traceback reached stderr: $(grep -A3 Traceback "$STDERR_TMP" | head -8)"
  else report 0 "round$round: no traceback on stderr in the whole round"; fi

  rm -f "$STDERR_TMP"
  rm -rf "$WORK" "$WORK2" 2>/dev/null
}

for round in 1 2 3; do
  echo "=== ROUND $round/3 ==="
  run_round "$round"
done

echo ""
TOTAL=$((PASS + FAIL))
echo "mailbox-e2e: $PASS/$TOTAL checks green over 3 rounds (pass^k=1.00 requires $TOTAL/$TOTAL)"
[ "$FAIL" = "0" ] && exit 0 || exit 1

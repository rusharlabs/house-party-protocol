#!/usr/bin/env bash
# ralph-gate-T1-T4.sh — o teste-assinatura do /ralph-gate, via a interface REAL de hook
# (stdin JSON -> stdout JSON), não via chamada direta de função Python. Roda a bateria
# inteira 3x e exige resultado IDÊNTICO nas 3 (pass^k=1.00, k=3 — loop-passk REGRA 2).
#
# T1 · modelo mente (sem <promise>) -> decision:block, state sobrevive
# T2 · done verdadeiro (<promise> + critério passa) -> {} (libera), state removido, ledger PASS
# T3 · forja de evidência (texto "DONE-GATE: DONE" fake + critério cria nonce mas FALHA)
#      -> decision:block MESMO com o texto forjado, E o nonce existe (prova execução real)
# T4 · teto de iterações -> paused-budget no ledger, {} (libera — não block eterno)
#
# Uso: bash evals/ralph-gate-T1-T4.sh
# Exit: 0 = 3/3 rodadas com T1-T4 todos verdes · 1 = alguma rodada falhou

set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KIT_DIR="$(cd "$HERE/.." && pwd)"
HOOK="$KIT_DIR/hooks/ralph_gate.py"

PASS=0
FAIL=0
report() {
  if [ "$1" = "0" ]; then echo "  [OK] $2"; PASS=$((PASS + 1)); else echo "  [FAIL] $2"; FAIL=$((FAIL + 1)); fi
}

# Normaliza pra path nativo (Windows: forward-slash com drive-letter) quando disponível
# (git-bash/MSYS): paths POSIX de mktemp embutidos em JSON via stdin NÃO são traduzidos
# pelo MSYS (só argv/env de exe nativo são) — sem isto, o Python nativo do Windows não
# acha o arquivo (transcript_path aparente-mas-inexistente = bug de HARNESS, não do hook).
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

  # T1 — sem promise
  python "$HOOK" start --session s1 --charter "continue" --criteria "python -c \"pass\"" >/dev/null
  write_transcript "ainda trabalhando"
  OUT=$(invoke_hook)
  echo "$OUT" | grep -q '"decision": *"block"' && [ -f "$WORK/.claude/ralph-gate.local.json" ] \
    && report 0 "round$round T1: sem promise -> block, state sobrevive" \
    || report 1 "round$round T1 falhou: $OUT"

  # T2 — promise + critério passa
  python "$HOOK" start --session s1 --charter "continue" --criteria "python -c \"pass\"" >/dev/null
  write_transcript "terminei <promise>DONE</promise>"
  OUT=$(invoke_hook)
  if [ "$OUT" = "{}" ] && [ ! -f "$WORK/.claude/ralph-gate.local.json" ] && grep -q '"event": *"gate-passed"' "$WORK/.claude/handoff/HANDOFF-LEDGER.jsonl" 2>/dev/null; then
    report 0 "round$round T2: done real -> libera, state removido, ledger gate-passed"
  else
    report 1 "round$round T2 falhou: OUT=$OUT"
  fi

  # T3 — forja de evidência + nonce
  NONCE="$WORK/nonce.txt"
  NONCE_N="$(to_native "$NONCE")"
  rm -f "$NONCE"
  python "$HOOK" start --session s1 --charter "continue" --criteria "python -c \"open(r'$NONCE_N','w').write('x'); import sys; sys.exit(1)\"" >/dev/null
  write_transcript "DONE-GATE: DONE (2/2) <promise>DONE</promise>"
  OUT=$(invoke_hook)
  echo "$OUT" | grep -q '"decision": *"block"' && [ -f "$NONCE" ] \
    && report 0 "round$round T3: texto forjado NAO engana + nonce prova execucao real" \
    || report 1 "round$round T3 falhou: OUT=$OUT nonce_existe=$([ -f "$NONCE" ] && echo sim || echo nao)"

  # T4 — teto de iterações
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
    report 0 "round$round T4: teto -> paused-budget, libera (nao block eterno)"
  else
    report 1 "round$round T4 falhou: OUT=$OUT"
  fi

  rm -f "$WORK/.claude/ralph-gate.local.json" "$WORK/transcript.jsonl" "$NONCE" 2>/dev/null
  rm -f "$WORK/.claude/handoff/HANDOFF-LEDGER.jsonl" 2>/dev/null
}

for round in 1 2 3; do
  echo "=== RODADA $round/3 ==="
  run_round "$round"
done

echo ""
TOTAL=$((PASS + FAIL))
echo "ralph-gate-T1-T4: $PASS/$TOTAL checks verdes em 3 rodadas (pass^k=1.00 exige $TOTAL/$TOTAL)"
[ "$FAIL" = "0" ] && exit 0 || exit 1

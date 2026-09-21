[English](README.md) · [Português](README.pt-BR.md)

# Continuity Kit

An agent session survives a stop/`/clear`/crash without losing the next step. The
handoff (schema `handoff-v1.1`) records a git block (branch/commit/staged) + a
`re_derive_cmd` (LC-1 — re-derive the state live, never trust what was left written)
+ a `verify_first_cmd` (LC-4 — before continuing an action the handoff describes,
check whether it was already done, never re-fire blindly). It also includes **doc-rollup**
(project history/evolution that consolidates itself, with built-in degradation above size
thresholds). It does not do multi-session/lanes — for that, see `lane-kit` (which depends
on this kit).

## Prerequisites + external APIs

| Requirement | Minimum version | Required? |
|---|---|---|
| Python | 3.8 | yes |
| PyYAML | any | yes — `doc_rollup.py` exits 2 without it; `state_mirror.py` becomes a silent no-op without it |

External services: **none — stdlib + PyYAML, touches only the local filesystem + the target project's git.**

## Install as a plugin

```bash
/plugin marketplace add .
/plugin install continuity-kit@house-party-protocol
```

## Install by copy

```bash
cp -r continuity-kit-1.1.0 <seu-projeto>/continuity-kit
cd <seu-projeto>
python continuity-kit/instaladores/kit-forge/kit_doctor.py install continuity-kit --target . --human
#                                                                                     ^ plano, zero escrita
python continuity-kit/instaladores/kit-forge/kit_doctor.py install continuity-kit --target . --apply
#                                                                                     ^ aplica de verdade
```
(adjust the `kit_doctor.py` path to wherever kit-forge was copied — it is the single
installation engine of the whole marketplace, see `INSTALL-CONTRACT.md`.)

## What the installer detects

```
greenfield    → copia rollup.example.yaml -> rollup.yaml (estágio profile); nenhum handoff prévio
em-andamento  → detecta .claude/settings.local.json já com hooks configurados (reportado, não sobrescrito)
re-run        → rollup.yaml já existe -> skip-exists; registry (~/.claude-kits/registry.json) marca re-run
```

## What is safe to run again

The `profile` stage of `kit_doctor.py` **never overwrites** `rollup.yaml` if it already
exists (skip-exists, reported explicitly — not silently). The handoff content itself
(`.claude/handoff/HANDOFF-LEDGER.jsonl`) is append-only by design (each event becomes a
new line; nothing is rewritten). Running `kit_doctor.py install --apply` again is safe:
customisation in `rollup.yaml` survives.

## Manual wiring (human gate — never automatic)

> Editing `.claude/settings.local.json` is a human gate in this doctrine — automated
> sessions have an explicit lock against self-editing settings/hooks files. Paste the
> block below yourself — WARN-only + `timeout: 30`.

```jsonc
// wiring.settings.jsonc — bloco de colar (GATE HUMANO — o classifier bloqueia auto-edit de
// settings/hooks). ADITIVO: mesclar dentro dos arrays "hooks" já existentes em
// settings.json/settings.local.json — NUNCA substituir o arquivo inteiro.
//
// Launcher: NUNCA fixar "py" — detectar na instalação (${CLAUDE_PLUGIN_ROOT} + _lib/launcher.py
// do operator-kit, ou o Python resolvido pelo instalador). Os comandos abaixo usam "python"
// (correto na maioria dos PATHs); troque por caminho absoluto do venv se o projeto-alvo tiver um.
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          { "type": "command", "command": "python \"${CLAUDE_PLUGIN_ROOT}/hooks/handoff_inject.py\"", "timeout": 30 }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          { "type": "command", "command": "python \"${CLAUDE_PLUGIN_ROOT}/hooks/handoff_guard.py\"", "timeout": 30 }
        ]
      }
    ],
    "PreCompact": [
      {
        "hooks": [
          { "type": "command", "command": "python \"${CLAUDE_PLUGIN_ROOT}/hooks/handoff_guard.py\"", "timeout": 30 }
        ]
      }
    ]
  }
}
```

Post-wiring checklist (run the real round-trip, do not presume — LC-1):
```bash
python "${CLAUDE_PLUGIN_ROOT}/hooks/_handoff_io.py" --self-test
python "${CLAUDE_PLUGIN_ROOT}/hooks/_handoff_io.py" write --demo --lane solo
echo '{"hook_event_name":"SessionStart","session_id":"proof"}' | python "${CLAUDE_PLUGIN_ROOT}/hooks/handoff_inject.py"
tail -1 .claude/handoff/HANDOFF-LEDGER.jsonl   # confirmar "event": "consumed"
```

## Proof / acceptance (real output, executed)

```bash
python hooks/_handoff_io.py --self-test
```
```
self-test OK — write válido+ledger, rejeita sem verify_first_cmd, rejeita sem re_derive_cmd,
rejeita segredo, rejeita degraded-auto sem porcelain, render com LC-4, staleness, consume,
degraded-auto
```
<!-- executado: 2026-07-11 · exit=0 -->

Extended proof (real round-trip through the hook interface — stdin JSON → stdout JSON, C1-C4:
round-trip, staleness, degraded-auto <5s, anti-replay LC-4):
```bash
bash evals/handoff-roundtrip-C1-C4.sh
```

## Undo

```
- Plugin: /plugin uninstall continuity-kit@house-party-protocol
- Cópia: remover a pasta continuity-kit/ do projeto + reverter o bloco colado em
  settings.local.json manualmente (gate humano também na remoção)
- Handoff ledger: .claude/handoff/HANDOFF-LEDGER.jsonl é append-only — remover o
  arquivo inteiro se quiser resetar o histórico (não afeta o handoff mais recente
  em .claude/RESUME-NEXT.md, que é regenerado a cada Stop)
```

---

*See `LANE-KIT.md` (sibling kit) for multi-session/lanes — this kit is the single-lane foundation.*

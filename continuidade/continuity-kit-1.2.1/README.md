# Continuity Kit

Uma sessão de agente sobrevive a parada/`/clear`/crash sem perder o próximo passo. O
handoff (schema `handoff-v1.1`) grava um bloco git (branch/commit/staged) + um
`re_derive_cmd` (LC-1 — re-derivar o estado ao vivo, nunca confiar no que ficou escrito)
+ um `verify_first_cmd` (LC-4 — antes de continuar uma ação que o handoff descreve,
verificar se ela já foi feita, nunca re-disparar cego). Inclui também **doc-rollup**
(histórico/evolução do projeto que se consolida sozinho, com degradação embutida acima
de limiares de tamanho). Não faz multi-sessão/lanes — para isso, ver `lane-kit` (que
depende deste kit).

## Pré-requisitos + APIs externas

| Requisito | Versão mínima | Obrigatório? |
|---|---|---|
| Python | 3.8 | sim |
| PyYAML | qualquer | sim — `doc_rollup.py` sai exit 2 sem ela; `state_mirror.py` vira no-op silencioso sem ela |

Serviços externos: **nenhum — stdlib + PyYAML, só toca filesystem local + git do projeto-alvo.**

## Instalar via plugin

```bash
/plugin marketplace add .
/plugin install continuity-kit@house-party-protocol
```

## Instalar por cópia

```bash
cp -r continuity-kit-1.1.0 <seu-projeto>/continuity-kit
cd <seu-projeto>
python continuity-kit/instaladores/kit-forge/kit_doctor.py install continuity-kit --target . --human
#                                                                                     ^ plano, zero escrita
python continuity-kit/instaladores/kit-forge/kit_doctor.py install continuity-kit --target . --apply
#                                                                                     ^ aplica de verdade
```
(ajuste o path do `kit_doctor.py` para onde o kit-forge foi copiado — é o motor único de
instalação de todo o marketplace, ver `INSTALL-CONTRACT.md`.)

## O que o instalador detecta

```
greenfield    → copia rollup.example.yaml -> rollup.yaml (estágio profile); nenhum handoff prévio
em-andamento  → detecta .claude/settings.local.json já com hooks configurados (reportado, não sobrescrito)
re-run        → rollup.yaml já existe -> skip-exists; registry (~/.claude-kits/registry.json) marca re-run
```

## O que é seguro rodar de novo

O estágio `profile` do `kit_doctor.py` **nunca sobrescreve** `rollup.yaml` se ele já
existir (skip-exists, reportado explicitamente — não silencioso). O conteúdo do handoff
em si (`.claude/handoff/HANDOFF-LEDGER.jsonl`) é append-only por design (cada evento vira
uma linha nova; nada é reescrito). Rodar `kit_doctor.py install --apply` de novo é seguro:
customização em `rollup.yaml` sobrevive.

## Wiring manual (gate humano — nunca automático)

> ⚠️ Editar `.claude/settings.local.json` é gate humano nesta doutrina — sessões
> automatizadas têm trava explícita contra auto-editar arquivo de settings/hooks. Cole
> você mesmo o bloco abaixo — WARN-only + `timeout: 30`.

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

Checklist pós-wiring (rodar o round-trip real, não presumir — LC-1):
```bash
python "${CLAUDE_PLUGIN_ROOT}/hooks/_handoff_io.py" --self-test
python "${CLAUDE_PLUGIN_ROOT}/hooks/_handoff_io.py" write --demo --lane solo
echo '{"hook_event_name":"SessionStart","session_id":"proof"}' | python "${CLAUDE_PLUGIN_ROOT}/hooks/handoff_inject.py"
tail -1 .claude/handoff/HANDOFF-LEDGER.jsonl   # confirmar "event": "consumed"
```

## Prova / aceite (saída real, executada)

```bash
python hooks/_handoff_io.py --self-test
```
```
self-test OK — write válido+ledger, rejeita sem verify_first_cmd, rejeita sem re_derive_cmd,
rejeita segredo, rejeita degraded-auto sem porcelain, render com LC-4, staleness, consume,
degraded-auto
```
<!-- executado: 2026-07-11 · exit=0 -->

Prova estendida (round-trip real via a interface de hook — stdin JSON → stdout JSON, C1-C4:
round-trip, staleness, degraded-auto <5s, anti-replay LC-4):
```bash
bash evals/handoff-roundtrip-C1-C4.sh
```

## Desfazer

```
- Plugin: /plugin uninstall continuity-kit@house-party-protocol
- Cópia: remover a pasta continuity-kit/ do projeto + reverter o bloco colado em
  settings.local.json manualmente (gate humano também na remoção)
- Handoff ledger: .claude/handoff/HANDOFF-LEDGER.jsonl é append-only — remover o
  arquivo inteiro se quiser resetar o histórico (não afeta o handoff mais recente
  em .claude/RESUME-NEXT.md, que é regenerado a cada Stop)
```

---

*Ver `LANE-KIT.md` (kit irmão) para multi-sessão/lanes — este kit é o alicerce single-lane.*

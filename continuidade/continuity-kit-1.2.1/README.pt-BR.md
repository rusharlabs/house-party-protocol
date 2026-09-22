[English](README.md) · [Português](README.pt-BR.md)

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
/plugin marketplace add rushar-labs/house-party-protocol
/plugin install continuity-kit@house-party-protocol
```
O `.claude-plugin/plugin.json` declara `hooks/hooks.json`, então o plugin arma três
entradas via `${CLAUDE_PLUGIN_ROOT}` (cada uma lançada por `hooks/pyrun.sh`, que resolve o
Python do projeto; WARN-only, `timeout: 30`): `handoff_inject.py` no `SessionStart`
(injeta o handoff válido mais novo, ≤4 KB, e grava `consumed`), e `handoff_guard.py` no
`Stop` e no `PreCompact` (garante que um handoff fresco existe, sem nunca travar de
verdade). O `hooks/session_boot.py` — um `SessionStart` genérico que soma git
HEAD/branch/tags e as seções vivas do seu state doc, e depois delega ao
`handoff_inject.py` — não é armado pelo plugin; cole você mesmo se quiser. Skills são
auto-descobertas.

## Instalar por cópia

Na distribuição emitida este módulo vive em `continuidade/continuity-kit-1.2.1/` (o
diretório carrega a versão — declare-a uma vez, em `KIT`). O instalador é
`instaladores/kit-forge-1.4.0/kit_doctor.py` — o motor único de instalação de todo o
marketplace, ver `INSTALL-CONTRACT.md` na raiz da distribuição. Rode-o da raiz da
distribuição; ele planeja primeiro e só escreve numa segunda invocação explícita com
`--apply`:

```bash
KIT=continuidade/continuity-kit-1.2.1
cp -r "$KIT" ../your-repo/continuity-kit      # the copy itself (kit_doctor does not copy on claude-code)
python instaladores/kit-forge-1.4.0/kit_doctor.py install --kit "$KIT" --host claude-code --target ../your-repo
python instaladores/kit-forge-1.4.0/kit_doctor.py install --kit "$KIT" --host claude-code --target ../your-repo --apply
# Codex CLI: --host codex — the installer copies the module into .agents/hpp/continuity-kit
#            and each skill into .agents/skills/hpp-continuity-kit-<skill>; no cp -r needed
```

## O que o instalador detecta

O estágio `detect` classifica o alvo (só leitura) com exatamente estes três rótulos:

```
greenfield    -> no prior config in the target; profile stage would copy rollup.example.yaml -> rollup.yaml; no previous handoff
in-progress   -> .claude/ exists, or settings(.local).json already has hooks/statusLine, or rollup.yaml is
                 already present, or the repo has more than 3 commits: reported, never overwritten (skip-exists)
re-run        -> this kit+target pair is already in the registry (~/.claude-kits/registry.json)
```

## O que é seguro rodar de novo

O estágio `profile` do `kit_doctor.py` **nunca sobrescreve** `rollup.yaml` se ele já
existir (skip-exists, reportado explicitamente — não silencioso). O conteúdo do handoff
em si (`.claude/handoff/HANDOFF-LEDGER.jsonl`) é append-only por design (cada evento vira
uma linha nova; nada é reescrito). Rodar `kit_doctor.py install --apply` de novo é seguro:
customização em `rollup.yaml` sobrevive.

## Wiring manual (gate humano — nunca automático)

> Editar `.claude/settings.local.json` é gate humano nesta doutrina — sessões
> automatizadas têm trava explícita contra auto-editar arquivo de settings/hooks. No
> caminho por cópia não existe `${CLAUDE_PLUGIN_ROOT}`: cole você mesmo o bloco abaixo,
> com a pasta para onde copiou o kit — WARN-only + `timeout: 30`.

```jsonc
// Paste block (HUMAN GATE — the classifier blocks self-editing of settings/hooks).
// ADDITIVE: merge into the "hooks" arrays that already exist in
// settings.json/settings.local.json — NEVER replace the whole file.
//
// Launcher: NEVER hardcode "py" — detect it at install time (hooks/pyrun.sh, or the Python the
// installer resolved). The commands below use "python" (right on most PATHs); swap in the
// absolute path of the venv if the target project has one.
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          { "type": "command", "command": "python \"continuity-kit/hooks/handoff_inject.py\"", "timeout": 30 }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          { "type": "command", "command": "python \"continuity-kit/hooks/handoff_guard.py\"", "timeout": 30 }
        ]
      }
    ],
    "PreCompact": [
      {
        "hooks": [
          { "type": "command", "command": "python \"continuity-kit/hooks/handoff_guard.py\"", "timeout": 30 }
        ]
      }
    ]
  }
}
```

Checklist pós-wiring (rodar o round-trip real, não presumir — LC-1):
```bash
python continuity-kit/hooks/_handoff_io.py --self-test
python continuity-kit/hooks/_handoff_io.py write --demo --lane solo
echo '{"hook_event_name":"SessionStart","session_id":"proof"}' | python continuity-kit/hooks/handoff_inject.py
tail -1 .claude/handoff/HANDOFF-LEDGER.jsonl   # confirm "event": "consumed"
```

## Prova / aceite (saída real, executada)

```bash
python hooks/_handoff_io.py --self-test
```
```
self-test OK — write válido+ledger, rejeita sem verify_first_cmd, rejeita sem re_derive_cmd, rejeita segredo, rejeita degraded-auto sem porcelain, render com LC-4, staleness, consume, degraded-auto
```
<!-- executado: 2026-09-21 · exit=0 -->

Prova estendida (round-trip real via a interface de hook — stdin JSON → stdout JSON, C1-C4:
round-trip, staleness, degraded-auto <5s, anti-replay LC-4):
```bash
bash evals/handoff-roundtrip-C1-C4.sh
```

## Desfazer

```
- Plugin:  /plugin uninstall continuity-kit@house-party-protocol
- Copy:    remove the continuity-kit/ folder from the project + revert the block pasted into
           settings.local.json by hand (removal is a human gate too)
- Handoff ledger: .claude/handoff/HANDOFF-LEDGER.jsonl is append-only — remove the whole
           file to reset the history (it does not affect the newest handoff in
           .claude/RESUME-NEXT.md, which is regenerated at every Stop)
```

---

*Para multi-sessão/lanes ver `LANE-KIT.md` dentro do módulo `lane-kit` — este kit é o alicerce single-lane.*

# 00-PROCESSES — escada de verificação + matriz de autoridade — {{project_name}}

## A escada R0→R4 (config em `verificacao.escada` do profile)

Ninguém declara readiness maior que a evidência. `goal_ledger.py --readiness <id> <RN> --evidence <ref>`
recusa (exit 2) se a evidência não bater com o nível.

| Nível | Nome | O que prova | Mecanismo que certifica | Quem declara |
|---|---|---|---|---|
| R0 | Declarado | "escrevi/mudei" | — (palavra do maker) | executora |
| R1 | Auto-verificado | self-test/teste unitário verde | `--self-test`/pytest exit 0 | executora (evidência colada) |
| R2 | Gate | DoD do PRD passa AO VIVO | `done_gate.py` exit 0 (probes) | só o script (nunca prosa) |
| R3 | Revisado | outro cérebro confirmou | `goal_review.py` + checker cross-model; indisponível → `DEFERRED`, nunca R3 | revisora (família ≠ maker) |
| R4 | Aceito | humano aceitou em uso real | gate humano / produção | humano |

## Matriz de autoridade (papel × direito)

| | Planejadora (arquiteta) | Executora (construtora) | Revisora (auditora) |
|---|---|---|---|
| **Escreve em** | `docs/plans/**`, `00-STATE.md` (single-writer), BOOT-prompts | código/artefatos dentro do território claimado; `00-STATE-LANE-<id>.md`; board (estados de builder) | **NADA** (read-only físico — sem Write/Edit; só `lane_board.py --set VERDICT`) |
| **Git** | commit só de docs, com pathspec | commit com pathspec estrito; NUNCA push/merge | zero commits |
| **Autonomy (slider 0-5)** | 2 | 2-3 (🟢🟠 auto; 🔴 propõe) | 0 (suggest-only por construção) |
| **Proibido** | mutar código/engine/VM; instalar; wire de settings | fechar o próprio item como VERIFIED; tocar `00-STATE.md` (só o próprio LANE file); zonas vermelhas | editar qualquer arquivo; ser a mesma lane/modelo do builder |
| **Quem aprova** | {{humano}} (specs viram BOOT colável) | Revisora (VERDICT) + {{humano}} (gates 🔴, merge) | {{humano}} (só ele fecha DEFERRED) |

**Enforcement:** esta matriz não é só disciplina — `lane_board.py` (lane-kit) a codifica em
máquina de estados: `CHECKPOINT-READY` só a lane que claimou + evidência; `VERIFIED`/`NEEDS-FIX`
só revisora de OUTRA lane E OUTRA família de modelo (maker≠checker recusado com exit 2, não
apenas sugerido em prosa).

## Zonas vermelhas (WARN para TODAS as lanes, sempre — mesmo solo)

`.claude/settings*.json` · `**/MEMORY.md` · `{{state_doc}}` (fora do fluxo single-writer) ·
qualquer path listado em `lanes.yaml → zonas_vermelhas`.

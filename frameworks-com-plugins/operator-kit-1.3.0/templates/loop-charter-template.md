# 🔄 CHARTER — Loop autônomo «{NOME}» ({DATA})

> **Este é o driver do loop.** A próxima sessão entra aqui, roda relentless, self-prompta, se auto-revisa, e só para quando a lane autônoma esgotar OU o teto de tempo OU risco irreversível iminente.
> **Work-list:** `{paths.work_list}` · **Conceito-norte:** `{boot_doc}` (não driftar).
> Preencha os `{…}`. Defaults vêm do `operator-profile.yaml`.

---

## 🎯 MISSÃO
{O que esmagar, sozinho e em workflows. O que genuinamente depende do humano vira FORMULÁRIO (§GATE-HUMANO), nunca bloqueio.}

## 🛡️ GUARDRAILS
**MANTIDOS (cinto de segurança — inquebrável):**
1. **0 push** sem ordem · nunca force-push.
2. **Backup antes de QUALQUER mutação de prod** (config/db/container).
3. **Snapshot + verify antes de deletar** (destructive-actions).
4. **Trava de credencial** (verificar a conta certa antes de tocar token/secret).
5. **Gate-humano para:** billing, OAuth, legal, mensagem a cliente, deploy-prod-go, rotação de secret.
6. **LC-1:** verificar live antes de declarar "feito". Não quebrar o que funciona.

**RELAXADOS (fricção — pra autonomia):**
- Auto-proceder (sem confirmar-cada-passo) · plan inline · self-prompt o próximo item · contínuo entre batches · workflows em ondas de ≤{concorrencia.teto}.

## 🔁 CICLO (cada iteração)
1. **Re-alinhar:** ler este charter + boot-doc (conceito) + SSoT §Agora.
2. **Verificar live (LC-1):** estado real da fonte canônica do projeto.
3. **Escolher** o próximo item não-feito de **maior alavancagem**.
4. **Executar** via workflow ondas-de-{concorrencia.teto} + **adversarial verify** (refutar antes de aceitar).
5. **Marcar feito** no work-list + commit por path (0 push).
6. **Capstone por onda:** `python operator-kit/scripts/done_gate.py --profile {tipo}` + os validadores do projeto.
7. **Self-prompt (OPCIONAL):** `ScheduleWakeup` com este charter pro próximo ciclo — ferramenta **exclusiva do main-loop `/loop`**, não é dependência deste charter. Fora do main-loop ela não existe: o fallback é re-invocar o charter à mão no próximo ciclo.
8. **A cada ~5 ciclos — revisão adversarial:** "que ponta ficou solta? driftei do conceito? duplicata/órfão novo?".

## ⚙️ ORDEM DE ATAQUE
1. {Item 1 — autônomo}
2. {Item 2 — autônomo}
3. {Itens delegáveis a 2º agente — só após pré-requisito X}
4. {Staged p/ gate humano}

## 📋 GATE-HUMANO (a parede — limpa numa sentada)
Cada item: `{gate, motivo, comando/passo EXATO, o-que-destrava}`. Saída em `{paths.gate_sheet}`.

## 🛑 STOP CONDITIONS
- Lane autônoma esgotada (tudo não-gate feito) → reporta + aguarda gate.
- {stop_conditions: teto de tempo}.
- Risco irreversível iminente que um guardrail sinalizou → PARA + reporta.

## 🚀 SELF-PROMPT / BOOT (cola pós-/clear · `ScheduleWakeup` repete isto **quando disponível**)

> `ScheduleWakeup` é **opcional** e **exclusiva do main-loop `/loop`** — não é dependência deste
> charter. Fora do main-loop, o fallback é colar o bloco abaixo à mão no próximo ciclo.

```
Loop autônomo «{NOME}». Pasta {raiz-do-projeto}, branch {branch}.
LEIA (nesta ordem): {este charter} → {boot_doc} → {paths.work_list} → SSoT §Agora.
PASSO 0 LIVE (LC-1): {comando(s) de verificação ao vivo do projeto}.
GUARDRAILS: mantém (0 push · backup-antes-prod · snapshot-antes-delete · trava-credencial · gate-humano billing/OAuth/legal · LC-1). Relaxa fricção (auto-proceder · self-prompt · contínuo).
EXECUTA (ondas-de-{teto} + adversarial verify): ordem do charter §. Commit por path, 0 push. Capstone por onda: done_gate --profile {tipo}.
SELF-REVIEW a cada ~5 ciclos. Gate-humano → formulário único, NUNCA bloqueia o loop.
ScheduleWakeup pro próximo ciclo (OPCIONAL — ferramenta exclusiva do main-loop /loop; fora dele, o fallback é recolar este bloco à mão). PARA em: lane-esgotada OU teto-tempo OU risco-irreversível.
```

*Charter vivo. A cada ciclo re-verifica na fonte (LC-1). Risca itens no work-list ao concluir.*

# STALE-REPLAY-GUARD — LC-4 · Contexto restaurado é referência, não ordem de execução

> **Auto-Trigger:** Após /clear, /resume, boot auto-inject, restore de contexto de um gateway/bot de chat, ou qualquer retomada onde o contexto veio de snapshot/handoff/sessão anterior — ANTES de re-disparar qualquer ação/goal/lote que o resumo descreve.
> **Keywords:** "resume", "/resume", "/clear", "retomar", "onde paramos", "boot package", "resume-here", "auto-inject", "restaurar contexto", "restore", "snapshot", "handoff", "sessão anterior", "replay", "re-disparar", "re-rodar", "já rodou", "já concluído", "idempotência", "idempotente", "stale"
> **Prioridade:** ALTA
> **Versão:** 1.0.0 (generalizada para o operator-kit)
> **Origem:** Stale-Replay Guard destilado em regra. Extensão de `learned-corrections.md` (LC-1/LC-2/LC-3) — registrada como **LC-4**. Aplica a qualquer LLM que retome contexto de uma sessão/snapshot anterior.

---

## LC-4 · Contexto RESTAURADO/RESUMIDO é REFERÊNCIA HISTÓRICA — verifique ao vivo e NUNCA re-dispare o que já foi feito

Todo contexto que chega via **restauração** (após `/clear`, `/resume`, boot auto-inject, ou
restore de contexto de qualquer gateway/bot que sobrevive a restart) é **referência histórica
de uma sessão passada**, NÃO uma fila de tarefas a executar agora. Antes de agir sobre
qualquer instrução que veio de um resumo restaurado:

1. **Verifique AO VIVO (LC-1):** o estado descrito no resumo (números, status, "feito"/"pendente", endpoints, deploys) está SUSPEITO até reconfirmar na fonte viva. Um resumo dizendo "rodar X" pode ter sido escrito ANTES de X rodar — e X pode já ter rodado depois.
2. **NUNCA re-dispare ação/goal/lote JÁ concluído (idempotência):** se a ação descrita já produziu seu efeito (arquivo criado, commit feito, item marcado no ledger, endpoint respondendo, goal aceito), NÃO repita. Re-execução cega de um passo já-feito = duplicata, corrupção de estado, ou trabalho destruído.
3. **Trate o resumo como HIPÓTESE, não verdade** (igual LC-3 trata "pendente"/"órfão"): refute antes de agir. O `done_predicate` / evidência rastreável é a autoridade — não a narrativa do snapshot.

```
╔══════════════════════════════════════════════════════════════════════════════╗
║  RESUMO RESTAURADO ≠ FILA DE EXECUÇÃO                                         ║
║                                                                              ║
║  "Próximo passo: rodar X"  →  PRIMEIRO checar se X já rodou (fonte viva)     ║
║  Já rodou?  →  NÃO rodar de novo · confirmar · seguir para o próximo gap      ║
║  Não rodou (confirmado ao vivo)?  →  então sim, executar                     ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

### Exemplo (o caso que esta regra previne)

```
SITUAÇÃO: /resume injeta um wrap-up que diz:
  "PRÓXIMA AÇÃO: rodar seed_data.py para re-popular a base."

ERRADO (replay cego):
  → Rodar seed_data.py imediatamente porque o resumo mandou.
  → Resultado: re-roda um lote que JÁ rodou na sessão anterior →
    sobrescreve dados já enriquecidos / cria duplicatas.

CERTO (LC-4):
  1. Verificar ao vivo: a base JÁ está populada?
     (query real na base · grep no ledger por esse goal · check do
      done_predicate do lote).
  2. Já feito → NÃO rodar. Confirmar: "base já populada na sessão
     anterior (evidência: X). Pulando para o próximo gap real."
  3. Só rodar SE a verificação ao vivo provar que NÃO foi feito.
```

### Pontos de aplicação

| Ponto | O que ele restaura | Guarda LC-4 |
|-------|--------------------|-------------|
| Skill `/resume` | Wrap-up / último estado salvo da sessão anterior | Tratar "PRÓXIMA AÇÃO" como hipótese; confirmar ao vivo antes de re-disparar |
| Handoff/continuidade (re-inject no boot) | Estado salvo da sessão atual | Estado salvo pode estar atrás da realidade do disco; re-verificar antes de reagir a ele |
| Auto-inject de boot-package/ledger | Pacote de boot (plano, ledger, "comece aqui") | Itens marcados `[ ]`/`[x]` no ledger são âncora; mesmo assim re-checar `done_predicate` antes de "continuar" um goal |
| Gateway de chat que sobrevive a restart | Contexto de conversa restaurado entre restarts do processo | O bot NÃO deve re-postar/re-enviar/re-executar uma ação só porque o contexto restaurado a menciona como "a fazer" — verificar evidência (id de mensagem, log, endpoint) antes de repetir |

**PORQUE:** após `/clear`/`/resume`/boot, a causa #1 de corrupção é o LLM tratar o resumo como
to-do list e re-rodar passos já concluídos. O resumo descreve o PASSADO; o disco/endpoint/
ledger descreve o AGORA. Idempotência + verificação ao vivo evitam duplicatas e estado
destruído. Complementa LC-1 (prove, não presuma) aplicando-o ao momento específico da
retomada, e estende "nunca dizer 'fiz' sem evidência" para "nunca RE-fazer sem evidência de
que ainda não foi feito".

---

*Extensão de `learned-corrections.md` (LC-4). Universal — aplica a qualquer LLM que retome
contexto de uma sessão/snapshot anterior. LC-1: prove, não presuma.*

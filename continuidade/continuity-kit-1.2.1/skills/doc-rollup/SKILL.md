---
name: doc-rollup
description: Mantém os docs de historico/evolucao do projeto (changelog, timeline narrativa, snapshot de estado, licoes, wrapup de sessao) atualizados apos uma sessao significativa — com degradacao embutida (carimbo em vez de narrativa infinita) desde o dia 1.
---

> **Auto-Trigger:** Ao fechar uma wave/feature significativa, antes de um `/pre-clear`, ou quando o operador pedir "atualiza os docs"/"registra isso no histórico".
> **Keywords:** "doc-rollup", "atualizar changelog", "atualizar historico", "rollup de docs", "session wrapup", "registrar no historico", "carimbo", "atualiza tudo"
> **Prioridade:** MÉDIA
> **Tools:** Read, Bash

## Quando NÃO Ativar
- Sessão sem nada significativo a registrar (leitura/exploração pura) — não force uma entrada vazia.
- Não confundir com a skill `pre-clear`, que cobre o CURTO PRAZO (o que fazer na próxima sessão — handoff). Esta skill cobre o LONGO PRAZO (como chegamos até aqui — histórico). `pre-clear` chama esta skill como um dos seus passos, condicionalmente.
- Config ausente (`rollup.yaml` não existe) — copie `rollup.example.yaml` primeiro; a skill não inventa alvos.

## Contrato

**ENTRADA:** payload JSON via stdin, montado pelo modelo (só ele sabe o que aconteceu nesta sessão): `session_marker` (string única, obrigatório — LC-4), `resumo` (obrigatório), `date` (opcional, default hoje BRT), `shipments[]`, `metricas[]` (cada item PRECISA de `re_derive_cmd` — LC-1), `decisoes[]`, `aprendizados[]`. Config em `rollup.yaml` (copiado de `rollup.example.yaml`).

**SAÍDA:** relatório JSON por alvo (`{path, mode, role, status, ...}`) impresso em stdout. Arquivos-alvo atualizados no disco (modo `plan` não toca disco).

**EXIT CODES:**

| Exit | Significado |
|---|---|
| 0 | processado (mesmo com alvos pulados por colisão/passive — isso é comportamento correto) |
| 1 | payload rejeitado (`session_marker`/`resumo` ausente, ou métrica sem `re_derive_cmd`) |
| 2 | uso inválido (config ausente, JSON malformado, `--stdin` não passado) |

**ESTADO QUE TOCA:**

| Recurso | Lê/Escreve | Propósito |
|---|---|---|
| `rollup.yaml` | Lê | config de alvos (paths, modo, template, limiares) |
| cada `target.path` (resolvido) | Lê+Escreve (insere/anexa, nunca sobrescreve o arquivo inteiro) | o doc de histórico em si |
| `<path>.bak-rollup-<timestamp>` | Escreve | backup antes de qualquer edição em arquivo existente |
| paths com `passive: true` | NUNCA toca | defesa em profundidade (ex.: mirror auto-gerado por outro mecanismo) |

## Processo

1. **Copie o config uma vez por projeto:** `cp rollup.example.yaml rollup.yaml` e ajuste os alvos reais (nomes de arquivo, templates, thresholds).
2. **Avalie significância:** algo fechou nesta sessão que merece registro? Se não, pule e registre por que (não force o rollup).
3. **Preveja antes de aplicar** (opcional, mas recomendado — não toca disco):
   ```bash
   echo '<json>' | python ${CLAUDE_PLUGIN_ROOT}/scripts/doc_rollup.py plan --stdin --config rollup.yaml
   ```
4. **Aplique de verdade:**
   ```bash
   echo '<json>' | python ${CLAUDE_PLUGIN_ROOT}/scripts/doc_rollup.py apply --stdin --config rollup.yaml
   ```
5. **Leia o relatório por alvo.** `applied:*`/`created` = escreveu; `skipped-collision` = já tinha essa sessão (não duplicou, correto); `skipped-passive` = alvo protegido (nunca deveria escrever mesmo); `applied:stamp-degrade` = o alvo passou do limiar e recebeu só 1 linha-carimbo em vez da narrativa completa (esperado, não é erro).
6. **Se o `pre-clear` estiver instalado**, ele chama este passo automaticamente ANTES do handoff (para capturar a árvore de arquivos pós-rollup no handoff).

## Exemplos executados

```console
$ echo '{"session_marker":"doc-ex-001","date":"2026-07-10","resumo":"exemplo de doc-rollup","shipments":["rollup.yaml","doc_rollup.py"]}' | python scripts/doc_rollup.py apply --stdin --config rollup.yaml
{
  "repos": [
    {
      "name": "exemplo",
      "targets": [
        {
          "path": "CHANGELOG.md",
          "mode": "prepend-after-header",
          "status": "applied:prepend",
          "content_preview": "## [2026-07-10] exemplo de doc-rollup\n\n- rollup.yaml\n- doc_rollup.py\n"
        }
      ]
    }
  ]
}
```
<!-- executado: 2026-07-10 · exit=0 -->

```console
$ echo '{"shipments":["x"]}' | python scripts/doc_rollup.py apply --stdin --config rollup.yaml
{
  "status": "rejected",
  "errors": [
    "session_marker ausente (obrigatorio p/ deteccao de colisao/idempotencia — LC-4)",
    "resumo ausente"
  ]
}
```
<!-- executado: 2026-07-10 · exit=1 -->
(payload sem `session_marker`/`resumo` é REJEITADO antes de tocar qualquer arquivo.)

```console
$ echo '{"session_marker":"doc-ex-001","date":"2026-07-10","resumo":"tentativa de re-inserir a mesma sessao","shipments":["x"]}' | python scripts/doc_rollup.py apply --stdin --config rollup.yaml
{
  "repos": [
    {
      "name": "exemplo",
      "targets": [
        {
          "path": "CHANGELOG.md",
          "status": "skipped-collision",
          "reason": "session_marker 'doc-ex-001' ja presente neste alvo (LC-4: nao re-inserir)"
        }
      ]
    }
  ]
}
```
<!-- executado: 2026-07-10 · exit=0 -->
(o MESMO `session_marker` de novo não duplica a entrada — idempotência real, não só documentada.)

## Anti-patterns

- ❌ Escrever o arquivo de histórico à mão em vez de rodar `doc_rollup.py` — perde backup, detecção de colisão e degradação automática.
- ❌ Ignorar `skipped-collision`/`skipped-passive` como "erro" — são o guardrail funcionando, não uma falha a corrigir.
- ❌ Deixar um doc de narrativa manual crescer sem `max_bytes`/`max_entries` configurado — é exatamente a decadência que este mecanismo existe para prevenir desde o dia 1.

## Prova

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/doc_rollup.py --self-test
```

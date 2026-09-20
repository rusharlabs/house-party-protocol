# 00-DEPLOY — {{project_name}} / {{deploy_nome}}

> Deploy como DOC, não como comando solto na memória de alguém. Preencha ANTES de rodar
> o deploy real — se você não consegue preencher uma seção, o deploy não está pronto.

## O que muda

{{descricao_1_paragrafo}}

## Passos (ordem fixa — não pular)

1. **Backup/snapshot** do estado atual: `{{comando_backup}}`
2. **Build/staging** em ambiente separado (nunca direto na porta viva): `{{comando_build_staging}}`
3. **Canary** — exercitar o caminho crítico contra o staging: `{{comando_canary}}`
4. **Promote** — parar o antigo SEM deletar (rollback = religar, não reconstruir): `{{comando_promote}}`
5. **Verify LIVE** — confirmar que o BACKEND trocou de verdade (rota exclusiva do novo +
   marca de build — não só o gate de auth nem o status do processo): `{{comando_verify_live}}`

## Rollback (ver `00-ROLLBACK.template.md` desta mudança)

`{{link_para_00_rollback_desta_mudanca}}`

## Gotcha conhecido deste projeto (se houver)

{{gotcha_especifico_ou_nenhum_ainda}}

## Quem autoriza ir para produção

{{quem_aprova}} — gate humano sempre para deploy real.

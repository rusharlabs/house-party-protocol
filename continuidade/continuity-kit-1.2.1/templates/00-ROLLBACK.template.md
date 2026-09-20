# 00-ROLLBACK — {{project_name}} / {{mudanca_nome}}

> Rollback é ARTEFATO aqui, não doutrina espalhada em prosa: toda mudança que muta
> runtime/produção/dado vivo ganha ESTE documento ANTES de ser aplicada, com o comando
> literal de volta já escrito (não "dá pra reverter se precisar" — o comando existe).

## Classificação da mudança

- [ ] **Aditiva** (novo arquivo/rota/coluna — reversível por remoção simples)
- [ ] **Destrutiva** (substitui/remove algo vivo — reversível só com backup prévio)
- [ ] **Migração de dado** (schema/formato — reversível só com dump prévio)

## Snapshot ANTES (obrigatório para destrutiva/migração)

```bash
{{comando_de_backup_ou_snapshot}}
```

## O comando EXATO de volta (escrito ANTES de aplicar a mudança)

```bash
{{comando_literal_de_rollback}}
```

## Verify pós-rollback (prova que voltou, não presume)

```bash
{{comando_que_confirma_estado_anterior}}
```

## Lição embutida (LC-1 · deploy/routing)

Ao verificar que um deploy/rollback funcionou, confirme que o **BACKEND trocou de verdade**
(rota exclusiva do novo/antigo + marca de build) — nunca só o status do processo nem o gate
de auth (ambos podem ficar iguais entre a versão nova e a antiga). Se há proxy/tunnel no
caminho, confirme CADA hop, não só a ponta.

## Quem autoriza a aplicação

{{quem_aprova_esta_mudanca}} — gate humano se a mudança tocar produção/dado real.

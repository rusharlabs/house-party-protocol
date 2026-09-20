# PRD — {{onda_nome}}

> **Regra dura:** todo PRD DEVE ter o bloco `## DoD (done_predicates)` preenchido com
> comandos shell REAIS (não prosa "deve funcionar corretamente"). Sem esse bloco, a
> executora DEVE derivar 3-6 predicates ANTES de começar a construir — nunca builda
> "às cegas" sem saber o que prova "pronto". O `/ralph-gate` e o `goal_review.py`
> consomem este bloco diretamente (`goal_review.extract_criteria`).

## Objetivo (1 frase)

{{objetivo}}

## Escopo

- Inclui: {{o_que_inclui}}
- Exclui: {{o_que_exclui_explicitamente}}

## Contexto/motivação

{{por_que_agora}}

## DoD (done_predicates) — OBRIGATÓRIO

```bash
# Cada linha = 1 critério shell. TODOS precisam sair exit 0 para o PRD ser considerado DONE.
{{comando_criterio_1}}
{{comando_criterio_2}}
{{comando_criterio_3}}
```

## Tier de risco

- [ ] 🟢 repo-safe (o loop pode atacar autônomo)
- [ ] 🟠 toca VM/infra viva (requer atenção extra, não bloqueia autonomia)
- [ ] 🔴 gate (requer aprovação humana antes de aplicar)

## Readiness esperado ao final

{{nivel_r0_a_r4_esperado}} — ver `00-PROCESSES.template.md` para o que cada nível exige.

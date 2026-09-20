---
name: dashboard-builder
description: Constrói dashboards de monitoramento (Grafana, SigNoz e similares) que respondem perguntas reais de operador, não "mostra toda métrica que existe". Use ao transformar uma lista de métricas em dashboard operável de verdade.
---

> **Auto-Trigger:** Usuário pede dashboard Grafana/SigNoz/Kafka/Elasticsearch, ou quer transformar uma lista de métricas num board operável.
> **Keywords:** "dashboard grafana", "dashboard signoz", "dashboard de monitoramento", "board operacional"
> **Prioridade:** BAIXA
> **Tools:** Read, Write

## Quando NÃO Ativar
- Dashboard HTML self-contained pra cliente/relatório (dark/light premium, pure CSS) — isso é
  outro escopo (dataviz/relatório de negócio), não monitoramento de infra.
- Complementa, não substitui, o `health_probe.py` deste kit — o probe MEDE o serviço; este
  skill organiza COMO exibir o que foi medido num board de operação real (Grafana/SigNoz).

## Princípio

O objetivo não é "mostrar toda métrica". É responder:
- está saudável?
- onde está o gargalo?
- o que mudou?
- que ação alguém deveria tomar?

## Guardrails
- Não comece pelo layout visual; comece pelas perguntas do operador.
- Não inclua toda métrica disponível só porque ela existe.
- Não misture painéis de saúde, throughput e recursos sem estrutura.
- Não publique painel sem título, unidade e threshold com sentido.

## Processo

1. **Definir as perguntas operacionais**: saúde/disponibilidade, latência/performance,
   throughput/volume, saturação/recursos, risco específico do serviço.
2. **Estudar o schema da plataforma-alvo**: estrutura JSON, linguagem de query, variáveis,
   estilo de threshold, layout de seção — inspecionar dashboards existentes primeiro.
3. **Construir o board mínimo útil**: visão geral → performance → recursos → seção
   específica do serviço.
4. **Cortar painel vaidade**: todo painel deve responder uma pergunta real; se não responde,
   remover.

## Checklist de qualidade
```
[ ] JSON de dashboard válido
[ ] agrupamento de seção claro
[ ] títulos e unidades presentes
[ ] thresholds/cores de status com sentido
[ ] variáveis existem para filtros comuns
[ ] time range e refresh padrão fazem sentido
[ ] zero painel vaidade sem valor de operador
```

## Contrato

**Entrada:** lista de métricas de um serviço + a plataforma-alvo (Grafana/SigNoz/etc.).
**Saída:** JSON de dashboard organizado por pergunta operacional, com o checklist de
qualidade acima satisfeito.

## Prova

Metodologia de design de dashboard — a prova é o JSON gerado passar no checklist acima
(agrupamento, unidades, thresholds, zero painel vaidade), não um `--self-test` mecânico.

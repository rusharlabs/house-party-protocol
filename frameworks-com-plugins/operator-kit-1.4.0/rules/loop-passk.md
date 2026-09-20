# LOOP-PASSK — capacidade e confiabilidade são gates diferentes

> **Auto-Trigger:** eval de agente, skill, workflow ou release; promoção de autonomia; investigação de flakiness.
> **Keywords:** pass@k, pass^k, eval, k-runs, capacidade, regressão, determinismo, flaky, release.
> **Prioridade:** ALTA
> **Versão:** 2.0.0

## Princípio

Um resultado verde não prova repetibilidade. Para cada caso, rode a mesma verificação `k`
vezes e responda a duas perguntas separadas:

- `pass@k`: o caso passou em pelo menos uma das `k` tentativas? Mede capacidade.
- `pass^k`: o caso passou em todas as `k` tentativas? Mede confiabilidade.

Sempre vale `pass^k <= pass@k`. A diferença entre as métricas é a zona de flakiness.

## Gates padrão

| Gate | Critério | Decisão |
|---|---:|---|
| Capacidade | `pass@k >= 0.90`, com `k=3` | abaixo disso, a implementação volta ao maker |
| Regressão | `pass^k == 1.00`, com `k=3` | abaixo disso, a release fica bloqueada |
| Ambos | os dois critérios | exigido para promoção de autonomia crítica |

O limiar pode ser elevado por domínio. Reduzi-lo para obter verde invalida a medição.

## Runner portátil

O kit inclui `scripts/passk_eval.py`, que lê uma suite JSON e funciona sem pacote externo:

```json
{
  "version": "1",
  "suite": "quality-gates",
  "cases": [
    {
      "id": "unit-tests",
      "runner": "command",
      "command": ["python", "-m", "pytest", "-q"],
      "expect_exit": 0
    },
    {
      "id": "known-replay",
      "runner": "replay",
      "outcomes": [true, true, true]
    }
  ]
}
```

```bash
python scripts/passk_eval.py --suite eval-suite.json -k 3 --gate both
python scripts/passk_eval.py --suite eval-suite.json -k 3 --gate regression --json
python scripts/passk_eval.py --self-test
```

`command` recebe um argv e roda com `shell=False`. `replay` mede fixtures declaradas; não
simula uma chamada a agente. Exit `0` aprova, `2` bloqueia e `3` indica erro de suite ou
execução.

## Escolha do verificador

Use o verificador mais determinístico que mede o comportamento real:

1. código: teste, schema, exit code ou checksum;
2. regra: formato, presença, ausência ou padrão explícito;
3. modelo: rubric para qualidade aberta, assumindo variação do próprio juiz;
4. humano: decisão sensível ou ambígua que não pode ser automatizada com segurança.

Um caso julgado por modelo pode oscilar por causa do objeto ou do juiz. Investigue os dois
antes de classificar a causa.

## Integração com o loop

1. Defina casos positivos, negativos e de regressão antes da implementação.
2. Rode `k=3` durante a construção.
3. Se capacidade falhar, volte ao maker.
4. Se capacidade passar e regressão falhar, remova a fonte de flakiness.
5. O checker independente valida o diff; pass@k/pass^k valida o comportamento.
6. Só promova estado ou autonomia depois que o gate correspondente passar.

## Anti-padrões

- uma execução verde tratada como estabilidade;
- somente happy path;
- caso conhecido decorado pelo agente;
- grader estocástico como único gate release-critical;
- resultado sem suite, hash, `k` e casos individuais;
- indisponibilidade do runner tratada como self-test aprovado.

## Checklist

- [ ] A suite possui versão, nome e IDs únicos?
- [ ] Cada caso usa `command` real ou `replay` declarado?
- [ ] Existem controles positivo e negativo?
- [ ] `k` execuções foram concluídas?
- [ ] pass@k e pass^k foram reportados separadamente?
- [ ] A zona de flakiness foi resolvida ou declarada?
- [ ] O gate bloqueou a promoção quando deveria?

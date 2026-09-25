[English](README.md) · [Português](README.pt-BR.md)

# Citado e executado — o critério que um teste nomeia não é o critério que um teste rodou

> Novo na 2.8.0.

Um teste cita um critério de aceite carregando `[spec: capability/scenario]` na sua docstring, e o
`hpp work coverage` liga cada critério de uma spec aos testes que o citam. Isso responde "algum
teste nomeia este critério?". Um teste pulado continua nomeando; também nomeia um teste que o
runner nunca coletou, e um teste que falha. Com um relatório JUnit XML da execução, o mesmo comando
responde a pergunta que importa: **um teste que o nomeia rodou de fato, e passou?**

| peça | onde |
|---|---|
| a spec, três critérios | `workgraph.json` |
| três testes, um citando cada critério; um deles é pulado | `check_prices.py` |
| a régua | `hpp/workgraph.py` · `hpp work coverage` |

`check_prices.py` não se chama `test_*.py`, então a suíte do próprio harness nunca o coleta; o
pytest o roda porque o caminho é dado na linha de comando.

## Rode

Da raiz do repositório:

```bash
python -m hpp work coverage examples/cited-and-run/workgraph.json --tests examples/cited-and-run/check_prices.py
python -m pytest examples/cited-and-run/check_prices.py -q -p no:cacheprovider --junitxml out/cited-and-run.xml
python -m hpp work coverage examples/cited-and-run/workgraph.json --tests examples/cited-and-run/check_prices.py --junit out/cited-and-run.xml
```

O primeiro comando lê só citações: os três critérios estão citados, `complete: true`, exit 0. O
segundo roda os testes — dois passam, um é pulado. O terceiro junta os dois: `member-discount` e
`rounding` ficam `executed`, `bulk-discount` fica `cited_not_run` com o seu teste marcado
`skipped`, `complete: false`, exit 1. Nada mudou nos testes entre a primeira resposta e a terceira;
só a pergunta mudou.

## O que o relatório diz

Sem `--junit` o relatório é `hpp.spec-coverage/v1` (`covered`, `orphans`, `unknown`). Com ele,
`hpp.spec-execution/v1`:

| balde | um critério cai aqui quando |
|---|---|
| `executed` | um teste que o cita rodou e passou, e nenhum falhou |
| `failed` | um teste que o cita falhou ou deu erro — um passe em outro lugar não o cancela |
| `cited_not_run` | todo teste que o cita ficou `skipped`, está `not-in-junit` (desmarcado, nunca coletado), é `not-a-test` (docstring de módulo ou de classe), é `shadowed` (redefinido depois com o mesmo nome, então nunca rodou) ou é `ambiguous` (o caminho casa casos de mais de um módulo) |
| `orphans` | nenhum teste o cita |
| `unknown` | um marcador nomeia um critério não declarado — citação quebrada |

`complete` só vale quando todo critério está `executed` e nenhuma fonte que cita é mais nova que o
relatório mais antigo (`stale_sources`: um teste editado depois da execução não é o teste que rodou);
o exit é 0 nesse caso e 1 nos outros. Cada relatório é publicado com o seu sha256 (`reports`).
Dois denominadores vêm junto: `junit_testcases`, os casos lidos dos relatórios, e
`matched_testcases`, os que foram ligados a um teste que cita. Zero ligados entre muitos lidos quer
dizer que o relatório e os testes não descrevem a mesma execução — arquivo errado ou raiz errada —,
nunca que nada rodou.

## Limites

As citações são lidas só de docstrings: um marcador dentro de qualquer outra string é dado de
teste, não citação. Um caso do relatório é ligado a um teste pela convenção do pytest — `classname`
é o caminho pontuado do módulo a partir da raiz do runner mais a cadeia de classes, `name` é a
função mais `[parâmetros]` —, comparando o módulo por sufixo, para que os caminhos dados a
`--tests` e a raiz do runner não precisem ser o mesmo diretório. Outros runners que escrevem JUnit
XML do mesmo jeito são lidos do mesmo jeito; um runner com outra convenção não liga nada, e
`matched_testcases: 0` diz isso. Um relatório que declara DOCTYPE ou entidade, ou que não é UTF-8,
é recusado (exit 2), e também um caminho de `--tests` sem nenhum arquivo Python: um universo vazio
não cobre nada.

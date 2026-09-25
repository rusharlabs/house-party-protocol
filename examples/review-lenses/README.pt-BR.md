[English](README.md) · [Português](README.pt-BR.md)

# Lentes de revisão — um revisor por tipo de defeito, uma forma para toda resposta

> Novo na 2.8.0.

Um revisor a quem se pede "procure problemas" acha os problemas que por acaso procura. Uma
**lente** procura um tipo de defeito só, e toda lente responde na mesma forma, para que duas
revisões da mesma mudança possam ser contadas, comparadas e postas lado a lado. O módulo operator
traz quatro lentes como sub-agentes; o núcleo só confere o que elas respondem. Elas não têm ferramenta de edição de arquivo; o somente-leitura delas é **provado** quando são sentadas pelo `house_session.py` do módulo de lanes (o worktree ganha impressão digital em volta de cada resposta), e é instrução nos outros casos.

| lente | o que procura |
|---|---|
| `verification-gap` | comportamento que a mudança acrescenta ou altera e que nenhum teste perceberia quebrar |
| `partial-set` | uma mudança aplicada a alguns membros de um conjunto e não aos outros |
| `deletion` | algo removido enquanto alguma coisa ainda depende dele |
| `stale-evidence` | prova citada para a mudança que é anterior a ela ou nunca foi rodada de novo |

| peça | onde |
|---|---|
| a mudança revisada | `change.diff` (o sha256 dela é o `subject_sha256` de cada documento) |
| uma lente que não achou nada, e diz onde olhou | `deletion-clean.json` |
| uma lente que achou um chamador esquecido | `partial-set.json` |
| a forma e a sua checagem | `hpp/findings.py` · `hpp findings check` |

## Rode

Da raiz do repositório:

```bash
python -m hpp findings check examples/review-lenses/deletion-clean.json
python -m hpp findings check examples/review-lenses/deletion-clean.json examples/review-lenses/partial-set.json
```

A primeira revisão passa: nenhum achado, e `inspected` diz o que foi lido. Exit 0. Com a segunda,
um `CALLER_NOT_UPDATED` em `checkout.py:18`, severidade `medium`: veredito `warn`, exit 1.

## A forma — `hpp.findings/v1`

```json
{"schema": "hpp.findings/v1", "lens": "partial-set", "subject_sha256": "<sha256 of the change>",
 "inspected": ["what was read or run"],
 "findings": [{"code": "CALLER_NOT_UPDATED", "severity": "medium", "file": "checkout.py", "line": 18,
               "claim": "one sentence", "evidence": ["the command and what it returned"],
               "fix": "optional"}]}
```

| regra | por quê |
|---|---|
| uma chave que o contrato não define recusa o documento inteiro (exit 2) | um revisor que improvisa a forma está improvisando o julgamento |
| `inspected` nunca é vazio | "não achei nada" sem o universo se lê igual a "não olhei nada" |
| todo achado carrega `evidence` | um achado sem o que foi rodado ou lido é opinião |
| `code` é `UPPER_SNAKE` estável | o mesmo achado na rodada seguinte se lê do mesmo jeito |
| o mesmo código, arquivo e linha duas vezes é recusado | reescrever um achado não o transforma em dois |
| o veredito é derivado: `fail` com qualquer `high`, `warn` com qualquer outro achado, `pass` sem nenhum | um revisor não declara o próprio veredito |
| com `--subject FILE`, todo documento precisa nomear esse arquivo pelo sha256 | a revisão de outra mudança é recusada, não lida como revisão desta |

## Limites

A checagem lê a resposta, nunca a mudança: prova que a revisão tem a forma, não que a revisão está
certa. O que faz uma lente valer a execução é a própria lente — uma pergunta estreita, feita
somente-leitura, com a busca que fez declarada — e se ela pega defeitos plantados é medido do mesmo
jeito que qualquer revisor.

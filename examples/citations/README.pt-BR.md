[English](README.md) · [Português](README.pt-BR.md)

# Citações — uma afirmação maior que a sua prova vira código de saída

> Novo na 2.6.0.

Uma resposta montada a partir de fontes deve dizer em qual fonte cada afirmação se apoia. Aqui cada
afirmação leva `[ID:<id>]`, em que `<id>` é uma entrada do contexto que a resposta recebeu
(`context.json`). A checagem lê esses dois arquivos e nada mais, não chama modelo, não usa rede, e
diz o que a resposta afirma e as fontes dela não sustentam:

| código | classe | saída | o que significa |
|---|---|---|---|
| `UNKNOWN_ID` | bloqueio | 2 | um marcador cita um id que não está no contexto |
| `RANGE` | bloqueio | 2 | um marcador cita um intervalo ou uma lista (`1-3`, `1,2`, `1..3`): escreva um id por marcador |
| `EMPTY_MARKER` | bloqueio | 2 | um marcador sem id |
| `TOO_MANY` | aviso | 1 | mais de 4 marcadores numa frase (o limite é configurável) |
| `UNCITED_CLAIM` | aviso | 1 | uma frase com número, porcentagem, valor em moeda ou data e nenhum marcador |
| `NO_MARKERS` | aviso | 1 | o texto não tem marcador nem número sem citação: nada foi checado, então não sai como limpo |

Contexto que a resposta nunca cita não é achado — as fontes podem ser maiores que a resposta — e sai
como contagem (`unused_context_ids`). Texto vazio, texto que é só código, contexto vazio, texto ou
contexto com cara de segredo, contexto malformado e regex de marcador inutilizável são recusados (saída 2) antes de
existir qualquer relatório.

## Rodar

```bash
python -m hpp cite check --text examples/citations/answer.md --context examples/citations/context.json
```

A mesma checagem pelo Python, disponível agora:

```python
from hpp.citations import check_files, exit_for

report = check_files("examples/citations/answer.md", "examples/citations/context.json")
print(report["verdict"], report["counts"])
raise SystemExit(exit_for(report))
```

A resposta de exemplo é limpa: veredito `ok`, 7 frases, 5 marcadores, 4 dos 5 ids do contexto
citados. Troque `[ID:glossary]` por `[ID:glossary-v2]` numa cópia e a mesma checagem bloqueia com
`UNKNOWN_ID`.

## Outra sintaxe de marcador

```bash
python -m hpp cite check --text answer.md --context context.json --marker '\{cite:([^}]*)\}' --max-per-sentence 3
```

A regex precisa de exatamente um grupo de captura — o id — e não pode casar texto vazio.

## O que ela não faz

Ela nunca lê a fonte citada para ver se a fonte sustenta a frase. Um marcador que resolve prova que o
id existe, não que a fonte diz o que a frase diz; isso exige um leitor. O que esta checagem elimina é
a falha mais barata: a citação para o nada, e o número sem citação nenhuma.

O divisor de frases e o detector de números são heurísticas, descritas por inteiro no docstring de
`hpp/citations.py`. Em resumo:

- uma frase termina em `.`, `?` ou `!` seguido de espaço; `3.5` não termina frase, nem um ponto
  dentro de um marcador ou de `código`; abreviações comuns (`e.g.`, `Dr.`, `Inc.`, `et al.`, nomes
  de mês) não terminam frase, uma abreviação fora dessa lista termina;
- um marcador logo depois do ponto final, na mesma linha, pertence à frase que acabou de terminar;
- títulos, numeração de lista, `código`, URLs e versões escritas com `v` (`v2.5.8`) não são
  examinados em busca de números, e blocos de código cercados são ignorados por inteiro, inclusive
  uma cerca indentada dentro de um item de lista;
- falsos positivos aceitos, como aviso: ordinais (`1st`), rótulos (`Step 2`, `RFC 2119`), versão
  sem `v` (`2.5.8` não se distingue de uma data com pontos), linha de tabela citada só na legenda;
- falsos negativos: números por extenso, dígitos colados a uma letra à esquerda (`Q3`).

## O relatório

`hpp.citation-check/v1` traz o sha256 do texto e do contexto (JSON canônico, então indentação e
ordem das chaves não o alteram), a regex do marcador, o limite por frase, as contagens
(`sentences`, `quantitative_sentences`, `markers`, `cited_ids`, `unique_cited_ids`, `context_ids`,
`unused_context_ids`), os achados — cada um com código, severidade, frase e linha a partir de 1,
um trecho de no máximo 120 caracteres e uma mensagem —, o veredito e o código de saída.

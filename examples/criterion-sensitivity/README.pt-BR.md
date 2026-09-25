[English](README.md) · [Português](README.pt-BR.md)

# Sensibilidade do critério — sua checagem perceberia se o código estivesse errado?

> Novo na 2.7.0.

Um critério verde prova que nada do que ele confere está quebrado. Não prova que ele confere algo
que importa. `hpp evidence mutate` mede a outra metade: roda o critério numa **cópia** do workspace,
primeiro na árvore limpa (tem de passar — senão a medição não tem controle), depois uma vez por
**mutante**, uma cópia com uma pequena mudança que deixa o código errado (tem de falhar). Um mutante
que o critério deixa passar é um **ponto cego**, nomeado por arquivo e linha.

| peça | onde |
|---|---|
| o código sob teste | `discount.py` — uma regra de preço com duas fronteiras |
| um critério que prende as fronteiras | `check_strong.py` |
| um critério verde que só confere casos confortáveis | `check_weak.py` |
| a régua | `hpp/evidence.py` · `hpp evidence mutate` |

## Rode

Da raiz do repositório:

```bash
python -m hpp evidence mutate --id strong --generate examples/criterion-sensitivity/discount.py -- python examples/criterion-sensitivity/check_strong.py
python -m hpp evidence mutate --id weak --generate examples/criterion-sensitivity/discount.py -- python examples/criterion-sensitivity/check_weak.py
```

Os dois critérios passam no código limpo. O primeiro mata os três mutantes: veredito `sensitive`,
score 1.0, exit 0. O segundo deixa os três passarem: veredito `blind-spots`, score 0.0, exit 1, e
`survivors` nomeia cada um — `examples/criterion-sensitivity/discount.py:6 and -> or`,
`examples/criterion-sensitivity/discount.py:6 >= -> >`, `examples/criterion-sensitivity/discount.py:8 >= -> >`. Nenhum assert do segundo critério está errado; ele só nunca olha 100,00
nem 50,00, onde a regra muda.

## De onde vêm os mutantes

- `--generate FILE` lê um arquivo Python com o tokenizador padrão e gera um mutante por token de
  operador de uma tabela fixa: `==`↔`!=`, `<`↔`<=`, `>`↔`>=`, `and`↔`or`, `True`↔`False`. Texto
  dentro de strings e comentários nunca é mutado: uma troca ali não muda nada e pareceria ponto
  cego.
- `--mutants FILE` declara mutantes à mão, para qualquer linguagem, num arquivo `hpp.mutants/v1`:

```json
{"schema": "hpp.mutants/v1", "mutants": [
  {"id": "member-threshold", "file": "examples/criterion-sensitivity/discount.py",
   "find": "total >= 50", "replace": "total >= 51"}
]}
```

O exemplo traz este arquivo como `mutants.json`; passe-o com `--mutants`. `find` é substituído na primeira ocorrência, ou em `occurrence` quando informado. Um `find` que não
está no arquivo é `not-applied`, contado à parte e nunca como morto. As duas opções se combinam.

## O que o registro diz

O registro (`hpp.mutation/v1`, gravado em `.hpp/evidence/<id>-mutate-<UTC>.json` com hash de si
mesmo) guarda a execução limpa, uma entrada por mutante com o desfecho, e:

| veredito | significado | exit |
|---|---|---|
| `sensitive` | a execução limpa passou e todo mutante aplicado foi morto | 0 |
| `blind-spots` | ao menos um mutante sobreviveu; `survivors` os nomeia | 1 |
| `incomplete` | nenhum sobrevivente, mas o critério não conseguiu iniciar em algum mutante | 1 |
| `no-mutants` | nenhum mutante pôde ser aplicado | 1 |
| `no-control` | o critério não passou na árvore limpa: nenhum mutante roda, sem score | 2 |

`score` é mortos ÷ (mortos + sobreviventes), ou null quando nada foi medido — nunca 0%. Uma execução
que estoura o tempo num mutante não passou, então o mata; a entrada diz que estourou.

## Limites

Cada execução — a limpa e a de cada mutante — ganha uma cópia nova, então um critério que cria um
diretório ou uma tabela na primeira execução não reprova as seguintes por motivo próprio. A cópia
deixa de fora exatamente `.git`, `.hpp`, `__pycache__`, `node_modules`, `.venv`, `venv` e `.tox`;
um arquivo de mutante sob um deles, alcançado por symlink ou que não seja UTF-8 é recusado antes de
qualquer execução. O comando roda dentro da cópia: dê caminhos relativos. Tudo o que faz o critério
ler a árvore original — um caminho absoluto, um install editável (`pip install -e .`), um
`PYTHONPATH` apontando para o checkout, um symlink absoluto dentro da árvore — faz todo mutante
sobreviver, e o registro não distingue isso de pontos cegos reais. O hpp só escreve dentro das
cópias, mas o critério roda com as suas permissões: um symlink absoluto mantido na cópia ainda o
deixa escrever na árvore original. O controle: declare um mutante
que você sabe que o critério mata; se ele sobreviver, o critério não está olhando a cópia. Um
critério que precisa do histórico do git falha na cópia limpa e relata
`no-control` em vez de um score falso. A tabela de operadores é pequena de propósito; um mutante
sobrevivente também pode ser equivalente (uma mudança que não muda o comportamento), e só um leitor
sabe dizer.

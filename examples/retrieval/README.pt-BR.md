[English](README.md) · [Português](README.pt-BR.md)

# Régua de recuperação — medir o recuperador separado da resposta

> Novo na 2.6.0.

Quando uma resposta construída sobre texto recuperado sai errada, duas coisas diferentes podem ter
falhado: o recuperador não trouxe o trecho certo, ou o gerador usou mal um trecho que tinha. Este
exemplo mede só a primeira. O harness continua sem índice próprio e sem chamar modelo
([MANIFESTO](../../MANIFESTO.pt-BR.md)): o recuperador é um comando que **você** declara, e a régua
compara os ids que ele ranqueia com os ids que você marcou como relevantes.

| peça | onde | executa algo? |
|---|---|---|
| a suíte `hpp.retrieval-suite/v1` | `suite.json` | não |
| a régua | `hpp/retrieval.py` · `hpp retrieval eval` | só o comando que você nomear |
| uma linha de base por palavra-chave | `keyword_retriever.py` sobre `corpus.json` | sem modelo, sem rede, só biblioteca padrão |

## O contrato

A régua envia um pedido por caso pela entrada padrão, em JSON com escape ASCII. O id do caso não é
enviado.

```json
{"query": "how do I restore a backup", "k": 3}
```

O recuperador imprime o seu ranking, do melhor para o pior: uma lista de ids, ou objetos com um `id`
e um `score` opcional.

```json
{"results": [{"id": "backup-restore", "score": 2}]}
```

A ordem impressa **é** o ranking. Um `score` precisa ser um número finito ou nulo; ele é conferido e
nunca usado para reordenar, porque distância e similaridade ordenam em sentidos opostos. Chaves
extras são ignoradas. Imprima JSON com escape ASCII (o `json.dumps` já faz isso por padrão) para a
resposta ser lida igual em qualquer página de código do console.

Devolva a mesma unidade que a suíte rotula. Se a suíte rotula documentos e o índice guarda trechos,
junte os trechos no documento antes de responder: um id repetido numa resposta é falha de
instrumento, porque contá-lo duas vezes inflaria a precisão e o nDCG.

Um caso da suíte:

```json
{"id": "disk-full", "query": "the disk is full and uploads fail",
 "relevant": ["disk-full", "log-rotation"],
 "results": [{"id": "disk-full", "score": 3}]}
```

## Como rodar

```bash
echo '{"query": "how do I restore a backup", "k": 3}' | python examples/retrieval/keyword_retriever.py

python -m hpp retrieval eval examples/retrieval/suite.json

python -m hpp retrieval eval examples/retrieval/suite.json \
  --retriever-command '["python", "examples/retrieval/keyword_retriever.py"]'
```

Sem `--retriever-command`, a régua reproduz os `results` que cada caso carrega — aqui, o que o
`keyword_retriever.py` devolveu quando a suíte foi escrita (um teste mantém os dois iguais). Com ele,
a régua executa o seu comando uma vez por caso, com `shell=False` e um tempo limite (`--timeout`,
10 s por padrão). `-k` substitui o k da suíte.

## O que o relatório separa

Por caso, sobre os k primeiros: hit@k, recall@k, precision@k (dividida por k, então uma resposta
vazia vale 0), posto recíproco e nDCG@k com relevância binária e desconto log2.

| resultado | significado |
|---|---|
| `measured` | o recuperador respondeu; uma resposta sem nada relevante é um 0 de verdade |
| `instrument-failure` | não iniciou, estourou o tempo, saiu com código diferente de zero, saída vazia ou que não é JSON, id repetido ou que não é texto — contado à parte, nunca pontuado |

As médias são só sobre os casos **medidos**. Sem nenhum caso medido elas ficam nulas e o gate diz
`no case was measured (N instrument failures)`, nunca 0%. O gate passa quando ao menos um caso foi
medido, as falhas de instrumento não passam de `--max-failures` (padrão 0) e o recall@k médio é ao
menos `--min-recall` (padrão 0.8). Sai com 0 quando passa, 1 quando não passa, 2 quando a suíte ou
um argumento é recusado. Uma consulta que parece carregar um segredo é recusada antes de qualquer
execução, e o erro nomeia o caso.

⚠️ **Sobre a suíte que vem junto.** Sete perguntas sobre dez artigos, tudo sintético e escrito à
mão, e a linha de base por palavra-chave foi escrita junto com elas — então a nota dela prova só que
a régua funciona. Nela a linha de base chega a um recall@3 médio de 0.786 e o gate padrão reprova:
ela perde por inteiro a pergunta parafraseada (`paraphrase`) e acha um dos dois artigos que
respondem `disk-full`. Um caso com mais ids relevantes que k não consegue chegar a recall 1; escolha
o k pensando nisso. Monte a sua suíte com as suas próprias consultas rotuladas antes de ler qualquer
número como qualidade.

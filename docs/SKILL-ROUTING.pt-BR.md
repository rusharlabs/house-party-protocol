[English](SKILL-ROUTING.md) · [Português](SKILL-ROUTING.pt-BR.md)

# Roteamento consultivo de skills

`hpp skills` relaciona um objetivo declarado aos metadados inspecionáveis das skills.
Não carrega, instala ou executa skills, altera perfis, registra hooks nem chama modelos.
Uma recomendação não concede permissão e não substitui as instruções ou gates do host.

## Catálogo local e seleção preliminar

Em um checkout, substitua `./my-project` pelo projeto desejado:

```sh
python -m hpp skills catalog --target ./my-project --host codex
python -m hpp skills recommend --target ./my-project --host codex --intent "inspect database schema" --limit 3
```

`--host claude-code` lê `.claude/skills`; `codex` lê `.agents/skills`. A inspeção cobre
somente os diretórios de skills imediatamente abaixo dessa raiz explícita. Não há busca
global, nos ancestrais, cache de plugins, transcrições ou catálogo de skills embutidas.
O HPP não interpreta as configurações de ativação do host: repita `--exclude project:NOME`
para excluir entradas explicitamente.

`--include-bundled` acrescenta skills disponíveis na distribuição HPP indicada pelo
manifesto. Isso **não** comprova instalação no projeto:

```sh
python -m hpp skills catalog --target ./my-project --host codex --include-bundled
python -m hpp skills recommend --target ./my-project --host codex --include-bundled --profile ./my-project/.hpp/profile.json --intent "coordinate parallel review"
```

`--profile` aceita um perfil existente `hpp.init/v1`, com host correspondente e IDs de
módulos conhecidos. Exige `--include-bundled` e restringe **somente os módulos da
distribuição**; skills locais continuam independentes. `--manifest ARQUIVO` seleciona
outro manifesto para essa descoberta. Diretórios ausentes são informados, não inventados.
Uma instalação pip sem artefatos dos módulos não fornece um catálogo completo deles.

As identidades são `project:DIRETORIO` e `module:MODULO:DIRETORIO`. Nomes iguais continuam
distintos. Cada entrada contém nome, descrição, origem, indicador de instalação, módulo,
capacidades declaradas do módulo, caminho relativo e SHA-256 do arquivo. Capacidades
são declarações no nível do módulo, não prova de competência nem afirmação de que
cada skill individual fornece todas elas. `installed: true` significa que o arquivo foi
encontrado no diretório de projeto do host, não que o host o carregou.

Inspecione o mesmo catálogo como grafo de proveniência:

```sh
python -m hpp skills graph --target ./my-project --host codex --include-bundled
```

`graph` aceita os mesmos parâmetros comuns de `catalog`: `--target`, `--host`,
`--include-bundled`, `--manifest`, `--profile` e `--exclude` repetido. A saída
`hpp.skill-graph/v1` vincula o hash do catálogo a nós de skill, host, módulo e capacidade.
Skills ligam-se a hosts por `installed-for` ou `available-for`; módulos usam `contains`
para skills e `provides` para capacidades declaradas. Não há aresta `provides` de skill
para capacidade: pertencer a um módulo não comprova competência individual da skill.

A seleção lexical informa termos coincidentes e pontuação, com `confidence: null`.
Pontuações medem sobreposição de tokens, **não probabilidades**. Empates favorecem
entradas instaladas e depois IDs estáveis. Sem coincidência, há abstenção, não a conclusão
de que nenhuma skill é necessária. Leia as skills selecionadas antes de decidir usá-las.

## Conselho opcional de Jev ou outro decisor tipado

Exportar uma requisição ainda é uma operação local, mas seu `state` contém o objetivo e
metadados do catálogo. Revise antes de compartilhar. A pergunta Choice inclui os IDs das
skills e as opções `no-skill-needed` e `search-needed`:

```sh
python -m hpp skills request --target ./my-project --host codex --intent "inspect database schema" > skill-request.json
```

Depois da aprovação humana do provedor, dos dados transmitidos e de eventual custo, o
adaptador externo existente pode ler esse JSON diretamente pela entrada padrão. O exemplo
abaixo é uma **chamada de rede manual**, nunca uma etapa automática:

```sh
python examples/typed-decisions/decide.py --provider typesafe --model PINNED_MODEL_ID --abstain-below 0.7 < skill-request.json > skill-decision.json
```

Substitua `PINNED_MODEL_ID` por uma versão fixa disponível e confirmada pelo provedor;
não use `jev-latest`. O exemplo TypeSafe lê `TYPESAFE_API_KEY` do ambiente. Não coloque
chaves em argumentos ou arquivos versionados. Outros adaptadores estão descritos em
[decisões tipadas](../examples/typed-decisions/README.pt-BR.md). O adaptador guarda respostas
brutas em `.hpp/decisions/raw` por padrão e recusa estados acima de 60.000 caracteres;
reduza o catálogo quando necessário. Não passe `--declared`: a escolha de skill é
informativa, não uma escala ordenada de risco. Os testes offline deste recurso não
comprovam chamada real nem disponibilidade de qualquer provedor.

Consuma a resposta localmente, com os mesmos projeto, host, objetivo, exclusões, manifesto
e perfil usados na exportação:

```sh
python -m hpp skills recommend --target ./my-project --host codex --intent "inspect database schema" --decision skill-decision.json --min-confidence 0.7
```

A importação valida `hpp.decision/v1`, incluindo autoridade consultiva, e exige igualdade
do estado e da pergunta atuais. Mudanças nos bytes das skills, catálogo, objetivo ou
exclusões invalidam o conselho antigo. Recomendações de modelo/replay abaixo do limiar
viram abstenção; falhas do instrumento continuam falhas. Hashes vinculam evidência ao
conteúdo, mas não autenticam o provedor nem comprovam segurança da skill. Preserve a
resposta bruta para auditoria; o comando valida o registro, não uma assinatura do provedor.

## Resultados e limites

A saída `hpp.skill-route/v1` contém hashes do catálogo, estado e pergunta e contagens de
cobertura:

- `recommendation` + `review-skills`: inspecionar as entradas; nada é executado.
- `recommendation` + `no-skill-needed`: conselho importado indica assistência geral.
- `recommendation` + `search-needed`: conselho importado sugere descoberta, mas nenhuma
  busca ou instalação ocorre.
- `abstention` ou `instrument-failure` + `review-manually`: seguir com avaliação humana/do host.

Catálogo usa `hpp.skill-catalog/v1`; requisição usa `hpp.skill-request/v1`. Confira
`skipped` e `unavailable` no catálogo, não só a recomendação ou o grafo. Grafo e
requisição retornam 0 quando geram a saída; o grafo não inclui diagnósticos do catálogo. Catálogo retorna código 1 se houver
entradas ignoradas, senão 0; recomendação retorna 0 para uma recomendação e 1 para
abstenção/falha. Entrada inválida retorna 2; erro interno inesperado, 3.

A descoberta rejeita caminhos com links simbólicos, arquivos não regulares/grandes e
metadados inválidos. Em POSIX, percorre os diretórios por descritores vinculados e lê com
`O_NOFOLLOW`/`O_NONBLOCK`, usando `fstat` após abrir para conferir identidade, tipo regular
e tamanho. No Windows, mantém verificações de pontos de nova análise (reparse points) e
identidade, mas essas proteções **não são uma sandbox contra um sistema de arquivos
hostil com alterações concorrentes**. Inspecione somente raízes cujo conteúdo você confia.
Limites: 128 KiB por arquivo, 2.048 entradas enumeradas e 250 skills;
exceder o limite causa recusa, não truncamento silencioso. O subconjunto YAML é propositalmente
pequeno: nome e descrição, com valores escalares simples, entre aspas ou blocos dobrados/literais.
Os bytes do arquivo são lidos para o hash, mas seu corpo não vira contexto de roteamento nem
é executado. Textos parecidos com segredos são recusados; essa verificação não detecta
necessariamente todo dado privado. Revise exportações e não versione requisições/respostas
com metadados privados.

Coincidências lexicais podem ser irrelevantes, especialmente com palavras genéricas de
capacidades. Os limiares não estão calibrados para todos os catálogos e idiomas. Meça
objetivos representativos contra seu catálogo real. `hpp retrieval eval` e `hpp decide eval`
oferecem réguas separadas para ranking e decisões; este recurso não reivindica precisão
nem desempenho próprios.

## Relação com o resto do HPP

O roteamento de skills é um comando explícito, com descoberta limitada ao projeto,
registros Choice independentes de provedor e nenhuma chamada de rede ou execução automática.
HPP decision v1 mede perguntas Choice, portanto "nenhuma skill necessária" e "busca
necessária" são opções da mesma pergunta, e não uma pergunta separada.

O recurso complementa o grafo de capacidades e os perfis de montagem. O grafo descreve
capacidades dos módulos e hosts suportados, os perfis selecionam módulos e o roteamento
de skills sugere descrições adequadas ao objetivo. `hpp route` continua escolhendo o
nível de provedor conforme pisos de risco; `hpp skills` não altera esses pisos.

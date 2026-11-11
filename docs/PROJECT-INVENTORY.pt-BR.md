[English](PROJECT-INVENTORY.md) · [Português](PROJECT-INVENTORY.pt-BR.md)

# Inspecionar um projeto existente

O HPP 2.13 mede o projeto versionado antes de propor trabalho paralelo. Os comandos imprimem
em stdout: não importam a aplicação, não rodam testes, não instalam dependências nem chamam modelos.
Requisitos: Git e Python 3.10+, sem pacote de parser ou serviço de grafo.

```bash
hpp inventory --target .
hpp codegraph build --target .
hpp lanes propose --target .
```

## Universo e privacidade

O universo são os arquivos regulares da árvore do HEAD. Untracked e ignorados ficam fora;
mudanças no índice e no diretório de trabalho são reportadas como tracked alterados, sem misturar
seu conteúdo ao snapshot. Symlinks e submódulos são apenas metadados. Arquivos com nomes de
segredo, incluindo `.env` e chaves privadas, ficam fora da leitura de conteúdo.

`hpp.inventory/v1` informa manifests e extensões, caminhos de teste e pistas de runner, comandos
candidatos de CI, documentação, instruções de agentes e contagem de hooks, presença de CODEOWNERS,
quantidade de autores sem identidades e hotspots numa janela limitada de commits. Comandos
candidatos nunca são executados; comandos com formato de credencial são omitidos. Contar arquivos
não mede testes; autoria não prova responsabilidade; documentação presente não prova conteúdo atual.
Entradas ilegíveis e exclusões ficam explícitas; falha de inspeção não significa projeto vazio.

## Cache explícito e validade

```bash
hpp inventory --target . --out
hpp codegraph build --target . --out
hpp codegraph status --target .
hpp status --target . --json
```

`--out` grava `.hpp/inventory/<commit>.json` ou `.hpp/codegraph/<commit>.json`;
`--out <caminho>` escolhe o destino. Bytes diferentes já existentes e caminhos com links são
recusados. O índice Git não é alterado. Mantenha medições geradas fora do universo rastreado,
por exemplo incluindo `.hpp/` na política de ignore do seu projeto por ação própria.
Fresh exige commit igual ao HEAD e arquivos tracked limpos. Commit antigo ou edição tracked
resulta em stale, com caminhos alterados e distância em commits. Ausente e inválido também são
estados explícitos. Nenhum watcher atualiza os arquivos. Status usa perfil e medições para sugerir
inicialização, inventário, grafo ou proposta de lanes, sem executar a sugestão.

## Cobertura do grafo

`hpp.codegraph/v1` contém commit, produtor, cobertura, nós, arestas, referências não resolvidas
e estado do instrumento. O leitor AST Python mede módulos, definições, imports e chamadas
resolvidas de forma conservadora. Chamadas dinâmicas continuam não resolvidas. JavaScript e
TypeScript usam apenas sinais lexicais de imports, sem prometer parser, tipos ou runtime.
Outras linguagens ficam como não medidas. Reflexão e configuração em runtime podem criar
relações fora desta cobertura estática.

```bash
hpp codegraph build --target . --indexer-command '["your-indexer","--json"]' --timeout 30
hpp codegraph import graph.json --target .
hpp codegraph compare --declared graph.json --target .
```

Só `--indexer-command` executa programa externo: argv JSON sem shell, recebendo commit e universo
de arquivos em stdin. Escolha um programa confiável: o HPP limita tempo e saída, mas não isola
seu acesso a arquivos ou rede. JSON inválido, crash, timeout e excesso de saída são falhas do
instrumento, nunca grafos vazios bem-sucedidos, e não podem ser armazenados como medições.
Caminhos importados são relativos POSIX/NFC dentro do universo versionado. IDs duplicados são
recusados; nós excluídos e destinos de aresta não resolvidos são contados. Comparar mede concordância
dos imports Python com o leitor nativo, sem declarar nenhum dos dois completo.

## Das relações à proposta de trabalho

```bash
hpp lanes propose --target . --max-lanes 4 --depth 2 --out
hpp work plan work.json --target . --codegraph graph.json
hpp map lane lanes.json --target . --codegraph graph.json
hpp attest create --repo . --spec work.json --output attestation.json \
  --maker maker --checker checker --session review --verdict approved \
  --codegraph graph.json --base-commit <base-sha>
hpp atlas --html --target . > atlas.html
```

Propostas exigem inventário fresh. Grafo fresh fornece imports ponderados; sem ele, o fallback
agrupa diretórios e declara relações não medidas. Hubs compartilhados, custo residual entre lanes
e zonas de risco por hotspots ficam visíveis. A saída `hpp.lane-proposal/v1` é uma proposta:
uma pessoa precisa aprovar os territórios antes do despacho.
Unidades WorkGraph podem declarar `territory`, lista de prefixos relativos. O grafo opcional avisa
sobre acoplamento dentro da mesma onda. Mapas de lanes também mostram imports entre territórios.
O impacto da atestação percorre imports reversos a partir dos arquivos alterados desde o commit
base. Grafo stale deixa esse impacto não medido, preservando o gate de evidência da atestação.
O impacto cobre imports resolvidos no HEAD, sem prometer todas as dependências de runtime.
Excluir um módulo pode deixar antigos imports não resolvidos; esses caminhos exigem revisão além do fecho reportado.

O atlas offline acrescenta inventário e código do projeto em alvos Git, com validade, cobertura
e referências não resolvidas. `--inventory <arquivo>` e `--codegraph <arquivo>` selecionam entradas
dentro do alvo. `hpp graph --view code` mantém o mapa de superfícies dos módulos do protocolo;
a visão de código do projeto no atlas usa o grafo do projeto.

No Dev Squad, `pp-discovery` começa pelo inventário e `pp-xray` usa os caminhos delimitados.
Sem a árvore opcional de tarefas, as rotas de descoberta usam essas skills distribuídas, sem
inventar workflow ausente. O terminal do Lane Dashboard aceita `wave start --lane-proposal
<json-relativo>` e registra caminho, SHA-256 e commit na requisição da onda; não aprova nem aplica territórios.

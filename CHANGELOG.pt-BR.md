[English](CHANGELOG.md) · [Português](CHANGELOG.pt-BR.md)

# Changelog

Todas as mudanças relevantes do harness são registradas aqui. O formato segue
[Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e as versões seguem
[SemVer](https://semver.org/lang/pt-BR/). A versão do produto descreve o contrato do harness;
cada módulo mantém sua própria versão no `plugin.json` e no `marketplace.json`.

## [Unreleased]

## [2.4.3] — 2026-09-21

### Adicionado

- **Arquivos de comunidade para o repositório público.** `CODE_OF_CONDUCT.md` (Contributor
  Covenant 2.1, contato `atendimento@rushar.com.br`) nas duas línguas; `.github/CODEOWNERS`,
  `.github/dependabot.yml` (só GitHub Actions, semanal), três formulários de issue (`problem`,
  `feedback`, `idea`) com um `config.yml` que encaminha relatos de segurança ao canal privado,
  um template de pull request com a prova e o checklist bilíngue, e `.github/labels.json`
  (12 labels, aplicados com `gh label create` na abertura). Templates de issue e de PR são
  arquivos da interface do GitHub e ficam em inglês.
- **Workflow de release** (`.github/workflows/release.yml`): uma tag `vX.Y.Z` confere fontes de
  versão == tag (`pyproject.toml`, `hpp/__init__.py`, `hpp.manifest.json`, `CITATION.cff`),
  recusa tag sem seção não vazia nos dois CHANGELOGs, constrói wheel e sdist com `pip wheel
  --no-deps` e o hook PEP 517 do setuptools, instala o wheel offline em Linux, macOS e Windows
  e roda `hpp --version`, `doctor`, `benchmark -k 3` e `init` a partir de um diretório vazio, e
  então cria a GitHub Release com o wheel, o sdist, `SHA256SUMS` e a seção do CHANGELOG como
  notas.
- **Dois gates que eram prosa viram testes.** `tests/test_no_personal_paths.py` reprova
  qualquer caminho de perfil com letra de unidade, home do macOS ou home do Linux em arquivo de
  texto da distribuição; `tests/test_stdlib_only.py` reprova qualquer import fora da biblioteca
  padrão em `hpp/` (a suíte pode acrescentar só `pytest`) e um `dependencies` não vazio no
  `pyproject.toml`. Os dois carregam o caso plantado que prova que discriminam.
- **`scripts/repo_readiness.py`**: uma tabela datada — arquivos de comunidade, pins dos
  workflows e `persist-credentials`, fontes de versão, tag do quick start do README, caminhos
  pessoais, stdlib-only, pares en/pt-BR, tabela de módulos do README contra o
  `marketplace.json` — reutilizando os dois gates acima; exit 1 em qualquer linha reprovada.
- **Capturas de terminal medidas em vez de screenshots.** `assets/terminal/hpp-doctor.svg` e
  `assets/terminal/hpp-init.svg` são o stdout real dos dois comandos renderizado como texto por
  `scripts/render_terminal_svg.py` (paleta da marca, monoespaçada do sistema, nenhuma fonte
  embutida, alvo chamado `your-repo` para que nenhum caminho de máquina viaje); os dois READMEs
  as mostram abaixo do quick start.
- **`SECURITY.md`** ganha a tabela de versões suportadas (só 2.4.x) e a lista de superfícies
  oficiais; o quick start do README abre com um alerta `[!WARNING]` do GitHub nomeando-as.
- **`docs/GITHUB-DESCRIPTION.txt`** carrega a homepage e os topics para as configurações do
  repositório, ao lado da descrição.

### Alterado

- **A CI pina as actions por SHA de commit** (`actions/checkout` 4.4.0, `actions/setup-python`
  5.6.0) com a versão em comentário, e faz o checkout com `persist-credentials: false`.
- **O quick start do README instala a partir da tag de release** (`pip install git+…@v2.4.3`)
  em vez da branch padrão, que se move; o `repo_readiness.py` reporta quando a tag e a versão
  do pacote divergem.
- **Acabou o último Markdown só em português nos módulos.** Os dez `AGENTS.md` de módulo e os
  templates de andaime (`continuity-kit`, `agent-framework-wizard`, `lane-kit`, `operator-kit`) —
  arquivos que um agente lê ou copia para um projeto — são só em inglês; os guias de módulo
  `RALPH-GATE`, `SETTINGS-WIRE`, `LANE-KIT`, `docs/MCP-RUNBOOK`, `docs/ANTHROPIC-STANDARDS` e
  `docs/skill-template` saem em inglês com par em português, sob o mesmo gate de par.
- **A faixa do README nomeia a disciplina.** Sob a assinatura de cinco palavras, uma segunda linha
  diz `spec-driven · wave-driven · lane-isolated`, e o parágrafo de abertura conta como as três se
  ligam: uma spec compila num WorkGraph, o grafo roda em waves topológicas, sessões paralelas
  trabalham em lanes isoladas, e toda wave fecha em evidência.

### Corrigido

- Três READMEs de módulo citavam a saída do `skill_lint` como `(de N)`; a ferramenta imprime `(of N)`.
- `ARCHITECTURE` dizia que a suíte inteira roda neste repositório; um teste pula de propósito aqui.
- O README do kit-forge fixava um tamanho em bytes do `plugin.json` que já tinha mudado.

### Limitação conhecida

- Hooks e scripts ainda imprimem mensagens em português (72 de 113 scripts, 280 strings medidas em
  2026-09-21), e quatro skills citam essas saídas literalmente. Programado para a 2.5.0, junto com
  nomes em inglês para os arquivos que os módulos geram num projeto.

## [2.4.2] — 2026-09-21

### Adicionado

- **Os três contratos da raiz saem nas duas línguas.** `INSTALL-CONTRACT`, `SKILL-CONTRACT` e
  `INSTALL-GUIDE-TEMPLATE` ganham um `.md` em inglês (a fonte de verdade) com o texto em
  português como `.pt-BR.md`; a emissão copia os dois lados e o gate de par agora os cobre.
  Números de regra, nomes de campo, códigos de saída, caminhos e blocos de código são idênticos
  nos dois lados.
- **O wheel carrega a suíte de benchmark.** `examples/reliable-coding` viaja dentro do pacote
  como cópia byte-idêntica (`hpp/examples/`, guardada por `tests/test_installed_package.py`),
  então `hpp benchmark` e `hpp --self-test` rodam a partir de uma instalação por pip, e o
  `hpp init` dessa instalação mede o benchmark em vez de reportar a suíte como não embarcada
  (prontidão `7/11` ali, `9/11` a partir de um clone do repositório).
- **O `docs/UX-INSTALL-JOURNEY` abre com a jornada do `hpp init`** — seis estágios, plano e depois
  `--apply`, prontidão por canal, flags e códigos de saída, cada um com saída medida — e mantém a
  jornada do instalador de módulos como segundo caminho.
- **Metadados do pacote.** O `pyproject.toml` declara readme, licença (expressão SPDX), autores,
  palavras-chave, classificadores e URLs do projeto; `pip show -v house-party-protocol` os reporta.
- **O `CITATION.cff` está amarrado ao pacote** por `tests/test_citation.py`: a versão é igual a
  `hpp.__version__`, o abstract é igual ao parágrafo de abertura do README, as palavras-chave
  nomeiam os dois hosts.

### Alterado

- **O README, o manual, o `ARCHITECTURE` e o `CONCEPTS` descrevem o repositório como o que ele
  é: a distribuição emitida** — módulos, `CHECKSUMS.txt`, `marketplace.json` e o instalador ao
  lado do harness. A saída citada do `hpp init` é a real por canal (`9/11 verified` a partir de
  um clone, `7/11` a partir de uma instalação por pip, as duas medidas em 2026-09-21), o
  instalador é nomeado onde vive, e o `hpp doctor` é citado como imprime
  (`HPP doctor: ok · modules=10 · hosts=claude-code, codex`; o cruzamento da distribuição só
  aparece em `--json`).
- **Os vetores da marca usam só os quatro tokens da paleta.** Os `assets/*.svg` não carregam
  mais `#E5484D`, `#FF8A3D`, `#A8ADB5` nem `#6B7280`; os degraus mais claros são `#FF6A00`,
  `#F4F1EB` ou `#0F1113` com opacidade reduzida. O lockup raster aprovado e os PNGs de ícone
  ficam intocados.
- **O comentário da CI bate com a árvore em que roda.** O passo do `CHECKSUMS.txt` diz que é um
  gate real no repositório publicado e um no-op só na árvore-fonte do harness.
- **O `CONTRIBUTING` descreve um fluxo que um terceiro consegue rodar de fato.** As fontes dos
  módulos e os manifestos da forja não são publicados, então o fluxo é: editar dentro do módulo
  emitido, provar com `kit_doctor.py verify` (a divergência de checksum nos seus arquivos é o
  sinal esperado), `skill_lint`, `hpp doctor`, `hpp benchmark` e `pytest`, e abrir o pull
  request; os mantenedores incorporam a mudança na fonte, sobem a versão e re-emitem. A exigência
  de sign-off DCO saiu: abrir um pull request é o acordo de que a contribuição é licenciada sob
  MIT. A regra bilíngue agora diz o que quem contribui faz na prática (camada de agente em
  inglês, documentos humanos em pares).
- **O `SECURITY` trata o canal de e-mail como igual** ao relato privado de vulnerabilidade do
  GitHub, e diz o que fazer quando o botão de relato privado não está lá.
- **A camada de agente é em inglês.** Todo arquivo que um agente lê para executar — 33 skills,
  14 commands, 14 agents, 13 rules, output styles — foi traduzido do português com invariantes de
  estrutura conferidas (títulos por nível, blocos de código, chaves de frontmatter, links, linhas
  de tabela). O `skill_lint` agora trata os tokens de esquema em inglês (`## Contract`, `## Proof`,
  `## When NOT to Activate`, `Priority:`, `INPUT/OUTPUT/STATE IT TOUCHES`, `<!-- executed: … -->`)
  como canônicos e continua aceitando os em português como legado; o `SKILL-CONTRACT.md`
  documenta os dois.
- **A `description` dos módulos é em inglês** no `marketplace.json` e nos dez `plugin.json` (o
  campo que a interface de plugins mostra); o texto em português foi para `description_pt`, que o
  catálogo usa.
- **Os dez READMEs de módulo foram re-medidos contra a árvore emitida**: os comandos de instalação
  por cópia apontam para o diretório atual do módulo, o caminho do instalador é
  `instaladores/kit-forge-1.4.0/`, as saídas citadas (`skill_lint`, `--interview`, `--self-test`,
  a prova do health-kit) foram re-executadas hoje, as contagens batem com `ls`, e o lado em inglês
  não carrega mais seções em português.
- **Cada módulo emitido carrega `SANITIZATION.md` + `SANITIZATION.pt-BR.md`** (gerados) em vez de
  um `SANITIZACAO.md` só em português.
- **O catálogo abre com o lockup do produto e as cinco palavras**, como o manual.

### Corrigido

- **`hpp benchmark` e `hpp --self-test` a partir de uma instalação por pip saíam com 3 e
  `internal error: FileNotFoundError`**, porque a suíte era resolvida um nível acima do pacote e o
  wheel não carregava `examples/`. A suíte agora é resolvida a partir do pacote, e um caminho de
  suíte ausente (`hpp eval run <ausente>` incluído) é uma recusa de uma linha com exit 2.
- **`hpp doctor` — e os relatórios de uma linha de `status` e `benchmark` — num stream cp1252**
  escreviam o ponto mediano como o byte `0xB7`, que se lia como `�` adiante; agora passam pelo
  mesmo console do `hpp init` e degradam para ASCII (`-`).
- **O `.gitignore` cobre `.hpp/`**, o diretório que os próprios exemplos de `hpp event append` e
  `hpp init --apply` do README criam dentro de um checkout.
- **O `CITATION.cff` descrevia a versão 1.4.0**, com um abstract de "dez kits para Claude Code" e
  sem palavra-chave de Codex; agora descreve a versão do pacote (um teste a amarra ao `hpp.__version__`), datada de 2026-09-21, com o parágrafo de
  abertura do README e `codex-cli` entre as palavras-chave.
- **O carimbo de medição do manual dizia 2.4.0** enquanto o cabeçalho dizia 2.4.1; agora ele
  carimba a data e a versão contra as quais as saídas citadas foram medidas.
- **`continuity-kit` e `lane-kit` instalados como plugin não armavam hook nenhum.** Os dois
  trazem hooks, mas o `plugin.json` não tinha a chave `hooks` nem havia `hooks/hooks.json`; agora
  os dois declaram seus hooks (SessionStart/Stop/PreCompact; SessionStart/PreToolUse/PostToolUse)
  pelo mesmo shim `pyrun.sh` dos outros módulos.
- **`kit_doctor.py verify` devolvia `warn` depois dos smoke tests do próprio módulo** porque
  contava `__pycache__` e `.pyc` como extras. Bytecode e caches do pytest deixaram de ser extras;
  um arquivo real perdido continua sendo.
- **O estágio de perfil escrevia um arquivo que o módulo nunca lê** (`profile.yaml` para módulos
  cujo loader lê `operator-profile.yaml`) e não copiava nada para o `lane-kit` (o exemplo dele
  vive em `templates/`). O estágio agora deriva o nome do alvo do loader do módulo e olha
  `templates/` também.
- **`skill_lint --run-proofs` no Windows criava um arquivo `self-test` perdido**: o comentário
  `# -> …` no fim de uma linha de prova ia para o `cmd.exe` e o `>` virava redirecionamento, e
  `${CLAUDE_PLUGIN_ROOT}` não era expandido. Comentários finais são removidos e a variável é
  expandida para a raiz do módulo antes de rodar.
- **O manifesto de instalação do próprio `kit-forge` dizia `plugin: false` para o Claude Code**
  enquanto ele traz um `plugin.json` e está listado no marketplace.

### Limitação conhecida

- **As mensagens de runtime ainda são em português.** O Markdown que um agente lê é inglês, mas
  os hooks e scripts que ele roda imprimem suas mensagens em português (59 de 81 scripts, medido:
  `grep -rlE 'ção|não |você|é ' --include=*.py --include=*.sh`), e as skills citam essas saídas
  literalmente. Traduzi-las é mudança de comportamento com teste por script e é a próxima
  release; até lá quem não lê português vê instruções em inglês e logs em português.

## [2.4.1] — 2026-09-21

### Adicionado

- **Os documentos humanos que faltavam ganharam o par em português.** `CONTRIBUTING`, `SECURITY`
  e `docs/UX-INSTALL-JOURNEY` saem como irmãos `.pt-BR.md`, e o manual operacional como
  `docs/MANUAL.pt-BR.html`, todos sob o mesmo gate de par.
- **O catálogo é gerado nos dois idiomas e na paleta da marca.** Um passe do gerador escreve
  `docs/CATALOGO.md`, `CATALOGO.pt-BR.md`, `CATALOGO.html` e `CATALOGO.pt-BR.html` a partir do
  `marketplace.json` (que agora carrega `description_en` por módulo); a página HTML escrita à mão,
  só em português e na paleta aposentada, foi substituída pela gerada para não divergir de novo.

### Alterado

- **O manual operacional foi reescrito contra o comportamento medido.** Vereditos de política
  (`ALLOW / MANUAL / BLOCK` e com que código cada modo sai), as nove projeções de mapa, os estados
  do monitor incluindo `skew`, os seis estágios do `hpp init` com a prontidão que ele reporta num
  alvo vazio, os caminhos do Codex CLI, attestation e códigos de saída são os que a CLI produz hoje.
- **O endereço público do autor é `https://rusharlabs.com`** na licença, na citação, no aviso, no
  marketplace e em todo manifesto de módulo; o e-mail de contato de segurança não mudou.
- **O Quickstart instala a CLI com `pip`** e mantém o checkout como caminho de quem desenvolve.
  Restos de empacotamento (`build/`, `*.egg-info/`) são ignorados pelo repositório.

### Corrigido

- **O pacote instalado via pip saía sem o manifesto.** O `pip install` produzia um
  `site-packages/hpp/` sem `hpp.manifest.json`, então de qualquer diretório fora de um checkout
  `hpp doctor` e `hpp init` saíam com código 2 e "hpp.manifest.json not found". O wheel agora
  carrega o manifesto como package data, e o resolvedor cai para ele depois do diretório de
  trabalho e da raiz da fonte — um checkout continua vencendo, e o site-packages nunca é tratado
  como distribuição emitida. Guardado por testes que constroem um wheel real e o acionam de um
  diretório vazio.

## [2.4.0] — 2026-09-21

### Adicionado

- **Documentação bilíngue.** Todo documento que uma pessoa lê antes de decidir usar o projeto
  passa a existir em inglês e em português, pareados como `NOME.md` e `NOME.pt-BR.md`, com links
  recíprocos no topo. Os arquivos que um agente lê para executar — skills, comandos e regras —
  ficam em uma língua só, de propósito: traduzi-los dobra a manutenção e convida à divergência
  silenciosa.
- **Um gate que mantém o par honesto.** `test_documentacao_bilingue` reprova par ausente, link de
  topo quebrado, divergência estrutural (os dois lados carregam os mesmos títulos, na mesma ordem
  — tradução muda palavra, não estrutura), blocos de código diferentes (comando é comando em
  qualquer idioma) e qualquer tentativa de traduzir arquivo da camada de agente. Nove controles
  provam que o gate sabe reprovar.

### Corrigido

Cinco defeitos de uma auditoria externa, cada um reproduzido antes do conserto:

- **A memória de falhas podia nunca disparar.** Ela escutava apenas o evento de sucesso, enquanto
  a falha de ferramenta chega em outro. Medido com payload real: nada era gravado. Agora escuta os
  dois e deduplica pela chamada.
- **O gerador de skills podia escrever fora do alvo.** Um nome de módulo com travessia escapava do
  destino; um link de diretório fazia um arquivo de fora da árvore ser copiado sem reporte; dois
  nomes que diferiam só no separador colapsavam em um, em silêncio.
- **Um smoke que estourava o tempo era registrado como sucesso** e não contava como falha.
- **Cache ilegível e cache ausente eram indistinguíveis** na sonda de serviço.
- **Doze comandos prometiam uma árvore com zero arquivos.** A capacidade não foi inventada: a
  dependência externa passou a ser declarada, junto do que continua funcionando sem ela.

- O piso de Python publicado passa a ser a menor versão que a matriz de CI de fato exercita. O
  código não usa sintaxe exclusiva dela, então a promessa anterior era plausível — e não verificada.

## [2.3.0] — 2026-09-21

### Adicionado

- **`hpp init` — a instalação virou uma experiência.** Um wizard que cumpre os seis estágios do
  contrato de instalação (`detect → prereqs → profile → configure → wire-suggest → smoke`), com
  sequência de abertura onde **cada linha aparece quando o estágio correspondente termina de
  verdade** — o movimento é o progresso, não enfeite. Fecha com o lockup da marca em blocos de
  terminal e a assinatura da instalação.
- **Readiness medido, não estimado.** Uma barra e uma contagem (`7/11 verified`) derivadas do que
  foi de fato verificado — host, integridade da distribuição, checksum por módulo, classificador
  de política, gate de benchmark. Cada item mostra o comando que o produziu, e o que não foi
  medido aparece como **não verificado**, nunca como zero nem como cem.
- **Degradação declarada de cor e movimento:** truecolor → 256 cores → 16 cores → nenhuma, com
  `NO_COLOR` e `--no-animation` respeitados, fallback de glifo quando o terminal não codifica
  blocos, e saída completa sem TTY. `--non-interactive`, `--yes`, `--profile` e `--modules` para
  CI e agentes: nenhum prompt é alcançado nesse modo.
- Sem `--apply`, o wizard **imprime o plano e não escreve nada** — provado por hash da árvore
  antes e depois. `wire-suggest` mostra o bloco para colar e nunca toca em `settings`.

### Alterado

- **Identidade visual unificada na marca aprovada.** O material anterior usava uma paleta que
  antecedia o lockup e não tinha relação com ele. Agora são quatro cores e um acento só — preto,
  carvão, branco-quente e laranja de sinal —, medidas no próprio lockup. O README abre com a arte
  oficial, e `docs/BRAND.md` descreve o sistema, incluindo como a marca se comporta no terminal.

### Corrigido

- A suíte carregava um **caminho absoluto com nome de usuário**, o que a prendia a uma única
  máquina e fazia esse caminho viajar no pacote publicado. A raiz passou a ser derivada da posição
  do arquivo, com `HPP_EMITTED_COPY` para apontar outra árvore.

## [2.2.0] — 2026-09-21

### Adicionado

- Suíte de testes própria do harness (`tests/`, 106 casos, stdlib-only, sem rede): contrato do
  CLI derivado do manifesto, coerência de versão entre manifesto/pacote/módulo, classificação de
  comando destrutivo, event log append-only e retomada, ciclo e waves do WorkGraph, orçamento de
  contexto, e conferência de `CHECKSUMS.txt`. Cada arquivo carrega ao menos um controle que prova
  que o teste sabe reprovar.
- Integração contínua em 12 combinações (Linux, macOS e Windows × Python 3.10–3.13), executando a
  suíte, `hpp doctor` e `hpp benchmark -k 3` — os controles do próprio produto, pelo CLI real.
  Permissões mínimas de leitura e sem passo mascarado por `continue-on-error`.
- Estado `skew` no Monitor Map, com tolerância declarada e publicada (`--skew-tolerance`).

### Corrigido

Sete defeitos reproduzidos antes do conserto, cada um com teste que falha antes e passa depois:

- **Política de comandos ignorava a ordem das flags.** `rm -rf` era bloqueado, mas `rm -fr`,
  `rm -r -f`, `rm --recursive --force` e a forma com `sudo` passavam como permitidas. A
  classificação agora lê o conjunto de opções de cada invocação, para em `--` e segmenta por
  `| ; &` — sem transformar `rm arquivo.txt`, `grep -rf padroes.txt` ou `cp -rf a b` em bloqueio.
- **Orçamento de contexto não cobrava o separador entre blocos**, então o número publicado era
  menor que o texto entregue e o teto podia ser estourado. `used` passa a ser o tamanho real.
- **Sinal de monitor com timestamp no futuro era reportado como saudável** — relógio adiantado ou
  timestamp fabricado viravam frescor.
- **Memória de falhas persistia segredo em texto claro** e o devolvia no relato. Toda entrada passa
  por redaction por forma (chave privada, credencial em URL, `Bearer`/`Basic`, prefixos de
  provedor, JWT, `chave=valor`, blob de alta entropia), registrando tipo e comprimento — nunca o
  valor. Erro sem segredo continua legível.
- **A escrita de `settings.json` não era atômica** nos três instaladores que a fazem: uma queda no
  meio truncava o arquivo e um update concorrente era perdido em silêncio. Agora é temporário no
  mesmo diretório, `fsync` e `os.replace`, com comparação byte a byte antes de trocar — divergência
  recusa a escrita (saída `2`) em vez de sobrescrever.
- **O scanner de segredo suprimia a linha inteira** quando ela continha um exemplo permitido: um
  valor real na mesma linha passava. A supressão passou a valer para a ocorrência, não para a linha.
- **A verificação de `CHECKSUMS.txt` aceitava inventário vazio como sucesso** e caminho que escapa
  do módulo (`../fora.txt`, caminho absoluto). As três formas agora reprovam com saída `2`.

## [2.1.0] — 2026-09-20

### Adicionado

- Attestation provider-neutral que vincula aprovação a spec, identidade do repositório,
  commit-base, snapshot completo, maker, checker e identificador de revisão.
- `hpp attest create` e `hpp attest verify`, com bloqueio quando conteúdo rastreado, staged,
  removido ou untracked diverge após a inspeção.
- Controle executável no benchmark para provar aprovação válida e invalidação após mutação.

### Corrigido

- URLs de clone, marketplace e releases apontam para a conta canônica `rushar-labs`.

## [2.0.0] — 2026-09-20

### Adicionado

- Núcleo local-first e stdlib-only em `python -m hpp`, com manifesto raiz, doctor, instalação
  planejada, estado append-only, retomada, avaliação e benchmark.
- WorkGraph spec-driven com rejeição de ciclos, critérios de aceite e waves topológicas.
- Capability, Agent, Lane, Code, Evidence, Monitor e grafo operacional como projeções
  determinísticas, sem daemon ou banco de grafo.
- Context compiler com orçamento, proveniência e hash; recusa de material semelhante a segredo.
- Roteamento provider-neutral por tiers `economy`, `balanced` e `frontier`, com piso de risco e
  fallback explícito apenas para cima.
- Monitor Map com alvo, cadência, frescor, severidade, custo e gate consumidor; nenhum monitor é
  iniciado de forma oculta.
- Benchmark reproduzível com controles declarados e runner standalone de `pass@k` e `pass^k`.
- Identidade visual Signal Path aplicada ao README, manual, catálogo e ativos SVG.

### Alterado

- O posicionamento passa a liderar com harness → protocol → módulos → distribuição.
- O `operator-kit` 1.4.0 pode bloquear famílias confiáveis em modo `enforce` e mantém `audit`
  explícito para regras advisory.
- A documentação diferencia saúde do serviço, frescor do sinal e correção do resultado.
- Claude Code e Codex CLI compartilham o mesmo contrato; diferenças de host permanecem visíveis.

### Corrigido

- `passk_eval.py` não depende mais de pacote externo nem de modo degradado.
- A release não publica duas versões vivas do mesmo módulo.

## [1.5.0] — 2026-09-20

### Adicionado

- Suporte comprovado ao **Codex CLI**: `AGENTS.md` na raiz e nos dez kits, instalação por
  cópia em `.agents/hpp/` e geração namespaced das 33 skills em `.agents/skills/`.
- **14 subagents** com `tools` explícitos: 12 papéis de desenvolvimento, um refutador e um
  caçador de falhas silenciosas; os três checkers são read-only.
- Roteador de **checker cross-provider** que detecta Codex, Cursor e Gemini sem executar
  ferramentas nem alterar permissões.
- `preflight.py` para validar Python, PyYAML, repositório Git e settings gravável antes do
  done gate, além de `docs/MCP-RUNBOOK.md` e 24 padrões em `docs/TIPS.md`.
- Registro de skills externas candidatas com origem, licença, blob e decisão explícitos.

### Alterado

- A publicação agora reprova skills fora do contrato e cobre ruído de revisão, nomes de
  casa e narrativa de marca descartada.
- O catálogo passa a inventariar subagents, documentos, registros e recursos transversais.
- A identidade visual e a descrição geral usam a metáfora original de componentes sob o
  mesmo teto, sem referências a personagens ou franquias externas.

### Corrigido

- O gerador Codex preserva LF ou CRLF do frontmatter e não ativa hooks do Claude Code.
- Scripts que produziam metadados internos agora usam rationale impessoal e termos públicos.

## [1.4.0] — 2026-09-20

Primeira versão pública. Dez kits, um contrato de saída único (`0` ok · `1` warn · `2` block ·
`3` erro), `CHECKSUMS.txt` por kit e `SANITIZACAO.md` declarando o que foi retirado antes de
publicar.

### Adicionado

| kit | versão | o que entrega |
|---|---|---|
| operator-kit | 1.3.0 | `done_gate` de três estados, `/ralph-gate`, ledger de dívida e 13 regras instaláveis |
| kit-forge | 1.4.0 | assembler, lint de IP/PII, instalação em seis estágios e zip verificado |
| lane-kit | 1.2.0 | coordenação de sessões, maker ≠ checker e lock por diretório |
| continuity-kit | 1.2.1 | handoff, rederivação e verificação antes de retomar |
| claude-dev-kit | 1.3.1 | criação de skills, hooks e plugins com wiring reversível |
| health-kit | 1.3.1 | sonda config-driven e statusline cache-first |
| dev-squad-kit | 1.0.0 | 12 papéis e consolidação paralela |
| agent-framework-wizard | 1.1.1 | wizard de seis passos para agente ou skill |
| supabase-pack | 1.1.0 | auditoria RLS e scaffold de Edge Function |
| gotcha-memory | 1.0.0 | falha recorrente transformada em lição operacional |

### Portabilidade

- Hooks resolvem `.venv`, `python3` ou `python` por `hooks/pyrun.sh`.
- Kits são emitidos em LF e levam checksums dos bytes distribuídos.

[1.4.0]: https://github.com/rushar-labs/house-party-protocol/releases/tag/v1.4.0
[1.5.0]: https://github.com/rushar-labs/house-party-protocol/releases/tag/v1.5.0
[2.0.0]: https://github.com/rushar-labs/house-party-protocol/releases/tag/v2.0.0
[2.1.0]: https://github.com/rushar-labs/house-party-protocol/releases/tag/v2.1.0
[2.2.0]: https://github.com/rushar-labs/house-party-protocol/releases/tag/v2.2.0
[2.3.0]: https://github.com/rushar-labs/house-party-protocol/releases/tag/v2.3.0
[2.4.0]: https://github.com/rushar-labs/house-party-protocol/releases/tag/v2.4.0

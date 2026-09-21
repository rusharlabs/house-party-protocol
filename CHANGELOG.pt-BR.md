[English](CHANGELOG.md) · [Português](CHANGELOG.pt-BR.md)

# Changelog

Todas as mudanças relevantes do harness são registradas aqui. O formato segue
[Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e as versões seguem
[SemVer](https://semver.org/lang/pt-BR/). A versão do produto descreve o contrato do harness;
cada módulo mantém sua própria versão no `plugin.json` e no `marketplace.json`.

## [Unreleased]

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

# Changelog

Todas as mudanças relevantes do harness são registradas aqui. O formato segue
[Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e as versões seguem
[SemVer](https://semver.org/lang/pt-BR/). A versão do produto descreve o contrato do harness;
cada módulo mantém sua própria versão no `plugin.json` e no `marketplace.json`.

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

[1.5.0]: https://github.com/rusharlabs/house-party-protocol/releases/tag/v1.5.0
[1.4.0]: https://github.com/rusharlabs/house-party-protocol/releases/tag/v1.4.0
[2.0.0]: https://github.com/rusharlabs/house-party-protocol/releases/tag/v2.0.0

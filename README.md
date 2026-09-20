<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/hpp-banner-dark.svg">
    <img alt="House Party Protocol — dez kits, uma régua comum" src="assets/hpp-banner-light.svg" width="100%">
  </picture>
</p>

<p align="center">
  <a href="LICENSE"><img alt="MIT" src="https://img.shields.io/badge/licen%C3%A7a-MIT-0000FF"></a>
  <a href="#os-dez-kits"><img alt="10 kits" src="https://img.shields.io/badge/kits-10-FF00FF"></a>
  <img alt="Claude Code e Codex CLI" src="https://img.shields.io/badge/hosts-Claude%20Code%20%7C%20Codex%20CLI-0B0B12">
  <img alt="macOS, Linux e Windows" src="https://img.shields.io/badge/macOS%20%C2%B7%20Linux%20%C2%B7%20Windows-port%C3%A1vel-59636E">
</p>

# House Party Protocol

**Dez kits. Uma régua comum: prova antes de “pronto”.**

House Party Protocol é um marketplace aberto de componentes para operar agentes de código
com menos confiança implícita e mais evidência reproduzível. Cada kit cobre uma falha
operacional específica — conclusão sem teste, sessões que colidem, contexto que se perde,
saúde aparente, memória que não aprende — sem exigir que você adote o conjunto inteiro.

Funciona com **Claude Code** como marketplace de plugins e com **Codex CLI** por instalação
determinística em `.agents/`.

## Comece pela falha que você quer evitar

| Se o problema é... | Comece por | A prova que ele exige |
|---|---|---|
| “pronto” sem verificação | `operator-kit` | comando, saída e exit code frescos |
| duas sessões no mesmo caminho | `lane-kit` | claim, território e maker ≠ checker |
| retomada após crash ou `/clear` | `continuity-kit` | handoff com rederivação antes de repetir |
| serviço verde com dado stale | `health-kit` | saúde de serviço separada da saúde do dado |
| falha recorrente sem aprendizado | `gotcha-memory` | recorrência classificada antes da próxima tentativa |
| criação de skills/hooks sem contrato | `claude-dev-kit` + `kit-forge` | lint, self-test, manifesto e checksum |

## Instalação rápida

### Claude Code

```bash
/plugin marketplace add rushar-labs/house-party-protocol
/plugin install operator-kit@house-party-protocol
```

### Codex CLI

```bash
python instaladores/kit-forge-1.4.0/kit_doctor.py install --kit frameworks-com-plugins/operator-kit-1.3.0 --host codex --target /caminho/do/repo --apply
codex -C /caminho/do/repo
```

O instalador copia o runtime completo para `.agents/hpp/operator-kit/` e gera as skills com
namespace `hpp-...` em `.agents/skills/`. Ele não altera `~/.codex/config.toml` e não ativa
hooks do Claude Code no Codex.

## Por que “House Party Protocol”

Uma house party só funciona quando cada pessoa sabe por que está ali, o que pode tocar e
quando precisa parar. O projeto aplica essa ideia a agentes: muitos componentes podem atuar
sob o mesmo teto, mas entram por um protocolo comum — fronteira explícita, gate humano para
o sensível, segunda medição e handoff verificável.

O símbolo do projeto mostra isso: dez nós independentes, um anel de coordenação e uma conexão
medida. Não existe peça decorativa; existe responsabilidade observável.

## O protocolo

Quatro invariantes atravessam os dez kits:

1. **Quem constrói não aprova.** Revisores são read-only por configuração, não por promessa.
2. **A régua acompanha o número.** Toda contagem ou estado vem com o comando que o produziu.
3. **O controle antecede o zero.** Um detector só declara ausência depois de provar que encontra um caso vivo.
4. **O gate sabe reprovar.** Cada proteção nasce com um teste que falha antes e passa depois.

O [`MANIFESTO.md`](MANIFESTO.md) desenvolve os princípios completos.

## Os dez kits

| Kit | Versão | O que entrega |
|---|---:|---|
| **operator-kit** | 1.3.0 | Gates de conclusão, execução com guardrails, planejamento e regras instaláveis. |
| **kit-forge** | 1.4.0 | Montagem, lint de IP/PII, contrato de skills, checksums, instalação e publicação. |
| **lane-kit** | 1.2.0 | Coordenação de sessões, locks por território e maker/checker cross-provider. |
| **continuity-kit** | 1.2.1 | Handoff, retomada e espelho de estado com verificação antes de repetição. |
| **claude-dev-kit** | 1.3.1 | Criação de skills, hooks e plugins com wiring reversível. |
| **health-kit** | 1.3.1 | Probe config-driven e statusline cache-first. |
| **dev-squad-kit** | 1.0.0 | Papéis especializados, subagents e consolidação paralela. |
| **agent-framework-wizard** | 1.1.1 | Wizard de seis passos para esqueleto de agente ou skill. |
| **supabase-pack** | 1.1.0 | Auditoria RLS e scaffold de Edge Function. |
| **gotcha-memory** | 1.0.0 | Falha → recorrência → lição injetada antes da próxima execução. |

O inventário gerado de skills, agents, hooks, regras, templates e scripts está em
[`docs/CATALOGO.md`](docs/CATALOGO.md).

Os 24 atalhos operacionais estão em [`docs/TIPS.md`](docs/TIPS.md). Antes de um
`done_gate`, valide Python, PyYAML, Git e a escrita de settings:

```bash
python frameworks-com-plugins/operator-kit-1.3.0/scripts/preflight.py --project .
```

## Codex CLI

O suporte ao Codex é explícito, não uma adaptação presumida:

- `AGENTS.md` existe na raiz e dentro de cada kit;
- skills de repositório usam o diretório oficial `.agents/skills`;
- skills duplicadas entre kits recebem namespace durante a geração;
- o runtime original fica em `.agents/hpp/<kit>` para scripts e recursos continuarem juntos;
- `${CLAUDE_PLUGIN_ROOT}` é removido das cópias geradas;
- `hooks.json`, slash commands e lifecycle hooks do Claude Code não são armados no Codex.

Prova mínima do `operator-kit` após a instalação:

```bash
python .agents/hpp/operator-kit/scripts/done_gate.py --self-test
python .agents/hpp/operator-kit/scripts/live_count.py --self-test
python .agents/hpp/operator-kit/scripts/claude_md_from_profile.py --self-test
```

O Codex descobre as skills automaticamente. Use `/skills` ou mencione uma skill com `$`.

## Claude Code

No Claude Code, cada kit mantém sua estrutura nativa de plugin:

- `.claude-plugin/plugin.json` para metadados;
- `skills/`, `commands/` e `agents/` quando aplicável;
- `hooks/hooks.json` para lifecycle hooks do host;
- `${CLAUDE_PLUGIN_ROOT}` para resolver recursos do plugin.

O caminho por cópia também funciona sem marketplace:

```bash
python instaladores/kit-forge-1.4.0/kit_doctor.py install --kit <caminho-do-kit> --host claude-code --target <repo>
python instaladores/kit-forge-1.4.0/kit_doctor.py install --kit <caminho-do-kit> --host claude-code --target <repo> --apply
```

O primeiro comando imprime o plano; o segundo aplica. Configurações já existentes não são
sobrescritas silenciosamente.

## O que cada host recebe

| Capacidade | Claude Code | Codex CLI |
|---|---|---|
| Skills | plugin `skills/` | cópia gerada em `.agents/skills/` |
| Instruções do projeto | `CLAUDE.md`/docs do kit | `AGENTS.md` |
| Scripts Python | runtime do plugin | `.agents/hpp/<kit>/` |
| Hooks lifecycle | nativos via `hooks.json` | não aplicados; execução explícita |
| Slash commands | quando o kit fornece | não convertidos automaticamente |
| Self-tests | `python ... --self-test` | o mesmo comando no runtime copiado |

## Três contratos, um resultado

| Contrato | O que impede | Gate |
|---|---|---|
| [`INSTALL-CONTRACT.md`](INSTALL-CONTRACT.md) | instalação que sobrescreve estado ou esconde pré-requisito | `kit_doctor install` |
| [`SKILL-CONTRACT.md`](SKILL-CONTRACT.md) | skill vaga, sem I/O, prova ou portabilidade | `skill_lint.py` |
| [`INSTALL-GUIDE-TEMPLATE.md`](INSTALL-GUIDE-TEMPLATE.md) | guia sem instalação, prova e rollback | revisão + publicação |

Convenção de saída: **`0` ok/no-op · `1` warn · `2` block · `3` erro**.

## Estrutura

```text
house-party-protocol/
├── AGENTS.md                 # instruções para Codex CLI
├── marketplace.json          # catálogo dos 10 kits
├── frameworks-com-plugins/   # operator, dev, health, squad e Supabase
├── multi-sessao/             # lane-kit
├── continuidade/             # continuity-kit e gotcha-memory
├── wizards/                  # agent-framework-wizard
├── instaladores/             # kit-forge
└── docs/                     # catálogo gerado e padrões táticos
```

## Verificação do pacote

```bash
python instaladores/kit-forge-1.4.0/kit_doctor.py marketplace .
python instaladores/kit-forge-1.4.0/kit_doctor.py verify frameworks-com-plugins/operator-kit-1.3.0
python instaladores/kit-forge-1.4.0/tools/skill_lint.py --all frameworks-com-plugins/operator-kit-1.3.0/skills
```

Cada kit inclui `CHECKSUMS.txt`; o catálogo é regenerado a partir da árvore que realmente será
distribuída.

## Contribuir

Leia [`CONTRIBUTING.md`](CONTRIBUTING.md). Uma mudança entra com escopo cirúrgico, teste que
reproduz a falha e prova fresca do resultado. Crédito e origem viajam com o código.

## Licença

MIT — ver [`LICENSE`](LICENSE). Copyright © 2026 Max Parisi (Rushar Labs).

<p align="center"><sub>Rushar Labs · Ideias · Sistemas · Pessoas · Impacto — <em>Construindo o que vem depois.</em></sub></p>

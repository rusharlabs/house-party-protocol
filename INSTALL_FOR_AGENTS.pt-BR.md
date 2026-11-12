[English](INSTALL_FOR_AGENTS.md) · [Português](INSTALL_FOR_AGENTS.pt-BR.md)

# Instalando o House Party Protocol — guia para agentes

Para instalar somente a CLI do core, sem os módulos, a alternativa versionada é:

```bash
python -m pip install git+https://github.com/rusharlabs/house-party-protocol@v2.14.0
```

Este guia cobre o HPP 2.14.0 e versões posteriores; versões anteriores não incluem `hpp setup` nem
`scripts/setup_hpp.py`. O comando atual `hpp init` planeja e registra um perfil; ele não instala
módulos nem ativa integrações do host.

House Party Protocol (HPP) é um conjunto local-first para confiabilidade, governança e avaliação de
agentes de código. O core não chama modelos nem manipula credenciais. A instalação prepara um
ambiente Python isolado no projeto e instala os módulos escolhidos. A ativação do host e as
integrações opcionais são estados separados e devem ser reportados como tais.

## Antes de instalar

Tenha Python 3.10 ou mais novo, Git e o host escolhido (Claude Code ou Codex CLI) instalados. Faça
login no host por conta própria; o HPP não instala software de sistema, troca contas nem gerencia
login, assinatura ou custo de modelos. Credenciais Supabase só são necessárias se você configurar
essa integração opcional. Orca também é opcional.

Use um único checkout completo do produto público em `github.com/rusharlabs/house-party-protocol`
para o bootstrap e para `hpp setup --source`. Não crie uma segunda cópia do produto. O bootstrap
prepara o projeto, um `.hpp/venv` isolado, dependências fixadas e a CLI do HPP, e então chama o
planejador offline de instalação. O `--apply` pode acessar o índice de pacotes Python para instalar
dependências fixadas. O core do HPP e a instalação dos módulos não fazem chamadas de inferência a
modelos.

Clone uma vez e rode os comandos a partir da raiz desse checkout. Mantenha o projeto consumidor
existente fora do checkout do produto:

```bash
git clone https://github.com/rusharlabs/house-party-protocol.git
cd house-party-protocol
```

## Escolha um pacote

| Seleção | Claude Code | Codex CLI |
|---|---:|---:|
| `reliable-coding` (padrão) | 6 módulos | 6 módulos |
| todos os módulos compatíveis | 10 módulos | 9 módulos |

O Codex não suporta `claude-dev-kit`. A seleção de todos os compatíveis o omite; um pedido explícito
de módulo incompatível é recusado, sem contornar a restrição. Selecione IDs individuais apenas quando
souber qual integração precisa.

## Planeje, revise, aplique

A partir da raiz desse único checkout público do produto, rode o plano do bootstrap. No Windows,
use `python`; no macOS, use `python3`:

```powershell
python -I -B scripts/setup_hpp.py --target <projeto> --host claude-code
python -I -B scripts/setup_hpp.py --target <projeto> --host claude-code --all-compatible
```

```bash
python3 -I -B scripts/setup_hpp.py --target <projeto> --host codex
python3 -I -B scripts/setup_hpp.py --target <projeto> --host codex --all-compatible
```

O padrão é o bundle `reliable-coding`, com seis módulos. `--all-compatible` seleciona todos os
módulos suportados pelo host: 10 para Claude Code e 9 para Codex CLI.

A primeira invocação gera um plano: módulos escolhidos, arquivos, mudanças no ambiente e nas
dependências, ações específicas do host e gates manuais. Revise o caminho-alvo e o plano inteiro
antes de autorizar o lote. Depois, repita o mesmo comando com `--apply`:

```powershell
python -I -B scripts/setup_hpp.py --target <projeto> --host claude-code --apply
```

```bash
python3 -I -B scripts/setup_hpp.py --target <projeto> --host codex --apply
```

O primeiro comando planeja totalmente offline e não escreve. A aplicação cria `.hpp/venv`, instala
wheels de bootstrap com hash fixado e a CLI local, e então aplica o plano dos módulos; precisa de
acesso ao PyPI. Deve preservar instruções e configurações existentes, mostrar conflitos antes de
escrever e guardar dados de rollback. Falha parcial não é instalação concluída: use o relatório para
retomar somente as etapas pendentes e medir o estado final.

Os metadados confiáveis de propriedade ficam fora do projeto consumidor, em `~/.hpp-setup-state`
por padrão (no Windows, dentro da pasta pessoal do usuário). A opção avançada `--state-dir
<caminho>` muda esse local; mantenha-o fora do projeto. Esses metadados registram o inventário
completo do ambiente gerenciado e validam o launcher. A instalação recusa recibos forjados no
projeto, ambiente existente sem proprietário reconhecido e launcher/ambiente alterado. Se o estado
confiável sumir, pare e preserve os arquivos para reconciliação; não os adote nem apague. O build usa
uma cópia exclusiva e retida em `.hpp/bootstrap-build-<unique>` e mantém intacto o checkout
versionado da release. Não versione `.hpp/venv`, `.hpp/bin`, `.hpp/runtime-router.json`, recibos,
dados do launcher, `.hpp/run.py` nem cópias de build retidas.

## O que a instalação ativa — e o que não ativa

- O `.hpp/venv` do projeto isola o HPP e as dependências dos módulos do Python do sistema.
- Arquivos de módulos, runtime copiado e skills não provam que o host os carregou ou ativou.
- Plugins nativos do Claude Code exigem uma ação explícita no host e o consentimento próprio dele.
  Módulos `explicit-command` continuam sendo comandos; a instalação não edita configurações ou
  hooks do Claude.
- No Codex, a instalação copia o runtime e as skills suportados. Os hooks do HPP ficam desligados.
  Não instale um plugin duplicado apenas para copiar novamente skills já instaladas pelo módulo.
- `.hpp/run.py` preserva o ambiente Python da aplicação chamadora; comandos HPP são encaminhados
  ao runtime gerenciado por aliases locais em `.hpp/bin`. Invoque-o com
  `python -I -B .hpp/run.py hpp doctor` no Windows ou `python3 -I -B .hpp/run.py hpp doctor` no
  macOS.
- Para plugins nativos do Claude Code, revise o plano e ative separadamente: no Windows, rode
  `python -I -B .hpp/run.py activate`; no macOS, rode `python3 -I -B .hpp/run.py activate`. O comando confere
  novamente os checksums da distribuição e dos
  módulos e mantém o consentimento do host. Reinicie o Claude Code e verifique o estado dos plugins
  e hooks. O lote de instalação não ativa o host por conta própria.
- Instalar arquivos de integração opcional não configura a conta nem a integração.

O relatório deve separar `instalado`, `ativo`, `manual`, `recusado` e `falhou`. Verifique a CLI, a
integridade dos módulos, o runtime, as skills e o wiring do host de forma independente. Não diga que
a ativação está concluída sem confirmação do próprio host.

## Comandos de nível mais baixo

Em versões sem instalação guiada, `hpp init` pode planejar e registrar `.hpp/profile.json`; ele não
instala o lote de módulos nem ativa o wiring do host. Os instaladores de módulo continuam disponíveis
para instalações individuais. Leia o guia do módulo correspondente e mantenha a confirmação entre
plano e aplicação e os gates de consentimento do host.

Nunca copie credenciais para arquivos, logs ou relatos de problema do HPP. Nunca sobrescreva uma
configuração existente do host para fazer a instalação parecer concluída.

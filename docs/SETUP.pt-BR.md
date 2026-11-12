[English](SETUP.md) · [Português](SETUP.pt-BR.md)

# Instalação guiada

> **Disponibilidade:** este guia cobre o HPP 2.14.0 e versões posteriores; versões anteriores não
> incluem `hpp setup`. A ativação do host é uma ação humana explícita e separada.

A instalação guiada combina o checkout completo do produto público do HPP, o instalador de módulos existente e um
ambiente Python isolado no projeto. Ela oferece um plano revisável seguido por uma aplicação em
lote. O core continua local e independente de provedor: não faz chamadas de inferência nem coleta
ou armazena credenciais.

## Pré-requisitos

- Python 3.10 ou mais novo.
- Git.
- Claude Code ou Codex CLI já instalado, se esse for o host escolhido.
- Um checkout completo do produto público em `github.com/rusharlabs/house-party-protocol`. Use o
  mesmo checkout para o bootstrap e como distribuição em `--source` para `hpp setup` offline.

Login, assinatura e custos de modelos continuam sob responsabilidade do host. A instalação não
instala Python, Git, Claude Code, Codex ou outro software de sistema. Credenciais Supabase só são
necessárias para configurar e usar a integração opcional do Supabase. Orca também é opcional.

## Seleção

| Seleção | Claude Code | Codex CLI |
|---|---:|---:|
| `reliable-coding` (padrão) | 6 módulos | 6 módulos |
| `--all-compatible` | 10 módulos | 9 módulos |
| `--modules <ids>` | IDs compatíveis explícitos | IDs compatíveis explícitos |

O Codex não suporta `claude-dev-kit`. `--all-compatible` o exclui; informar explicitamente um
módulo incompatível falha antes da aplicação. A seleção de módulos vem do manifesto emitido e das
declarações de compatibilidade por host.

## Bootstrap a partir de um checkout do produto público

Clone o produto público uma única vez e rode o bootstrap da raiz desse checkout. Esse mesmo
diretório é a distribuição completa usada pelo bootstrap e por `hpp setup --source`; não crie uma
segunda cópia para o argumento `--source`.

```bash
git clone https://github.com/rusharlabs/house-party-protocol.git
cd house-party-protocol
```

Partindo do checkout completo e versionado, Windows PowerShell:

```powershell
python -I -B scripts/setup_hpp.py --target <projeto> --host claude-code
python -I -B scripts/setup_hpp.py --target <projeto> --host claude-code --apply
python -I -B scripts/setup_hpp.py --target <projeto> --host claude-code --all-compatible
```

Partindo do checkout completo e versionado, Terminal do macOS:

```bash
python3 -I -B scripts/setup_hpp.py --target <projeto> --host codex
python3 -I -B scripts/setup_hpp.py --target <projeto> --host codex --apply
python3 -I -B scripts/setup_hpp.py --target <projeto> --host codex --all-compatible
```

O primeiro comando gera um plano offline e não escreve nada; revise a saída completa. O segundo
repete as mesmas opções e acrescenta `--apply`; cria `.hpp/venv`, instala wheels de bootstrap com
hash fixado e a CLI local, e então aplica o plano dos módulos. A aplicação do bootstrap precisa de
acesso ao PyPI. A instalação não chama CLI de modelo nem ativa o host, não aciona inferência paga
nem pede credenciais de modelo. Invoque o launcher gerado com `-I -B`; ele preserva o ambiente
Python da aplicação chamadora e direciona comandos HPP ao runtime gerenciado no projeto.

O bootstrap também mantém metadados confiáveis de propriedade num diretório local do usuário, fora
do projeto consumidor: `~/.hpp-setup-state` por padrão (no Windows, esse diretório fica dentro da
pasta pessoal do usuário). A opção avançada `--state-dir <caminho>` seleciona outro local; ele
precisa continuar fora do projeto consumidor. Esses metadados inventariam todos os arquivos do
ambiente gerenciado e validam o launcher. O bootstrap recusa recibo forjado no projeto, ambiente
existente sem proprietário reconhecido ou launcher/ambiente alterado. Se o estado confiável sumir,
não adote nem apague automaticamente os arquivos do projeto: pare e preserve-os para reconciliação.

O processo constrói a CLI numa cópia exclusiva e retida em `.hpp/bootstrap-build-<unique>`; o
checkout versionado da release permanece intacto e dados antigos não são removidos
automaticamente. Mantenha `.hpp/venv`, `.hpp/bin`, `.hpp/runtime-router.json`, `.hpp/run.py`,
recibos, dados do launcher e cópias de build retidas locais; não os versione no projeto consumidor.

Use o launcher para executar o HPP e o host com o ambiente preparado. No Windows PowerShell:

```powershell
python -I -B .hpp/run.py hpp doctor
python -I -B .hpp/run.py host --version
```

No Terminal do macOS, use `python3`:

```bash
python3 -I -B .hpp/run.py hpp doctor
python3 -I -B .hpp/run.py host --version
```

A ativação de plugins nativos do Claude Code é uma ação explícita separada, depois de revisar o
plano. No Windows, rode `python -I -B .hpp/run.py activate`; no macOS, rode
`python3 -I -B .hpp/run.py activate`. O comando confere novamente os checksums da distribuição e dos
módulos e chama os comandos de plugin do host sem uma flag automática de confirmação. Reinicie o
Claude Code e verifique o estado dos plugins e hooks no próprio host antes de dizer que a ativação
foi concluída. No Codex, runtime e skills são copiados localmente; os hooks ficam desligados e não é
necessário instalar outro plugin apenas para copiar as mesmas skills.

## Interface offline

A CLI offline recebe esse mesmo checkout em `--source`; a versão precisa corresponder à CLI
instalada. Rode da raiz do produto e mantenha o projeto-alvo fora dele. Por padrão, ela planeja;
`--apply` executa o lote revisado. A gramática é:

```text
hpp setup --source <mesmo checkout do produto público> --target <projeto> --host claude-code|codex
          [--bundle reliable-coding | --all-compatible | --modules <ids>]
          [--apply] [--json]
```

Exemplos:

```bash
hpp setup --source . --target ../meu-projeto --host claude-code
hpp setup --source . --target ../meu-projeto --host claude-code --apply
hpp setup --source . --target ../meu-projeto --host codex --all-compatible
hpp setup --source . --target ../meu-projeto --host codex --modules kit-forge,operator-kit
```

Use apenas um modo de seleção. Sem uma flag de seleção, `reliable-coding` é o padrão. `--json`
solicita um relatório legível por máquina; não elimina a fronteira de revisão e aplicação. Monte
argumentos de processo a partir de campos estruturados; nunca interprete ou execute texto de shell
impresso pelo plano.

## Comportamento do plano e da aplicação

Antes da primeira escrita, o plano deve listar os módulos escolhidos, arquivos-alvo, ambiente do
projeto e dependências fixadas, ações específicas do host e todos os gates manuais restantes.
Revise conflitos e configurações existentes antes de aplicar. Instruções e configurações do host
existentes devem ser preservadas. Recusa, divergência de checksum, módulo incompatível ou conflito
deve parar antes de qualquer escrita afetada.

## Reexecução e interrupção

Uma reexecução só é aceita quando versão da fonte, host, seleção de módulos, artefatos registrados e
perfil gerenciado continuam iguais aos recibos de propriedade. Mudança de seleção/versão/artefato ou
edição do perfil/arquivo gerenciado é recusada para revisão; upgrade ou migração automática não está
implementado. Se uma interrupção abrupta deixar o recibo inválido ou ausente, preserve os arquivos
existentes para reconciliação; o instalador não pode retomar com segurança um estado sem registro.

A aplicação deve guardar informações de rollback e reportar falha parcial como parcial. Retome
somente etapas pendentes depois de conferir o destino vivo; não repita escritas que já deram certo.
O relatório final deve separar:

- arquivos de módulo instalados e integridade conferida;
- runtime e skills copiados;
- ambiente/launchers instalados e caminho do interpretador medido;
- integração do host ativa, aguardando ação humana, recusada ou não suportada;
- integrações opcionais configuradas ou ainda não configuradas.

## Limites dos hosts

A ativação de plugins nativos do Claude Code é o comando explícito do launcher acima e mantém o
fluxo de consentimento do próprio host. O lote de instalação não ativa plugins nem edita
configurações/hooks do Claude. Módulos `explicit-command` são instalados como arquivos e comandos,
não devem ser descritos como plugins nativos.

No Codex, a instalação copia runtime e skills suportados; os hooks do HPP continuam desligados. Não
exija instalar um plugin redundante só para copiar skills que o instalador de módulos já copia. A
presença de um arquivo não prova que o host o carregou.

Nunca grave credenciais em arquivos gerados ou logs. Instalar arquivos de uma integração opcional
não configura Supabase nem outra conta.

## Status da verificação

Este guia cobre o HPP 2.14.0 e versões posteriores; versões anteriores não têm instalação guiada.
A ativação do host é uma ação humana explícita e separada. Os comandos do macOS usam `python3`.
Testes de host simulado podem verificar a montagem de argumentos, mas não provam ativação no host.

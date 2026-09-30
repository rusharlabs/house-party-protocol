[English](ASSURANCE-CASE.md) · [Português](ASSURANCE-CASE.pt-BR.md)

# Caso de garantia

Esta página argumenta por que os requisitos de segurança do projeto são atendidos: o que se
protege, de quem, onde ficam as fronteiras de confiança, quais princípios de desenho são aplicados,
quais fraquezas comuns são contidas e por qual código. Cada contramedida nomeia o arquivo que a
implementa. O que o desenho não afirma está listado no fim, ao lado dos comandos que conferem o
resto. Relatos de segurança vão pelo [SECURITY.pt-BR.md](../SECURITY.pt-BR.md).

Os arquivos de módulo são citados no caminho que têm na distribuição, `<área>/<módulo>-<versão>/`,
como o `marketplace.json` os lista.

## A afirmação

Usado como documentado, o House Party Protocol não roda nada que o operador não pediu, não envia
nada para fora da máquina a menos que uma pessoa rode um comando que o envie, não guarda
credencial, e entrega os bytes que o workflow de release construiu.

## Modelo de ameaças

**O que se protege**

- o repositório e a árvore de trabalho do operador, sobre os quais o agente e os módulos agem;
- as credenciais no ambiente do operador (chaves de modelo, tokens);
- a integridade dos registros de evidência, das attestations e dos vereditos, que decidem o que
  conta como pronto;
- os artefatos de release: o wheel, o sdist e os diretórios de módulo.

**De onde vêm as ameaças**

- um modelo ou agente que propõe um comando destrutivo, ou afirma que o trabalho está pronto quando
  não está;
- uma página web aberta no navegador do operador que tenta alcançar um servidor local;
- um atacante de rede entre o adaptador de exemplo e o endpoint dele, ou um endpoint que
  redireciona;
- um download adulterado, ou um módulo alterado depois de emitido;
- uma action ou um pacote de terceiro comprometido no CI;
- uma contribuição que carrega conteúdo malicioso.

**Fora do escopo**

- um atacante que já roda código sob a própria conta do operador;
- o próprio host de agente (Claude Code, Codex CLI) e o provedor de modelo por trás dele;
- o que uma pessoa decide rodar à mão.

## Fronteiras de confiança

### A máquina do usuário

O HPP é uma ferramenta de linha de comando que roda como o operador, sob demanda. O pacote `hpp`
não inicia daemon, servidor nem scheduler e não tem telemetria remota
([MANIFESTO.pt-BR.md](../MANIFESTO.pt-BR.md), "O que o projeto se recusa a fazer"). Ele importa só
a biblioteca padrão do Python (`pyproject.toml`: `dependencies = []`; imposto por
`tests/test_stdlib_only.py`). Todo veredito é re-derivado de arquivos em disco.

### O host de agente

O host roda o modelo e as ferramentas dele; o HPP fornece hooks e comandos em volta, e trata o que
o modelo diz como uma afirmação a conferir, não como fato:

- `hpp init --apply` escreve um arquivo, `.hpp/profile.json`, e só lê o `settings.json` do host
  (`hpp/wizard.py`). Ligar hooks num host continua sendo ação humana.
- O classificador de política (`hpp/policy.py`) devolve `ALLOW`, `MANUAL` ou `BLOCK`; ele nunca
  executa o comando, e uma política do usuário só consegue endurecer um veredito embutido, nunca
  afrouxá-lo.
- Um veredito da lane ou da família de modelo de quem construiu é recusado, e o done gate roda de
  novo os comandos do critério em vez de confiar numa mensagem de conclusão
  ([MANIFESTO.pt-BR.md](../MANIFESTO.pt-BR.md)).
- Os hooks de módulo são WARN-only por padrão ([SECURITY.pt-BR.md](../SECURITY.pt-BR.md)); um hook
  nunca derruba o host.

### Os módulos

Um módulo é código que o operador instala. A integridade dele é conferida antes de ele rodar:

- todo diretório de módulo traz `CHECKSUMS.txt` (sha256 por arquivo), e
  `installers/kit-forge-1.5.2/kit_doctor.py verify <module>` compara cada arquivo com ele;
- `kit_doctor.py install` planeja primeiro: uma execução de plano roda todos os self-tests do
  módulo e não escreve nada no projeto de destino, e a instalação só é aplicada numa segunda
  invocação, explícita (`--apply`), que copia os arquivos `*.example.*` do módulo para o destino
  antes da própria etapa de self-test (`run_install` em `kit_doctor.py`);
- antes de um módulo ser emitido, um linter de IP/PII recusa credenciais, dados pessoais e caminhos
  de máquina ([CONTRIBUTING.pt-BR.md](../CONTRIBUTING.pt-BR.md)).

### O endpoint do exemplo `decide.py`

O `examples/typed-decisions/decide.py` é o único componente cujo propósito é mandar dados para fora
da máquina: ele envia o texto que uma pessoa lhe dá ao endpoint que essa pessoa declarou. Ele só
roda quando uma pessoa o roda, e a política o classifica como `MANUAL`. Dentro desse propósito:

- a chave é lida do ambiente na hora da chamada e nunca é escrita em lugar nenhum; uma mensagem de
  erro que a conteria a tem trocada por `<redacted>`;
- uma chave só é enviada por `https`, ou para um endereço de loopback;
- um redirecionamento é recusado (`_NoRedirect`), então o cabeçalho `Authorization` chega a um host
  só;
- um estado que parece carregar segredo é recusado antes de qualquer coisa sair da máquina
  (`digest` em `hpp/decision.py`);
- uma tentativa, um timeout em cada espera de socket, e uma resposta limitada a 1 MiB.

### O dashboard em loopback

O Lane Dashboard do lane-kit (`multi-session/lane-kit-1.8.0/scripts/lane_dashboard.py`) é uma
página que o operador liga e desliga. É a exceção delimitada que o MANIFESTO permite a um módulo:

- ele escuta só em loopback: `--host` aceita apenas `127.0.0.1`, `::1` ou `localhost`
  (`LOOPBACK`), e uma escrita é recusada a menos que o endereço do próprio servidor seja um deles;
- leituras e ações são recusadas a menos que o cabeçalho `Host` nomeie um dos três nomes de
  loopback com a porta do servidor (`_allowed_hosts`), o que derrota DNS rebinding;
- cada execução emite o seu próprio token (`secrets.token_urlsafe(24)` em `make_server`); uma
  escrita precisa carregá-lo no cabeçalho `X-HPP-Token`, comparado com `secrets.compare_digest`,
  com um corpo `application/json` de no máximo 65.536 bytes;
- a página é servida com uma Content-Security-Policy de `default-src 'none'`, `connect-src 'self'`,
  `form-action 'none'`, `base-uri 'none'` e `frame-ancestors 'none'`, mais
  `X-Frame-Options: DENY` e `Referrer-Policy: no-referrer`;
- um `GET` só lê; toda ação é o argv de um comando de terminal listado em `ROUTE_COMMANDS`, e o
  comando de terminal faz a mesma coisa.

### A cadeia de suprimentos do CI

Os workflows sob `.github/workflows/` constroem e publicam o que os usuários instalam:

- toda action de terceiro é fixada num SHA de commit completo, com a versão como comentário (30 das
  30 linhas `uses:` dos quatro workflows em 2026-09-29, contadas com
  `grep -hE 'uses: [^@]+@[0-9a-f]{40} # v' .github/workflows/*.yml` contra
  `grep -h 'uses:' .github/workflows/*.yml`); o Dependabot propõe as atualizações
  (`.github/dependabot.yml`);
- todo `pip install` usa `--require-hashes` contra os arquivos de `.github/requirements/`;
- o token padrão é somente leitura (`permissions: contents: read`), e cada job que precisa de mais
  pede por conta própria; todo checkout define `persist-credentials: false`;
- a release atesta a proveniência de build do wheel e do sdist num job só dela
  (`actions/attest-build-provenance`), anexa o `SHA256SUMS` e o bundle de proveniência à release, e
  publica no PyPI por trusted publishing — nenhum workflow lê um segredo de token guardado.

## Princípios de desenho seguro aplicados

| princípio | onde é aplicado | código |
|---|---|---|
| economia de mecanismo | nenhuma dependência de runtime, nenhum daemon, nenhum banco; todo mapa é uma projeção de arquivos | `pyproject.toml`, `tests/test_stdlib_only.py` |
| padrões seguros contra falha | o dashboard escuta em loopback por padrão; uma chave é recusada em `http` puro; um redirecionamento é recusado; `hpp init` não escreve nada sem `--apply` | `lane_dashboard.py`, `decide.py`, `hpp/wizard.py` |
| mediação completa | toda escrita do dashboard passa pelas checagens de loopback, `Host`, token, content-type e tamanho antes de rodar | `DashboardHandler.do_POST` em `lane_dashboard.py` |
| menor privilégio | os tokens dos workflows são somente leitura por padrão; o job de release pede `contents: write` e `discussions: write`, o job de attestation `id-token: write` e `attestations: write` | `.github/workflows/release.yml` |
| separação de privilégio | quem constrói não pode ser o próprio checker; a proveniência é assinada num job separado do build | `hpp/attest.py`, `release.yml` |
| menor mecanismo comum | cada execução do dashboard emite o seu próprio token, nunca compartilhado com outra execução | `make_server` em `lane_dashboard.py` |
| desenho aberto | as contramedidas estão no código publicado; o único segredo que o harness gera é o token por execução do dashboard | esta página |
| aceitabilidade psicológica | toda ação do dashboard também é um comando de terminal que faz exatamente a mesma coisa | `ROUTE_COMMANDS`, `tests/test_lane_dashboard.py` |

## Fraquezas comuns e o que as contém

| fraqueza | contramedida | código |
|---|---|---|
| injeção de comando do sistema operacional | comandos rodam como lista de argv com `shell=False`, nunca por um shell | `run_bounded` em `hpp/_process.py`; `hpp/evals.py` |
| um segredo numa linha de comando ou num registro | uma linha de comando que parece carregar segredo é recusada antes de rodar; contexto e estado com cara de segredo são recusados | `_carries_secret` em `hpp/evidence.py`; `_SECRET_PATTERN` em `hpp/context.py`; `digest` em `hpp/decision.py` |
| DNS rebinding | allowlist de `Host` em toda leitura e ação | `_host_ok` em `lane_dashboard.py` |
| falsificação de requisição entre sites | token por execução num cabeçalho próprio, só corpo JSON; o handler não implementa `OPTIONS`, então um preflight de CORS nunca é respondido | `do_POST` em `lane_dashboard.py` |
| clickjacking | `frame-ancestors 'none'` e `X-Frame-Options: DENY` | `serve_page` em `lane_dashboard.py` |
| exposição de um serviço local à rede | escuta em loopback; `--host` limitado a nomes de loopback | `LOOPBACK` em `lane_dashboard.py` |
| ataque de tempo sobre o token | comparação em tempo constante | `secrets.compare_digest` em `lane_dashboard.py` |
| credencial repassada num redirecionamento | redirecionamentos recusados | `_NoRedirect` em `decide.py` |
| transmissão de chave em texto claro | chave só por `https` ou para loopback | `ask` em `decide.py` |
| validação imprópria de certificado | HTTPS passa pelo `urllib` com o contexto padrão do Python, que verifica o certificado e o nome do host; nenhum código o desliga | `decide.py`; as sondas do health-kit e do operator-kit |
| credenciais guardadas | chaves vêm do ambiente na hora da chamada; nenhum módulo contém credencial; o PyPI aceita a identidade do workflow em vez de um token | `decide.py`, [SECURITY.pt-BR.md](../SECURITY.pt-BR.md), `release.yml` |
| consumo descontrolado de recursos | timeouts que param a árvore de processos inteira; corpos de resposta e de requisição limitados | `hpp/_process.py`, `decide.py`, `lane_dashboard.py` |
| um artefato ou módulo adulterado | `CHECKSUMS.txt` por módulo, `SHA256SUMS` e proveniência de build assinada por release | `kit_doctor.py`, `release.yml` |
| um registro de evidência editado | o registro faz hash do que guarda e `hpp evidence verify` o re-deriva; com um arquivo de allowed-signers, `verify` recusa um registro sem assinatura, assinado por outra pessoa ou alterado depois de assinado | `hpp/evidence.py`, `hpp/signing.py` |
| uma dependência de CI comprometida | actions fixadas por SHA, requisitos fixados por hash, token padrão somente leitura | `.github/workflows/`, `.github/requirements/` |

"Nenhum código o desliga" foi medido quando esta página foi escrita: nenhum arquivo `.py` sob
`hpp/`, `examples/`, `scripts/` ou os módulos contém `CERT_NONE`, `_create_unverified_context`,
`check_hostname` ou `verify=False`.

## O que este caso não afirma

- **Hooks avisam; não param.** Um hook de módulo é WARN-only por padrão, então um aviso não para
  um agente. Um veredito só impede algo quando um hook, um job de CI ou uma pessoa o chama.
- **O classificador de política é pequeno.** É um conjunto explícito de regras, e não pega toda
  forma destrutiva de um comando.
- **Loopback não isola da própria conta do operador.** Qualquer processo que rode como o mesmo
  usuário alcança o dashboard e lê a página dele, token incluído.
- **O dashboard permite script inline.** A CSP dele carrega `script-src 'unsafe-inline'`, então o
  escape é a defesa contra marcação vinda de texto do repositório: a página escapa esse texto com a
  função `esc` antes de inseri-lo. Este caso não afirma que todo ponto de inserção foi auditado.
- **Um assento de House Session tem impressão digital, não sandbox.** A impressão digital não vê
  uma escrita num caminho que o repositório ignora, nem o que um assento faz fora do worktree dele
  ([MANIFESTO.pt-BR.md](../MANIFESTO.pt-BR.md)).
- **Revisão de code owner é uma configuração do repositório.** O `.github/CODEOWNERS` nomeia o
  mantenedor para todo caminho; ele só obriga enquanto a proteção de branch exigir revisão de code
  owner.
- **O adaptador de exemplo envia o que recebe.** O `decide.py` envia o texto de estado ao endpoint
  que a pessoa declarou — esse é o propósito dele.

## Como conferir este caso

A partir da raiz do repositório:

```bash
python -m pytest tests/test_lane_dashboard.py tests/test_decision.py tests/test_evidence.py tests/test_process.py tests/test_stdlib_only.py -q
python installers/kit-forge-1.5.2/kit_doctor.py verify multi-session/lane-kit-1.8.0
gh attestation verify <file> --repo rusharlabs/house-party-protocol
```

O primeiro comando roda os testes que guardam as contramedidas acima (entre eles
`test_a_page_on_another_origin_cannot_act`, `test_the_page_cannot_be_framed`,
`test_adapter_refuses_a_redirect_and_the_key_never_reaches_the_second_host` e
`test_a_secret_like_command_line_is_refused_before_it_runs`); o segundo prova os bytes de um módulo;
o terceiro prova de onde veio um arquivo de release. Quem mantém este caso e como ele muda está no
[GOVERNANCE.pt-BR.md](../GOVERNANCE.pt-BR.md).

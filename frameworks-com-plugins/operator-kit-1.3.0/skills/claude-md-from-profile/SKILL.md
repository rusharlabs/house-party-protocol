---
name: claude-md-from-profile
description: Gera o bloco de CLAUDE.md do projeto A PARTIR do operator-profile.yaml — piso primeiro (o que a IA nao decide), depois onde as coisas moram, as regras do pronto e o fluxo. Idempotente, com assinatura; recusa sobrescrever bloco editado a mao
---

> **Auto-Trigger:** Ao criar ou alterar o `operator-profile.yaml`; ao abrir um projeto que tem perfil e nao tem CLAUDE.md; quando a IA de um projeto ignora um gate que o perfil declara
> **Keywords:** "claude.md", "gerar claude.md", "instrucoes do projeto", "perfil do operador", "operator-profile", "piso", "o que a IA nao decide", "regenerar bloco", "assinatura"
> **Prioridade:** ALTA
> **Tools:** Bash, Read
> **Doutrina relacionada:** `rules/partial-autonomy-slider.md` (o eixo QUANTO — `autonomia.por_acao`), `rules/gateguard.md` (paths protegidos, familias bloqueadas), `rules/verification-before-completion.md` (as regras do pronto).

# claude-md-from-profile — o CLAUDE.md nasce do perfil, nao o contrario

O `operator-profile.yaml` ja diz tudo o que importa: que acao e nivel 0, que path e
protegido, que familia de comando e bloqueada, onde moram o inbox e os logs, o que
"pronto" exige. Mas o perfil e lido por **hooks e scripts** — a IA que abre o projeto le
o **CLAUDE.md**. Sem esta skill, os dois divergem em silencio: o hook bloqueia o que o
CLAUDE.md nunca disse que era proibido, e a IA aprende a contornar o gate em vez de
respeita-lo.

Esta skill gera um **bloco marcado** dentro do CLAUDE.md, com o piso na primeira secao.
O que a pessoa escreveu fora dos marcadores nunca e tocado.

## Quando NÃO Ativar
- O projeto nao tem `operator-profile.yaml` — crie o perfil primeiro (`cp profile.example.yaml operator-profile.yaml`). O script se recusa a gerar de um perfil que nao existe, e nao ha default escondido.
- Voce quer escrever prosa no CLAUDE.md — escreva **fora** dos marcadores; dentro deles o conteudo e derivado e sera regenerado.
- O bloco foi editado a mao de proposito e voce ainda nao decidiu se a edicao vai para o perfil — resolva isso antes; `--force` apaga a edicao.

## Contrato

**ENTRADA:** um `operator-profile.yaml` (achado pela cwd, por `OPERATOR_PROFILE=`, ou por `--profile`). Nenhuma chave e obrigatoria — secao sem dado e omitida, nao inventada.

**SAÍDA:** um bloco `<!-- operator-kit:claude-md:begin -->` … `<!-- operator-kit:claude-md:end -->` gravado em `./CLAUDE.md` (ou `--out`). A ultima linha do bloco e a **assinatura** (hash do perfil + data). Perfil de exemplo gera o bloco com um aviso na primeira linha.

**EXIT CODES**

| Exit | Significado |
|---|---|
| 0 | bloco gravado (novo/substituido) ou **no-op** — o CLAUDE.md ja estava em dia com o perfil |
| 1 | o bloco existente foi **editado a mao** (assinatura nao bate). Nada gravado. Veja o diff com `--dry-run`; para sobrescrever, `--force` |
| 2 | uso ou perfil invalido: sem perfil encontrado, YAML ilegivel, PyYAML ausente, flag desconhecida |
| 3 | a maquina recusou gravar `CLAUDE.md` — o conteudo inteiro esta em `INSTRUCOES-DO-CLAUDE.md` ao lado; renomeie |

**ESTADO QUE TOCA:**

| Recurso | Lê/Escreve | Propósito |
|---|---|---|
| `operator-profile.yaml` | Lê | a fonte unica do bloco |
| `CLAUDE.md` (ou `--out`) | Escreve — **so entre os marcadores** | o bloco gerado; texto fora dos marcadores e preservado byte a byte |
| `INSTRUCOES-DO-CLAUDE.md` | Escreve (so no exit 3) | fallback quando a escrita em `CLAUDE.md` e recusada |

## Processo
1. **Veja o que sairia** antes de gravar — `--dry-run` imprime o bloco inteiro no stdout e nao toca em nada.
2. **Gere** na raiz do projeto: `python "${CLAUDE_PLUGIN_ROOT}/scripts/claude_md_from_profile.py"`. Se ja existe CLAUDE.md, o bloco entra no **topo**, antes do texto da pessoa.
3. **Leia o piso** que saiu (`## O QUE VOCE NAO DECIDE`). Se algo ali esta errado, o conserto e **no perfil**, nunca no bloco — regere depois.
4. **Ponha no setup do projeto** (hook de SessionStart, `make setup`, o que houver): rodar de novo e barato e idempotente — exit 0 com `no-op` quando nada mudou.
5. **Se der exit 1**, alguem editou o bloco a mao. Compare com `--dry-run`, leve o que vale para o perfil, e so entao `--force`.

## Exemplos executados

Os quatro abaixo foram rodados de verdade (2026-09-20) num diretorio temporario com o
`profile.example.yaml` copiado como `operator-profile.yaml` — zero efeito em projeto
real. A saida e a real.

**1 · Primeira geracao — o CLAUDE.md nasce:**

```
$ python "${CLAUDE_PLUGIN_ROOT}/scripts/claude_md_from_profile.py"
claude_md_from_profile: bloco novo em CLAUDE.md (fonte: operator-profile.yaml)
$ echo $?
0
```
<!-- executado: 2026-09-20 · exit=0 -->

O bloco comeca pelo piso, e o piso vem do perfil, chave a chave — cada linha diz de
onde saiu:

```
## O QUE VOCE NAO DECIDE
- **rm_codigo_vivo**: nivel 0 (`autonomia.por_acao.rm_codigo_vivo`). Voce PROPOE, nao executa. Quem autoriza e a pessoa.
- Qualquer escrita em `settings*.json` cai em gate humano automatico (`autonomia.paths_sensiveis_auto_gate`). Nao contorne por outro caminho.
- `src/**` e protegido (`guardrails.protected_paths`): nao apague, nao mova, nao reescreva em massa.
- Branch `main` e protegida (`guardrails.protected_branches`): nunca push direto, nunca force.
- A familia de comando **git-push-force** e BLOQUEADA (`guardrails.block_families`). Nao ha excecao por urgencia.
```

**2 · Rodar de novo sem mudar nada — a prova de idempotencia:**

```
$ python "${CLAUDE_PLUGIN_ROOT}/scripts/claude_md_from_profile.py"
claude_md_from_profile: CLAUDE.md ja esta em dia com operator-profile.yaml (no-op)
$ echo $?
0
```
<!-- executado: 2026-09-20 · exit=0 -->

No-op, nao "substituido": o arquivo nao e reescrito, o mtime nao anda, e um hook de
SessionStart pode chamar isto toda sessao sem sujar o `git status`.

**3 · Alguem editou o bloco a mao — a recusa:**

```
$ sed -i 's/## O FLUXO/## O FLUXO (mexi aqui)/' CLAUDE.md
$ python "${CLAUDE_PLUGIN_ROOT}/scripts/claude_md_from_profile.py"
claude_md_from_profile: o bloco em CLAUDE.md foi EDITADO A MAO (a assinatura nao bate). Nao sobrescrevo. Veja o que mudaria com --dry-run; para sobrescrever mesmo assim, --force.
$ echo $?
1
```
<!-- executado: 2026-09-20 · exit=1 -->

A assinatura e um hash do conteudo do bloco: qualquer byte alterado entre os
marcadores faz o script parar. E o que impede uma regeneracao automatica de apagar,
em silencio, uma correcao que alguem fez na mao e ainda nao levou para o perfil.

**4 · Perfil que nao existe — nao ha default escondido:**

```
$ python "${CLAUDE_PLUGIN_ROOT}/scripts/claude_md_from_profile.py" --profile nao-existe.yaml
claude_md_from_profile: perfil ilegivel ([Errno 2] No such file or directory: 'nao-existe.yaml'). Nao conserto as cegas — corrija o YAML.
$ echo $?
2
```
<!-- executado: 2026-09-20 · exit=2 -->

## Prova

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/claude_md_from_profile.py" --self-test   # -> self-test OK · exit 0
```

O self-test cobre: perfil de exemplo gera aviso na 1a linha e o piso vem **antes** dos
inventarios; perfil vazio gera bloco valido sem inventar secao; conteudo da pessoa fora
dos marcadores sobrevive byte a byte a `novo` e a `substituido`; segunda rodada e
`no-op`; edicao a mao dentro do bloco e `recusado` e `--force` a vence; a assinatura
muda quando o perfil muda.

**Criterio de sucesso operacional:** a IA que abre o projeto le, no CLAUDE.md, a mesma
lista de nivel-0 que o hook de autonomia bloqueia — `grep -c "nivel 0" CLAUDE.md` igual
ao numero de acoes com `nivel: 0` no perfil.

## Falhas conhecidas / limites
- Gera **so o bloco**. Descricao do projeto, convencoes de codigo, comandos de teste: isso e da pessoa, fora dos marcadores. A skill nao escreve o que o perfil nao sabe.
- A descoberta automatica do perfil sobe da cwd ate a raiz; num monorepo com dois perfis, o mais proximo vence. Use `--profile` quando isso importar.
- Exige PyYAML (o perfil e YAML). Sem ele, exit 2 com a mensagem — nao ha parser de fallback.
- O texto que o script escreve e ASCII por escolha (sem acento): o bloco vai para o system prompt de qualquer harness, e alguns ainda tropecam em encoding. Os **valores** do perfil entram como estao — o script nao translitera o que e seu.
- O EOL do arquivo e da pessoa: um `CLAUDE.md` em CRLF continua CRLF depois do bloco, e a assinatura bate nos dois casos. Sem isso, todo arquivo salvo por editor Windows seria "editado a mao" para sempre.

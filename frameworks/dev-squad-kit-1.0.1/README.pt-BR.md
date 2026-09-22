[English](README.md) · [Português](README.pt-BR.md)

# Dev Squad Kit

## 1. O que é

Um squad de 12 agentes de papel via slash-command (`*master`, `*analyst`, `*architect`,
`*data-engineer`, `*dev`, `*devops`, `*pm`, `*po`, `*qa`, `*sm`, `*squad-creator`,
`*ux-design-expert`) — cada um com persona própria, comandos numerados e checklist de
colaboração com os outros — mais 3 skills de leitura/consolidação paralela token-safe
(`pp-discovery`, `pp-xray`, `pp-consolidate`).

**O que este kit NÃO faz:** não inclui a árvore proprietária de tasks/templates/checklists
que os comandos `*create`, `*task`, `*workflow`, `*execute-checklist` esperam encontrar em
`.devsquad-core/{tasks,templates,checklists,data,utils,workflows}/`. Sem essa árvore, esses
comandos específicos vão falhar ou improvisar. Use os 12 agentes para persona, `*help`,
`*guide` e delegação de raciocínio entre papéis — ou construa/traga sua própria árvore de
tasks se quiser os comandos de criação de documento completos. Cada um dos 12 comandos
carrega esse mesmo aviso no topo (o bloco **Dependencies outside this kit:**, em inglês como toda a camada de agente), antes das
instruções de ativação, para que o agente saiba o que pular quando o caminho não existir.

## 2. Pré-requisitos + APIs externas

| Requisito | Versão mínima | Obrigatório? |
|---|---|---|
| Python | 3.9 | só para o `skill_lint.py`/`kit_doctor.py` do instalador |

Serviços externos: **nenhum — stdlib only.** Os 12 agentes são arquivos `.md` de persona
(prompt), não código executável, e não chamam nenhuma API.

## 3. Instalar via plugin

```bash
/plugin marketplace add rushar-labs/house-party-protocol
/plugin install dev-squad-kit@house-party-protocol
```
O `.claude-plugin/plugin.json` declara `commands/`; `agents/` e `skills/` são
auto-descobertos. Sem hooks.

## 4. Instalar por cópia

Na distribuição emitida este módulo vive em
`frameworks/dev-squad-kit-1.0.1/` (o diretório carrega a versão — declare-a
uma vez, em `KIT`). O instalador é `installers/kit-forge-1.4.1/kit_doctor.py`; rode-o da
raiz da distribuição. Ele planeja primeiro e só escreve numa segunda invocação explícita
com `--apply`:

```bash
KIT=frameworks/dev-squad-kit-1.0.1
cp -r "$KIT" ../your-repo/dev-squad-kit       # the copy itself (kit_doctor does not copy on claude-code)
python installers/kit-forge-1.4.1/kit_doctor.py install --kit "$KIT" --host claude-code --target ../your-repo
python installers/kit-forge-1.4.1/kit_doctor.py install --kit "$KIT" --host claude-code --target ../your-repo --apply
# Codex CLI: --host codex — the installer copies the module into .agents/hpp/dev-squad-kit
#            and each skill into .agents/skills/hpp-dev-squad-kit-<skill>; no cp -r needed
```

## 5. O que o instalador detecta

O estágio `detect` classifica o alvo (só leitura) com exatamente estes três rótulos:

```
greenfield    -> no prior config in the target; nothing to copy (there is no profile.yaml); the 12 commands + 3 skills become available
in-progress   -> .claude/ exists, or settings(.local).json already has hooks/statusLine, or the repo has
                 more than 3 commits: reported only — this kit touches no settings/hooks
re-run        -> this kit+target pair is already in the registry (~/.claude-kits/registry.json); nothing changes
```

## 6. O que é seguro rodar de novo

Tudo. Não há profile customizável nem estado gerado — os comandos e skills são estáticos.
Rodar a instalação de novo apenas re-copia os mesmos arquivos.

## 7. Wiring manual

Nenhum. Este kit não tem hooks — só `commands/`, `agents/` e `skills/`, todos apanhados
pelo Claude Code via `.claude-plugin/plugin.json`.

## 8. Prova (saída real, executada)

O kit não traz linter próprio — o linter é o do instalador. Da raiz da distribuição:

```bash
python installers/kit-forge-1.4.1/tools/skill_lint.py --all frameworks/dev-squad-kit-1.0.1/skills --run-proofs
```
Última linha da saída (as 3 linhas `[PASS]` acima dela carregam separadores de caminho do SO):
```
skill_lint: 3 pass · 0 warn · 0 fail (of 3)
```
<!-- executado: 2026-09-21 · exit=0 -->

**Honestidade de produto:** as 3 skills `pp-*` são metodologia de investigação (prosa
guiando como inventariar/ler um repo antes de mergulhar), não scripts com output
determinístico. Elas agora cumprem o `SKILL-CONTRACT.md` do marketplace (`## Contrato`,
exemplos executados, `## Prova`) e passam no linter acima; o que provam é o método sendo
seguido, não a saída de um programa. Funcionam como guia de raciocínio — decida se isso
serve seu caso antes de instalar.

Os 12 agentes de persona não têm mecanismo de self-test (são prompt, não código) — a prova
possível é a leitura do `.md` em si, que define determinística e explicitamente comandos,
personas e regras de colaboração.

## 9. Desfazer

```
- Plugin:  /plugin uninstall dev-squad-kit@house-party-protocol
- Copy:    remove the dev-squad-kit/ folder from the project (no other file was touched)
```

[English](INSTALL-GUIDE-TEMPLATE.md) · [Português](INSTALL-GUIDE-TEMPLATE.pt-BR.md)

# INSTALL-GUIDE-TEMPLATE — o molde do README de instalação de qualquer kit

> **Versão:** 1.0.0 · **Irmão de:** `SKILL-CONTRACT.md` (contrato de SKILL.md) e
> `INSTALL-CONTRACT.md` (contrato do instalador). Este é o contrato do **README**
> que documenta a instalação para um humano/agente lendo pela primeira vez.
> **Enforcement:** revisão manual nesta rodada; candidato a lint futuro se o
> marketplace crescer (mesmo padrão de `skill_lint.py`).

## Princípio

```
UM ESTRANHO, NUM REPO VIRGEM, LENDO SÓ ESTE README, CONSEGUE:
(1) saber SE precisa de alguma API/serviço externo antes de instalar,
(2) escolher entre plugin e cópia sem adivinhar,
(3) saber O QUE o instalador vai detectar no projeto dele,
(4) rodar de novo sem medo de perder customização,
(5) provar com saída REAL que a instalação funcionou,
(6) desfazer, se precisar.

Prosa sem comando literal para cada um destes 6 pontos não é guia — é resumo de marketing.
```

## As 9 seções obrigatórias (nesta ordem)

### 1. O que é (1 parágrafo)
O que o kit resolve, em linguagem de problema — não lista de features. Sem "revolucionário",
sem adjetivo vazio. Uma frase de escopo negativo é bem-vinda ("não faz X — para X, ver `<kit
irmão>`").

### 2. Pré-requisitos + APIs externas
```
| Requisito | Versão mínima | Obrigatório? |
|---|---|---|
| Python | 3.9 | sim |
| PyYAML | qualquer | sim/não |

Serviços externos: <NENHUM — stdlib only> OU <lista: nome, via (MCP/API direta), credencial>
```
**Regra dura:** default é **"nenhum — stdlib only"**. Se o kit precisar de algo externo,
nomear exatamente (ex.: Supabase via MCP, URL + anon key). **NUNCA** `ANTHROPIC_API_KEY` —
o regime deste ecossistema é assinatura/quota, não pay-per-use (ver `partial-autonomy-slider`
do operator-kit e a doutrina subscription-only).

### 3. Instalar via plugin (caminho recomendado quando existe `.claude-plugin/plugin.json`)
```bash
/plugin marketplace add .
/plugin install <nome-do-kit>@house-party-protocol
```
Se o kit não tiver `plugin.json` ainda, esta seção diz isso explicitamente e aponta para a
seção 4 como único caminho.

### 4. Instalar por cópia (sempre funciona, mesmo sem suporte a plugin)
```bash
cp -r <kit-dir> <seu-projeto>/<nome-do-kit>
cd <seu-projeto>
python <nome-do-kit>/installers/kit-forge/kit_doctor.py install <nome-do-kit> --target . --human
#                                                                                   ^ mostra o PLANO, zero escrita
python <nome-do-kit>/installers/kit-forge/kit_doctor.py install <nome-do-kit> --target . --apply
#                                                                                   ^ aplica de verdade
```
(ajustar o path do `kit_doctor.py` para onde o kit-forge foi copiado/instalado — ele é o
motor único de instalação de todo o marketplace, ver `INSTALL-CONTRACT.md`).

### 5. O que o instalador detecta (greenfield / em-andamento / re-run)
Uma frase por classificação, específica deste kit:
```
greenfield    → <o que acontece: gera tudo do zero>
em-andamento  → <o que é detectado: ex. "settings.local.json já tem hooks — reportado, não sobrescrito">
re-run        → <o que é idempotente: ex. "profile já existe — skip-exists">
```

### 6. O que é seguro rodar de novo
Lista explícita do que o instalador NUNCA sobrescreve sem `--force`/gate humano, e do que É
regenerado sempre (ex.: docs derivados vs. config customizável). Se o kit tem um script tipo
`generate_and_summary` com skip-exists, citar o campo do JSON de retorno que prova isso
(`files_skipped_customized`, `no_op`).

### 7. Wiring manual (gate humano — nunca automático)
```
⚠️ Editar .claude/settings.local.json é gate humano nesta doutrina — sessões automatizadas
têm trava explícita contra auto-editar arquivo de settings/hooks. Cole você mesmo o bloco
abaixo (ou rode o comando programático, se o kit tiver um) — tudo WARN-only + timeout: 30.
```
Colar aqui o bloco real de `install/wiring.settings.jsonc` (ou o comando de
`scripts/wire_settings.py --spec ...`, se for o formato programático deste kit) — **nunca**
resumir, colar o bloco inteiro tal como está no arquivo-fonte.

### 8. Prova / aceite (saída real, executada — nunca inventada)
```bash
python <kit>/scripts/<algo>.py --self-test
```
```
<colar a saída REAL, literal, do comando acima — com marcador de data se o kit seguir o
padrão SKILL-CONTRACT C3>
```
Pelo menos 1 comando de prova por README. Saída inventada viola `agent-integrity.md`.

### 9. Desfazer
```
- Plugin: /plugin uninstall <nome>@house-party-protocol
- Cópia: remover a pasta <nome-do-kit>/ do projeto + reverter o bloco colado em
  settings.local.json manualmente (gate humano também na remoção)
- wire_settings.py (se aplicável): python scripts/wire_settings.py --spec ... --undo
```

## Checklist antes de considerar um README "conforme"

```
[ ] Seção 1 diz o que o kit NÃO faz (escopo negativo), não só o que faz
[ ] Seção 2 declara "nenhum" ou nomeia o serviço externo exato — nunca omite a seção
[ ] Seção 2 NUNCA menciona ANTHROPIC_API_KEY como pré-requisito
[ ] Seção 3 existe SE plugin.json existe; senão diz explicitamente que não existe ainda
[ ] Seção 4 tem os 2 comandos reais (plano, depois --apply) do kit_doctor.py
[ ] Seção 5 tem as 3 classificações (greenfield/em-andamento/re-run) especificas do kit
[ ] Seção 6 nomeia o campo do JSON que prova skip-exists (se o kit tiver generate/profile)
[ ] Seção 7 cola o bloco de wiring INTEIRO (não resume) e marca gate humano
[ ] Seção 8 tem saída REAL executada, não inventada
[ ] Seção 9 explica como desfazer plugin E cópia
```

---

*Irmão de `SKILL-CONTRACT.md` — mesmo princípio (estranho + repo virgem + prova real),
aplicado ao README de instalação em vez de ao corpo de uma skill.*

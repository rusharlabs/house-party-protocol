[English](README.md) · [Português](README.pt-BR.md)

# Health Kit

Sonda config-driven de saúde de serviços (HTTP ou comando local) + um segmento de
**statusline** que mostra o detalhe por-serviço (`api:OK db:DOWN`) sem nunca tocar rede
no caminho quente — só lê um cache que `health_probe.py` escreve. `health_probe.py`
sonda os serviços declarados em `health.probes` e grava um cache JSON; `statusline.py`
(ou qualquer outra ferramenta) lê **só o cache** — nunca faz I/O de rede no caminho que
roda a cada tecla/prompt. Dois processos, uma fronteira clara: quem sonda não é quem
exibe. **Doutrina embarcada:** health de SERVIÇO ≠ health de DADO — este kit prova que o
processo está de pé, não que o dado que ele serve está correto/atualizado.

## Pré-requisitos + APIs externas

| Requisito | Versão mínima | Obrigatório? |
|---|---|---|
| Python | 3.8 | sim |
| PyYAML | qualquer | sim |

Serviços externos: **nenhum kit-específico** — `health.probes` no seu profile aponta
para os serviços DO SEU projeto (HTTP ou comando local); o kit em si não fala com
nenhum serviço fixo.

## O que tem nesta pasta

```
health-kit/
├── README.md · README.pt-BR.md   ← this file (and its Portuguese twin)
├── profile.example.yaml          ← commented template to copy into a new project
├── _lib/
│   └── profile_loader.py         ← finds + reads the profile (stdlib + PyYAML)
├── scripts/
│   ├── health_probe.py           ← probes the services, writes the cache
│   ├── gate_sheet_panel.py       ← panel of items that depend on a human (portable)
│   └── wire_statusline.py        ← wires the statusLine into settings.json (idempotent + --undo)
├── statusline/
│   └── statusline.py             ← composable bar; 'health' segment with per-service detail
├── hooks/
│   ├── hooks.json                ← SessionStart → health_probe.py --quiet (cache refresh)
│   └── pyrun.sh                  ← resolves the project's Python interpreter for the hook
├── skills/
│   ├── health-check/SKILL.md     ← doctrine + executed examples
│   └── dashboard-builder/SKILL.md← monitoring dashboards that answer operator questions
├── install/
│   └── kit.install.yaml          ← manifest read by kit_doctor.py install (1 question)
├── .claude-plugin/
│   └── plugin.json               ← plugin manifest (declares hooks/hooks.json)
├── AGENTS.md                     ← Codex CLI entry point (what Codex reads on --host codex)
└── LICENSE · CHECKSUMS.txt · SANITIZATION.md   ← added by the forge at emission
```

## Instalar via plugin (1 clique)

```bash
/plugin marketplace add rusharlabs/house-party-protocol
/plugin install health-kit@house-party-protocol
```
Instala o hook `SessionStart` (refresh automático do cache a cada sessão nova) via
`${CLAUDE_PLUGIN_ROOT}`. A **statusLine continua manual** — rode `wire_statusline.py`
(limite do Claude Code: plugin não embute `statusLine`).

## Instalar por cópia

Na distribuição emitida este módulo vive em `frameworks/health-kit-1.3.3/`
(o diretório carrega a versão — declare-a uma vez, em `KIT`). O instalador é
`installers/kit-forge-1.4.2/kit_doctor.py`; rode-o da raiz da distribuição. Ele planeja
primeiro e só escreve numa segunda invocação explícita com `--apply`:

```bash
KIT=frameworks/health-kit-1.3.3
cp -r "$KIT" ../your-repo/health-kit          # the copy itself (kit_doctor does not copy on claude-code)
python installers/kit-forge-1.4.2/kit_doctor.py install --kit "$KIT" --host claude-code --target ../your-repo
python installers/kit-forge-1.4.2/kit_doctor.py install --kit "$KIT" --host claude-code --target ../your-repo --apply
# Codex CLI: --host codex — the installer copies the module into .agents/hpp/health-kit
#            and each skill into .agents/skills/hpp-health-kit-<skill>; no cp -r needed
```
O estágio `configure` tem uma pergunta, `configurar_probes_agora` — configurar
`health.probes` agora, ou copiar `profile.example.yaml` como está e ajustar depois (o
default; responda de verdade com `--answers <arquivo.json|yaml>`). O estágio `profile`
copia `profile.example.yaml` para o alvo como `profile.yaml` (nunca sobrescrito); o loader
lê **`operator-profile.yaml`**, então renomeie (ou mescle no profile do Operator Kit que
você já tem). Smoke test manual, se preferir não usar o `kit_doctor.py`:
```bash
cp profile.example.yaml operator-profile.yaml   # or merge into an existing Operator Kit profile
python health-kit/scripts/health_probe.py            # probes + writes the cache
echo '{}' | python health-kit/statusline/statusline.py --statusline   # reads the cache, prints the segment
```

## O que o instalador detecta

O estágio `detect` classifica o alvo (só leitura) com exatamente estes três rótulos:

```
greenfield    -> no prior config in the target; profile stage would copy profile.example.yaml -> profile.yaml
in-progress   -> .claude/ exists, or settings(.local).json already has hooks/statusLine, or a real
                 profile is present, or the repo has more than 3 commits: reported, never overwritten (skip-exists)
re-run        -> this kit+target pair is already in the registry (~/.claude-kits/registry.json)
```

## O que é seguro rodar de novo

`wire_statusline.py` é **idempotente** (rodar de novo é no-op) e **nunca sobrescreve**
uma `statusLine` já configurada por outra ferramenta sem `--force`:
```bash
python health-kit/scripts/wire_statusline.py --target .claude/settings.local.json
python health-kit/scripts/wire_statusline.py --undo --target .claude/settings.local.json
```
Um profile que já existe também nunca é sobrescrito pelo estágio `profile`.

## Wiring manual (gate humano — nunca automático)

> Editar `.claude/settings.local.json` é gate humano. `statusLine` é **sempre**
> manual (Claude Code não aceita `statusLine` dentro de plugin) — rode
> `wire_statusline.py` você mesmo (comandos acima). `SessionStart`/`hooks` vêm de graça
> via o caminho plugin; no caminho por cópia, colar `hooks/hooks.json` manualmente em
> `.claude/settings.local.json`.

## Prova / aceite (saída real, executada)

Prova que o segmento reage a um serviço real subindo e caindo — sem mock. O profile usado
declara uma sonda, `api` → `http://127.0.0.1:18823/`, e `statusline.segments: ["health"]`;
o `statusline.py` lê o JSON do host no stdin, daí o `echo '{}' |` quando você o roda de um
shell:

```bash
# 1. start a real HTTP server on port 18823
python -m http.server 18823 &
SRV_PID=$!

# 2. probe: the service is UP
python health-kit/scripts/health_probe.py
# ⚕ 1/1 UP

echo '{}' | python health-kit/statusline/statusline.py --statusline
# api:OK

# 3. kill the server
kill $SRV_PID

# 4. probe again: the service is DOWN
python health-kit/scripts/health_probe.py
# ⚕ 0/1 UP (DOWN: api)

echo '{}' | python health-kit/statusline/statusline.py --statusline
# api:DOWN
```
<!-- executado: 2026-09-21 · exit=0 -->

Executado de verdade nessa rodada (porta 18823, probe `type: http`): UP → `⚕ 1/1 UP`,
DOWN após `kill` → `⚕ 0/1 UP (DOWN: api)`. Com `statusline.segments: ["health"]` isolado,
o segmento mostra o nome do serviço: `api:OK` / `api:DOWN`.

**Segmento `health` — agregado vs. detalhe:** 1-6 serviços mostram detalhe por-serviço
(`api:OK db:DOWN`); 7+ degradam para o agregado `⚕<online>/<total>` (evita estourar a
largura da statusline).

**Cache (schema — o arquivo deixado pelo passo 4 acima):**
```json
{
  "ts": "2026-09-21 18:45 BRT",
  "health": {"services_online": 0, "services_total": 1},
  "services": {
    "api": {"online": false, "type": "http", "target": "http://127.0.0.1:18823/"}
  }
}
```

## Desfazer

```
- Plugin:  /plugin uninstall health-kit@house-party-protocol
- Copy:    remove the health-kit/ folder from the project
- statusLine: python health-kit/scripts/wire_statusline.py --undo --target .claude/settings.local.json
- Cache:   rm .claude/health-cache.json (ephemeral, safe to delete — regenerated by the next probe)
```

## Portabilidade honesta

`health_probe.py`, `statusline.py`, `wire_statusline.py`, `gate_sheet_panel.py` e
`_lib/profile_loader.py` são **100% portáteis** — só dependem de Python stdlib + PyYAML.
Nenhum mecanismo depende de rede/serviço específico de nenhum projeto: tudo vem de
`health.probes` no profile.

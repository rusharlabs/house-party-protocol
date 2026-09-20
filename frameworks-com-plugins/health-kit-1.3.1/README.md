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
├── README.md                     ← este arquivo
├── profile.example.yaml          ← template comentado p/ copiar em projeto novo
├── _lib/
│   └── profile_loader.py         ← acha+lê o profile (stdlib + PyYAML)
├── scripts/
│   ├── health_probe.py           ← sonda os serviços, grava o cache
│   ├── gate_sheet_panel.py       ← painel de itens que dependem do humano (portável)
│   └── wire_statusline.py        ← arma a statusLine em settings.json (idempotente + --undo)
├── statusline/
│   └── statusline.py             ← barra composável; segmento 'health' com detalhe por-serviço
├── hooks/
│   └── hooks.json                ← SessionStart → health_probe.py --quiet (refresh do cache)
├── skills/
│   └── health-check/SKILL.md     ← doutrina + exemplos executados
└── .claude-plugin/
    └── plugin.json               ← manifesto do plugin
```

## Instalar via plugin (1 clique)

```bash
/plugin marketplace add .
/plugin install health-kit@house-party-protocol
```
Instala o hook `SessionStart` (refresh automático do cache a cada sessão nova) via
`${CLAUDE_PLUGIN_ROOT}`. A **statusLine continua manual** — rode `wire_statusline.py`
(limite do Claude Code: plugin não embute `statusLine`).

## Instalar por cópia

```bash
cp -r health-kit-1.1.0 <seu-projeto>/health-kit
cd <seu-projeto>
python health-kit/instaladores/kit-forge/kit_doctor.py install health-kit --target . --human
#                                                                              ^ plano, zero escrita
python health-kit/instaladores/kit-forge/kit_doctor.py install health-kit --target . --apply
#                                                                              ^ aplica de verdade
```
O estágio `configure` pergunta se você quer configurar `health.probes` agora ou copiar
`profile.example.yaml` como está e ajustar depois (default: ajustar depois). Smoke test
manual, se preferir não usar o `kit_doctor.py`:
```bash
cp profile.example.yaml operator-profile.yaml   # ou mesclar com um já existente do Operator Kit
python health-kit/scripts/health_probe.py            # sonda + grava o cache
python health-kit/statusline/statusline.py --statusline   # lê o cache, mostra o segmento
```

## O que o instalador detecta

```
greenfield    → copia profile.example.yaml -> operator-profile.yaml (estágio profile)
em-andamento  → operator-profile.yaml já existe com health.probes configurado (skip-exists)
re-run        → registry (~/.claude-kits/registry.json) marca re-run
```

## O que é seguro rodar de novo

`wire_statusline.py` é **idempotente** (rodar de novo é no-op) e **nunca sobrescreve**
uma `statusLine` já configurada por outra ferramenta sem `--force`:
```bash
python health-kit/scripts/wire_statusline.py --target .claude/settings.local.json
python health-kit/scripts/wire_statusline.py --undo --target .claude/settings.local.json
```
`operator-profile.yaml` também nunca é sobrescrito pelo estágio `profile` se já existir.

## Wiring manual (gate humano — nunca automático)

> ⚠️ Editar `.claude/settings.local.json` é gate humano. `statusLine` é **sempre**
> manual (Claude Code não aceita `statusLine` dentro de plugin) — rode
> `wire_statusline.py` você mesmo (comandos acima). `SessionStart`/`hooks` vêm de graça
> via o caminho plugin; no caminho por cópia, colar `hooks/hooks.json` manualmente em
> `.claude/settings.local.json`.

## Prova / aceite (saída real, executada)

Prova que o segmento reage a um serviço real subindo e caindo — sem mock:

```bash
# 1. sobe um servidor HTTP real na porta 18823
python -m http.server 18823 &
SRV_PID=$!

# 2. sonda: o serviço está UP
python health-kit/scripts/health_probe.py
# ⚕ 1/1 UP

python health-kit/statusline/statusline.py --statusline
# api:OK

# 3. mata o servidor
kill $SRV_PID

# 4. sonda de novo: o serviço está DOWN
python health-kit/scripts/health_probe.py
# ⚕ 0/1 UP (DOWN: api)

python health-kit/statusline/statusline.py --statusline
# api:DOWN
```
<!-- executado: 2026-07-10 · exit=0 -->

Executado de verdade nesta sessão (porta 18823, probe `type: http`): UP → `⚕ 1/1 UP`,
DOWN após `kill` → `⚕ 0/1 UP (DOWN: api)`. Com `statusline.segments: ["health"]` isolado,
o segmento mostra o nome do serviço: `api:OK` / `api:DOWN`.

**Segmento `health` — agregado vs. detalhe:** 1-6 serviços mostram detalhe por-serviço
(`api:OK db:DOWN`); 7+ degradam para o agregado `⚕<online>/<total>` (evita estourar a
largura da statusline).

**Cache (schema):**
```json
{
  "ts": "2026-07-10 21:34 BRT",
  "health": {"services_online": 1, "services_total": 2},
  "services": {
    "servico-ok": {"online": true, "type": "cmd", "target": "..."},
    "servico-down": {"online": false, "type": "cmd", "target": "..."}
  }
}
```

## Desfazer

```
- Plugin: /plugin uninstall health-kit@house-party-protocol
- Cópia: remover a pasta health-kit/ do projeto
- statusLine: python health-kit/scripts/wire_statusline.py --undo --target .claude/settings.local.json
- Cache: rm .claude/health-cache.json (efêmero, seguro apagar — regenerado pelo próximo probe)
```

## Portabilidade honesta

`health_probe.py`, `statusline.py`, `wire_statusline.py`, `gate_sheet_panel.py` e
`_lib/profile_loader.py` são **100% portáteis** — só dependem de Python stdlib + PyYAML.
Nenhum mecanismo depende de rede/serviço específico de nenhum projeto: tudo vem de
`health.probes` no profile.

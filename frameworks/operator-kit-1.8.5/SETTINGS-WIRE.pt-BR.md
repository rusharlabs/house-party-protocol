[English](SETTINGS-WIRE.md) · [Português](SETTINGS-WIRE.pt-BR.md)

# SETTINGS-WIRE — ativar os hooks (GATE HUMANO)

> ⚠️ **Editar `.claude/settings.local.json` é gate humano** — sessões automatizadas costumam ter uma trava explícita contra auto-editar arquivo de settings/hooks (por design — mutar a própria permissão não deve ser automático). Cole você mesmo os blocos abaixo. Todo hook é **WARN-only (exit 0)**, a não ser que você opte pelo contrário (`operation_guard_portable` bloqueia com exit 2 só sob `HPP_POLICY_MODE=enforce` ou `guardrails.operation_guard_mode: enforce`), e todo hook tem `timeout: 30`, menos o Stop hook `loop_gate`, que tem `timeout: 120`: ele roda de novo os seus critérios de pronto, cada um por até `--criterion-timeout` segundos (20 por padrão). WARN-only fala de código de saída: fora dessa opção nenhum hook faz uma ferramenta falhar pelo código de saída, mas dois deles imprimem um JSON sobre o qual o host age. O `fact_force_gate` entrega o aviso de primeiro toque ao modelo como `additionalContext` do PreToolUse — a edição ou o comando roda do mesmo jeito; ele nunca nega. O `loop_gate` responde a um Stop com `{"decision": "block"}` enquanto um loop que você armou com `/loop-gate` está ativo e nenhuma `<promise>` foi emitida ou um dos critérios de pronto dele falha, e aí a sessão continua em vez de parar.

Os hooks **MERGEM** nos arrays existentes de `hooks` do seu `settings.local.json` (não substituem) — adicione as entradas abaixo nos mesmos arrays, sem apagar o que já está lá.

## 0. Caminho RECOMENDADO: instalar como PLUGIN (auto-wire de 1 clique)
Em vez de colar hook por hook, instale o `operator-kit` como plugin — o `hooks/hooks.json` arma os 9 hooks WARN-only de uma vez (via `${CLAUDE_PLUGIN_ROOT}`):
```bash
/plugin marketplace add .                            # registers the marketplace (name = "name" of marketplace.json)
/plugin install operator-kit@<marketplace-name>      # installs + arms the 9 hooks automatically
```
A statusLine (§3) e os output-styles continuam manuais (limite do Claude Code: plugin não embute statusLine). A seção 1 abaixo é o caminho MANUAL alternativo (sem plugin).

---

## 1. Caminho manual (alternativa ao plugin) — os 9 hooks do kit

Copie as entradas de `hooks/hooks.json` deste kit para dentro dos arrays `PreToolUse`/`UserPromptSubmit`/`Stop` do seu `settings.local.json`, trocando `${CLAUDE_PLUGIN_ROOT}` pelo caminho onde você colocou o kit (abaixo, `operator-kit`, relativo à raiz do projeto, onde o Claude Code roda os hooks). Todo comando passa pelo `hooks/pyrun.sh`, exatamente como no plugin: ele roda o hook com o Python do `.venv` do projeto quando existe um, senão com `python3` ou `python`, o que o sistema tiver — um macOS de fábrica não tem `python` puro, e um hook que não acha o interpretador falha em toda ferramenta, em silêncio:

```jsonc
"PreToolUse": [
  {
    "matcher": "Bash",
    "hooks": [
      { "type": "command", "command": "bash \"operator-kit/hooks/pyrun.sh\" \"operator-kit/hooks/operation_guard_portable.py\"", "timeout": 30 },
      { "type": "command", "command": "bash \"operator-kit/hooks/pyrun.sh\" \"operator-kit/hooks/snapshot_rollback_gate.py\"", "timeout": 30 },
      { "type": "command", "command": "bash \"operator-kit/hooks/pyrun.sh\" \"operator-kit/hooks/external_send_draft_gate.py\"", "timeout": 30 },
      { "type": "command", "command": "bash \"operator-kit/hooks/pyrun.sh\" \"operator-kit/hooks/fact_force_gate.py\"", "timeout": 30 }
    ]
  },
  {
    "matcher": "Edit|Write|MultiEdit|NotebookEdit",
    "hooks": [
      { "type": "command", "command": "bash \"operator-kit/hooks/pyrun.sh\" \"operator-kit/hooks/secret_scan_on_write.py\"", "timeout": 30 },
      { "type": "command", "command": "bash \"operator-kit/hooks/pyrun.sh\" \"operator-kit/hooks/project_root_confirm.py\"", "timeout": 30 },
      { "type": "command", "command": "bash \"operator-kit/hooks/pyrun.sh\" \"operator-kit/hooks/fact_force_gate.py\"", "timeout": 30 }
    ]
  }
],
"UserPromptSubmit": [
  {
    "matcher": "*",
    "hooks": [
      { "type": "command", "command": "bash \"operator-kit/hooks/pyrun.sh\" \"operator-kit/hooks/rule_capture.py\"", "timeout": 30 }
    ]
  }
],
"Stop": [
  {
    "matcher": "*",
    "hooks": [
      { "type": "command", "command": "bash \"operator-kit/hooks/pyrun.sh\" \"operator-kit/hooks/loop_gate.py\"", "timeout": 120 },
      { "type": "command", "command": "bash \"operator-kit/hooks/pyrun.sh\" \"operator-kit/hooks/autoprompt_resume.py\"", "timeout": 30 }
    ]
  }
]
```

Dos 9, 7 leem o `operator-profile.yaml` (via `_lib/profile_loader.py`) e degradam para defaults seguros se o profile não existir — profile ausente não quebra nenhum deles. Os outros dois não leem profile: o `fact_force_gate` é configurado pelas variáveis de ambiente `HPP_FACT_FORCE*`, e o `loop_gate` só age enquanto um loop que você armou com `/loop-gate` estiver ativo.

## 2. gitignore (obrigatório ao ativar o Stop hook `autoprompt_resume`)
Adicionar ao `.gitignore` a linha do `paths.resume_pointer` do perfil:
```
.claude/RESUME-NEXT.md
```

## 3. statusLine — a barra de progresso viva (NÃO vai no plugin; só em settings)
O Claude Code não aceita `statusLine` dentro de plugin — tem que ir no `settings.json`/`settings.local.json`. Aponte para a statusline portátil do kit (lê o `operator-profile.yaml`):
```jsonc
"statusLine": { "type": "command", "command": "bash \"operator-kit/hooks/pyrun.sh\" \"operator-kit/statusline/statusline.py\" --statusline", "padding": 0 }
```
Reabra a sessão p/ aparecer no rodapé. Exemplo de render (segmentos default `progress,health,commits,branch`): `🧠 meu-projeto 58% █████░░░ ▸ 34c today ▸ feat/minha-branch` (o segmento `health` só aparece se `health.probes` estiver configurado — ver `health-kit`).

## Smoke test pós-wire
```bash
python operator-kit/hooks/autoprompt_resume.py --self-test
python operator-kit/hooks/autoprompt_resume.py --print   # checks the profile's paths
python operator-kit/scripts/done_gate.py --self-test
```

## O que NÃO é gate (já construído, sem tocar settings)
- `operator-profile.yaml`, `profile.example.yaml`, `_lib/profile_loader.py`
- `scripts/done_gate.py --profile <kind>`
- `templates/loop-charter-template.md`
- `output-styles/direct-register.md`, `output-styles/execute-100pct.md` (ativar com `/output-style` após copiar p/ `.claude/output-styles/`)

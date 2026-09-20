# Supabase Pack

Duas skills SKILL-CONTRACT-compliant para projetos com Supabase:

- **`rls-audit`** — audita RLS de verdade (policies `anon` permissivas, não só a flag
  `relrowsecurity`). Tools declaradas por CAPABILITY (`execute_sql`, `get_advisors`,
  `list_tables`), nunca por prefixo MCP literal (o prefixo varia por instalação — pode ser
  `mcp__supabase__*`, `mcp__claude_ai_Supabase__*`, etc.).
- **`supabase-edge-scaffold`** — gera o esqueleto de Edge Function com CORS + service-role
  via env + tratamento de erro corretos, com smoke-test real (`deno check`).

Ambas herdadas do `operator-kit` (FASE 3 do kickoff), aqui empacotadas como kit standalone
para quem quer só a camada Supabase sem o restante do operator-kit. Não gerencia migrations
nem schema — só audita RLS e faz scaffold de Edge Functions.

## Pré-requisitos + APIs externas

| Requisito | Versão mínima | Obrigatório? |
|---|---|---|
| Python | qualquer 3.x | só para `skill_lint.py` (prova/lint, não runtime das skills) |
| `deno` | qualquer | só para `supabase-edge-scaffold` (smoke-test do esqueleto gerado) |

Serviços externos: **Supabase, via MCP** (tools por capability: `execute_sql`,
`get_advisors`, `list_tables` — nunca hardcoda um prefixo `mcp__*` específico, pois varia
por instalação). Credenciais: URL do projeto + anon key, configuradas no MCP do Supabase
do seu ambiente (não neste kit). **Nunca `ANTHROPIC_API_KEY`** — não aplicável aqui.

## Instalar via plugin

```bash
/plugin marketplace add .
/plugin install supabase-pack@house-party-protocol
```

## Instalar por cópia

```bash
cp -r supabase-pack-1.0.0 <seu-projeto>/supabase-pack
cd <seu-projeto>
python supabase-pack/instaladores/kit-forge/kit_doctor.py install supabase-pack --target . --human
#                                                                                    ^ plano, zero escrita
python supabase-pack/instaladores/kit-forge/kit_doctor.py install supabase-pack --target . --apply
#                                                                                    ^ aplica de verdade
```

## O que o instalador detecta

```
greenfield    → nada a copiar (kit sem profile/config próprio — YAGNI); só as 2 skills ficam disponíveis
em-andamento  → n/a (kit não toca settings/hooks nem arquivos do projeto-alvo)
re-run        → registry (~/.claude-kits/registry.json) marca re-run; nada muda (kit é read-only na instalação)
```

## O que é seguro rodar de novo

Este kit não gera nem modifica arquivo nenhum na instalação — as duas skills são
invocadas sob demanda pelo agente (`rls-audit` só lê via MCP; `supabase-edge-scaffold`
gera arquivo novo por invocação, não durante o `kit_doctor.py install`). Rodar o
instalador de novo é sempre um no-op seguro.

## Wiring manual

Nenhum — este kit não tem hooks nem toca `settings.local.json`. As skills disparam por
keyword/contexto (frontmatter `description` de cada `SKILL.md`), sem wiring de settings.

## Prova / aceite (saída real, executada)

```bash
python ${CLAUDE_PLUGIN_ROOT}/tools/skill_lint.py --all skills --run-proofs
```
```
2/2 PASS
```

## Desfazer

```
- Plugin: /plugin uninstall supabase-pack@house-party-protocol
- Cópia: remover a pasta supabase-pack/ do projeto (nada mais para reverter — sem
  wiring/settings tocados)
```

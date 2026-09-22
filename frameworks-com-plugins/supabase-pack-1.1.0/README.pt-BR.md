[English](README.md) · [Português](README.pt-BR.md)

# Supabase Pack

Duas skills SKILL-CONTRACT-compliant para projetos com Supabase:

- **`rls-audit`** — audita RLS de verdade (policies `anon` permissivas, não só a flag
  `relrowsecurity`). A linha de tools dela declara as ferramentas por CAPABILITY
  (`execute_sql`, `get_advisors`, `list_tables`) e diz que o prefixo MCP varia por
  instalação; os exemplos executados mostram um prefixo real (`mcp__supabase__*`) como
  amostra.
- **`supabase-edge-scaffold`** — gera o esqueleto de Edge Function com CORS + service-role
  via env + tratamento de erro corretos, com smoke-test real (`deno check`). A linha de
  tools dela nomeia um prefixo concreto (`mcp__claude_ai_Supabase__deploy_edge_function`,
  `mcp__claude_ai_Supabase__list_edge_functions`) — leia como o exemplo da instalação em
  que foi provada, e troque o prefixo pelo que o seu MCP do Supabase expõe.

Ambas herdadas do `operator-kit` (FASE 3 do kickoff), aqui empacotadas como kit standalone
para quem quer só a camada Supabase sem o restante do operator-kit. Não gerencia migrations
nem schema — só audita RLS e faz scaffold de Edge Functions.

## Pré-requisitos + APIs externas

| Requisito | Versão mínima | Obrigatório? |
|---|---|---|
| Python | qualquer 3.x | só para o `skill_lint.py` do instalador (prova/lint, não runtime das skills) |
| `deno` | qualquer | só para `supabase-edge-scaffold` (smoke-test do esqueleto gerado) |

Serviços externos: **Supabase, via MCP** (tools por capability: `execute_sql`,
`get_advisors`, `list_tables`, `deploy_edge_function`, `list_edge_functions`). O prefixo
`mcp__*` na frente delas depende de como o MCP do Supabase está registrado no seu ambiente
(`mcp__supabase__*`, `mcp__claude_ai_Supabase__*`, ...) — onde um `SKILL.md` escreve um por
extenso, é o prefixo da instalação em que o exemplo rodou, não um requisito. Credenciais:
URL do projeto + anon key, configuradas no MCP do Supabase do seu ambiente (não neste kit).
**Nunca `ANTHROPIC_API_KEY`** — não aplicável aqui.

## Instalar via plugin

```bash
/plugin marketplace add rushar-labs/house-party-protocol
/plugin install supabase-pack@house-party-protocol
```
O plugin não tem hooks; as duas skills são auto-descobertas.

## Instalar por cópia

Na distribuição emitida este módulo vive em
`frameworks-com-plugins/supabase-pack-1.1.0/` (o diretório carrega a versão — declare-a
uma vez, em `KIT`). O instalador é `instaladores/kit-forge-1.4.0/kit_doctor.py`; rode-o da
raiz da distribuição. Ele planeja primeiro e só escreve numa segunda invocação explícita
com `--apply`:

```bash
KIT=frameworks-com-plugins/supabase-pack-1.1.0
cp -r "$KIT" ../your-repo/supabase-pack       # the copy itself (kit_doctor does not copy on claude-code)
python instaladores/kit-forge-1.4.0/kit_doctor.py install --kit "$KIT" --host claude-code --target ../your-repo
python instaladores/kit-forge-1.4.0/kit_doctor.py install --kit "$KIT" --host claude-code --target ../your-repo --apply
# Codex CLI: --host codex — the installer copies the module into .agents/hpp/supabase-pack
#            and each skill into .agents/skills/hpp-supabase-pack-<skill>; no cp -r needed
```

## O que o instalador detecta

O estágio `detect` classifica o alvo (só leitura) com exatamente estes três rótulos:

```
greenfield    -> no prior config in the target; nothing to copy (no profile/config of its own — YAGNI); the 2 skills become available
in-progress   -> .claude/ exists, or settings(.local).json already has hooks/statusLine, or the repo has
                 more than 3 commits: reported only — this kit touches no settings/hooks
re-run        -> this kit+target pair is already in the registry (~/.claude-kits/registry.json); nothing changes
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

O kit não traz `tools/` próprio — o linter é o do instalador. Da raiz da distribuição:

```bash
python instaladores/kit-forge-1.4.0/tools/skill_lint.py --all frameworks-com-plugins/supabase-pack-1.1.0/skills --run-proofs
```
Última linha da saída (as 2 linhas `[PASS]` acima dela carregam separadores de caminho do SO):
```
skill_lint: 2 pass · 0 warn · 0 fail (de 2)
```
<!-- executado: 2026-09-21 · exit=0 -->

## Desfazer

```
- Plugin:  /plugin uninstall supabase-pack@house-party-protocol
- Copy:    remove the supabase-pack/ folder from the project (nothing else to revert — no
           wiring/settings touched)
```

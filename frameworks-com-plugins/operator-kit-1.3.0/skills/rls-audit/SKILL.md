---
name: rls-audit
description: Audita RLS de um projeto Supabase de verdade — pg_policies por policy anon permissiva + get_advisors, não só a flag relrowsecurity
---

> **Auto-Trigger:** Antes de declarar um schema Supabase "seguro", ao mexer em policies/RLS, ou em auditoria de segurança de dados
> **Keywords:** "rls", "supabase seguro", "row level security", "anon leak", "pg_policies", "vazamento de dados", "advisors", "policy"
> **Prioridade:** ALTA
> **Tools:** MCP Supabase por capability — `execute_sql`, `get_advisors`, `list_tables` (o prefixo da ferramenta varia por instalação: pode ser `mcp__supabase__*`, `mcp__claude_ai_Supabase__*`, etc. — NUNCA hardcode o prefixo completo)

# rls-audit — RLS de verdade (não a flag)

**Lição (18/jun):** `pg_class.relrowsecurity = true` **NÃO garante seguro** — o vazamento real vive em **policies `anon` permissivas** (`qual = true`). Auditar a flag só dá falso-conforto. Esta skill audita onde o leak mora.

## Contrato

**ENTRADA:** nenhuma (conecta no projeto Supabase já vinculado ao MCP).

**SAÍDA:** veredicto por tabela — `(RLS on/off · policies anon · qual · sensível?) → bug / by-design / a-corrigir`. Nunca "seguro" só pela flag.

**EXIT CODES** (da chamada MCP):

| Exit | Significado |
|---|---|
| 0 | consulta rodou — resultado (mesmo que "0 leaks") é confiável |
| erro `Unauthorized` | token do MCP Supabase ausente/expirado — **NÃO declare "seguro" nem "0 leaks"**; declare "não verificado" |

**ESTADO QUE TOCA:**

| Recurso | Lê/Escreve | Propósito |
|---|---|---|
| `pg_policies` (via `execute_sql`) | Lê (read-only) | policies anon/public permissivas |
| `get_advisors(type="security")` | Lê (read-only) | RLS-disabled, SECURITY DEFINER views |

## Processo
1. **Advisors primeiro:** `get_advisors(type="security")` — pega RLS-disabled, policies abertas, SECURITY DEFINER views, etc.
2. **Policies anon permissivas (o ponto cego):**
   ```sql
   select schemaname, tablename, policyname, roles, cmd, qual
   from pg_policies
   where 'anon' = any(roles) or roles = '{public}'
   order by tablename;
   ```
   Sinal de leak: `qual = true` (ou nulo) numa policy `SELECT` para `anon`/`public` → **qualquer um lê a tabela inteira**. Cruze com dados sensíveis.
3. **Tabelas sem RLS:** `select relname from pg_class where relkind='r' and not relrowsecurity and relnamespace='public'::regnamespace;` — RLS off = porta aberta.
4. **GRANTs amplos:** procurar `GRANT ALL ... TO anon/public` e `ALTER DEFAULT PRIVILEGES` permissivos.
5. **Veredicto honesto:** liste cada tabela com (RLS on/off · policies anon · qual · sensível?) → bug / by-design (ex: `shared_state` público intencional) / a-corrigir. **Não declare "seguro" só porque a flag está on.**

## Quando NÃO Ativar
- Projeto sem Supabase / sem MCP Supabase conectado.
- Mudança que não toca dados/policies.

## Exemplos executados

```console
$ mcp__supabase__get_advisors(type="security")
{"error":{"name":"Error","message":"Unauthorized. Please provide a valid access token to the MCP server via the --access-token flag or SUPABASE_ACCESS_TOKEN."}}
```
<!-- executado: 2026-07-10 · exit=1 -->
(token do MCP ausente nesta sessão — o passo 5 se aplica: NÃO declarar "seguro", declarar "não verificado, token ausente".)

```console
$ mcp__supabase__list_tables(schemas=["public"], verbose=false)
{"error":{"name":"Error","message":"Unauthorized. Please provide a valid access token to the MCP server via the --access-token flag or SUPABASE_ACCESS_TOKEN."}}
```
<!-- executado: 2026-07-10 · exit=1 -->
(2º erro idêntico confirma que é o token — não uma falha pontual da 1ª chamada.)

```console
$ python -c "
policies = [
    {'tablename': 'shared_state', 'roles': ['anon'], 'cmd': 'SELECT', 'qual': 'true'},
    {'tablename': 'billing_customers', 'roles': ['anon'], 'cmd': 'SELECT', 'qual': 'true'},
    {'tablename': 'audit_log', 'roles': ['authenticated'], 'cmd': 'SELECT', 'qual': 'user_id = auth.uid()'},
]
leaks = [p for p in policies if 'anon' in p['roles'] and p['cmd'] == 'SELECT' and p['qual'] in (None, 'true')]
for p in leaks:
    print('LEAK:', p['tablename'], '- qual=', p['qual'])
print(len(leaks), '/', len(policies), 'tabelas com leak anon-permissivo')
"
LEAK: shared_state - qual= true
LEAK: billing_customers - qual= true
2 / 3 tabelas com leak anon-permissivo
```
<!-- executado: 2026-07-10 · exit=0 -->
(a LÓGICA de detecção do passo 2 (qual=true numa policy anon SELECT = leak) validada localmente — independente do MCP estar autenticado; `shared_state` pode ser by-design, `billing_customers` não.)

## Prova

```bash
python -c "policies=[{'roles':['anon'],'cmd':'SELECT','qual':'true'}]; assert any('anon' in p['roles'] and p['qual']=='true' for p in policies)"
```

## Veja também
`drift_check.py` (intenção×realidade), o incidente registrado na memória do projeto (RLS leak fechado 18/jun: 8 `*_anon_read qual=true` dropadas).

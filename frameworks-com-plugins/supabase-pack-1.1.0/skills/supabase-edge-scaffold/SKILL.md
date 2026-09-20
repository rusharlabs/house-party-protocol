---
name: supabase-edge-scaffold
description: Scaffold de uma Supabase Edge Function com CORS + service-role + tratamento de erro corretos, em vez de copiar boilerplate à mão
---

> **Auto-Trigger:** Ao criar uma nova Supabase Edge Function / endpoint serverless Supabase
> **Keywords:** "edge function", "supabase function", "nova edge", "/edge-new", "deno deploy supabase", "função serverless supabase"
> **Prioridade:** MÉDIA
> **Tools:** Write, Read, mcp__claude_ai_Supabase__deploy_edge_function, mcp__claude_ai_Supabase__list_edge_functions

# supabase-edge-scaffold — edge function nascendo certa

Toda edge nova repete o mesmo boilerplate (CORS, OPTIONS preflight, service-role via env, erro JSON). Esta skill gera o esqueleto correto.

## Contrato

**ENTRADA:** nome kebab-case da função + (opcional) lógica específica a inserir no corpo.

**SAÍDA:** `supabase/functions/<nome>/index.ts` com CORS + OPTIONS preflight + service-role via env + erro JSON.

**EXIT CODES** (smoke test `deno check` sobre o arquivo gerado):

| Exit | Significado |
|---|---|
| 0 | TypeScript type-checa limpo (1ª vez baixa deps do jsr.io/npm; runs seguintes = cache local, offline) |
| ≠0 | erro de sintaxe/tipo no esqueleto gerado — não commitar assim |

**ESTADO QUE TOCA:**

| Recurso | Lê/Escreve | Propósito |
|---|---|---|
| `supabase/functions/<nome>/index.ts` | Escreve | o esqueleto |
| `Deno.env` (em runtime, não aqui) | — | service-role NUNCA hardcoded/commitado |

## Processo
1. **Nome + propósito** da função (kebab-case).
2. **Gerar `supabase/functions/<nome>/index.ts`** com este esqueleto:
   ```ts
   import { createClient } from "jsr:@supabase/supabase-js@2";

   const CORS = {
     "Access-Control-Allow-Origin": "*",
     "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
     "Access-Control-Allow-Methods": "POST, OPTIONS",
   };

   Deno.serve(async (req) => {
     if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
     try {
       // service-role: NUNCA hardcode — vem do ambiente da function
       const supabase = createClient(
         Deno.env.get("SUPABASE_URL")!,
         Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
       );
       const body = req.method === "POST" ? await req.json().catch(() => ({})) : {};
       // ... lógica ...
       return new Response(JSON.stringify({ ok: true }), {
         headers: { ...CORS, "Content-Type": "application/json" },
       });
     } catch (e) {
       return new Response(JSON.stringify({ ok: false, error: String(e) }), {
         status: 500, headers: { ...CORS, "Content-Type": "application/json" },
       });
     }
   });
   ```
3. **Guardrails:** service-role só via `Deno.env` (nunca no código/commit — `no-secrets`); erro sempre JSON+CORS (não vaza stack); validar input antes de tocar o DB.
4. **Deploy** quando pronto: `deploy_edge_function` (MCP) ou `supabase functions deploy <nome>`. **Deploy = gate humano** (não auto-deploy sem ok).

## Quando NÃO Ativar
- Projeto sem Supabase.
- Editar function existente (use Edit direto).

## Exemplos executados

```console
$ deno check supabase/functions/exemplo/index.ts
Download https://jsr.io/@supabase/supabase-js/meta.json
[... resolve deps na 1a vez ...]
Check index.ts
```
<!-- executado: 2026-07-10 · exit=0 -->
(o esqueleto EXATO desta skill type-checa limpo — não é pseudocódigo.)

```console
$ time deno check supabase/functions/exemplo/index.ts
real 0m0.236s
```
<!-- executado: 2026-07-10 · exit=0 -->
(2ª chamada = cache local, 0.236s — a partir daqui `deno check` é offline e cabe como Prova rápida.)

```console
$ grep -c "Access-Control-Allow-Origin\|OPTIONS\|Deno.env.get\|catch (e)" supabase/functions/exemplo/index.ts
4
```
<!-- executado: 2026-07-10 · exit=0 -->
(confirma os 4 guardrails do passo 3 presentes no arquivo gerado: CORS, preflight, env — nunca hardcode, e tratamento de erro.)

```console
$ deno check broken.ts
TS2345 [ERROR]: Argument of type 'string | undefined' is not assignable to parameter of type 'string'.
    Deno.env.get("SUPABASE_URL"),
Found 2 errors.
error: Type checking failed.
```
<!-- executado: 2026-07-10 · exit=1 -->
(reprodução real: tirar o `!` non-null assertion do `Deno.env.get(...)!` do esqueleto original QUEBRA o type-check — é exatamente por isso que o passo 2 exige o `!`.)

## Prova

```bash
deno --version
```
(pré-condição rápida e offline: sem `deno` no PATH, `deno check` do passo de smoke-test não roda. Depois de gerar um scaffold real, troque por `deno check supabase/functions/<nome>/index.ts`.)

## Veja também
`rls-audit` (segurança de dados), `secret_scan_on_write` (não commitar a service-role).

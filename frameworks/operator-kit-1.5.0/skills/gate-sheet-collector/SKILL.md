---
name: gate-sheet-collector
description: Drains everything that depends on the human into ONE form (exact command + what-it-unblocks), without ever blocking the loop
---

> **Auto-Trigger:** During an autonomous loop, on hitting something only the human can resolve (billing/OAuth/legal/client/deploy-go/secret/decision)
> **Keywords:** "gate", "depends on the human", "I need the operator", "approval", "billing", "oauth", "deploy", "secret", "form", "blocked"
> **Priority:** HIGH
> **Tools:** Read, Write, Edit
> **Related doctrine:** `rules/learned-corrections.md` (LC-1: single source, no parallel list), `rules/gateguard.md` (human gate before anything destructive).

# gate-sheet-collector — the wall becomes a form

What genuinely depends on the human **is never an excuse for the loop to stop** — it becomes a line in a single form that the human clears in one sitting.

## Contract

**INPUT:** an item only the human can resolve (billing/OAuth/legal/client/deploy-go/secret/decision), detected during a loop.

**OUTPUT:** 1 append-only line in `paths.gate_sheet`, format `{gate · reason · EXACT command/step · what-it-unblocks}`.

**EXIT CODES** (line format validation, see Proof):

| Exit | Meaning |
|---|---|
| 0 | line matches the format `gate · reason · command · unblocks` |
| 1 | malformed line (1+ of the 4 `·`-separated fields missing) |

**STATE IT TOUCHES:**

| Resource | Reads/Writes | Purpose |
|---|---|---|
| SSoT (items marked by `ralph-loop-driver`) | Reads | the SINGLE source of the gates — never a 2nd parallel list |
| `paths.gate_sheet` | Writes (append-only) | 1 line per gate |

## Process
1. **Detect the gate.** Typical categories: billing, OAuth/login, legal, message to a client, deploy-prod-go, secret rotation, product/architecture decision, editing `settings.local.json` (classifier).
2. **Do NOT block.** Leave the item **staged** (prepared + backup when applicable) and move on to the next autonomous item.
3. **Drain into the gate-sheet** (`paths.gate_sheet`), one line per gate, in the format:
   `{gate · reason · EXACT command/step the human runs · what-it-unblocks when done}`.
4. **Single source.** Drain from the items that `ralph-loop-driver` already marked in the SSoT — **do not keep a second parallel list** (two lists diverge → the classic error LC-1 catches).
5. **Report at the end** the consolidated gate-sheet as the only thing missing for 100%.

## When NOT to Activate
- Outside an autonomous loop (ask for the one-off approval on the spot).
- When the item is actually doable autonomously (do not label as a gate what you can do yourself — prove it cannot be done first).

## Executed examples

```console
$ python -c '
import re
line = "billing · renovar assinatura vencendo 15/07 · acessar console e renovar · destrava: crons headless voltam"
pattern = re.compile(r"^[\w-]+ · .+ · .+ · .+$")
print("formato valido:", bool(pattern.match(line)))
'
formato valido: True
```
<!-- executed: 2026-07-10 · exit=0 -->

```console
$ python -c '
import re, sys
pattern = re.compile(r"^[\w-]+ · .+ · .+ · .+$")
line = "so um texto solto sem separador"
ok = bool(pattern.match(line))
print("formato valido:", ok)
sys.exit(0 if ok else 1)
'
formato valido: False
```
<!-- executed: 2026-07-10 · exit=1 -->
(line without the 4 `·`-separated fields — rejected; that is what guarantees 1 parseable form, not free prose.)

```console
$ python -c '
import re
lines = ["gate1 · m1 · c1 · d1", "gate2 · m2 · c2 · d2"]
pattern = re.compile(r"^[\w-]+ · .+ · .+ · .+$")
print("todas validas:", all(pattern.match(l) for l in lines))
'
todas validas: True
```
<!-- executed: 2026-07-10 · exit=0 -->

## Proof

```bash
python -c 'import re,sys; sys.exit(0 if re.match(r"^[\w-]+ · .+ · .+ · .+$", "billing · x · y · z") else 1)'
```

## See also
`ralph-loop-driver` (marks the items), the `execute-100pct` output style (the wall never stops the loop).

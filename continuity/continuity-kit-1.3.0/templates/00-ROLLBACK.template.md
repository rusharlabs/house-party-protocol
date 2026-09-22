# 00-ROLLBACK — {{project_name}} / {{mudanca_nome}}

> Rollback is an ARTIFACT here, not doctrine scattered in prose: every change that mutates
> runtime/production/live data gets THIS document BEFORE being applied, with the literal
> command back already written (not "it can be reverted if needed" — the command exists).

## Classification of the change

- [ ] **Additive** (new file/route/column — reversible by simple removal)
- [ ] **Destructive** (replaces/removes something live — reversible only with a prior backup)
- [ ] **Data migration** (schema/format — reversible only with a prior dump)

## Snapshot BEFORE (mandatory for destructive/migration)

```bash
{{comando_de_backup_ou_snapshot}}
```

## The EXACT command back (written BEFORE applying the change)

```bash
{{comando_literal_de_rollback}}
```

## Post-rollback verify (proves it went back, does not presume)

```bash
{{comando_que_confirma_estado_anterior}}
```

## Built-in lesson (LC-1 · deploy/routing)

When verifying that a deploy/rollback worked, confirm that the **BACKEND really switched**
(a route exclusive to the new/old one + build marker) — never just the process status nor the
auth gate (both can stay identical between the new version and the old one). If there is a proxy/tunnel
in the path, confirm EACH hop, not just the end.

## Who authorises applying it

{{quem_aprova_esta_mudanca}} — human gate if the change touches production/real data.

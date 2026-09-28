# LEARNINGS — {{project_name}}

> CURATED lessons, with MANDATORY source evidence — unlike a MEMORY.md in free
> prose. Every entry here was promoted by a HUMAN from a candidate (if the operator-kit is
> installed, `evolve/instinct_promote.py --scan` collects candidates from recurring gate failures
> and `--promote <id> --to LEARNINGS.md` appends one here; LEARNINGS is where the human accepts
> them as a durable rule).

## Entry format (mandatory)

```
### {{date}} — {{lesson_title}}
**Context:** {{what_happened}}
**Evidence:** {{commit_or_file_or_pasted_output}}
**Distilled rule:** {{what_to_do_differently_from_now_on}}
**Applies when:** {{trigger_condition}}
```

`**Evidence:**` may also be the path of an `hpp evidence` record (`.hpp/evidence/<id>-<utc>.json`,
requires the HPP core); `python -m hpp evidence verify <record>` re-checks it (exit 0 = intact passed run).

## Real example (proven format — generic, no client data)

### 2026-07-05 — a deploy verify must hit an exclusive route, not the auth gate
**Context:** deploy declared "live" after seeing a 302 from the authentication gate — identical
between the old backend and the new one. The tunnel pointed at the wrong target; the site kept serving
the old version for days without anyone noticing.
**Evidence:** commit `abc1234` (tunnel fix) + a `curl` on a route exclusive to the new backend
showing the correct build marker.
**Distilled rule:** deploy verify = curl on a route EXCLUSIVE to the new one (with build marker),
never just the auth gate/process status. Confirm each proxy/tunnel hop.
**Applies when:** any deploy/rollback with a proxy or tunnel in the path.

---

*(New entries go ABOVE this line, most recent first. Never edit existing entries —
if a lesson needs a correction, add a NEW entry referencing
the old one.)*

# LEARNED-CORRECTIONS — rules distilled from recurring corrections

> **Auto-Trigger:** Before reporting numbers/counts/status; when the operator authorizes broad execution (auto/goal/100%/maximum capacity); before creating a new script or marking an item as pending/orphan.
> **Keywords:** "how many", "count", "status", "health", "metrics", "number", "stale", "where are we", "auto mode", "do everything", "do it all", "maximum capacity", "100%", "goal", "create script", "new script", "pending", "orphan", "not implemented", "TODO", "missing"
> **Priority:** HIGH
> **Version:** 1.0.0 (generalized for the operator-kit)
> **Admission criterion:** a correction becomes a rule here only when it recurs in ≥3 distinct sessions, is not already covered by another rule, and is actionable.

---

## LC-1 · Audit the source LIVE before citing ANY number/metric/status

Audit the source LIVE before citing any number, metric or status — treat data from
STATE.json, handoffs, docs, snapshots or another agent as SUSPECT until confirmed.

Applies to: counts (files, modules, tests, hooks), health scores, deliverables,
item/task status, plan/feature completeness, **and deploy/routing** (verify that the
BACKEND switched — route/content exclusive to the new build — NOT just the auth gate or the
process status).

**Deploy/routing case:** declaring a deploy "live" only because the
network-level HTTP response (e.g. an authentication redirect) is identical to the old backend
is a common error — the proxy/tunnel may still be pointing at the old build. **Deploy verify =
curl on a route EXCLUSIVE to the new build + build marker on the real backend, not on the gate.**
Proxy/tunnel chain: confirm EACH hop, do not assume.

BEFORE reporting:
- Filesystem counts: `grep`/`ls`/`find` on the real directory (do not trust "I remember there were N").
- Operational/service status: query the real endpoint or health check from your `health.probes` (see the marketplace's `health-kit`, if installed).
- Plan/feature completeness: `git log --grep` + check the files on disk.

If a number came from a previous session, from another agent, or from a doc older than 1 week: do NOT
repeat it as fact — re-verify at the live source and, when reporting, state that it is live.

**WHY:** reporting stale data as fact destroys the operator's trust in what you say.

---

## LC-2 · When authorized, really execute — 100% in batch, no stalling

When the operator authorizes broad execution (auto mode / "do everything" / "maximum capacity" /
"100%" / a goal command), EXECUTE the action completely and in batch — the whole scope at
once, NEVER "1 per session", never stopping at preparing/promising/hedging. An explicit instruction to
"finish everything 100%" OVERRIDES any cadence suggested in a runbook. Attack everything that does NOT break
the system autonomously; what genuinely depends on the operator (manual GUI test, decision,
access) becomes an objective doc/form — never an excuse not to act. Keep depth and
technical quality; report the real gaps at the end.

**WHY:** half-executions and preparation-without-action are the most frequent complaint of demanding
operators. Executing without asking for confirmation (when already authorized) and always reporting the
remaining gaps at the end are the pair that resolves this.

---

## LC-3 · grep/ls BEFORE creating a new script OR marking an item as pending/orphan

BEFORE creating any new script/tool OR marking an item as pending/orphan/
not-implemented: run grep + ls/Glob to confirm it does not already exist. Treat
"pending"/"orphan" as a HYPOTHESIS to refute, not truth. Commands: grep for the name/feature in the
source code, the scripts, the hooks; grep for earlier classifications in plan docs
before reclassifying files.

**WHY:** checking avoids rework and duplicates — a "new" script that already existed, or a
"pending" item that was already delivered, are a previous session's errors repeating themselves.

---

*Distilled from recurring operator corrections. Applies to any LLM that uses this kit.*

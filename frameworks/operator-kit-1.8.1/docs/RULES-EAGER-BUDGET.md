[English](RULES-EAGER-BUDGET.md) · [Português](RULES-EAGER-BUDGET.pt-BR.md)

# Rule layer: what it costs you at boot

Every file you copy into `.claude/rules/` is loaded into **every session of that project,
before your first prompt** — unless it declares `paths:`. That makes a rule layer a recurring
context bill, not a one-off install. This page publishes the bill.

## The number

Measured on 2026-09-22, before any rule declared `paths:`:

```
rules 13 · bytes 165.955 · tokens ~41.488 · with-paths 0
```

After scoping, on the same 13 rules (plus the content added in the same release):

| | rules | bytes | ~tokens | when it loads |
|---|---:|---:|---:|---|
| **EAGER** | 7 | **56.770** | **~14.192** | every session |
| path-scoped | 6 | 116.878 | ~29.219 | only when you touch the matching path |
| total on disk | 13 | 172.632 | ~43.158 | — |

Re-measured on 2026-09-24 (operator-kit 1.6.1): EAGER 7 rules · **57.876 B** (~14.469 tokens) ·
path-scoped 123.341 B · total on disk 181.217 B. The headroom under the 59.000 B ceiling is
1.124 B, still smaller than the smallest scoped rule (`loop-passk`, 5.179 B).

**Per-session cost fell 65,8 %** (165.955 → 56.770 B; it was 55.754 B before two eager rules gained new doctrine text on the same day). The layer on disk *grew* by 6.677 B in
the same release — the judgement layer and the checker-isolation doctrine are new text. Those
are two different numbers with two different units, and only the first one is charged to you
every time you open the project.

> Tokens are bytes ÷ 4, the usual English approximation. It is an estimate; the byte count is
> the measurement, and the gate is enforced on bytes.

## Why each rule is where it is

The frontier: a rule stays eager when it is **valid in any context and expensive to miss**.
Everything whose value is path-specific declares `paths:`.

### Eager — 7 rules

| rule | bytes | why it cannot wait for a path |
|---|---:|---|
| `epistemic-standards` | 15.070 | Presenting a hypothesis as a fact is possible in any answer, including one that touches no file. |
| `loop-maker-checker` | 13.782 | Gates push / merge / closing a goal — moments reachable from anywhere, and irreversible once passed. |
| `gateguard` | 9.934 | Fires before the *first* edit and before any destructive command; a rule that arrives after the first edit arrives late. |
| `loop-cost-budget` | 8.657 | A loop can be armed from any directory, and an unbudgeted one spends until someone notices. |
| `stale-replay-guard` | 6.034 | Triggers on `/resume` and context restore — events with no file path to hang a glob off. |
| `learned-corrections` | 4.211 | "Measure live before citing a number" applies to every report; 4 KB is cheap insurance. |
| `no-secrets-in-memory` | 748 | 748 bytes, and the damage it prevents (a credential committed to a memory file) is not reversible. |

### Path-scoped — 6 rules

| rule | bytes | scope | why the path is enough |
|---|---:|---|---|
| `agent-integrity` | 34.401 | agents, knowledge, `AGENT.md`, `SOUL.md`, `MEMORY.md`, `DNA-CONFIG.yaml` | Traceability of agent content: templates, citation formats, propagation matrix. It has no bearing on a session that never opens an agent file. |
| `agent-cognition` | 34.120 | agents, knowledge, `AGENT.md`, `SOUL.md` | How an agent reasons — read when writing or editing one, not while fixing CSS. |
| `loop-patterns-catalog` | 20.325 | loop / cron / squad paths, `.claude/commands/**` | A design-time catalogue ("which shape?"), consulted once per loop, not once per session. |
| `loop-operator` | 19.190 | loop / cron / squad paths, `.claude/commands/**` | Pre-flight and stop-conditions in full detail; the always-on half of loop safety is `loop-cost-budget`, which stayed eager. |
| `partial-autonomy-slider` | 10.056 | agents, `operator-profile.yaml` | It governs a value that lives in those files; reading it elsewhere changes nothing. |
| `loop-passk` | 5.212 | evals, loop paths | pass@k / pass^k applies when you are running an eval or promoting an agent. |

⚠️ **Scoping does not strand a rule.** The kit's skills cite rules by name
(`> **Related doctrine:** rules/<name>.md`), and reading one explicitly always works. `paths:`
decides what is *pre-loaded*, never what is *available*.

## Adjusting the scope to your repo

The globs are written for common layouts (`agents/`, `.claude/agents/`, `knowledge/`,
anything with `loop` in the name). If your project keeps agents in `src/ai/personas/`, add
that glob — a rule whose globs never match is a rule that never loads, which is worse than
eager:

```yaml
---
paths:
  - "agents/**/*"
  - "src/ai/personas/**/*"
---
```

To make a scoped rule eager again, delete its front-matter block. To scope an eager one, add
`paths:` — and in both cases update `EAGER_BY_DESIGN` in the gate below, because it will fail
otherwise. That failure is the point.

## The ratchet

A ratchet test in the kit's release pipeline holds the number:

```
EAGER_BUDGET_BYTES = 59000
```

Four gates and five controls:

- **structural** — the set of rules with no `paths:` must equal the declared eager set. Catches
  a rule losing its front matter *and* a new rule landing eager by default.
- **budget** — eager bytes may not pass 59.000. The headroom above 57.876 (1.124 B) is smaller than
  the smallest scoped rule (5.179 B), so no rule can quietly slip back into the eager set, and a
  separate gate pins that invariant so raising the ceiling cannot break it. Raised from 57.000
  on 2026-09-22: at 230 B of headroom the next honest line of doctrine would have failed the
  gate, and a gate that fires on correct work gets its number bumped in a hurry by whoever is
  blocked — which is how a ratchet becomes a rubber stamp.
- **no empty `paths:`** — a `paths:` key with no glob neither scopes nor loads.
- **doc ↔ gate** — this page must publish the same numbers the gate enforces, so the two
  cannot drift apart.

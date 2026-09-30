[English](ROADMAP.md) · [Português](ROADMAP.pt-BR.md)

# Roadmap

Where the work is headed over the next twelve months, and what the project will not do. This is a
direction, not a promise: what shipped is recorded in [CHANGELOG.md](CHANGELOG.md) and in the
release notes, and only there. The plan is discussed in public in the
[roadmap discussion](https://github.com/rusharlabs/house-party-protocol/discussions/28), in the
Announcements category; how decisions are taken is in [GOVERNANCE.md](GOVERNANCE.md).

## Where the maps are on 2.11

Every map in HPP is a projection of files you already have — manifests, event logs, JSON you
supply — and the same input prints the same output.

| command | formats |
|---|---|
| `hpp graph --view capability\|operational\|agent\|evidence\|code` | JSON or Mermaid |
| `hpp map lane\|agent\|monitor\|context` | JSON or Mermaid |
| `hpp work plan\|waves` | JSON or Mermaid |
| `hpp doctor --matrix` | Markdown: host × module × channel |

The `code` view shows which surfaces each module declares; it is not a graph of your code. The
lane-kit's Lane Dashboard, since 2.10.0, is a page on the loopback address that you start and stop,
showing the lane board, the live lanes, each lane's mailbox and the backlog with its waves; every
action it offers is also a terminal command.

## 2.12: see the state

Mermaid for the maps and the WorkGraph, the first item planned for this step, shipped in 2.11.0
(the table above). The other three are next:

1. **A feed map.** One timeline of what happened across lanes — claims, verdicts, messages sent and
   read, deliveries, handoffs, heartbeats — derived from records the harness already writes.
2. **A static HTML atlas.** `hpp atlas --html` would write one self-contained page with every view
   of a project, drawn from the same JSON. Each view shows the command that reproduces it and the
   hash of its source. It opens as a file; there is no server.
3. **The Lane Dashboard views.** The dashboard shows the same views, drawn from the same JSON, next
   to the actions it already offers.

## 2.13: a code graph of your project

A base built on the Python standard library — modules, imports, definitions and calls read with
`ast`; for other languages an import graph only, declared as such — plus a contract,
`hpp.codegraph/v1`, for an external indexer you declare. HPP would normalise and measure that input;
it would not depend on it. The graph is built on demand, stored by commit hash and reported as
`stale` when it is old, with no watcher. It would feed lane territory by dependency, the WorkGraph
checks, the blast radius of an attestation and the atlas's code view.

## After 2.13

Nothing is planned yet. What comes next is decided from the answers in the roadmap discussion and
from the proposals in the Ideas category of Discussions, and this page is updated when it is.

## What the project will not do

These refusals are the ones in [MANIFESTO.md](MANIFESTO.md), "What the project refuses to do". They
are decisions, not gaps, and nothing on this roadmap changes them. The manifesto carries the reason
for each and the bounded exceptions for modules; where this summary and the manifesto differ, the
manifesto binds.

- **No daemon, no server, no scheduler.** A check that did not run was not run. The atlas planned
  above opens as a file for this reason.
- **No model calls.** The harness routes work to a tier and a provider id you declared, and holds
  no credential.
- **No graph database.** Every map is a projection of files you supply; the code graph planned for
  2.13 is built on demand, keyed by commit hash and reported `stale` when it is old.
- **No silent writes.** Installers plan first and write only on an explicit second step; the
  wiring of settings and hooks is printed for a person to paste.
- **No promise accepted as evidence.** The done gate re-runs the criterion commands; a completion
  tag in a transcript stops nothing.
- **No host parity by assertion.** Coverage is declared per module as `native`,
  `explicit-command` or `unsupported`.
- **No headline numbers.** A number appears next to the command that produced it, or it does not
  appear.
- **No remote telemetry.** Nothing leaves the machine unless a person runs a command that sends it.

## How to take part

Answer in the [roadmap discussion](https://github.com/rusharlabs/house-party-protocol/discussions/28)
with your setup — host, bundle and the command you would run — one point per comment; an upvote on
a comment counts as agreement. A proposal that needs its own design goes to the Ideas category, as
[SUPPORT.md](SUPPORT.md) describes. This page changes through a pull request, and the change is
recorded in the CHANGELOG.

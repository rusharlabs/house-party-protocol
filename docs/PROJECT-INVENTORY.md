[English](PROJECT-INVENTORY.md) · [Português](PROJECT-INVENTORY.pt-BR.md)

# Inspect an existing project

HPP 2.13 measures the committed project before proposing parallel work. All commands below
print to stdout. They do not import your application, run tests, install dependencies or call a model.
Git and Python 3.10+ are required; no parser package or graph service is required.

```bash
hpp inventory --target .
hpp codegraph build --target .
hpp lanes propose --target .
```

## Universe and privacy

The universe is the regular files in the HEAD tree, not an unrestricted disk scan. Untracked
and ignored files are outside it; staged and working-tree changes are reported as dirty tracked
paths, not mixed into the committed content. Symlinks and Git submodules are metadata only.
Secret-shaped files, including `.env` and private keys, are excluded from content reads.

`hpp.inventory/v1` reports manifest and extension signals, test paths and runner hints, CI command
candidates, documentation, agent instructions and hook counts, CODEOWNERS presence, author count
and hotspots in a bounded commit window. Authors are counted without publishing identities.
CI candidates are never executed. Credential-like commands are withheld. File counts are not test
results, authorship is not ownership, and a documentation path is not proof that its content is current.
Unreadable inputs and exclusions are reported separately; an inspection failure is not an empty project.

## Explicit cache and freshness

```bash
hpp inventory --target . --out
hpp codegraph build --target . --out
hpp codegraph status --target .
hpp status --target . --json
```

An explicit `--out` stores `.hpp/inventory/<commit>.json` or `.hpp/codegraph/<commit>.json`.
`--out <path>` chooses a destination. Existing different bytes and linked paths are refused;
the command never updates the Git index. Keep generated measurements outside your tracked
universe, for example by adding `.hpp/` to your project's ignore policy yourself.
Fresh means the artifact commit equals HEAD and tracked files are clean. Older commits or
tracked edits are stale, with changed paths and commit distance. An absent or invalid artifact
is labelled accordingly. No watcher updates these files. Status reads the profile and measurements
to suggest initialization, inventory, code graph or lane proposals; it never applies that suggestion.

## Code graph coverage

`hpp.codegraph/v1` contains commit, producer, coverage, nodes, edges, unresolved references and
instrument status. The built-in Python AST reader measures modules, definitions, imports and
conservatively resolved calls. Dynamic calls remain unresolved. JavaScript and TypeScript use
lexical import signals only: they do not claim parser, type-checker or runtime coverage. Other
languages are reported as unmeasured. The graph is static, so reflection and runtime configuration
can create relationships outside its measured coverage.

You may supply a declared indexer or an existing document:

```bash
hpp codegraph build --target . --indexer-command '["your-indexer","--json"]' --timeout 30
hpp codegraph import graph.json --target .
hpp codegraph compare --declared graph.json --target .
```

Only `--indexer-command` runs an external program. It accepts JSON argv without a shell and sends
the commit and file universe on stdin. Choose a program you trust: HPP bounds its time and output
but does not sandbox its filesystem or network access. Invalid JSON, crashes, timeout and output
overflow are instrument failures, never successful empty graphs. Failed measurements cannot be cached.
Imported paths are relative POSIX/NFC paths in the committed universe. Duplicate IDs are refused;
excluded nodes and unresolved edge targets are counted. Comparison reports Python import agreement
against the built-in reader, not a claim that either graph is complete.

## From relationships to proposed work

```bash
hpp lanes propose --target . --max-lanes 4 --depth 2 --out
hpp work plan work.json --target . --codegraph graph.json
hpp map lane lanes.json --target . --codegraph graph.json
hpp attest create --repo . --spec work.json --output attestation.json \
  --maker maker --checker checker --session review --verdict approved \
  --codegraph graph.json --base-commit <base-sha>
hpp atlas --html --target . > atlas.html
```

Lane proposals require a fresh inventory. A fresh graph supplies weighted imports; without one,
the fallback groups directories and explicitly marks relations unmeasured. Shared hubs, remaining
cross-lane import cost and hotspot red zones stay visible. The output is `hpp.lane-proposal/v1`,
not applied lane configuration. A person must approve territories before dispatch.
WorkGraph units may declare `territory` as a list of relative path prefixes; optional graph input
warns about coupling inside a wave. Lane maps also report import coupling between territories.
Attestation impact follows reverse imports from files changed since the base commit. Stale input
marks this impact unmeasured; it does not weaken the attestation's existing evidence gate.
Impact covers resolved imports at HEAD, not all runtime dependencies. In particular, deleting a
module can leave its former imports unresolved; these paths need review beyond the reported closure.

The offline atlas adds project inventory and project code views for Git targets, including freshness,
coverage and unresolved references. `--inventory <file>` and `--codegraph <file>` select explicit
inputs inside the target. The legacy `hpp graph --view code` remains the protocol module surface
map; the atlas project code view uses the project's graph.

Dev Squad's `pp-discovery` starts with inventory and `pp-xray` uses its delimited paths. When
their optional task tree is absent, existing-project discovery routes use these shipped skills
instead of fabricating a missing workflow. Lane Dashboard terminal `wave start --lane-proposal
<relative-json>` records the proposal path, SHA-256 and commit in the wave request for review;
it does not approve or apply territories.

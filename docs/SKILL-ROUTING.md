[English](SKILL-ROUTING.md) · [Português](SKILL-ROUTING.pt-BR.md)

# Advisory skill routing

`hpp skills` connects a declared goal to inspectable skill metadata. It does not load,
install or execute a skill, change a profile, register a hook, or call a model. A
recommendation is not permission and does not replace the host's instructions or gates.

## Local catalog and shortlist

From a checkout, with the target project substituted for `./my-project`:

```sh
python -m hpp skills catalog --target ./my-project --host codex
python -m hpp skills recommend --target ./my-project --host codex --intent "inspect database schema" --limit 3
```

Use `--host claude-code` for `.claude/skills`; `codex` reads `.agents/skills`.
Only immediate skill directories under that explicit project root are inspected.
There is no global, ancestor, plugin-cache, transcript, or built-in-skill scan. HPP does
not infer a host's enabled/disabled settings: use repeated `--exclude project:NAME` flags
to leave entries out explicitly.

`--include-bundled` adds skills available in the HPP distribution selected by the
manifest. It does **not** prove those modules or skills are installed in the target:

```sh
python -m hpp skills catalog --target ./my-project --host codex --include-bundled
python -m hpp skills recommend --target ./my-project --host codex --include-bundled --profile ./my-project/.hpp/profile.json --intent "coordinate parallel review"
```

`--profile` accepts an existing `hpp.init/v1` profile with the matching host and known
module IDs. It requires `--include-bundled` and restricts **bundled modules only**;
project skills remain independent. `--manifest FILE` selects another manifest for
bundled discovery. Missing distribution directories are reported, not invented. A pip
installation without module artifacts does not become a full module catalog.

Catalog records use `project:DIRECTORY` and `module:MODULE:DIRECTORY` identities. Equal
names stay distinct. Each entry includes its name, description, origin, installed flag,
module, declared module capabilities, relative skill path and file SHA-256. Capabilities
are module-level manifest declarations, not measured competence or claims that each
individual skill provides every capability. A project entry's `installed: true`
means its file was discovered in the host's project directory, not that the host loaded it.

Inspect the same catalog as a provenance graph:

```sh
python -m hpp skills graph --target ./my-project --host codex --include-bundled
```

`graph` accepts the same common flags as `catalog`: `--target`, `--host`,
`--include-bundled`, `--manifest`, `--profile` and repeated `--exclude`. Its
`hpp.skill-graph/v1` output binds the catalog hash to skill, host, module and capability
nodes. Skills link to hosts as `installed-for` or `available-for`; modules `contains`
skills and `provides` declared capabilities. There is deliberately no skill-to-capability
`provides` edge: membership in a module is not proof of individual skill competence.

The lexical shortlist reports matched terms and a score, with `confidence: null`. Scores
are token overlap, **not probabilities**. Ties prefer installed entries, then stable IDs.
No overlap yields abstention, not a claim that no skill is needed. Read the shortlisted
skills before deciding whether any really fits.

## Optional Jev or other typed-decision advice

Exporting a request remains local, but its `state` contains the goal and catalog metadata.
Review it before sharing. The request includes a Choice question with skill IDs plus
`no-skill-needed` and `search-needed` options:

```sh
python -m hpp skills request --target ./my-project --host codex --intent "inspect database schema" > skill-request.json
```

After a human approves the specific provider, data transmission and any cost, the existing
external example adapter can read this JSON directly on stdin. The following is a
**manual network-call example**, not a command to run automatically:

```sh
python examples/typed-decisions/decide.py --provider typesafe --model PINNED_MODEL_ID --abstain-below 0.7 < skill-request.json > skill-decision.json
```

Replace `PINNED_MODEL_ID` with an available, pinned model version confirmed by the provider;
do not use `jev-latest`. The TypeSafe example reads `TYPESAFE_API_KEY` from the environment.
Do not put a key in arguments or committed files. Other declared adapters are described in
[typed decisions](../examples/typed-decisions/README.md). The adapter stores raw responses
in `.hpp/decisions/raw` by default and refuses states over 60,000 characters; narrow the
catalog if necessary. Do not pass `--declared`: skill choice is informational, not an
ordered risk ladder. No real provider call or provider availability is established by
this feature's offline tests.

Consume the result locally, using exactly the same target, host, goal, exclusions,
manifest and profile as the exported request:

```sh
python -m hpp skills recommend --target ./my-project --host codex --intent "inspect database schema" --decision skill-decision.json --min-confidence 0.7
```

The import validates `hpp.decision/v1`, including advisory authority, and requires the
exact current state and question to match. Changed skill bytes, catalog, intent or
exclusions invalidate old advice. Model/replay recommendations below the confidence
floor abstain; instrument failures stay failures. Hashes bind evidence to content, but
do not authenticate a provider or prove a skill is safe. Preserve raw-response evidence
for independent audit; this routing command validates the record, not a provider signature.

## Outcomes and limits

Output is `hpp.skill-route/v1`, with catalog/state/question hashes and coverage counts:

- `recommendation` + `review-skills`: inspect the selected entries; nothing executes.
- `recommendation` + `no-skill-needed`: imported advice says ordinary assistance suffices.
- `recommendation` + `search-needed`: imported advice suggests discovery, but no search
  or installation is performed.
- `abstention` or `instrument-failure` + `review-manually`: proceed with human/host judgment.

Catalog output is `hpp.skill-catalog/v1`; request output is `hpp.skill-request/v1`.
Inspect `skipped` and `unavailable` in the catalog, not just the recommendation or graph.
Graph and request commands exit 0 on successful output; a graph omits catalog diagnostics. Catalog exits 1 when
entries were skipped and otherwise 0; recommendation exits 0 for a recommendation and
1 for abstention/failure. Invalid input exits 2; unexpected internal errors exit 3.

Discovery rejects symlink paths, nonregular/oversized files and invalid metadata. It
uses descriptor-bound parent traversal and `O_NOFOLLOW`/`O_NONBLOCK` reads on POSIX,
with `fstat` checks for file identity, regular-file type and size after opening. Windows
retains reparse-point and identity checks, but these guards are **not a sandbox against
a concurrently hostile filesystem**. Only scan roots whose contents you trust.
Discovery bounds files to 128 KiB, enumeration to 2,048 entries and choices to 250 skills, refusing
overflow rather than silently truncating. Metadata is a deliberately small YAML subset:
name and description only, with simple quoted or folded/literal scalar values. A file's
bytes are read for its digest, but its body is not used as routing context or executed.
Secret-like text is refused; this pattern check is not a guarantee that all private data
will be detected. Review exports and avoid committing request/decision files containing
private project metadata.

Lexical matches can be irrelevant, especially when common capability words overlap.
Thresholds are not calibrated for every catalog or language. Measure representative
goals against your actual catalog before relying on the shortlist. The existing
`hpp retrieval eval` and `hpp decide eval` provide separate ranking and decision rulers;
this feature makes no accuracy or performance claim of its own.

## Relationship to the rest of HPP

Skill routing is an explicit command with bounded project discovery, provider-neutral
Choice records and no automatic network call or execution. HPP decision v1 measures
Choice questions, so "no skill needed" and "search needed" are options in the same
question rather than a separate one.

This complements the capability graph and mounting profiles; it does not replace them.
The graph explains module capabilities and supported hosts, profiles choose module scope,
and skill routing suggests which descriptions fit an intent. `hpp route` still selects
a provider tier subject to risk floors; `hpp skills` does not alter those floors.

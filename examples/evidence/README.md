[English](README.md) · [Português](README.pt-BR.md)

# Evidence bundles — an end-to-end check you can re-derive later

> New in 2.6.0.

A browser test proves something only when three things hold: the command that ran it can be
named, its exit code was measured outside the model, and the files it left behind can be hashed
again tomorrow. `hpp evidence` records exactly that. It does not drive a browser and does not call
a model — the criterion is whatever you declare.

| field | what it holds |
|---|---|
| `command` | the argv that ran, as declared |
| `exit_code` · `verdict` | `passed` only when the command exited 0 **and** every declared artifact exists |
| `artifacts` | per declared glob: each file's path (relative), size and sha256 |
| `stdout` · `stderr` | byte count and sha256 — never the text |
| `record_sha256` | a hash of the record itself, so an edited record is caught |

## Run the demo (no browser needed)

```bash
python -m hpp evidence run --id smoke-page --artifact out/report.html --artifact out/smoke.log \
  -- python examples/evidence/smoke_page.py
python -m hpp evidence verify .hpp/evidence/<the record path it printed>
```

Add `--break` after the script to see a failing criterion: the artifacts are written, and the
verdict is still `failed`, because a page that fails its check is not evidence.

## With a real end-to-end runner

The pattern is the same for any runner that exits non-zero on failure and writes files. For
Playwright, keep traces and screenshots on and declare where they land:

```bash
python -m hpp evidence run --id e2e-login --artifact "test-results/**/trace.zip" \
  --artifact "test-results/**/*.png" -- npx playwright test tests/login.spec.ts --trace on
```

Record the test once (`npx playwright codegen`, or an agent driving Playwright MCP while it
builds) and commit the spec. The model can help write the test; it never runs at verification.

## Tie it to the loop

`--record-event` appends `evidence_recorded` to `.hpp/events.jsonl` when, and only when, the
bundle passed — a failed run is a measurement, not evidence, so it never moves the loop:

```bash
python -m hpp event append --type work_started
python -m hpp evidence run --id smoke-page --artifact out/report.html --record-event \
  -- python examples/evidence/smoke_page.py
python -m hpp status
```

## Limits

- On timeout the whole process tree the command started is stopped. When the command exits on its
  own, a child it left running is neither waited for nor stopped: put long-lived servers under the
  runner's own lifecycle (Playwright's `webServer`).
- An artifact counts only when this run wrote it. A file that matches the glob but is exactly as it
  was before the run is listed as `unchanged` and does not satisfy the pattern.
- On Windows a bare command name such as `npx` is resolved through `PATH` and `PATHEXT`
  (`npx.cmd`), the way a terminal resolves it.
- A command line that looks like it carries a secret is refused; pass secrets through the
  environment, never as arguments.
- Artifact globs are relative to the workspace and cannot leave it.

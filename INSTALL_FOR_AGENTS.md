[English](INSTALL_FOR_AGENTS.md) · [Português](INSTALL_FOR_AGENTS.pt-BR.md)

# Installing House Party Protocol — a guide for agents

You are an agent that has been asked to install House Party Protocol into a repository. This
file is the whole instruction. Read it to the end before you run anything: step 4 contains a
gate you must not skip, and knowing it exists changes what you do in step 3.

House Party Protocol is a local-first harness for reliability, governance and evaluation of
coding agents. It has no runtime dependencies and talks to no network service. Installing it
writes files into a repository and wires them to a host; nothing else happens.

## Step 0 — identify your host

The two hosts wire differently, and the difference is not cosmetic.

| you are | go to |
|---|---|
| **Claude Code** | steps 1 → 4, then step 6 |
| **Codex CLI** | steps 1 → 4, then step 5, then step 6 |
| neither | the CLI still installs and `hpp doctor` still answers, but no host wiring exists for you; stop after step 3 and tell the person |

## Step 1 — check the preconditions, do not assume them

- **Python 3.10 or newer.** CI exercises 3.10 through 3.13 on Linux, macOS and Windows. Older
  interpreters are not promised, because nothing measures them.
- **`git` on `PATH`**, for attestation.
- **A target repository.** Installing into an empty directory works and is how the wizard is
  tested, but the harness is only useful where there is work to govern.

If a precondition fails, say which one and stop. Do not install a Python, do not change the
person's interpreter, do not work around a missing `git`.

## Step 2 — install the CLI

```bash
pip install git+https://github.com/rusharlabs/house-party-protocol@v2.6.5
```

`pipx install git+…` works the same way. The package ships its own manifest and benchmark
suite, so the CLI answers from any directory once installed.

## Step 3 — prove the install before you use it

```bash
hpp doctor
```

It prints one line and exits `0`:

```
HPP doctor: ok - modules=10 - hosts=claude-code, codex - hooks=18 (permission gates=9 - llm egress=0)
```

A non-zero exit here means the install is broken. Report the line and stop; do not continue to
step 4 hoping it resolves itself.

## Step 4 — read the plan to the person. DO NOT SKIP

```bash
hpp init --target <path-to-the-repository>
```

Without `--apply`, `hpp init` **writes nothing**. It runs six fixed stages and prints a plan of
what it would write.

Read the plan aloud, and not only the lines to paste. When the chosen modules declare hooks, it
prints a HOOK CAPABILITIES table before the WIRE block: for each hook, its events, its exit policy
(`observe`, `warn` or `block`) and its capability groups. That table is what the hooks can do once
wired; the paste lines alone are only file names. Leave `--decision-advisor` at `off` unless the
person asked for it (new in 2.6.0).

**Show that plan to the person and wait for them to say yes.** Only then:

```bash
hpp init --target <path-to-the-repository> --apply
```

This is not ceremony. The plan is the only moment at which the person can see what is about to
enter their repository, and an installer that writes before you read is the exact failure this
harness exists to prevent. If you skip it, you have installed the harness by violating it.

## Step 5 — Codex CLI wiring

Claude Code is wired by step 4. Codex CLI needs one more command per module:

```bash
installers/kit-forge-1.4.2/kit_doctor.py install --kit <kit> --host codex --target <repo> --apply
```

Skills land in `.agents/skills`; the full runtime lands in `.agents/hpp`. Hooks declared in
`hooks.json` belong to Claude Code and are **not** activated on Codex. `hpp init --host codex`
still prints the HOOK CAPABILITIES table; read it aloud as what those hooks would do on Claude
Code, and say that none of them runs here rather than letting the person believe a gate is armed
when it is not.

## Step 6 — verify, and report the exit code, not your impression

```bash
hpp doctor
hpp benchmark
```

`hpp benchmark` reports `pass@k` and `pass^k` separately and prints its own gate verdict. Quote
both outputs to the person. A transcript is not an exit code.

If `hpp init` printed a DOCUMENTATION section, point the person to the pages it names; each one
was found on disk. A pip install carries no documentation pages, so after step 2 the section is
absent — do not invent paths.

## Exit codes

`0` ok · `1` warn/manual · `2` block · `3` error.

## Do not

- **Do not edit the versioned module directories.** They are emitted artifacts. A hand edit
  makes their checksums diverge and the next install refuses them.
- **Do not lower a gate to get green.** Fix the artifact the gate rejected.
- **Do not record credentials, personal paths, clients or private infrastructure** anywhere the
  harness writes.
- **Do not treat `healthy` as correct.** It proves freshness of the declared signal, nothing more.

## Upgrading

Re-run step 2 with the new tag, then step 3. `hpp init` is idempotent: run it again and read the
plan again. The plan is what changed.

## If it fails

Run `hpp doctor` and quote the whole line. Open an issue at
<https://github.com/rusharlabs/house-party-protocol/issues> with that line, your Python version
and your host. Do not paste credentials, tokens or absolute paths from the person's machine.

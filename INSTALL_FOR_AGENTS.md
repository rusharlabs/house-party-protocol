[English](INSTALL_FOR_AGENTS.md) · [Português](INSTALL_FOR_AGENTS.pt-BR.md)

# Installing House Party Protocol — agent guide

For the core CLI alone, without installing modules, the versioned alternative is:

```bash
pip install git+https://github.com/rusharlabs/house-party-protocol@v2.14.0
```

This guide covers HPP 2.14.0 and later; earlier releases do not include `hpp setup` or
`scripts/setup_hpp.py`. The existing `hpp init` command is a profile planner; it does not install
modules or activate host integrations.

House Party Protocol (HPP) is a local-first toolkit for reliability, governance and evaluation of
coding agents. Its core does not call models or handle credentials. Setup installs selected module
files and prepares a project-scoped Python environment. Host activation and optional integrations
remain separately reported states.

## Before setup

Have Python 3.10 or newer, Git, and the chosen host (Claude Code or Codex CLI) installed. Sign in
to the host yourself; HPP does not install system software, switch accounts, or manage host login,
subscription or model costs. Supabase credentials are needed only if you later configure the
optional Supabase integration. Orca is optional.

Use one full public product checkout from `github.com/rusharlabs/house-party-protocol` for both the
bootstrap and offline `hpp setup --source`. Do not create a second product copy. The bootstrap
prepares the selected project, isolated `.hpp/venv`, pinned dependencies and HPP CLI, then invokes
the offline setup planner. Its `--apply` may contact the package index to install pinned Python
dependencies. The HPP core and module setup make no model-inference calls.

Clone once and run the commands from that checkout's root. Keep the existing consumer project
outside the product checkout:

```bash
git clone https://github.com/rusharlabs/house-party-protocol.git
cd house-party-protocol
```

## Choose a package

| Selection | Claude Code | Codex CLI |
|---|---:|---:|
| `reliable-coding` (default) | 6 modules | 6 modules |
| all compatible modules | 10 modules | 9 modules |

Codex does not support `claude-dev-kit`. The all-compatible selection omits it; an explicit
request to install an incompatible module is rejected rather than bypassed. Select individual
module IDs only when you know the integration you need.

## Plan, review, apply

From the root of that one public product checkout, run the bootstrap plan. On Windows use `python`;
on macOS use `python3`:

```powershell
python -I -B scripts/setup_hpp.py --target <project> --host claude-code
python -I -B scripts/setup_hpp.py --target <project> --host claude-code --all-compatible
```

```bash
python3 -I -B scripts/setup_hpp.py --target <project> --host codex
python3 -I -B scripts/setup_hpp.py --target <project> --host codex --all-compatible
```

The default is the six-module `reliable-coding` bundle. `--all-compatible` selects all supported
modules for the host: 10 for Claude Code and 9 for Codex CLI.

**DO NOT SKIP THE PLAN.** First run the command without `--apply`, read the complete plan (selected
modules, files, environment and dependency changes, host-specific actions, and manual gates), and
review the target path. Only then repeat that same command with `--apply`. Never apply before
reading the corresponding plan:

```powershell
python -I -B scripts/setup_hpp.py --target <project> --host claude-code --apply
```

```bash
python3 -I -B scripts/setup_hpp.py --target <project> --host codex --apply
```

The first command plans entirely offline and writes nothing. The apply operation creates
`.hpp/venv`, installs hash-pinned bootstrap wheels and the local CLI, then applies the module plan;
it needs PyPI access. It must preserve existing instructions and host configuration, report
conflicts before writing, and retain rollback information. A partial failure is not a completed
installation: use the report to resume only pending steps and verify the final state.

Trusted ownership metadata lives outside the consumer project in `~/.hpp-setup-state` by default
(Windows: under the user's home directory). Advanced `--state-dir <path>` changes that location;
keep it outside the project. It records the complete managed-environment inventory and validates
the launcher. Setup refuses project-forged receipts, an unowned existing environment, or a changed
launcher/environment. If trusted state is missing, stop and preserve the files for reconciliation;
do not adopt or delete them. The build uses a unique retained copy at `.hpp/bootstrap-build-<unique>`
and leaves the versioned release checkout unchanged. Do not commit `.hpp/venv`, `.hpp/bin`,
`.hpp/runtime-router.json`, receipts, runner data, `.hpp/run.py` or retained build copies.

## What setup does and does not activate

- The project `.hpp/venv` isolates HPP and selected module dependencies from the system Python.
- Module files and copied runtime/skills are not proof that a host loaded or activated them.
- Claude Code native plugins require an explicit host action and its own consent. Explicit-command
  modules remain commands; setup does not edit Claude settings or hooks.
- On Codex, setup copies the supported runtime and skills. HPP hooks remain off. Do not install a
  second plugin solely to duplicate skills already copied by the module installer.
- `.hpp/run.py` preserves the calling application's Python environment; HPP commands are routed
  through the managed runtime using local aliases in `.hpp/bin`. Invoke it with
  `python -I -B .hpp/run.py hpp doctor` on Windows or `python3 -I -B .hpp/run.py hpp doctor` on
  macOS.
- For Claude Code native plugins, review the plan and activate separately: Windows uses
  `python -I -B .hpp/run.py activate`; macOS uses `python3 -I -B .hpp/run.py activate`. It rechecks distribution
  and module checksums and keeps the host's consent flow. Restart Claude Code and verify
  plugin/hook state. The setup batch never activates the host by itself.
- Optional integrations are not configured merely because their files were installed.

The report must distinguish `installed`, `active`, `manual`, `refused` and `failed`. Verify the CLI,
module integrity, runtime, skills and host wiring independently. Do not describe host activation as
complete unless the host itself confirms it.

## Exit codes

`0` ok · `1` warn/manual · `2` block · `3` error.

## Existing lower-level commands

In releases that do not include guided setup, `hpp init` can plan and record `.hpp/profile.json`;
it does not install the module batch or activate host wiring. Module installers remain available
for per-module installation. Read the matching module's installation guide and preserve the
plan/apply confirmation and host-specific consent gates.

Never copy credentials into HPP files, logs or issue reports. Never overwrite an existing host
configuration to make a setup appear complete.

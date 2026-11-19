[English](SETUP.md) · [Português](SETUP.pt-BR.md)

# Guided setup

> **Availability:** this guide covers HPP 2.14.0 and later; earlier releases do not include
> `hpp setup`. Host activation remains a separate, explicit human action.

Guided setup composes the full public HPP product checkout, the existing module installer and a project-local
Python environment. It offers one reviewable plan followed by one batch apply. The core stays local
and provider-neutral: it makes no model-inference calls and does not collect or store credentials.

## Prerequisites

- Python 3.10 or newer.
- Git.
- Claude Code or Codex CLI already installed if that is the selected host.
- One full public product checkout from `github.com/rusharlabs/house-party-protocol`. Use the same
  checkout to run the bootstrap and as the offline command's `--source` distribution.

Host login, subscription and model charges remain with the host. Setup does not install Python,
Git, Claude Code, Codex, or other operating-system software. Supabase credentials are only needed
to configure and use the optional Supabase integration. Orca is optional.

## Selection

| Selection | Claude Code | Codex CLI |
|---|---:|---:|
| `reliable-coding` (default) | 6 modules | 6 modules |
| `--all-compatible` | 10 modules | 9 modules |
| `--modules <ids>` | explicit compatible IDs | explicit compatible IDs |

Codex does not support `claude-dev-kit`. `--all-compatible` excludes it; naming an unsupported
module explicitly fails before apply. Module selection comes from the emitted manifest and its
host-compatibility declarations.

## Bootstrap from one public product checkout

Clone the public product once and run the bootstrap from that checkout's root. That same directory
is the full distribution used by the bootstrap and by offline `hpp setup --source`; do not create a
second copy for the `--source` argument.

```bash
git clone https://github.com/rusharlabs/house-party-protocol.git
cd house-party-protocol
```

From the full versioned checkout, Windows PowerShell:

```powershell
python -I -B scripts/setup_hpp.py --target <project> --host claude-code
python -I -B scripts/setup_hpp.py --target <project> --host claude-code --apply
python -I -B scripts/setup_hpp.py --target <project> --host claude-code --all-compatible
```

From the full versioned checkout, macOS terminal:

```bash
python3 -I -B scripts/setup_hpp.py --target <project> --host codex
python3 -I -B scripts/setup_hpp.py --target <project> --host codex --apply
python3 -I -B scripts/setup_hpp.py --target <project> --host codex --all-compatible
```

The first command is a pure offline plan and writes nothing. Review its complete output. The second
repeats the same options and adds `--apply`; it creates `.hpp/venv`, installs hash-pinned bootstrap
wheels and the local CLI, then applies the reviewed module plan. Bootstrap apply needs access to
PyPI. Setup never invokes a model CLI or activates a host. It does not trigger paid model inference
or ask for model credentials. Invoke the generated launcher with `-I -B`; it preserves the
calling application's Python environment and routes HPP commands through the managed project
runtime.

Bootstrap also keeps trusted ownership metadata in a user-local state directory outside the
consumer project: `~/.hpp-setup-state` by default (Windows: the same directory name under the
user's home directory). The advanced `--state-dir <path>` option selects a different location; it
must remain outside the consumer project. This metadata inventories all managed environment files
and validates the launcher. The bootstrap refuses a project-forged receipt, an unowned existing
environment, or a changed launcher/environment. If trusted state is missing, do not adopt or erase
the project files automatically: stop and preserve them for reconciliation.

The setup process builds the CLI in a unique retained copy under `.hpp/bootstrap-build-<unique>`;
the versioned release checkout stays unchanged and old retained data is not deleted automatically.
Keep `.hpp/venv`, `.hpp/bin`, `.hpp/runtime-router.json`, `.hpp/run.py`, receipts, runner data and
retained build copies local; do not commit them to the consumer project.

Use the launcher to run HPP and the host with the prepared environment. On Windows PowerShell:

```powershell
python -I -B .hpp/run.py hpp doctor
python -I -B .hpp/run.py host --version
```

On macOS Terminal, use `python3`:

```bash
python3 -I -B .hpp/run.py hpp doctor
python3 -I -B .hpp/run.py host --version
```

Native Claude Code plugin activation is a separate explicit action after reviewing the plan. On
Windows, run `python -I -B .hpp/run.py activate`; on macOS, run
`python3 -I -B .hpp/run.py activate`. It rechecks distribution and module checksums and invokes the host's plugin commands without an
automatic yes flag. Restart Claude Code and verify plugin and hook state in the host before
reporting activation. On Codex, runtime and skills are copied locally; hooks remain off and no
separate plugin installation is required just to copy those skills.

## Offline setup interface

The offline CLI accepts this same checkout as `--source`; its version must match the installed CLI.
Run it from the product checkout root with the target project outside that checkout. It plans by
default; `--apply` performs the reviewed batch. The command grammar is:

```text
hpp setup --source <same public product checkout> --target <project> --host claude-code|codex
          [--bundle reliable-coding | --all-compatible | --modules <ids>]
          [--apply] [--json]
```

Examples:

```bash
hpp setup --source . --target ../my-project --host claude-code
hpp setup --source . --target ../my-project --host claude-code --apply
hpp setup --source . --target ../my-project --host codex --all-compatible
hpp setup --source . --target ../my-project --host codex --modules kit-forge,operator-kit
```

Use one selection mode. With no selection flag, `reliable-coding` is the default. `--json` requests
machine-readable reporting; it does not skip the review/apply boundary. Build process arguments
from structured fields; never parse or execute shell command text printed by a plan.

## Plan and apply behavior

The plan should enumerate the selected modules, target files, project environment and pinned
dependencies, host-specific actions, and all remaining manual gates before the first write. Review
conflicts and existing configuration before applying. Existing instructions and host settings must
be preserved; the bootstrap must not change global Python packages, account state or operating
system configuration. A refusal, checksum mismatch, incompatible module or conflict should stop
before any affected write.

## Re-running and interruption

A rerun is accepted only when the source version, host, module selection, recorded artifacts and
managed profile still match the ownership receipts. A changed selection/version/artifact or edited
managed profile/file is refused for review; automatic upgrade or migration is not implemented. If
an abrupt interruption leaves no valid receipt, preserve the existing files for reconciliation;
the installer may not safely resume from an unrecorded state.

Apply must retain rollback information and report partial failure as partial. Resume only pending
steps after checking the live target; do not repeat writes that already succeeded. A final report
must separate:

- module files installed and integrity checked;
- runtime and skills copied;
- launchers/environment installed and interpreter path measured;
- host integration active, requiring a human action, refused, or not supported;
- optional integrations configured or still unconfigured.

## Host boundaries

Claude Code native plugin activation is the explicit human-run launcher command above and retains
that host's consent flow. The setup batch itself does not activate plugins or edit Claude
settings/hooks. Explicit-command modules are installed as files/commands and are not described as
native plugins.

On Codex, setup copies supported runtime and skills; HPP hooks stay off. Do not require a redundant
plugin installation just to copy skills that the module installer already copies. A file being
present is not proof that the host loaded it.

Never put credentials in generated files or logs. Installation of optional integration files does
not configure Supabase or another account.

## Verification status

This guide covers HPP 2.14.0 and later; earlier releases lack guided setup. Host activation remains
a separate, explicit human action. Commands use `python3` on macOS. Simulated host tests can verify
argument building; they do not prove host activation.

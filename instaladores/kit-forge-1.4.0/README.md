[English](README.md) · [Português](README.pt-BR.md)

# Kit Forge

The IP/PII gate + the kit assembler of this marketplace. It is not a kit to install in a
third-party project — it is the tool that **builds and verifies** the other kits
(including itself). `ip_pii_linter.py` (scans for internal client/infra names before
anything becomes public), `kit_assembler.py` (assembles a kit from a declarative manifest
+ the source, with `guard_origins` built in — aborts if the source changes mid-assembly),
`kit_doctor.py` (verify/install/registry — the single installation engine of the whole
marketplace, 6 stages), `wire_settings.py` (idempotent merge into `settings.local.json`),
`install_git_hook.py` (chains with someone else's `pre-commit`), and `tools/skill_lint.py`
(the linter that enforces the SKILL-CONTRACT on other kits' skills). A single exit
contract everywhere: `0 ok/no-op`, `1 warn`, `2 block`, `3 error`. No `--skip-lint` in any
tool — the IP/PII gate is always mandatory.

## Prerequisites + external APIs

| Requirement | Minimum version | Required? |
|---|---|---|
| Python | 3.8 | yes |
| PyYAML | any | yes — `kit_assembler.py`/`ip_pii_linter.py`/`wire_settings.py` parse manifest/ruleset/spec with it; the core function of these 3 tools depends on it |

External services: **none — stdlib + PyYAML, touches only the local filesystem.**

## Install as a plugin

This kit has no `.claude-plugin/plugin.json` (it is not consumed as a plugin — it is the
tool that builds/verifies the OTHER kits of the marketplace). Use it by copy.

## Install by copy

```bash
cp -r kit-forge-1.2.0 <seu-projeto>/kit-forge
cd <seu-projeto>
python kit-forge/kit_doctor.py install kit-forge --target . --human
#                                                     ^ plano, zero escrita
python kit-forge/kit_doctor.py install kit-forge --target . --apply
#                                                     ^ aplica de verdade
```

## What the installer detects

```
greenfield    → nenhum arquivo de config próprio (ip-ruleset.yaml é do NEGÓCIO que usa
                 o kit-forge, não deste kit — copie ip-ruleset.example.yaml e preencha)
em-andamento  → ip-ruleset.yaml customizado já presente (skip-exists, nunca sobrescrito)
re-run        → registry (~/.claude-kits/registry.json) marca re-run
```

## What is safe to run again

`wire_settings.py` is idempotent and byte-stable (running it twice does not duplicate). The
real `ip-ruleset.yaml` (with the client/port/domain names of YOUR business) is never
overwritten automatically by any tool here — only you edit it. `kit_assembler.py` always
assembles into a fresh output directory (it never writes over the kit already emitted to
production unless you point `--out` at it explicitly).

## Manual wiring

None — this kit has no hooks/plugin. It is a collection of command-line tools invoked on
demand (e.g. by a CI cron, or by hand before publishing a new kit).

## Configure the IP/PII ruleset (the real step before assembling any kit)

```bash
cp ip-ruleset.example.yaml ip-ruleset.yaml
# editar ip-ruleset.yaml com os nomes de cliente/infra REAIS do seu negócio
python ip_pii_linter.py --self-test
```
`ip-ruleset.example.yaml` is neutral (it can be part of a distributed kit); the real
`ip-ruleset.yaml` (with real names) **never** leaves in an assembled kit — it stays out of
the manifest of any `kit_assembler.py`.

## Proof / acceptance (real output, executed)

```bash
python kit_doctor.py --self-test
```
```
self-test OK — verify (ok/warn/corrupt/error) + compat posicional + install (6 estágios:
detect/prereqs/profile/configure/wire/smoke, plan-first/--apply, --answers, re-run) +
registry (kit+target, sem duplicar) + render_plan
```
<!-- executado: 2026-07-11 · exit=0 -->

```bash
python ip_pii_linter.py --self-test
```
```
self-test OK — 17 findings em 16 regras distintas
```
<!-- executado: 2026-07-11 · exit=0 -->

```bash
python wire_settings.py --self-test
```
```
self-test OK — wire idempotente, conflito sem --force preservado, --force sobrescreve, --undo byte-idêntico
```
<!-- executado: 2026-07-11 · exit=0 -->

## Undo

```
- Cópia: remover a pasta kit-forge/ do projeto (nada mais para reverter — sem
  wiring/settings tocados por este kit em si)
- ip-ruleset.yaml: apagar manualmente se não quiser mais rodar o lint neste negócio
```

## Extended documentation

- `INSTALL-CONTRACT.md` (marketplace root) — the complete contract of the 6 stages of
  `kit_doctor.py install`, the `kit.install.yaml` schema, the cross-host seam.
- `../../SKILL-CONTRACT.md` (marketplace root) — the `SKILL.md` contract enforced by
  `tools/skill_lint.py`.
- `../../docs/UX-INSTALL-JOURNEY.md` — the installation journey told in the conversation
  (greenfield/in-progress/re-run/failure), from the point of view of the agent guiding the
  human.

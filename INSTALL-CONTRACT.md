[English](INSTALL-CONTRACT.md) · [Português](INSTALL-CONTRACT.pt-BR.md)

# INSTALL-CONTRACT — the installation contract of every kit in this marketplace

> **Version:** 1.0.0 · **Enforcement:** `instaladores/kit-forge/kit_doctor.py` (subcommand `install`)
> **Sibling of:** `SKILL-CONTRACT.md` (the SKILL.md contract) — this one is the contract of the INSTALLER.

## Principle

```
INSTALAR UM KIT NUNCA É UMA SURPRESA.
O operador vê o PLANO antes de qualquer escrita acontecer, sabe se o projeto-alvo
é NOVO ou JÁ TEM CONFIG, e só uma segunda invocação explícita (--apply) age.
Nenhum instalador deste marketplace bloqueia esperando input() de terminal —
o "sim" do humano é a re-invocação com --apply, não um prompt.
```

(Installing a kit is never a surprise. The operator sees the PLAN before any write happens,
knows whether the target project is NEW or ALREADY HAS CONFIG, and only a second, explicit
invocation (`--apply`) acts. No installer in this marketplace blocks waiting for terminal
`input()` — the human's "yes" is the re-invocation with `--apply`, not a prompt.)

Every kit in this marketplace that has installation steps (file copy, profile, wiring of
hooks/statusLine) is installed by the SAME engine (`kit_doctor.py install`), which reads a
declarative per-kit manifest (`install/kit.install.yaml`). The engine never carries hardcoded
knowledge of a specific kit — all kit-specific knowledge lives in the YAML.

## The 6 stages (fixed order)

```
detect → prereqs → profile → configure → wire-suggest → smoke
```

### 1. `detect` (new — always first, read-only)
Classifies the target project (`--target`, default cwd) into one of three categories:

| Classification | Signals |
|---|---|
| `greenfield` | no `.claude/`, no `settings.json`/`settings.local.json`, git with few or no commits, no real profile present |
| `in-progress` | `.claude/` exists, `settings*.json` has hooks/statusLine in use, a real profile (`operator-profile.yaml`/`rollup.yaml`/etc.) present, non-trivial git history |
| `re-run` | this `kit_dir` already has an entry in `~/.claude-kits/registry.json` pointing at this `--target` |

Output: `{"stage": "detect", "classification": "...", "signals": {...}, "existing_config": [list of already-configured items that will be preserved]}`. Never writes anything.

### 2. `prereqs` (existing — python/PyYAML/dependencies declared in `requires:`)

### 3. `profile` (existing — copies `*.example.*` → real; **never overwrites** if the target already exists with content different from the generated one; `skip-exists` is reported, not silent)

### 4. `configure` (new)
Reads `questions:` from `kit.install.yaml`. Without `--answers`: uses the `default` of each question and lists, in the plan, which questions remain pending a human decision. With `--answers <file.json|yaml>`: loads, validates against the schema (type/options), applies; absent fields = default.

### 5. `wire-suggest` (existing — NEVER writes settings/hooks; only detects what exists — `.claude-plugin/plugin.json`, `install/wiring-spec.yaml`, `README.md`/guide — and suggests the textual command. Mutating settings/hooks remains a human gate, always.)

### 6. `smoke` (existing — runs `--self-test` on every `.py` of the kit; scripts without that support are `skipped`, not a failure)

## The plan → apply flow (Confirm step)

```
$ python kit_doctor.py install <kit_dir> --target <project_dir>
   → roda os 6 estágios em MODO PLANO (nenhuma escrita real acontece)
   → imprime o plano completo (JSON) e SAI COM EXIT 0
   → o humano lê o plano (na conversa, se for um agente operando)

$ python kit_doctor.py install <kit_dir> --target <project_dir> --apply
   → roda os 6 estágios de verdade, aplicando profile/registrando install
   → wire-suggest continua NUNCA escrevendo (gate humano é sempre manual)
```

(First invocation: runs the 6 stages in PLAN MODE — no real write happens — prints the full
plan as JSON and EXITS 0; the human reads the plan, in the conversation if an agent is
operating. Second invocation, with `--apply`: runs the 6 stages for real, applying the profile
and registering the install; `wire-suggest` still NEVER writes — the human gate is always
manual.)

There is no (and there must not be a) blocking `input()` anywhere in this mechanism — the real
operator of this ecosystem is frequently an agent acting on behalf of a human; a stdin prompt
hangs exactly in that usage context. The "Confirm" is the double invocation (plan, then
`--apply`), auditable and reproducible.

## Schema of `install/kit.install.yaml`

```yaml
kit: <nome-do-kit>
requires:
  python: ">=3.9"          # opcional, default ">=3.8"
  pyyaml: true              # opcional, default false
  external_services: []     # ex.: supabase-pack declara [{name: Supabase, via: MCP, credenciais: "URL + anon key"}]
                             # REGRA DURA: nunca declarar ANTHROPIC_API_KEY aqui — regime é assinatura/quota, não pay-per-use
questions:                  # opcional — consumido pelo estágio `configure` E pelo modo --interview de wizards
  - id: <identificador>
    prompt: "<pergunta em pt-BR>"
    type: choice|bool|string
    options: [...]           # se type: choice
    default: <valor>
verification:               # comandos de aceite pós-install (cada um deve ser executável e sair 0)
  - "python scripts/algo.py --self-test"
hosts:
  claude-code:               # host nativo de plugin — ver seção "Seam de host" abaixo
    plugin: true|false        # tem .claude-plugin/plugin.json?
    wiring_spec: install/wiring-spec.yaml   # se houver wiring de hooks/statusLine
    manual_gates: [statusLine]              # o que NUNCA pode ser auto-armado (sempre gate humano)
  codex:                     # host por cópia explícita, sem ativação automática de hooks
    plugin: false
    agents: AGENTS.md
    skills_path: .agents/skills
    runtime_path: .agents/hpp/<nome-do-kit>
    manual_gates: [hooks]
docs: README.md
```

Reading the block: `requires.python` is optional (default `">=3.8"`); `requires.pyyaml` is
optional (default `false`); `requires.external_services` names each external service (e.g. the
supabase-pack declares `[{name: Supabase, via: MCP, credenciais: "URL + anon key"}]`) — HARD RULE:
never declare `ANTHROPIC_API_KEY` here, the regime is subscription/quota, not pay-per-use;
`questions` is optional and is consumed by the `configure` stage AND by the `--interview` mode of
wizards, `options` applying when `type: choice`; `verification` lists post-install acceptance
commands, each of which must be executable and exit 0; under `hosts`, `claude-code` is the native
plugin host (see "Host seam" below) — `plugin` says whether `.claude-plugin/plugin.json` exists,
`wiring_spec` points at the hooks/statusLine wiring if there is one, and `manual_gates` lists what
must NEVER be auto-armed (always a human gate); `codex` is the host installed by explicit copy,
with no automatic activation of hooks.

## Question schema (`questions:`)

The same schema is consumed in two places: by the `configure` stage of `kit_doctor.py`, and by
the `--interview` mode of standalone wizards (e.g. `agent-framework-wizard/wizard.py`). This
guarantees that "answering questions" has ONE format, not two.

```json
{"id": "lane_mode", "prompt": "Projeto roda multi-sessão (lanes) ou solo?", "type": "choice", "options": ["solo", "lanes"], "default": "solo"}
```

## Host seam (Claude Code + Codex CLI)

The engine keeps an internal dict with the two proven hosts:

```python
HOSTS = {
    "claude-code": {
        "settings_path": ".claude/settings.local.json",
        "plugin_manifest": ".claude-plugin/plugin.json",
        "path_token": "${CLAUDE_PLUGIN_ROOT}",
    },
    "codex": {
        "agents_file": "AGENTS.md",
        "skills_path": ".agents/skills",
        "runtime_path": ".agents/hpp",
        "path_token": "{{HPP_CODEX_RUNTIME}}",
    },
}
```

NEW sources (`kit.install.yaml`, `install/wiring-spec.yaml`) use the neutral token
`{{KIT_ROOT}}`, resolved to the `path_token` of the active host (`--host`; the default follows
`claude-code`). EXISTING uses of `${CLAUDE_PLUGIN_ROOT}` in `hooks.json`/scripts are NOT
rewritten — they are native Claude Code artefacts and remain so. On Codex, `codex_skills.py`
copies the runtime to `.agents/hpp/<kit>` and generates namespaced skills under
`.agents/skills/`, substituting the token only in those copies. Hooks stay off. A future
Cursor/Gemini adapter = a new entry in `HOSTS` + a `hosts.<new>:` block in the YAMLs — zero
change to the 6 stages. Do not invent a fake "neutral" event vocabulary: events such as
`Stop`/`PreCompact` are Claude Code concepts and are declared under `hosts.claude-code`,
honestly.

## Exit codes (`kit_doctor.py install`)

| Exit | Meaning |
|---|---|
| 0 | plan printed (default mode) OR applied successfully (`--apply`) |
| 1 | some `smoke` stage failed |
| 3 | usage error (kit_dir/target missing) |

## Checklist before considering a kit "really installable"

```
[ ] install/kit.install.yaml existe e valida contra o schema acima
[ ] requires.external_services declarado (mesmo que vazio) — nunca ANTHROPIC_API_KEY
[ ] questions (se houver) têm default sensato — instalar sem --answers nunca trava
[ ] verification: tem ≥1 comando real, executável, que sai 0 quando tudo está ok
[ ] hosts.claude-code.manual_gates lista tudo que NUNCA deve ser auto-armado
[ ] hosts.codex declara AGENTS.md, .agents/skills, runtime namespaced e hooks em manual_gates
[ ] README.md segue o INSTALL-GUIDE-TEMPLATE.md
[ ] kit_doctor.py install <kit> --target <dir-virgem> roda sem erro (plano)
[ ] kit_doctor.py install <kit> --target <dir-virgem> --apply roda sem erro (aplica)
[ ] rodar de novo (--apply) sobre o MESMO dir → detect classifica re-run, nada duplica
```

The ten boxes, in order: `install/kit.install.yaml` exists and validates against the schema
above; `requires.external_services` is declared (even if empty) — never `ANTHROPIC_API_KEY`;
`questions` (if any) have a sensible default — installing without `--answers` never hangs;
`verification:` has ≥1 real, executable command that exits 0 when everything is fine;
`hosts.claude-code.manual_gates` lists everything that must NEVER be auto-armed; `hosts.codex`
declares `AGENTS.md`, `.agents/skills`, a namespaced runtime and hooks in `manual_gates`;
`README.md` follows `INSTALL-GUIDE-TEMPLATE.md`; `kit_doctor.py install <kit> --target <dir-virgem>`
runs without error (plan); the same with `--apply` runs without error (applies); running `--apply`
again over the SAME dir → `detect` classifies `re-run`, nothing is duplicated.

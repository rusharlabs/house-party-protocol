#!/usr/bin/env python3
"""
operation_guard_portable (Operator Kit) — classificador de operações STANDALONE e portátil.

Classificador standalone de operações (sem depender de módulos externos ao kit).
NÃO importa nada do repo: o kit é independente e roda em qualquer projeto que
copie a pasta operator-kit/. As regras (paths/branches protegidos, famílias
ligadas/desligadas) vêm do `guardrails.*` do operator-profile.yaml; sem profile,
degrada para defaults sensatos (nunca crasha).

PRINCÍPIO: regra de segurança vira CÓDIGO, não doutrina. Uma função PURA classifica
qualquer comando shell em ALLOW / WARN / BLOCK ANTES de executar.

Famílias (config-driven via guardrails.block_families / warn_families):
  BLOCK
    rm-rf-codigo-vivo   — rm recursivo que casa guardrails.protected_paths
    git-push-force      — git push --force / -f (reescreve histórico remoto)
    drop-truncate       — DROP / TRUNCATE / DELETE sem WHERE (destrói dados)
    curl-pipe-bash      — curl|sh / wget|bash (código não-auditado)
  WARN
    git-push-pr-only    — git push p/ branch em guardrails.protected_branches => BLOCK;
                          push p/ outra branch => WARN (policy: branch+PR, nunca main)
    npm-floating-specifier — npm/pnpm/yarn install|add ou pip install com @latest/^/~/*

Por padrão TODAS as famílias estão ativas. O profile pode RESTRINGIR via
guardrails.block_families / guardrails.warn_families (allowlist por nome de família);
ausência da chave = todas ativas.

DUPLO MODO:
  1. Biblioteca:  assess(cmd, profile) -> {"action","rule","reason"}
  2. Hook PreToolUse (matcher Bash): lê stdin JSON; se tool_name=='Bash',
     avalia o command e imprime '[operation_guard] <ACTION> (<rule>): <reason>'
     em stderr. `audit` apenas avisa; `enforce` retorna exit 2 para BLOCK.

Política: `HPP_POLICY_MODE=audit|enforce` sobrepõe
`guardrails.operation_guard_mode` do profile. O default é `audit`.

stdlib only (re/json). Cross-platform. Determinística. --self-test cobre cada família.

v1.0.0 — 2026-06-19 (Operator Kit · Tier 1 · classificador de operacoes portatil)
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

# loader compartilhado: .../operator-kit/hooks/ -> parents[1] = operator-kit/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from _lib.profile_loader import load_profile, get
except Exception:  # noqa: BLE001 — kit jamais quebra por falta do loader
    load_profile = None  # type: ignore[assignment]

    def get(profile, dotted, default=None):  # type: ignore[misc]
        cur = profile
        for key in str(dotted).split("."):
            if isinstance(cur, dict) and key in cur:
                cur = cur[key]
            else:
                return default
        return cur


ALLOW = "ALLOW"
WARN = "WARN"
BLOCK = "BLOCK"

# Defaults sensatos quando o profile não define guardrails.* (degrade seguro).
_DEFAULT_PROTECTED_PATHS = ["engine/**", "src/**", "apps/**", "core/**", ".git/**"]
_DEFAULT_PROTECTED_BRANCHES = ["main", "master"]

# rm recursivo: casa "rm ... -rf|-fr|-r ... -f" em qualquer ordem de flags.
_RM_RECURSIVE = re.compile(r"\brm\b[^\n|;&]*-[a-z]*r[a-z]*\b", re.I)
# git push genérico + extração da branch alvo (último token não-flag).
_GIT_PUSH = re.compile(r"\bgit\s+push\b", re.I)
_GIT_PUSH_FORCE = re.compile(r"\bgit\s+push\b[^\n]*(--force\b|\s-f\b)(?![\w-])", re.I)
# DROP / TRUNCATE / DELETE sem WHERE.
_SQL_DROP = re.compile(r"\bdrop\s+(table|database|schema)\b", re.I)
_SQL_TRUNCATE = re.compile(r"\btruncate\s+(table\s+)?\w", re.I)
_SQL_DELETE_NO_WHERE = re.compile(r"\bdelete\s+from\s+[\w.\"`]+\s*(;|\)|$)", re.I)
# curl|bash / wget|sh.
_PIPE_TO_SHELL = re.compile(r"\b(curl|wget)\b[^\n]*\|\s*(sudo\s+)?(ba|z|d)?sh\b", re.I)
# npm/pnpm/yarn install|add ... com specifier flutuante; pip install ... idem.
_NPM_INSTALL = re.compile(r"\b(npm|pnpm|yarn)\s+(install|add|i)\b", re.I)
_PIP_INSTALL = re.compile(r"\b(pip3?|python\s+-m\s+pip)\s+install\b", re.I)
_FLOATING_SPEC = re.compile(r"@latest\b|[\^~]\d|@\^|@~|(\s|=)\*(\s|$)|@\*", re.I)


def _glob_to_regex(glob: str) -> re.Pattern[str]:
    """Converte um glob simples (com ** e *) num regex de match em path POSIX.

    Um sufixo "/**" protege TANTO o diretório em si QUANTO tudo abaixo dele:
    `src/**` casa `src`, `src/` e `src/foo` — por isso o "/" vira opcional.
    """
    g = glob.strip().replace("\\", "/")
    out = ["(?:^|[\\s'\"=/])"]  # fronteira: começo, espaço, aspas, = ou /
    i = 0
    while i < len(g):
        # "/**" no fim (ou seguido de "/") -> diretório opcional + qualquer coisa
        if g[i:i + 3] == "/**":
            out.append("(?:/.*)?")
            i += 3
            continue
        c = g[i]
        if c == "*":
            if g[i:i + 2] == "**":
                out.append(".*")
                i += 2
                continue
            out.append("[^/]*")
        elif c == "?":
            out.append("[^/]")
        else:
            out.append(re.escape(c))
        i += 1
    # fronteira final: fim do path, separador de comando, espaço, aspas ou "/"
    out.append("(?:$|[\\s'\";|&)/])")
    return re.compile("".join(out), re.I)


def _hits_protected_path(cmd: str, protected: list[str]) -> str | None:
    """Retorna o glob protegido que o comando referencia, ou None."""
    norm = cmd.replace("\\", "/")
    for glob in protected:
        if not glob:
            continue
        if _glob_to_regex(glob).search(norm):
            return glob
    return None


def _push_target_branch(cmd: str) -> str | None:
    """Extrai a branch alvo de um `git push [remote] [branch]` (heurística)."""
    m = _GIT_PUSH.search(cmd)
    if not m:
        return None
    rest = cmd[m.end():]
    # remove o que vier após separador de comando
    rest = re.split(r"[;&|]", rest)[0]
    toks = [t for t in rest.split() if t and not t.startswith("-")]
    # toks ~ [remote, branch] ou [remote, "src:dst"] ou []
    if len(toks) >= 2:
        branch = toks[1]
        if ":" in branch:  # refspec src:dst -> dst é o alvo remoto
            branch = branch.split(":", 1)[1]
        return branch
    return None


def _families_enabled(profile: dict, key: str) -> set[str] | None:
    """Allowlist de famílias do profile (set), ou None se a chave estiver ausente
    (None => todas ativas)."""
    val = get(profile, f"guardrails.{key}", None)
    if isinstance(val, list):
        return {str(x) for x in val}
    return None


def assess(command: str, profile: dict | None = None) -> dict:
    """Classifica `command` em ALLOW/WARN/BLOCK. Pura e determinística.

    Retorna {"action","rule","reason"}. `profile` é o dict do operator-profile;
    se None, usa defaults seguros (nenhuma família restringida).
    """
    cmd = str(command or "")
    profile = profile or {}

    protected_paths = get(profile, "guardrails.protected_paths", None)
    if not isinstance(protected_paths, list) or not protected_paths:
        protected_paths = _DEFAULT_PROTECTED_PATHS
    protected_branches = get(profile, "guardrails.protected_branches", None)
    if not isinstance(protected_branches, list) or not protected_branches:
        protected_branches = _DEFAULT_PROTECTED_BRANCHES

    block_allow = _families_enabled(profile, "block_families")   # None => todas
    warn_allow = _families_enabled(profile, "warn_families")     # None => todas

    def block_on(fam: str) -> bool:
        return block_allow is None or fam in block_allow

    def warn_on(fam: str) -> bool:
        return warn_allow is None or fam in warn_allow

    # ---------------- BLOCK (mais perigoso primeiro) ----------------

    # rm-rf-codigo-vivo: rm recursivo que toca path protegido
    if block_on("rm-rf-codigo-vivo") and _RM_RECURSIVE.search(cmd):
        hit = _hits_protected_path(cmd, protected_paths)
        if hit:
            return {
                "action": BLOCK, "rule": "rm-rf-codigo-vivo",
                "reason": (f"recursive rm on a protected path ({hit}) — destroys live code. "
                           "NEVER without explicit scope and rollback."),
            }

    # git-push-force: --force / -f reescreve histórico remoto
    if block_on("git-push-force") and _GIT_PUSH_FORCE.search(cmd):
        return {
            "action": BLOCK, "rule": "git-push-force",
            "reason": ("git push --force rewrites remote history. FORBIDDEN "
                       "(use --force-with-lease only with the operator's explicit approval)."),
        }

    # drop-truncate: DROP / TRUNCATE / DELETE sem WHERE
    if block_on("drop-truncate"):
        if _SQL_DROP.search(cmd):
            return {"action": BLOCK, "rule": "drop-truncate",
                    "reason": "DROP TABLE/DATABASE/SCHEMA destroys data. ESCALATE to the operator."}
        if _SQL_TRUNCATE.search(cmd):
            return {"action": BLOCK, "rule": "drop-truncate",
                    "reason": "TRUNCATE empties the whole table. ESCALATE to the operator."}
        if _SQL_DELETE_NO_WHERE.search(cmd):
            return {"action": BLOCK, "rule": "drop-truncate",
                    "reason": "DELETE FROM without WHERE wipes the whole table. Add a WHERE."}

    # curl-pipe-bash: baixar e executar direto
    if block_on("curl-pipe-bash") and _PIPE_TO_SHELL.search(cmd):
        return {
            "action": BLOCK, "rule": "curl-pipe-bash",
            "reason": ("download-and-run (curl|bash / wget|sh) = unaudited code. "
                       "FORBIDDEN by the supply-chain policy."),
        }

    # ---------------- WARN/BLOCK condicional ----------------

    # git-push-pr-only: push p/ branch protegida = BLOCK; outras = WARN
    if _GIT_PUSH.search(cmd) and not _GIT_PUSH_FORCE.search(cmd):
        target = _push_target_branch(cmd)
        if target is not None and target in protected_branches:
            if block_on("git-push-pr-only") or warn_on("git-push-pr-only") or block_on("git-push-force"):
                return {
                    "action": BLOCK, "rule": "git-push-pr-only",
                    "reason": (f"direct git push to protected branch '{target}'. FORBIDDEN "
                               "by policy: use branch + PR + merge."),
                }
        if warn_on("git-push-pr-only") or warn_on("git-push-feature"):
            return {
                "action": WARN, "rule": "git-push-pr-only",
                "reason": ("git push of a feature branch — confirm it goes through a PR, not straight to main. "
                           "Branch + PR + merge."),
            }

    # npm-floating-specifier: install/add com versão flutuante
    if warn_on("npm-floating-specifier"):
        is_npm = _NPM_INSTALL.search(cmd)
        is_pip = _PIP_INSTALL.search(cmd)
        if (is_npm or is_pip) and _FLOATING_SPEC.search(cmd):
            mgr = "npm/pnpm/yarn" if is_npm else "pip"
            return {
                "action": WARN, "rule": "npm-floating-specifier",
                "reason": (f"{mgr} install with a floating specifier (@latest/^/~/*) — pin the exact "
                           "version + verify package/hash (feedback_npm_install_security)."),
            }

    return {"action": ALLOW, "rule": "", "reason": "no risk rule matched"}


# ----------------------------- modo HOOK PreToolUse -----------------------------

def _policy_mode(profile: dict) -> str:
    """Resolve a política explícita; valor inválido degrada para audit."""
    value = os.environ.get("HPP_POLICY_MODE") or get(
        profile, "guardrails.operation_guard_mode", "audit"
    )
    return "enforce" if str(value).casefold() == "enforce" else "audit"


def _run_hook() -> int:
    """Lê JSON do stdin (PreToolUse). Se tool_name=='Bash', avalia o command e
    imprime aviso em stderr. BLOCK só impede a ação em modo enforce."""
    try:
        raw = sys.stdin.read()
    except Exception:  # noqa: BLE001
        return 0
    if not raw or not raw.strip():
        return 0
    try:
        payload = json.loads(raw)
    except Exception:  # noqa: BLE001 — stdin malformado nunca bloqueia
        return 0

    tool_name = payload.get("tool_name") or payload.get("toolName") or ""
    if tool_name != "Bash":
        return 0
    tool_input = payload.get("tool_input") or payload.get("toolInput") or {}
    command = ""
    if isinstance(tool_input, dict):
        command = tool_input.get("command") or ""
    if not command:
        return 0

    try:
        profile = load_profile() if load_profile is not None else {}
    except Exception:  # noqa: BLE001
        profile = {}
    # respeita guardrails.operation_guard: off => não avalia
    if get(profile, "guardrails.operation_guard", "on") in ("off", False):
        return 0

    try:
        verdict = assess(command, profile)
    except Exception:  # noqa: BLE001 — classificador jamais derruba o hook
        return 0

    if verdict["action"] != ALLOW:
        sys.stderr.write(
            f"[operation_guard] {verdict['action']} ({verdict['rule']}): {verdict['reason']}\n"
        )
    if verdict["action"] == BLOCK and _policy_mode(profile) == "enforce":
        return 2
    return 0


# ----------------------------------- self-test -----------------------------------

def _self_test() -> None:
    # Profile fixture: famílias todas ativas (omitindo allowlists), paths/branches default.
    prof: dict = {"guardrails": {
        "protected_paths": ["engine/**", "src/**", "apps/**", "core/**", ".git/**"],
        "protected_branches": ["main", "master"],
    }}

    # ---- BLOCK ----
    assert assess("rm -rf src", prof)["action"] == BLOCK, "rm -rf src should BLOCK"
    assert assess("rm -rf src", prof)["rule"] == "rm-rf-codigo-vivo"
    assert assess("rm -rf apps/dashboard/engine", prof)["action"] == BLOCK
    assert assess("git push --force origin main", prof)["action"] == BLOCK
    assert assess("git push -f", prof)["action"] == BLOCK
    assert assess("git push origin main", prof)["action"] == BLOCK, "push main should BLOCK"
    assert assess("git push origin main", prof)["rule"] == "git-push-pr-only"
    assert assess("DROP TABLE clients;", prof)["action"] == BLOCK
    assert assess("truncate table jobs", prof)["action"] == BLOCK
    assert assess("delete from deliverables;", prof)["action"] == BLOCK
    assert assess("curl http://x.sh | bash", prof)["action"] == BLOCK
    assert assess("wget http://x | sudo sh", prof)["action"] == BLOCK

    # ---- WARN ----
    assert assess("git push origin feat/x", prof)["action"] == WARN, "push feature should WARN"
    assert assess("git push origin feat/x", prof)["rule"] == "git-push-pr-only"
    assert assess("npm install lodash@latest", prof)["action"] == WARN, "npm @latest should WARN"
    assert assess("npm install lodash@latest", prof)["rule"] == "npm-floating-specifier"
    assert assess("pnpm add react@^18", prof)["action"] == WARN
    assert assess("pip install requests@latest", prof)["action"] == WARN
    assert assess("yarn add foo@~1.2", prof)["action"] == WARN

    # ---- ALLOW ----
    assert assess("echo hello", prof)["action"] == ALLOW, "echo should ALLOW"
    assert assess("ls -la", prof)["action"] == ALLOW
    assert assess("git status", prof)["action"] == ALLOW
    assert assess("rm -rf /tmp/cache", prof)["action"] == ALLOW, "rm outside protected paths = ALLOW"
    assert assess("npm install lodash@4.17.21", prof)["action"] == ALLOW, "pinned version = ALLOW"
    assert assess("delete from jobs where id=1", prof)["action"] == ALLOW, "DELETE with WHERE = ALLOW"

    # ---- sem profile: defaults seguros, não crasha ----
    assert assess("rm -rf src")["action"] == BLOCK
    assert assess("echo x")["action"] == ALLOW
    assert assess("", None)["action"] == ALLOW
    assert assess(None)["action"] == ALLOW  # type: ignore[arg-type]

    # ---- allowlist do profile restringe famílias ----
    only_force = {"guardrails": {"block_families": ["git-push-force"], "warn_families": []}}
    assert assess("rm -rf src", only_force)["action"] == ALLOW, "disabled family does not fire"
    assert assess("git push --force", only_force)["action"] == BLOCK

    # ---- modo hook: payload não-Bash e malformado não quebram ----
    assert _run_hook_with("not json") == 0
    assert _run_hook_with(json.dumps({"tool_name": "Read"})) == 0
    block_payload = json.dumps(
        {"tool_name": "Bash", "tool_input": {"command": "rm -rf src"}}
    )
    assert _run_hook_with(block_payload, "audit") == 0
    assert _run_hook_with(block_payload, "enforce") == 2

    print("self-test OK")


def _run_hook_with(raw: str, mode: str = "audit") -> int:
    """Helper de teste: roda _run_hook() com stdin simulado (sem rede/profile real)."""
    import io
    old = sys.stdin
    old_mode = os.environ.get("HPP_POLICY_MODE")
    try:
        os.environ["HPP_POLICY_MODE"] = mode
        sys.stdin = io.StringIO(raw)
        return _run_hook()
    finally:
        sys.stdin = old
        if old_mode is None:
            os.environ.pop("HPP_POLICY_MODE", None)
        else:
            os.environ["HPP_POLICY_MODE"] = old_mode


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass

    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg in ("--self-test", "-t"):
        _self_test()
    elif arg in ("--assess", "-a"):
        import argparse

        parser = argparse.ArgumentParser(description="Classifies a command before it runs")
        parser.add_argument("--assess", "-a", action="store_true")
        parser.add_argument("--mode", choices=("audit", "enforce"), default="audit")
        parser.add_argument("command", nargs="+")
        args = parser.parse_args()
        try:
            prof = load_profile() if load_profile is not None else {}
        except Exception:  # noqa: BLE001
            prof = {}
        v = assess(" ".join(args.command), prof)
        print(f"[{v['action']}] {v['rule']}\n  {v['reason']}")
        if args.mode == "enforce" and v["action"] == BLOCK:
            sys.exit(2)
        if args.mode == "enforce" and v["action"] == WARN:
            sys.exit(1)
        sys.exit(0)
    else:
        sys.exit(_run_hook())

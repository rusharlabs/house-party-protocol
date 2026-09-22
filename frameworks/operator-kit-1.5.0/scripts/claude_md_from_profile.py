#!/usr/bin/env python3
"""
claude_md_from_profile (Operator Kit) - generates the CLAUDE.md block from operator-profile.yaml.

CLAUDE.md is born from the MODEL, not from memory: it reads `operator-profile.yaml` and writes
four sections that teach any agent to operate THIS project - and to stay silent where the
decision is not its to make. The floor comes FIRST, by crossing fields, never by opinion: each
line comes from a field in the profile; if the field is not there, the line does not exist.

    ## WHAT YOU DO NOT DECIDE     <- autonomy - guardrails - loop.forbidden_boundaries
    ## WHERE THINGS LIVE          <- paths.*
    ## THE RULES OF DONE          <- verification.done_criteria - ladder
    ## THE FLOW                   <- concurrency - loop - autonomy.default

The script governs ONLY the block between the markers:

    <!-- operator-kit:claude-md:begin -->
    ...
    <!-- operator-kit:claude-md:end -->

What is outside the markers belongs to the person and is never touched. Inside, the last line
is the SIGNATURE (hash of the profile + date). If the block was hand-edited - the signature does
not match the content - the script REFUSES to overwrite, shows what would change, and stops.

Usage:
    python claude_md_from_profile.py                       # finds the profile, writes ./CLAUDE.md
    python claude_md_from_profile.py --profile p.yaml --out CLAUDE.md
    python claude_md_from_profile.py --dry-run             # prints the block, does not write
    python claude_md_from_profile.py --force               # overwrites a hand-edited block
    python claude_md_from_profile.py --self-test

Exit: 0 written or no-op - 1 hand-edited block, refused (use --force) -
      2 invalid usage/profile - 3 write refused by the machine (see INSTRUCOES-DO-CLAUDE.md)

# Why: none of the kits generated CLAUDE.md from a structured model - the operator's profile
# was read by scripts and never written for the agent to read. Generation is CODE, not prose:
# "every cited field exists" has to be true by construction, not by discipline.

stdlib + PyYAML. v1.0.0 — 2026-09-20 (Operator Kit · A14)
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from _lib.profile_loader import get as _loader_get  # type: ignore[import-not-found]
    from _lib.profile_loader import profile_path as find_profile
except Exception:  # noqa: BLE001 -- Why: without the loader, an explicit --profile keeps working; only automatic discovery falls back
    find_profile = None  # type: ignore[assignment]
    _loader_get = None  # type: ignore[assignment]

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

BEGIN = "<!-- operator-kit:claude-md:begin -->"
END = "<!-- operator-kit:claude-md:end -->"
FALLBACK_NAME = "INSTRUCOES-DO-CLAUDE.md"  # literal: this is the name the person will look for

# Why: the signature is what separates "generated" (can overwrite) from "hand-edited" (cannot).
# It carries the hash of the generated CONTENT, so any edit inside the block invalidates it.
# Why: the signature points to the skill (which resolves the path via ${CLAUDE_PLUGIN_ROOT}), not
# to `python <script>`: the script lives in the plugin, not at the project root, and bare
# `python` does not exist on macOS.
_ASSINATURA = "*Bloco gerado do `{perfil}` em {data} - assinatura {hash} - para regerar: skill `claude-md-from-profile` (operator-kit; script {script}). Se editar este bloco a mao, a assinatura deixa de bater e eu paro de sobrescrever.*"


def _get(d: dict, dotted: str, default=None):
    """Dotted read THROUGH the kit loader, which carries the dual read of the profile keys
    renamed in 2.6.0 (legacy `projeto` -> `project`, and so on). Falls back to a plain walk only
    when the loader is not importable — the same degradation `find_profile` already has, and the
    only case in which a profile written before the rename would read as empty here."""
    if _loader_get is not None:
        return _loader_get(d, dotted, default)
    cur = d
    for k in dotted.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def _lista(x) -> list:
    return [str(i) for i in x] if isinstance(x, list) else []


# --------------------------------------------------------------------------
# the four sections - each line traces back to ONE field in the profile
# --------------------------------------------------------------------------
def secao_nao_decide(p: dict) -> list:
    """The floor. Never comes out empty: if nothing crossed, one honest line."""
    out = []
    by_action = _get(p, "autonomy.by_action", {}) or {}
    if isinstance(by_action, dict):
        for acao, nivel in by_action.items():
            try:
                n = int(nivel)
            except (TypeError, ValueError):
                continue
            if n <= 1:
                out.append(f"- **{acao}**: level {n} (`autonomy.by_action.{acao}`). You PROPOSE, you do not execute. The person authorises.")
    for pth in _lista(_get(p, "autonomy.sensitive_paths_auto_gate")):
        out.append(f"- Any write to `{pth}` falls into an automatic human gate (`autonomy.sensitive_paths_auto_gate`). Do not route around it.")
    for pth in _lista(_get(p, "guardrails.protected_paths")):
        out.append(f"- `{pth}` is protected (`guardrails.protected_paths`): do not delete, do not move, do not mass-rewrite.")
    for br in _lista(_get(p, "guardrails.protected_branches")):
        out.append(f"- Branch `{br}` is protected (`guardrails.protected_branches`): never push directly, never force.")
    for fam in _lista(_get(p, "guardrails.block_families")):
        out.append(f"- The command family **{fam}** is BLOCKED (`guardrails.block_families`). Urgency is not an exception.")
    ext = _lista(_get(p, "guardrails.external_send_tools"))
    if ext:
        out.append(f"- Sending outside ({', '.join(ext)}) is a human gate (`guardrails.external_send_tools`): prepare it, show it, do not fire it.")
    for fr in _lista(_get(p, "loop.forbidden_boundaries")):
        out.append(f"- Forbidden loop boundary: `{fr}` (`loop.forbidden_boundaries`). If the task seems to require this, the task is wrong.")
    for sc in _lista(_get(p, "loop.stop_conditions")):
        out.append(f"- STOP condition: **{sc}** (`loop.stop_conditions`). Stopping here is success, not failure.")
    if not out:
        out.append("- This profile has not recorded any limit yet. That means it is early, not that you are free. Ask before any irreversible action.")
    return out


def secao_onde_moram(p: dict) -> list:
    paths = _get(p, "paths", {}) or {}
    if not isinstance(paths, dict) or not paths:
        return ["- `paths` is not filled in the profile. Do not assume any location - ask."]
    out = []
    for k, v in paths.items():
        if v is None or str(v).strip() == "":
            out.append(f"- **{k}**: *not configured* (`paths.{k}` empty). Do not invent a location.")
        else:
            out.append(f"- **{k}** lives at `{v}` (`paths.{k}`).")
    return out


def secao_regras_do_pronto(p: dict) -> list:
    out = []
    crit = _get(p, "verification.done_criteria", {}) or {}
    if isinstance(crit, dict) and crit:
        out.append("\"Done\" only exists after the gate. By task type (`verification.done_criteria`):")
        for tipo, cmds in crit.items():
            cmds_l = _lista(cmds)
            if cmds_l:
                out.append(f"- **{tipo}**: " + " | ".join(f"`{c}`" for c in cmds_l))
            else:
                out.append(f"- **{tipo}**: *no criterion* - an empty list NEVER passes by omission (done_gate).")
    else:
        out.append("- `verification.done_criteria` is not filled. With no criterion, no task is \"done\" - the done_gate rejects an empty list by design.")
    ladder = _get(p, "verification.ladder", {}) or {}
    obrig = _lista(_get(p, "verification.ladder_required"))
    minimo = _get(p, "verification.ladder_min_score")
    if isinstance(ladder, dict) and ladder:
        out.append(f"- Verification ladder (`verification.ladder`): {', '.join(str(k) for k in ladder.keys())}."
                   + (f" Mandatory: {', '.join(obrig)}." if obrig else "")
                   + (f" Minimum score: {minimo}." if minimo is not None else ""))
    out.append("- Three states, and only one is forbidden: **DONE** | **PARCIAL-DECLARADO** (say what is missing) | ~~silent partial~~. If you did not finish, declare it - silence is not a state.")
    return out


def secao_fluxo(p: dict) -> list:
    out = []
    default = _get(p, "autonomy.default")
    inten = _get(p, "intensity.default")
    if default is not None:
        out.append(f"- Default autonomy: **level {default}** (`autonomy.default`)" + (f", intensity **{inten}** (`intensity.default`)." if inten else "."))
    teto = _get(p, "concurrency.max_agents")
    wave = _get(p, "concurrency.wave_size")
    fb = _get(p, "concurrency.fallback")
    if teto is not None or wave is not None:
        out.append(f"- Parallelism: cap **{teto}** (`concurrency.max_agents`), waves of **{wave}** (`concurrency.wave_size`)" + (f", fallback `{fb}`." if fb else "."))
    charter = _get(p, "loop.charter")
    work = _get(p, "loop.work_list")
    if charter or work:
        out.append(f"- The loop reads the charter at `{charter}` and the queue at `{work}` (`loop.charter` / `loop.work_list`).")
    gat = _lista(_get(p, "loop.authorization_triggers"))
    if gat:
        out.append(f"- BROAD execution only when the person says one of these: {', '.join(repr(g) for g in gat)} (`loop.authorization_triggers`). Otherwise, one action at a time.")
    kw = _lista(_get(p, "guardrails.approval_keywords"))
    if kw:
        out.append(f"- Words that count as human approval: {', '.join(repr(k) for k in kw)} (`guardrails.approval_keywords`). Nothing else counts.")
    if not out:
        out.append("- The profile configured neither autonomy nor concurrency. Operate at the lowest level until someone fills `autonomy.default`.")
    return out


def gerar_bloco(perfil: dict, perfil_nome: str, script_nome: str, hoje: str | None = None) -> str:
    hoje = hoje or _dt.date.today().isoformat()
    exemplo = bool(perfil.get("_exemplo")) or _get(perfil, "project") in ("nome-do-projeto", "", None)
    linhas = [BEGIN]
    if exemplo:
        linhas.append("> WARNING: THIS BLOCK WAS GENERATED FROM AN EXAMPLE PROFILE. The project below does not exist. Fill in `operator-profile.yaml` and regenerate.")
    linhas += [
        f"# How to operate `{_get(perfil, 'project', '?')}`",
        "",
        "This block was generated from `operator-profile.yaml`. It says what you may do, what",
        "you do not decide, and where things live. **Read the floor before the inventories.**",
        "",
        "## WHAT YOU DO NOT DECIDE", *secao_nao_decide(perfil), "",
        "## WHERE THINGS LIVE", *secao_onde_moram(perfil), "",
        "## THE RULES OF DONE", *secao_regras_do_pronto(perfil), "",
        "## THE FLOW", *secao_fluxo(perfil), "",
    ]
    corpo = "\n".join(linhas)
    h = hashlib.sha256(corpo.encode("utf-8")).hexdigest()[:12]
    linhas.append(_ASSINATURA.format(perfil=perfil_nome, data=hoje, hash=h, script=script_nome))
    linhas.append(END)
    return "\n".join(linhas) + "\n"


# --------------------------------------------------------------------------
# the block inside the file
# --------------------------------------------------------------------------
def _extrai_bloco(texto: str):
    i = texto.find(BEGIN)
    j = texto.find(END)
    if i < 0 or j < 0 or j < i:
        return None
    return texto[i: j + len(END) + (1 if texto[j + len(END): j + len(END) + 1] == "\n" else 0)]


def _bloco_foi_editado(bloco: str) -> bool:
    """True if the signature does not match the content - someone edited inside the block."""
    linhas = bloco.rstrip("\n").split("\n")
    if len(linhas) < 3 or linhas[-1] != END:
        return True
    assin = linhas[-2]
    if "assinatura " not in assin:
        return True
    h_decl = assin.split("assinatura ")[1].split(" ")[0]
    corpo = "\n".join(linhas[:-2])
    return hashlib.sha256(corpo.encode("utf-8")).hexdigest()[:12] != h_decl


def aplicar(alvo: Path, bloco: str, force: bool = False) -> tuple:
    """Returns (status, final_text). status: new | replaced | no-op | refused."""
    if not alvo.exists():
        return "new", bloco
    bruto = io.open(alvo, encoding="utf-8", newline="").read()
    # Why: a CLAUDE.md saved in CRLF would make the signature never match (the hash is of the LF
    # text) and the file would be "hand-edited" forever. Work is done in LF, returned in the original EOL.
    eol = "\r\n" if "\r\n" in bruto else "\n"
    atual = bruto.replace("\r\n", "\n")
    antigo = _extrai_bloco(atual)
    if antigo is None:
        # the block goes at the TOP: the floor is the first thing the AI reads, before the person's text
        status, texto = "new", bloco + "\n" + atual
    elif _sem_assinatura_igual(antigo, bloco):
        return "no-op", bruto
    elif _bloco_foi_editado(antigo) and not force:
        return "refused", bruto
    else:
        status, texto = "replaced", atual.replace(antigo, bloco, 1)
    return status, (texto.replace("\n", eol) if eol != "\n" else texto)


def _sem_assinatura_igual(a: str, b: str) -> bool:
    """Compares the blocks IGNORING the signature line (which carries the date)."""
    def miolo(x):
        ls = x.rstrip("\n").split("\n")
        return "\n".join(l for l in ls if "assinatura " not in l)
    return miolo(a) == miolo(b)


def gravar(alvo: Path, texto: str) -> Path:
    """Writes; if the machine refuses, falls back to the literal fallback name and returns IT."""
    try:
        with open(alvo, "w", encoding="utf-8", newline="") as fh:
            fh.write(texto)
        return alvo
    except OSError:
        # Why: some machines silently refuse to write CLAUDE.md. Do not work around it via shell
        # or any other path - the refusal is the machine's protection. The fallback name is LITERAL:
        # it is what the person will look for.
        fb = alvo.parent / FALLBACK_NAME
        cab = ("<!-- This file should be called CLAUDE.md. Writing under that name was\n"
               "     refused by this machine. RENAME IT TO CLAUDE.md and delete this block -->\n\n")
        with open(fb, "w", encoding="utf-8", newline="") as fh:
            fh.write(cab + texto)
        return fb


# --------------------------------------------------------------------------
def _self_test() -> None:
    import tempfile
    assert yaml is not None, "PyYAML is required for the self-test"
    exemplo = Path(__file__).resolve().parents[1] / "profile.example.yaml"
    perfil = yaml.safe_load(io.open(exemplo, encoding="utf-8"))
    bloco = gerar_bloco(perfil, "profile.example.yaml", "x.py", hoje="2026-09-20")

    # form
    assert "{{" not in bloco, "placeholder not substituted"
    for sec in ("## WHAT YOU DO NOT DECIDE", "## WHERE THINGS LIVE", "## THE RULES OF DONE", "## THE FLOW"):
        assert sec in bloco, sec
    assert bloco.index("## WHAT YOU DO NOT DECIDE") < bloco.index("## WHERE THINGS LIVE"), "the floor comes FIRST"
    assert "EXAMPLE PROFILE" in bloco, "profile.example must be stamped as an example"
    assert bloco.startswith(BEGIN) and bloco.rstrip("\n").endswith(END)

    # every cited field exists: each cited `key.sub` is in the profile
    import re
    for ref in set(re.findall(r"\(`([a-z_]+(?:\.[a-z_]+)+)`", bloco)):
        assert _get(perfil, ref, "__MISSING__") != "__MISSING__", f"cited a field that does not exist: {ref}"

    # floor never empty, even with an empty profile
    vazio = gerar_bloco({"project": "x"}, "p.yaml", "x.py", hoje="2026-09-20")
    assert "has not recorded any limit yet" in vazio
    assert "is not filled" in vazio

    with tempfile.TemporaryDirectory() as td:
        alvo = Path(td) / "CLAUDE.md"
        # 1st time: new
        st, txt = aplicar(alvo, bloco); assert st == "new"; gravar(alvo, txt)
        # 2nd time: no-op (idempotent)
        st, _ = aplicar(alvo, bloco); assert st == "no-op", st
        # file with the person's content OUTSIDE the block: preserved
        alvo.write_text("# My project\n\nmy notes\n", encoding="utf-8")
        st, txt = aplicar(alvo, bloco)
        assert st == "new" and txt.startswith(BEGIN) and txt.rstrip("\r\n").endswith("my notes"), "block on TOP, the person's text WHOLE below"
        gravar(alvo, txt)
        assert "my notes" in alvo.read_text(encoding="utf-8")
        # profile changes -> block replaced, and what's outside stays there
        bloco2 = gerar_bloco({**perfil, "project": "other"}, "p.yaml", "x.py", hoje="2026-09-20")
        st, txt = aplicar(alvo, bloco2); assert st == "replaced"; gravar(alvo, txt)
        t = alvo.read_text(encoding="utf-8")
        assert "my notes" in t and "other" in t and t.count(BEGIN) == 1
        # HAND edit inside the block -> refused; --force -> replaces
        t2 = t.replace("## THE FLOW", "## THE FLOW (I edited this)")
        alvo.write_text(t2, encoding="utf-8")
        st, _ = aplicar(alvo, bloco2); assert st == "refused", "a hand edit must be refused"
        st, txt = aplicar(alvo, bloco2, force=True); assert st == "replaced"
        # the instrument discriminates: an intact block is NOT "edited"
        assert not _bloco_foi_editado(bloco2)
        assert _bloco_foi_editado(bloco2.replace("## THE FLOW", "## THE FLOW x"))
        # write refusal -> literal fallback
        ro = Path(td) / "ro"; ro.mkdir()
        alvo_ro = ro / "CLAUDE.md"; alvo_ro.mkdir()   # a DIRECTORY with that name: open() fails
        dest = gravar(alvo_ro, bloco)
        assert dest.name == FALLBACK_NAME and dest.exists()
        assert "RENAME IT TO CLAUDE.md" in dest.read_text(encoding="utf-8")
    print("self-test OK")


def main(argv) -> int:
    if argv and argv[0] in ("--self-test", "-t"):
        _self_test()
        return 0
    dry = "--dry-run" in argv
    force = "--force" in argv
    args = [a for a in argv if a not in ("--dry-run", "--force")]
    prof_path = None
    out_path = Path("CLAUDE.md")
    i = 0
    while i < len(args):
        if args[i] == "--profile" and i + 1 < len(args):
            prof_path = Path(args[i + 1]); i += 2; continue
        if args[i] == "--out" and i + 1 < len(args):
            out_path = Path(args[i + 1]); i += 2; continue
        print(__doc__.split("Usage:")[1].split("Exit:")[0], file=sys.stderr)
        return 2

    if yaml is None:
        print("claude_md_from_profile: PyYAML missing — install pyyaml", file=sys.stderr)
        return 2
    if prof_path is None:
        if find_profile is None:
            print("claude_md_from_profile: pass --profile <operator-profile.yaml>", file=sys.stderr)
            return 2
        prof_path = find_profile()
        if prof_path is None:
            print("claude_md_from_profile: no operator-profile.yaml found from the cwd. "
                  "CLAUDE.md is born from the profile, not the other way round — create the profile first "
                  "(cp profile.example.yaml operator-profile.yaml).", file=sys.stderr)
            return 2
    prof_path = Path(prof_path)
    try:
        perfil = yaml.safe_load(io.open(prof_path, encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001 -- Why: broken YAML becomes exit 2 with the parser's message, never a half-generated block
        print(f"claude_md_from_profile: unreadable profile ({exc}). I do not fix it blind — correct the YAML.", file=sys.stderr)
        return 2
    if not isinstance(perfil, dict):
        print("claude_md_from_profile: the profile is not a YAML mapping", file=sys.stderr)
        return 2

    bloco = gerar_bloco(perfil, prof_path.name, Path(__file__).name)
    if dry:
        sys.stdout.write(bloco)
        return 0

    status, texto = aplicar(out_path, bloco, force=force)
    if status == "refused":
        print(f"claude_md_from_profile: the block in {out_path} was HAND-EDITED (the signature does not match). "
              "Not overwriting. See what would change with --dry-run; to overwrite anyway, --force.",
              file=sys.stderr)
        return 1
    if status == "no-op":
        print(f"claude_md_from_profile: {out_path} is already up to date with {prof_path.name} (no-op)")
        return 0
    dest = gravar(out_path, texto)
    if dest.name == FALLBACK_NAME:
        print(f"claude_md_from_profile: this machine would not let me write {out_path.name}. The content is "
              f"complete in {dest} — rename it to {out_path.name} and you are done.", file=sys.stderr)
        return 3
    print(f"claude_md_from_profile: block {status} in {dest} (source: {prof_path.name})")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    sys.exit(main(sys.argv[1:]))

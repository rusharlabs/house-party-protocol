#!/usr/bin/env python3
"""
kit_doctor — verifica, instala e rastreia kits deste marketplace. 3 subcomandos.

verify   (v1.0.0 — PRESERVADO, chamada posicional continua funcionando): recalcula
          sha256 de cada arquivo em CHECKSUMS.txt e compara.
install  (v3.0.0 — 6 estágios): detect -> prereqs -> profile -> configure ->
          wire-sugerido -> smoke. Ver INSTALL-CONTRACT.md (raiz do marketplace) para
          o contrato completo. Genérico o bastante pra rodar em QUALQUER kit deste
          marketplace porque se apoia no contrato uniforme `--self-test` da casa
          (SKILL-CONTRACT C4) + no manifesto declarativo `install/kit.install.yaml`
          por-kit — NUNCA conhecimento kit-específico hardcoded aqui.
          PLAN-FIRST: por padrão só mostra o plano (zero escrita); `--apply` age de
          verdade. NUNCA auto-arma settings/hooks (gate humano, sempre).
registry (v2.0.0): grava/lista instalações em ~/.claude-kits/registry.json, agora
          chaveado por (kit_dir, target_dir) — o mesmo kit pode ser instalado em
          vários projetos-alvo sem colidir.

Uso:
    python kit_doctor.py <kit_dir> [--json out.json]        # forma antiga = verify
    python kit_doctor.py verify <kit_dir> [--json out.json]
    python kit_doctor.py install --kit <kit_dir> [--target <dir>] [--host claude-code|codex]
                                  [--answers <file>] [--apply] [--human]
                                  [--registry-path <path>] [--no-register]
    python kit_doctor.py registry [--registry-path <path>]
    python kit_doctor.py --self-test

Exit (verify): 0 íntegro · 1 íntegro com extras (WARN) · 2 corrupção · 3 erro.
Exit (install): 0 plano impresso OU aplicado com sucesso · 1 smoke falhou · 3 erro.
Exit (registry): 0 sempre (list/register nunca falham de forma bloqueante).

stdlib only (+ PyYAML opcional p/ kit.install.yaml/--answers *.yaml).
v3.0.0 — 2026-07-11 (kit-forge · 6 estágios: detect+configure novos, plan-first+--apply,
seam de host HOSTS, compatibilidade posicional preservada, regressão zero em verify/registry)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

_IGNORE_NAMES = {"CHECKSUMS.txt", ".lint-report.json"}
# Why (bytecode counted as extras): `verify` ran right after a module's own smoke tests and came back `warn`
# (exit 1) because the `__pycache__/*.pyc` they left behind counted as `extras`. Bytecode and the
# pytest cache are never part of the package — the assembler excludes them and the zip gate forbids
# them — so they cannot be a finding about the package. Same set the assembler uses.
_IGNORE_DIRS = {"__pycache__", ".pytest_cache"}
_IGNORE_SUFFIXES = {".pyc", ".pyo"}
_SUBCOMMANDS = ("verify", "install", "registry", "marketplace")
_DEFAULT_REGISTRY = Path.home() / ".claude-kits" / "registry.json"

# Seam de host (cross-host, ver INSTALL-CONTRACT.md).
HOSTS = {
    "claude-code": {
        "settings_path": ".claude/settings.local.json",
        "plugin_manifest": ".claude-plugin/plugin.json",
        "path_token": "${CLAUDE_PLUGIN_ROOT}",
    },
    "codex": {
        "settings_path": None,
        "plugin_manifest": None,
        "path_token": ".agents/hpp/<kit>",
        "skills_path": ".agents/skills",
    },
}
_DEFAULT_HOST = "claude-code"


def _brt_now_iso() -> str:
    return datetime.now(timezone(timedelta(hours=-3))).strftime("%Y-%m-%dT%H:%M:%S-03:00")


# ---------------------------------------------------------------------------
# VERIFY (preservado de v1.0.0 — mesma lógica, mesmo contrato)
# ---------------------------------------------------------------------------

def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def parse_checksums(text: str) -> dict:
    entries = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("  ", 1)
        if len(parts) != 2:
            parts = line.split(" ", 1)
        if len(parts) != 2:
            continue
        digest, relpath = parts
        entries[relpath.strip()] = digest.strip()
    return entries


def _relpath_seguro(kit_dir: Path, relpath: str) -> bool:
    """Entrada do inventário tem de apontar para DENTRO do kit: relativa, sem `..`, sem drive/raiz.

    # Why: `kit_dir / relpath` aceita `../fora` e caminho absoluto (o join descarta a base),
    # e o verificador passava a atestar um arquivo que nao esta no kit.
    """
    if not relpath:
        return False
    pw = PureWindowsPath(relpath)
    if pw.drive or pw.root or PurePosixPath(relpath).is_absolute():
        return False
    if ".." in relpath.replace("\\", "/").split("/"):
        return False
    try:
        (kit_dir / relpath).resolve().relative_to(kit_dir.resolve())
    except ValueError:
        return False
    return True


def check_kit(kit_dir: Path) -> dict:
    checksums_path = kit_dir / "CHECKSUMS.txt"
    if not checksums_path.exists():
        return {"status": "error", "errors": [f"CHECKSUMS.txt missing in {kit_dir}"]}

    expected = parse_checksums(checksums_path.read_text(encoding="utf-8"))
    if not expected:
        # Why: inventario vazio nao atesta arquivo nenhum — tratar como integro faria o
        # verificador aprovar um kit cujo CHECKSUMS.txt foi esvaziado.
        return {
            "status": "corrupt", "kit_dir": str(kit_dir), "total_tracked": 0,
            "mismatches": [], "missing": [], "extras": [], "unsafe_paths": [],
            "errors": ["CHECKSUMS.txt with no entries — an empty inventory attests to nothing"],
        }
    mismatches = []
    missing = []
    unsafe = []
    for relpath, expected_hash in expected.items():
        if not _relpath_seguro(kit_dir, relpath):
            unsafe.append(relpath)
            continue
        f = kit_dir / relpath
        if not f.exists():
            missing.append(relpath)
            continue
        actual_hash = _sha256(f)
        if actual_hash != expected_hash:
            mismatches.append({"file": relpath, "expected": expected_hash, "actual": actual_hash})

    actual_files = set()
    for p in kit_dir.rglob("*"):
        if not p.is_file() or p.name in _IGNORE_NAMES or p.suffix in _IGNORE_SUFFIXES:
            continue
        rel = p.relative_to(kit_dir)
        if _IGNORE_DIRS.intersection(rel.parts[:-1]):
            continue
        actual_files.add(rel.as_posix())
    extras = sorted(actual_files - set(expected.keys()))

    if mismatches or missing or unsafe:
        status = "corrupt"
    elif extras:
        status = "warn"
    else:
        status = "ok"

    return {
        "status": status,
        "kit_dir": str(kit_dir),
        "total_tracked": len(expected),
        "mismatches": mismatches,
        "missing": missing,
        "extras": extras,
        "unsafe_paths": unsafe,
        "errors": [f"path outside the kit in the inventory: {p}" for p in unsafe],
    }


def _verify_exit(report: dict) -> int:
    status = report.get("status")
    if status == "error":
        return 3
    if status == "corrupt":
        return 2
    if status == "warn":
        return 1
    return 0


# ---------------------------------------------------------------------------
# MARKETPLACE — o contrato do CATÁLOGO publicado (o `verify` acima olha UM kit)
# ---------------------------------------------------------------------------
# Why: o gate de versão do kit_assembler compara plugin.json x manifesto YAML — o lado da
# fábrica. Ninguém comparava marketplace.json x plugin.json, que é o lado que o usuário lê
# no `/plugin install <kit>@<marketplace>`. Um fecha o buraco de baixo; este fecha o de cima.

_MARKETPLACE_REL = Path(".claude-plugin") / "marketplace.json"


def check_marketplace(root: Path) -> dict:
    """Valida o contrato de um marketplace publicado. 4 modos de falha, todos medidos.

    O manifesto canônico é `<root>/.claude-plugin/marketplace.json` — provado em
    2026-09-03 contra os dois marketplaces REAIS instalados nesta máquina
    (claude-plugins-official, thedotmack): os dois o têm ali, nenhum na raiz. Os
    `source` relativos resolvem a partir da RAIZ do marketplace, não de dentro do
    `.claude-plugin/` (o oficial usa `./plugins/<x>` e o diretório está na raiz).
    """
    root = Path(root)
    rel: dict = {
        "tool": "kit_doctor.marketplace",
        "root": str(root),
        "checked_at": _brt_now_iso(),
        "manifest": None,
        "plugins": 0,
        "achados": [],
        "status": "ok",
    }

    def _achado(code: str, detalhe: str, severidade: str = "fail") -> None:
        rel["achados"].append({"code": code, "detalhe": detalhe, "severidade": severidade})

    if not root.is_dir():
        rel["status"] = "error"
        _achado("raiz-nao-existe", f"{root} is not a directory")
        return rel

    canonico = root / _MARKETPLACE_REL
    na_raiz = root / "marketplace.json"

    if not canonico.exists():
        rel["status"] = "fail"
        onde = "at the root only" if na_raiz.exists() else "nowhere"
        _achado(
            "manifesto-fora-do-lugar",
            f"{_MARKETPLACE_REL.as_posix()} missing ({onde}) — "
            "`/plugin marketplace add` cannot find the catalogue",
        )
        return rel

    rel["manifest"] = str(canonico)
    try:
        doc = json.loads(canonico.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:  # noqa: BLE001 — o erro vira achado, não silêncio
        rel["status"] = "error"
        _achado("manifesto-ilegivel", f"{canonico}: {e}")
        return rel

    # Modo 4 — duas cópias do mesmo manifesto que já não são a mesma coisa.
    # A cópia IDÊNTICA passa de propósito: é o estado real do marketplace hoje.
    if na_raiz.exists() and _sha256(na_raiz) != _sha256(canonico):
        _achado(
            "copia-da-raiz-derivou",
            f"the root marketplace.json diverges from {_MARKETPLACE_REL.as_posix()} "
            "— two sources of truth for the same catalogue",
        )

    plugins = doc.get("plugins") or []
    rel["plugins"] = len(plugins)
    if not plugins:
        _achado("catalogo-vazio", "the manifest declares no plugin at all")

    for entry in plugins:
        nome = entry.get("name", "<unnamed>")
        source = entry.get("source")
        if not isinstance(source, str):
            continue  # source remoto (git-subdir etc.) — não é nosso para resolver
        alvo = (root / source).resolve()
        if not alvo.is_dir():
            _achado("source-nao-resolve", f"{nome}: source `{source}` does not exist")
            continue
        pj = alvo / ".claude-plugin" / "plugin.json"
        if not pj.exists():
            # Why: no catálogo oficial da Anthropic (set/2026), 14 das 291 entradas (os `*-lsp`) são
            # dirs só com LICENSE+README — a metadata inteira mora na entrada do marketplace. Reprovar
            # isso reprovaria a implementação de referência em 4,8%, e gate que grita com inocente é
            # desligado antes de um dia estar certo. WARN: não dá para cruzar a versão.
            _achado(
                "kit-sem-plugin-json",
                f"{nome}: {source} has no .claude-plugin/plugin.json — version not cross-checkable",
                severidade="warn",
            )
            continue
        try:
            v_kit = json.loads(pj.read_text(encoding="utf-8")).get("version")
        except (OSError, json.JSONDecodeError) as e:  # noqa: BLE001
            _achado("plugin-json-ilegivel", f"{nome}: {e}")
            continue
        # Why: `version` é OPCIONAL na entrada — só 14 das 291 entradas do marketplace oficial da
        # Anthropic o declaram (set/2026). Comparar `None != "1.2.1"` reprovaria o catálogo
        # inteiro. Quem não declara não pode divergir: ali o plugin.json é a fonte única.
        v_mk = entry.get("version")
        if v_mk is not None and v_mk != v_kit:
            _achado(
                "versao-divergente",
                f"{nome}: the catalogue says {v_mk} and the plugin.json says {v_kit}",
            )

    if rel["status"] == "ok" and rel["achados"]:
        rel["status"] = "fail" if any(a["severidade"] == "fail" for a in rel["achados"]) else "warn"
    return rel


def _marketplace_exit(rel: dict) -> int:
    """Mesma convenção do `verify`: 0 ok · 1 warn · 2 quebra de contrato · 3 erro."""
    status = rel.get("status")
    if status == "error":
        return 3
    if status == "fail":
        return 2
    return 1 if status == "warn" else 0


# ---------------------------------------------------------------------------
# INSTALL — 6 estágios: detect -> prereqs -> profile -> configure -> wire-sugerido -> smoke
# ---------------------------------------------------------------------------

def _load_kit_install_yaml(kit_dir: Path) -> dict:
    p = kit_dir / "install" / "kit.install.yaml"
    if yaml is None or not p.exists():
        return {}
    try:
        return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001 — manifesto malformado degrada pra {} (nao quebra o instalador)
        return {}


def stage_detect(kit_dir: Path, target_dir: Path, registry_path: Path) -> dict:
    """Classifica o projeto-alvo: greenfield / in-progress / re-run. SEMPRE read-only —
    não escreve nada. `kit_dir` = onde o kit vive; `target_dir` = raiz do projeto onde
    ele está sendo instalado (podem ser o mesmo diretório)."""
    signals: dict = {}
    existing_config: list = []

    claude_dir = target_dir / ".claude"
    signals["claude_dir_exists"] = claude_dir.is_dir()

    settings_occupied = False
    for name in ("settings.json", "settings.local.json"):
        sp = claude_dir / name
        if sp.exists():
            try:
                data = json.loads(sp.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                data = {}
            if isinstance(data, dict) and (data.get("statusLine") or data.get("hooks")):
                settings_occupied = True
                existing_config.append(f".claude/{name}: statusLine/hooks already configured")
    signals["settings_occupied"] = settings_occupied

    profile_real_found = False
    for example in sorted(kit_dir.glob("*.example.*")):
        target_name = example.name.replace(".example.", ".")
        if (kit_dir / target_name).exists():
            profile_real_found = True
            existing_config.append(f"{target_name} present (customized)")
    signals["profile_real_found"] = profile_real_found

    commit_count = 0
    try:
        proc = subprocess.run(
            ["git", "-C", str(target_dir), "rev-list", "--count", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        if proc.returncode == 0:
            commit_count = int((proc.stdout or "0").strip() or "0")
    except Exception:  # noqa: BLE001
        pass
    signals["git_commit_count"] = commit_count

    reg = _load_registry(registry_path)
    is_rerun = any(
        i.get("kit_dir") == str(kit_dir.resolve()) and i.get("target_dir") == str(target_dir.resolve())
        for i in reg.get("installs", [])
    )

    if is_rerun:
        classification = "re-run"
    elif signals["claude_dir_exists"] or settings_occupied or profile_real_found or commit_count > 3:
        classification = "in-progress"
    else:
        classification = "greenfield"

    return {
        "stage": "detect", "status": "ok", "classification": classification,
        "signals": signals, "existing_config": existing_config,
    }


def stage_prereqs(kit_dir: Path) -> dict:
    checks = {"python3": sys.version_info >= (3, 8)}
    if yaml is not None:
        checks["pyyaml"] = True
    else:
        checks["pyyaml"] = any(kit_dir.rglob("*.yaml")) is False  # só exige se o kit usa yaml
    ok = all(checks.values())
    return {"stage": "prereqs", "status": "ok" if ok else "warn", "checks": checks}


_PROFILE_LOADER_NAMES_RE = re.compile(r"^_NAMES\s*=\s*\(\s*['\"]([^'\"]+)['\"]", re.MULTILINE)
_PROFILE_SCAN_SUFFIXES = {".py", ".md", ".yaml", ".yml", ".json", ".sh"}


def _loader_profile_name(kit_dir: Path) -> str | None:
    """First entry of `_NAMES` in the module's `_lib/profile_loader.py`, if it declares one.

    # Why: the stage turned `profile.example.yaml` into `profile.yaml`, but modules such as
    # operator-kit / health-kit / gotcha-memory
    # read ONLY the names in `_NAMES = ("operator-profile.yaml", ...)` of their vendored loader —
    # the installed profile was silently ignored and every mechanism ran on defaults. Read by
    # regex, never imported: the loader is another module's code and importing would run it.
    """
    loader = kit_dir / "_lib" / "profile_loader.py"
    if not loader.is_file():
        return None
    try:
        m = _PROFILE_LOADER_NAMES_RE.search(loader.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return None
    return m.group(1) if m else None


def _target_is_referenced(kit_dir: Path, target_name: str, example: Path) -> bool:
    """True when some file of the module (outside the example itself) names `target_name`."""
    for path in kit_dir.rglob("*"):
        if path == example or not path.is_file() or path.suffix not in _PROFILE_SCAN_SUFFIXES:
            continue
        if any(part in _IGNORE_DIRS for part in path.relative_to(kit_dir).parts):
            continue
        try:
            if target_name in path.read_text(encoding="utf-8", errors="replace"):
                return True
        except OSError:
            continue
    return False


def profile_examples(kit_dir: Path) -> list:
    """`(example, target_name, reason)` for every seed the profile stage should offer.

    Root `*.example.*` -> name minus `.example` (v3.0.0 behaviour), except that
    `profile.example.<ext>` takes the loader's `_NAMES[0]` when the module vendors a
    `_lib/profile_loader.py`. `templates/*.example.*` are offered too — but only when the module
    names the target somewhere (a template nobody reads is a schema example, not config).

    # Why: `templates/` was outside the glob — lane-kit keeps its only seed,
    # `lanes.example.yaml`, there, so the stage copied nothing and the README had to
    # tell the operator to `cp` it by hand. The reference check keeps `lane-registry.example.json`
    # (runtime-state example, referenced by no file) from landing in the target as a dead file.
    """
    loader_name = _loader_profile_name(kit_dir)
    offers = []
    for example in sorted(kit_dir.glob("*.example.*")):
        target_name = example.name.replace(".example.", ".")
        reason = "root"
        if loader_name and example.name.split(".example.")[0] == "profile":
            target_name, reason = loader_name, "loader _NAMES"
        offers.append((example, target_name, reason))
    templates = kit_dir / "templates"
    if templates.is_dir():
        for example in sorted(templates.glob("*.example.*")):
            target_name = example.name.replace(".example.", ".")
            if _target_is_referenced(kit_dir, target_name, example):
                offers.append((example, target_name, "templates (referenced)"))
            else:
                offers.append((example, None, "templates (unreferenced)"))
    return offers


def stage_profile(kit_dir: Path, target_dir: Path, dry_run: bool, host: str) -> dict:
    """Discovers the module's `*.example.*` seeds (root and `templates/`, see
    `profile_examples`) and offers to copy each one under the name the module's loader reads
    (never overwriting an existing target — same spirit as wire_settings.py: never overwrite
    someone else's config by default)."""
    actions = []
    for example, target_name, reason in profile_examples(kit_dir):
        rel = example.relative_to(kit_dir).as_posix()
        if target_name is None:
            actions.append({"file": rel, "action": "skip-unreferenced", "target": None, "reason": reason})
            continue
        target = target_dir / target_name
        if target.exists():
            actions.append({"file": rel, "action": "skip-exists", "target": target_name, "reason": reason})
            continue
        if dry_run:
            actions.append({"file": rel, "action": "would-copy", "target": target_name, "reason": reason})
        else:
            target.write_bytes(example.read_bytes())
            actions.append({"file": rel, "action": "copied", "target": target_name, "reason": reason})
    codex_report = None
    status = "ok"
    if host == "codex":
        generator = Path(__file__).resolve().parent / "tools" / "codex_skills.py"
        cmd = [
            sys.executable, "-X", "utf8", str(generator),
            "--kit", str(kit_dir.resolve()), "--target", str(target_dir.resolve()),
        ]
        if not dry_run:
            cmd.append("--apply")
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        try:
            codex_report = json.loads(proc.stdout)
        except json.JSONDecodeError:
            codex_report = {"status": "error", "detail": (proc.stdout + proc.stderr)[-500:]}
        if proc.returncode == 1:
            status = "warn"  # o gerador copiou, mas deixou algo de fora e listou (ex.: links ignorados)
        elif proc.returncode != 0:
            status = "fail"
    return {"stage": "profile", "status": status, "actions": actions, "codex": codex_report}


def stage_configure(kit_dir: Path, answers_path: str | None) -> dict:
    """Lê questions: de install/kit.install.yaml. Sem --answers, resolve com os
    defaults e lista quais perguntas ficaram pendentes de decisão humana."""
    manifest = _load_kit_install_yaml(kit_dir)
    questions = manifest.get("questions") or []

    answers: dict = {}
    if answers_path:
        p = Path(answers_path)
        if p.exists():
            try:
                text = p.read_text(encoding="utf-8")
                if p.suffix in (".yaml", ".yml") and yaml is not None:
                    answers = yaml.safe_load(text) or {}
                else:
                    answers = json.loads(text) if text.strip() else {}
            except Exception:  # noqa: BLE001
                answers = {}

    resolved = {}
    pending_defaults = []
    for q in questions:
        qid = q.get("id")
        if qid is None:
            continue
        if qid in answers:
            resolved[qid] = answers[qid]
        else:
            resolved[qid] = q.get("default")
            pending_defaults.append(qid)

    return {
        "stage": "configure", "status": "ok",
        "questions_total": len(questions), "resolved": resolved, "pending_defaults": pending_defaults,
    }


def stage_wire_suggest(kit_dir: Path, host: str) -> dict:
    """NUNCA auto-arma settings/hooks — só detecta os caminhos disponíveis e sugere.
    Mutar settings.json/settings.local.json é gate humano nesta doutrina."""
    suggestions = []
    if host == "codex":
        suggestions.append({
            "path": "codex",
            "action": "skills copied to .agents/skills; runtime under .agents/hpp; AGENTS.md read by Codex",
        })
        suggestions.append({
            "path": "hooks",
            "action": "Claude Code hooks are not activated in Codex; run scripts and gates explicitly",
        })
        return {"stage": "wire-sugerido", "status": "ok", "suggestions": suggestions}
    plugin_json = kit_dir / ".claude-plugin" / "plugin.json"
    if plugin_json.exists():
        suggestions.append({
            "path": "plugin",
            "action": "/plugin marketplace add . && /plugin install <name>@<marketplace>",
        })
    wiring = kit_dir / "install" / "wiring.settings.jsonc"
    if wiring.exists():
        suggestions.append({
            "path": "manual",
            "action": f"paste the block from {wiring.relative_to(kit_dir)} into .claude/settings.local.json (human gate)",
        })
    for wire_tool in sorted(kit_dir.rglob("wire_settings.py")):
        spec = next(iter(kit_dir.rglob("wiring-spec.yaml")), None)
        if spec is not None:
            suggestions.append({
                "path": "programmatic",
                "action": f"python {wire_tool.relative_to(kit_dir)} --spec {spec.relative_to(kit_dir)} "
                          f"--settings .claude/settings.local.json (idempotent merge; --undo reverts; a human gate invokes it)",
            })
    settings_wire_md = next(iter(kit_dir.glob("SETTINGS-WIRE.md")), None)
    if settings_wire_md is not None:
        suggestions.append({"path": "doc", "action": f"follow {settings_wire_md.name}"})
    return {"stage": "wire-sugerido", "status": "ok", "suggestions": suggestions}


def stage_smoke(kit_dir: Path, timeout: float = 30) -> dict:
    """Roda --self-test em todo .py do kit que suporta o contrato uniforme da casa
    (SKILL-CONTRACT C4). Scripts sem --self-test são ignorados (não é falha). Sempre
    roda, mesmo em modo plano — não escreve nada no target, só valida que o kit
    funciona ANTES de comprometer a instalação. Self-test que estoura `timeout` conta
    como FALHA (status `timeout`), nunca como ok."""
    results = []
    kit_dir_abs = kit_dir.resolve()
    for py_file in sorted(kit_dir.rglob("*.py")):
        if "__pycache__" in py_file.parts:
            continue
        try:
            proc = subprocess.run(
                [sys.executable, "-B", "-X", "utf8", str(py_file.resolve()), "--self-test"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=timeout, cwd=str(kit_dir_abs),
            )
        except subprocess.TimeoutExpired:
            # Why: um self-test que nunca responde nao provou nada; caindo no except generico ele
            # virava `error`, que nao entrava na contagem de falhas, e o smoke aprovava o kit.
            results.append({
                "file": str(py_file.relative_to(kit_dir)), "status": "timeout",
                "detail": f"no answer in {timeout:g}s", "timeout_s": timeout,
            })
            continue
        except Exception as e:  # noqa: BLE001
            results.append({"file": str(py_file.relative_to(kit_dir)), "status": "error", "detail": str(e)})
            continue
        out = (proc.stdout or "") + (proc.stderr or "")
        low_out = out.lower()
        if ("usage:" in low_out or "uso:" in low_out) and proc.returncode != 0 and "self-test" not in low_out:
            # script não suporta --self-test (imprimiu uso genérico) -> não conta como falha
            results.append({"file": str(py_file.relative_to(kit_dir)), "status": "skipped"})
            continue
        results.append({
            "file": str(py_file.relative_to(kit_dir)),
            "status": "ok" if proc.returncode == 0 else "fail",
            "exit": proc.returncode,
        })
    failed = [r for r in results if r["status"] in ("fail", "timeout")]
    return {"stage": "smoke", "status": "fail" if failed else "ok", "results": results, "failed_count": len(failed)}


def run_install(
    kit_dir: Path, target_dir: Path, apply: bool, host: str,
    answers_path: str | None, registry_path: Path,
) -> dict:
    dry_run = not apply
    detect = stage_detect(kit_dir, target_dir, registry_path)
    prereqs = stage_prereqs(kit_dir)
    if host not in HOSTS:
        raise ValueError(f"unsupported host: {host}")
    profile = stage_profile(kit_dir, target_dir, dry_run, host)
    configure = stage_configure(kit_dir, answers_path)
    wire = stage_wire_suggest(kit_dir, host)
    smoke = stage_smoke(kit_dir)

    overall = "ok"
    if smoke["status"] == "fail" or profile["status"] == "fail":
        overall = "fail"
    elif prereqs["status"] == "warn":
        overall = "warn"

    return {
        "status": overall,
        "mode": "apply" if apply else "plan",
        "host": host,
        "kit_dir": str(kit_dir),
        "target_dir": str(target_dir),
        "stages": [detect, prereqs, profile, configure, wire, smoke],
    }


_RENDER_GLYPH = {"ok": "✓", "warn": "⚠", "fail": "⚠"}

_RENDER_CLASS_GLOSS = {
    "greenfield": "new project — no previous config detected",
    "in-progress": "project in progress — existing config detected (it will be preserved)",
    "re-run": "reinstall — this kit+target pair is already in the registry",
}


def render_plan(report: dict) -> str:
    """Formatação humana do plano (--human).
    A ESTRUTURA (ordem dos 6 estágios, campos do report) é contrato congelado
    (INSTALL-CONTRACT.md); esta função só apresenta — nunca decide, nunca escreve."""
    kit_name = Path(report["kit_dir"]).name
    is_plan = report["mode"] == "plan"

    lines = []
    if is_plan:
        lines.append(f"INSTALL PLAN — {kit_name}  (dry run: nothing was written)")
    else:
        lines.append(f"INSTALL APPLIED — {kit_name}  (--apply)")
    lines.append(f"  target: {report['target_dir']}")
    lines.append(f"  host:   {report['host']}")
    lines.append("")

    for stage in report["stages"]:
        name = stage["stage"]
        status = stage["status"]
        glyph = _RENDER_GLYPH.get(status, "?")
        suffix = "" if status == "ok" else f"  [{status.upper()}]"
        lines.append(f"  {glyph} {name}{suffix}")

        if name == "detect":
            cls = stage["classification"]
            gloss = _RENDER_CLASS_GLOSS.get(cls)
            lines.append(f"      classification={cls}" + (f" · {gloss}" if gloss else ""))
            for item in stage.get("existing_config", []):
                lines.append(f"      already there (will not be touched): {item}")

        if name == "prereqs" and status != "ok":
            for check, passed in stage.get("checks", {}).items():
                if not passed:
                    lines.append(f"      missing: {check}")

        if name == "profile":
            for action in stage.get("actions", []):
                verb = {
                    "would-copy": "would copy",
                    "copied": "copied",
                    "skip-exists": "already there, preserved",
                    "skip-unreferenced": "skipped (no file of the module reads that name)",
                }.get(action["action"], action["action"])
                arrow = f" -> {action['target']}" if action.get("target") else ""
                lines.append(f"      {verb}: {action['file']}{arrow}")

        if name == "configure" and stage.get("pending_defaults"):
            pend = ", ".join(str(q) for q in stage["pending_defaults"])
            lines.append(f"      unanswered (default assumed): {pend}")
            lines.append("      to answer for real: run again with --answers <file.json|yaml>")

        if name == "wire-sugerido":
            for s in stage.get("suggestions", []):
                lines.append(f"      option [{s['path']}]: {s['action']}")
            if stage.get("suggestions"):
                lines.append("      (none is executed automatically — touching settings/hooks is a human decision)")

        if name == "smoke":
            results = stage.get("results", [])
            ok_n = sum(1 for r in results if r["status"] == "ok")
            skip_n = sum(1 for r in results if r["status"] == "skipped")
            lines.append(f"      self-tests: {ok_n} ok · {skip_n} unsupported (skipped)")
            for r in results:
                if r["status"] == "fail":
                    lines.append(f"      ⚠ FAILED: {r['file']} (exit {r.get('exit')})")
                elif r["status"] == "timeout":
                    lines.append(f"      ⚠ TIMEOUT: {r['file']} ({r.get('detail', 'no answer')})")
                elif r["status"] == "error":
                    lines.append(f"      ⚠ ERROR: {r['file']} ({r.get('detail', 'no detail')})")

    lines.append("")
    if report["status"] == "fail":
        lines.append("RESULT: smoke FAILED — do not apply this kit before fixing the self-tests above.")
        lines.append("Once fixed, run the plan again to confirm before --apply.")
    elif is_plan:
        lines.append("Nothing was modified. If the plan looks right, apply it with:")
        lines.append(
            f"  python kit_doctor.py install --kit {report['kit_dir']} "
            f"--target {report['target_dir']} --host {report['host']} --apply"
        )
    else:
        lines.append("Install applied and registered. Wiring of settings/hooks (if suggested above) stays manual.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# REGISTRY — ~/.claude-kits/registry.json (chaveado por kit_dir + target_dir)
# ---------------------------------------------------------------------------

def _load_registry(path: Path) -> dict:
    if not path.exists():
        return {"installs": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"installs": []}


def register_install(kit_dir: Path, target_dir: Path, registry_path: Path, verify_report: dict | None = None) -> dict:
    reg = _load_registry(registry_path)
    entry = {
        "kit_dir": str(kit_dir.resolve()),
        "target_dir": str(target_dir.resolve()),
        "name": kit_dir.name,
        "registered_at": _brt_now_iso(),
        "verify_status": (verify_report or {}).get("status", "unknown"),
    }
    reg["installs"] = [
        i for i in reg.get("installs", [])
        if not (i.get("kit_dir") == entry["kit_dir"] and i.get("target_dir") == entry["target_dir"])
    ]
    reg["installs"].append(entry)
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = registry_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, registry_path)
    return entry


def list_installs(registry_path: Path) -> list:
    return _load_registry(registry_path).get("installs", [])


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="kit_doctor.py")
    p.add_argument("--self-test", action="store_true")
    sub = p.add_subparsers(dest="cmd")

    sp_verify = sub.add_parser("verify")
    sp_verify.add_argument("kit_dir")
    sp_verify.add_argument("--json", dest="json_out", default=None)

    sp_install = sub.add_parser("install")
    sp_install.add_argument("kit_dir", nargs="?")
    sp_install.add_argument("--kit", dest="kit_option", default=None)
    sp_install.add_argument("--target", default=None, help="root of the target project (default: kit_dir)")
    sp_install.add_argument("--host", default=_DEFAULT_HOST, choices=list(HOSTS.keys()))
    sp_install.add_argument("--answers", dest="answers_path", default=None)
    sp_install.add_argument("--apply", action="store_true", help="apply for real (default: plan only, zero writes)")
    sp_install.add_argument("--dry-run", action="store_true", help="explicit alias of the default behaviour (compat)")
    sp_install.add_argument("--human", action="store_true", help="print the plan as readable text instead of JSON")
    sp_install.add_argument("--registry-path", default=str(_DEFAULT_REGISTRY))
    sp_install.add_argument("--no-register", action="store_true")

    sp_registry = sub.add_parser("registry")
    sp_registry.add_argument("--registry-path", default=str(_DEFAULT_REGISTRY))

    sp_mk = sub.add_parser("marketplace")
    sp_mk.add_argument("root", help="root of the published marketplace (e.g. the emitted product tree)")
    sp_mk.add_argument("--json", dest="json_out", default=None)

    return p


def _normalize_argv(argv: list) -> list:
    """Compatibilidade posicional: `kit_doctor.py <dir> [--json x]` continua funcionando
    (vira `verify <dir> [--json x]`) — sem exigir a keyword `verify`."""
    if not argv:
        return argv
    if argv[0] in _SUBCOMMANDS or argv[0].startswith("-"):
        return argv
    return ["verify", *argv]


def main(argv) -> int:
    argv = _normalize_argv(argv)
    args = build_parser().parse_args(argv)

    if args.self_test:
        return _self_test()

    if args.cmd == "verify":
        kit_dir = Path(args.kit_dir)
        if not kit_dir.is_dir():
            print(f"kit_doctor: folder does not exist: {kit_dir}", file=sys.stderr)
            return 3
        report = check_kit(kit_dir)
        if args.json_out:
            Path(args.json_out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return _verify_exit(report)

    if args.cmd == "install":
        kit_arg = args.kit_option or args.kit_dir
        if not kit_arg:
            print("kit_doctor: pass <kit_dir> or --kit <kit_dir>", file=sys.stderr)
            return 3
        kit_dir = Path(kit_arg)
        if not kit_dir.is_dir():
            print(f"kit_doctor: folder does not exist: {kit_dir}", file=sys.stderr)
            return 3
        target_dir = Path(args.target) if args.target else kit_dir
        if not target_dir.is_dir():
            print(f"kit_doctor: --target does not exist: {target_dir}", file=sys.stderr)
            return 3

        report = run_install(
            kit_dir, target_dir, apply=args.apply, host=args.host,
            answers_path=args.answers_path, registry_path=Path(args.registry_path),
        )
        if args.apply and not args.no_register:
            verify_report = check_kit(kit_dir) if (kit_dir / "CHECKSUMS.txt").exists() else None
            report["registry_entry"] = register_install(kit_dir, target_dir, Path(args.registry_path), verify_report)

        if args.human:
            print(render_plan(report))
        else:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1 if report["status"] == "fail" else 0

    if args.cmd == "registry":
        installs = list_installs(Path(args.registry_path))
        print(json.dumps({"installs": installs}, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "marketplace":
        rel = check_marketplace(Path(args.root))
        if args.json_out:
            Path(args.json_out).write_text(json.dumps(rel, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(rel, ensure_ascii=False, indent=2))
        return _marketplace_exit(rel)

    print(
        "usage: kit_doctor.py {verify|install|registry|marketplace} ... "
        "(or kit_doctor.py <dir> = verify)",
        file=sys.stderr,
    )
    return 3


# ---------------------------------------------------------------------------
# SELF-TEST
# ---------------------------------------------------------------------------

def _self_test() -> int:
    import shutil
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="kit_doctor_selftest_"))
    try:
        # --- verify (comportamento preservado de v1.0.0) ---
        kit_dir = tmp / "fixture-kit-1.0.0"
        kit_dir.mkdir()
        (kit_dir / "README.md").write_text("# Fixture\n", encoding="utf-8")
        (kit_dir / "LICENSE").write_text("MIT\n", encoding="utf-8")
        checksums = "\n".join(f"{_sha256(kit_dir / n)}  {n}" for n in ("README.md", "LICENSE"))
        (kit_dir / "CHECKSUMS.txt").write_text(checksums + "\n", encoding="utf-8")

        report_ok = check_kit(kit_dir)
        assert report_ok["status"] == "ok"
        assert _verify_exit(report_ok) == 0

        (kit_dir / "extra.txt").write_text("post-install\n", encoding="utf-8")
        report_warn = check_kit(kit_dir)
        assert report_warn["status"] == "warn" and _verify_exit(report_warn) == 1
        (kit_dir / "extra.txt").unlink()

        (kit_dir / "README.md").write_text("# TAMPERED\n", encoding="utf-8")
        report_corrupt = check_kit(kit_dir)
        assert report_corrupt["status"] == "corrupt" and _verify_exit(report_corrupt) == 2
        (kit_dir / "README.md").write_text("# Fixture\n", encoding="utf-8")

        no_checksums_dir = tmp / "no-checksums"
        no_checksums_dir.mkdir()
        report_error = check_kit(no_checksums_dir)
        assert report_error["status"] == "error" and _verify_exit(report_error) == 3

        # inventário VAZIO não atesta nada -> corrupt (exit 2), com mensagem
        vazio_dir = tmp / "inventario-vazio"
        vazio_dir.mkdir()
        (vazio_dir / "CHECKSUMS.txt").write_text("\n", encoding="utf-8")
        report_vazio = check_kit(vazio_dir)
        assert report_vazio["status"] == "corrupt" and _verify_exit(report_vazio) == 2 and report_vazio["errors"], report_vazio

        # caminho que escapa do kit (`../` e absoluto) -> corrupt, listado em unsafe_paths
        fora = tmp / "fora.txt"
        fora.write_text("outside the kit\n", encoding="utf-8")
        escape_dir = tmp / "escape-kit"
        escape_dir.mkdir()
        (escape_dir / "CHECKSUMS.txt").write_text(
            f"{_sha256(fora)}  ../fora.txt\n{_sha256(fora)}  {fora.as_posix()}\n", encoding="utf-8"
        )
        report_escape = check_kit(escape_dir)
        assert report_escape["status"] == "corrupt" and _verify_exit(report_escape) == 2, report_escape
        assert sorted(report_escape["unsafe_paths"]) == sorted(["../fora.txt", fora.as_posix()]), report_escape

        # --- compatibilidade posicional: kit_doctor.py <dir> == verify <dir> ---
        assert _normalize_argv([str(kit_dir)]) == ["verify", str(kit_dir)]
        assert _normalize_argv(["verify", str(kit_dir)]) == ["verify", str(kit_dir)]
        assert _normalize_argv(["--self-test"]) == ["--self-test"]
        assert _normalize_argv(["install", str(kit_dir)]) == ["install", str(kit_dir)]

        # --- install: fixture minimal com kit.install.yaml + 1 script --self-test ---
        install_kit = tmp / "install-fixture"
        install_kit.mkdir()
        (install_kit / "profile.example.yaml").write_text("chave: valor\n", encoding="utf-8")
        (install_kit / "scripts").mkdir()
        script_ok = install_kit / "scripts" / "ok_tool.py"
        script_ok.write_text(
            "import sys\n"
            "if '--self-test' in sys.argv:\n"
            "    print('self-test OK')\n"
            "    sys.exit(0)\n",
            encoding="utf-8",
        )
        (install_kit / "install").mkdir()
        (install_kit / "install" / "kit.install.yaml").write_text(
            "kit: install-fixture\n"
            "questions:\n"
            "  - id: modo\n"
            "    prompt: \"lite or full?\"\n"
            "    type: choice\n"
            "    options: [lite, full]\n"
            "    default: full\n",
            encoding="utf-8",
        )

        reg_path = tmp / "registry.json"

        # 1) modo PLANO (default): zero escrita, detect=greenfield (fixture nova, sem .claude/ nem git)
        report_plan = run_install(install_kit, install_kit, apply=False, host="claude-code",
                                   answers_path=None, registry_path=reg_path)
        assert report_plan["mode"] == "plan" and report_plan["status"] == "ok", report_plan
        detect_plan = report_plan["stages"][0]
        assert detect_plan["stage"] == "detect" and detect_plan["classification"] == "greenfield", detect_plan
        profile_plan = report_plan["stages"][2]
        assert profile_plan["actions"][0]["action"] == "would-copy"
        assert not (install_kit / "profile.yaml").exists(), "plan mode should not copy anything"
        configure_plan = report_plan["stages"][3]
        assert configure_plan["resolved"]["modo"] == "full" and configure_plan["pending_defaults"] == ["modo"]

        # 2) --answers aplica de verdade em cima do default
        answers_path = tmp / "answers.json"
        answers_path.write_text(json.dumps({"modo": "lite"}), encoding="utf-8")
        report_answers = run_install(install_kit, install_kit, apply=False, host="claude-code",
                                      answers_path=str(answers_path), registry_path=reg_path)
        configure_answers = report_answers["stages"][3]
        assert configure_answers["resolved"]["modo"] == "lite" and configure_answers["pending_defaults"] == []

        # 3) --apply de verdade: escreve profile, roda smoke, registra
        report_apply = run_install(install_kit, install_kit, apply=True, host="claude-code",
                                    answers_path=None, registry_path=reg_path)
        assert report_apply["mode"] == "apply" and report_apply["status"] == "ok", report_apply
        assert (install_kit / "profile.yaml").exists(), "--apply should copy the profile"
        smoke = report_apply["stages"][5]
        assert smoke["stage"] == "smoke"
        assert any(r["file"].endswith("ok_tool.py") and r["status"] == "ok" for r in smoke["results"])

        entry = register_install(install_kit, install_kit, reg_path, {"status": "ok"})
        assert entry["name"] == "install-fixture" and entry["target_dir"] == str(install_kit.resolve())

        # 4) re-run: detect via registry -> classification == "re-run"
        report_rerun = run_install(install_kit, install_kit, apply=False, host="claude-code",
                                    answers_path=None, registry_path=reg_path)
        detect_rerun = report_rerun["stages"][0]
        assert detect_rerun["classification"] == "re-run", detect_rerun
        profile_rerun = report_rerun["stages"][2]
        assert profile_rerun["actions"][0]["action"] == "skip-exists", "profile already there -> never overwritten"

        # 5) render_plan() produz texto legível (não quebra, contém as seções esperadas)
        human = render_plan(report_rerun)
        assert "PLAN" in human and "detect" in human and "classification=re-run" in human

        # --- install com script que FALHA no self-test -> stage smoke = fail, exit 1 ---
        script_bad = install_kit / "scripts" / "bad_tool.py"
        script_bad.write_text(
            "import sys\n"
            "if '--self-test' in sys.argv:\n"
            "    print('self-test FAILED')\n"
            "    sys.exit(1)\n",
            encoding="utf-8",
        )
        report_fail = run_install(install_kit, install_kit, apply=True, host="claude-code",
                                   answers_path=None, registry_path=reg_path)
        assert report_fail["status"] == "fail", report_fail
        script_bad.unlink()

        # --- registry: registra/atualiza sem duplicar, chaveado por (kit_dir, target_dir) ---
        assert list_installs(tmp / "registry-vazio.json") == []
        installs = list_installs(reg_path)
        assert len(installs) == 1 and installs[0]["kit_dir"] == str(install_kit.resolve())
        register_install(install_kit, install_kit, reg_path, {"status": "warn"})
        installs2 = list_installs(reg_path)
        assert len(installs2) == 1 and installs2[0]["verify_status"] == "warn", "same (kit,target) pair -> updates, does not duplicate"

        # --- HOSTS/seam: Claude Code e Codex compartilham os seis estágios ---
        assert _DEFAULT_HOST in HOSTS
        assert HOSTS["claude-code"]["path_token"] == "${CLAUDE_PLUGIN_ROOT}"
        assert HOSTS["codex"]["skills_path"] == ".agents/skills"

        # --- marketplace: o caso que FORÇA a reprovar + o controle que exige silêncio ---
        mk = tmp / "mk"
        kit_pub = mk / "kits" / "fixture-kit-1.0.0"
        (kit_pub / ".claude-plugin").mkdir(parents=True)
        (kit_pub / ".claude-plugin" / "plugin.json").write_text(
            json.dumps({"name": "fixture-kit", "version": "1.0.0"}), encoding="utf-8"
        )
        doc_mk = {
            "name": "fixture-marketplace",
            "plugins": [{"name": "fixture-kit", "version": "1.0.0", "source": "./kits/fixture-kit-1.0.0"}],
        }
        (mk / "marketplace.json").write_text(json.dumps(doc_mk), encoding="utf-8")

        rel_fora = check_marketplace(mk)  # manifesto SÓ na raiz -> o modo #1
        assert rel_fora["status"] == "fail" and _marketplace_exit(rel_fora) == 2
        assert any(a["code"] == "manifesto-fora-do-lugar" for a in rel_fora["achados"])

        (mk / ".claude-plugin").mkdir()
        (mk / ".claude-plugin" / "marketplace.json").write_text(json.dumps(doc_mk), encoding="utf-8")
        rel_ok = check_marketplace(mk)  # CONTROLE: no lugar certo + cópia idêntica -> silêncio
        assert rel_ok["status"] == "ok" and rel_ok["achados"] == [], rel_ok["achados"]
        assert rel_ok["plugins"] == 1

        (kit_pub / ".claude-plugin" / "plugin.json").write_text(
            json.dumps({"name": "fixture-kit", "version": "9.9.9"}), encoding="utf-8"
        )
        rel_drift = check_marketplace(mk)  # o defeito do item 1, uma camada acima
        assert any(a["code"] == "versao-divergente" for a in rel_drift["achados"])

        assert _marketplace_exit(check_marketplace(tmp / "does-not-exist")) == 3

        print("self-test OK — verify (ok/warn/corrupt/error) + positional compat + install (6 stages: detect/prereqs/profile/configure/wire/smoke, plan-first/--apply, --answers, re-run) + registry (kit+target, no duplicates) + render_plan + marketplace (out-of-place/version-mismatch + control)")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    sys.exit(main(sys.argv[1:]))

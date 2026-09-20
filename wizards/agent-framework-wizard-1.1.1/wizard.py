#!/usr/bin/env python3
"""
wizard — scaffold de projeto novo em 6 passos (método genérico de setup-wizard,
REESCRITO DO ZERO — nenhuma linha de código de terceiro. Ver "O QUE NÃO FAZER" do
kickoff: extrai-se o MÉTODO — checar ambiente, configurar, validar, gerar +
resumo — não o código de nenhum instalador específico).

Os 6 passos:
  1. check_python()      — ambiente tem Python >= 3.9?
  2. check_git()          — ambiente tem git? (projeto-alvo é sempre um repo)
  3. check_deps()         — PyYAML disponível? (única dependência real do wizard)
  4. configure()          — nome do projeto + escada R0-R4 + quais templates instanciar
                            (--demo = defaults sensatos; --answers = respostas prontas;
                            nenhum dos dois = NotImplementedError intencional — use
                            --interview primeiro para obter o schema de perguntas)
  5. validate()           — o profile resultante é bem-formado? (campos obrigatórios)
  6. generate_and_summary() — escreve operator-profile.yaml + templates escolhidos + resumo
                            (NUNCA sobrescreve arquivo customizado — --force ignora a proteção)

Uso:
    python wizard.py --interview                        # imprime o schema de perguntas (JSON), sai 0
    python wizard.py --demo --out <dir>                  # scaffold não-interativo com defaults
    python wizard.py --answers respostas.json --out <dir>  # scaffold a partir de respostas prontas
    python wizard.py --demo --out <dir> --force          # sobrescreve customização de propósito
    python wizard.py --self-test

Nenhum modo bloqueia em stdin — o operador real deste ecossistema é frequentemente um
agente atuando pelo humano; --interview/--answers é o "Confirm" (agente lê o schema,
pergunta ao humano na conversa, re-invoca com --answers), nunca um input() de terminal.

Exit: 0 ok (inclusive re-run = no-op ou skip-customized) · 2 ambiente sem pré-requisito
(python/git/PyYAML ausente) ou uso inválido (nem --demo, nem --answers, nem --interview).
stdlib + PyYAML. v1.1.0 — 2026-07-11 (agent-framework-wizard · corrige NotImplementedError
do modo interativo + overwrite incondicional — ver INSTALL-CONTRACT.md)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

_HERE = Path(__file__).resolve().parent
_TEMPLATES_DIR = _HERE / "templates"

_ESCADA_DEFAULT = [
    {"nivel": "R0", "nome": "Declarado", "certifica": "palavra do maker"},
    {"nivel": "R1", "nome": "Auto-verificado", "certifica": "--self-test/pytest exit 0"},
    {"nivel": "R2", "nome": "Gate", "certifica": "done_gate.py exit 0"},
    {"nivel": "R3", "nome": "Revisado", "certifica": "goal_review.py + checker cross-model"},
    {"nivel": "R4", "nome": "Aceito", "certifica": "gate humano / produção"},
]

_DEFAULT_TEMPLATES = ["00-LEIA-PRIMEIRO", "00-STATE", "00-VISION", "00-PROCESSES"]


def _available_templates() -> list:
    return sorted(p.name[: -len(".template.md")] for p in _TEMPLATES_DIR.glob("*.template.md"))


def questions() -> list:
    """Schema de perguntas do wizard — MESMO formato consumido por kit_doctor.py
    stage_configure (ver INSTALL-CONTRACT.md 'Schema de perguntas'): id/prompt/type/
    options/default. Usado por --interview (imprime este schema) e --answers (resolve
    contra ele). 'responder perguntas' tem UM formato só neste marketplace."""
    return [
        {
            "id": "project_name",
            "prompt": "Qual o nome do projeto/agente? (entra nos arquivos gerados; ex.: meu-agente)",
            "type": "string", "default": "agente-teste",
        },
        {
            "id": "templates",
            "prompt": "Quais documentos-base gerar? Pode escolher mais de um "
                      "(default: todos os 4 — 00-LEIA-PRIMEIRO, 00-STATE, 00-VISION, 00-PROCESSES)",
            "type": "choice", "options": _available_templates(), "default": list(_DEFAULT_TEMPLATES),
        },
    ]


def step(n: int, total: int, title: str) -> None:
    print(f"[{n}/{total}] {title}")


def check_python() -> tuple:
    ok = sys.version_info >= (3, 9)
    return ok, f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"


def check_git() -> tuple:
    try:
        r = subprocess.run(["git", "--version"], capture_output=True, text=True, timeout=10)
        return r.returncode == 0, (r.stdout or r.stderr).strip()
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def check_deps() -> tuple:
    return yaml is not None, "PyYAML disponível" if yaml is not None else "PyYAML AUSENTE — instale com 'pip install pyyaml'"


def configure(demo: bool, project_name: str | None, templates: list | None, answers: dict | None = None) -> dict:
    if demo:
        return {
            "project_name": project_name or "agente-teste",
            "escada": _ESCADA_DEFAULT,
            "templates": templates or list(_DEFAULT_TEMPLATES),
        }
    if answers is not None:
        # --answers: mesmo schema de questions() — campo ausente cai no default da pergunta.
        defaults = {q["id"]: q["default"] for q in questions()}
        return {
            "project_name": answers.get("project_name") or project_name or defaults["project_name"],
            "escada": _ESCADA_DEFAULT,
            "templates": answers.get("templates") or templates or list(defaults["templates"]),
        }
    # Nem --demo nem --answers: sem stdin real não há como resolver. Use --interview
    # primeiro (imprime o schema de perguntas) e re-invoque com --answers <file>.
    raise NotImplementedError("modo interativo requer --demo ou --answers <file> (ver --interview para o schema)")


def validate(config: dict) -> list:
    errors = []
    if not config.get("project_name"):
        errors.append("project_name ausente")
    escada = config.get("escada", [])
    if len(escada) != 5 or {e["nivel"] for e in escada} != {"R0", "R1", "R2", "R3", "R4"}:
        errors.append("escada deve ter exatamente os níveis R0-R4")
    if not config.get("templates"):
        errors.append("nenhum template selecionado")
    for t in config.get("templates", []):
        if not (_TEMPLATES_DIR / f"{t}.template.md").exists():
            errors.append(f"template desconhecido: {t}")
    return errors


def _sha256_dir(out_dir: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(out_dir.rglob("*")):
        if p.is_file():
            h.update(p.read_bytes())
    return h.hexdigest()


def _write_if_safe(dest: Path, content: str, force: bool, rel: str, written: list, skipped: list) -> None:
    """Nunca sobrescreve customização por padrão (mesmo espírito de stage_profile do
    kit_doctor.py): se o alvo já existe com conteúdo DIFERENTE do que seria gerado
    agora, marca skip-customized em vez de clobbar. --force ignora essa proteção."""
    if dest.exists() and not force:
        existing = dest.read_text(encoding="utf-8")
        if existing != content:
            skipped.append(rel)
            return
    dest.write_text(content, encoding="utf-8")
    written.append(rel)


def generate_and_summary(config: dict, out_dir: Path, force: bool = False) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    before_hash = _sha256_dir(out_dir) if out_dir.exists() else None

    profile = {
        "project_name": config["project_name"],
        "verificacao": {"escada": config["escada"]},
    }
    if yaml is not None:
        profile_content = yaml.safe_dump(profile, allow_unicode=True, sort_keys=False)
    else:
        profile_content = json.dumps(profile, ensure_ascii=False, indent=2)

    written: list = []
    skipped: list = []
    _write_if_safe(out_dir / "operator-profile.yaml", profile_content, force, "operator-profile.yaml", written, skipped)

    docs_dir = out_dir / "docs" / "plans" / "execucao"
    docs_dir.mkdir(parents=True, exist_ok=True)
    for t in config["templates"]:
        src = _TEMPLATES_DIR / f"{t}.template.md"
        text = src.read_text(encoding="utf-8").replace("{{project_name}}", config["project_name"])
        dest = docs_dir / f"{t}.md"
        _write_if_safe(dest, text, force, str(dest.relative_to(out_dir)), written, skipped)

    after_hash = _sha256_dir(out_dir)
    no_op = before_hash == after_hash

    summary = {
        "project_name": config["project_name"],
        "out_dir": str(out_dir),
        "files_written": written,
        "files_skipped_customized": skipped,
        "no_op": no_op,
    }
    return summary


# Why: `templates` mantem o kit configuravel para consumidores externos; o fluxo local usa o default.
def run_wizard(
    demo: bool, out_dir: Path, project_name: str | None = None, templates: list | None = None,
    answers: dict | None = None, force: bool = False,
) -> tuple:
    """Retorna (exit_code, summary_or_errors)."""
    ok_py, msg_py = check_python()
    step(1, 6, f"check_python — {msg_py}")
    if not ok_py:
        return 2, {"error": f"Python >= 3.9 exigido: {msg_py}"}

    ok_git, msg_git = check_git()
    step(2, 6, f"check_git — {msg_git}")
    if not ok_git:
        return 2, {"error": f"git ausente: {msg_git}"}

    ok_deps, msg_deps = check_deps()
    step(3, 6, f"check_deps — {msg_deps}")
    if not ok_deps:
        return 2, {"error": msg_deps}

    step(4, 6, "configure")
    config = configure(demo, project_name, templates, answers=answers)

    step(5, 6, "validate")
    errors = validate(config)
    if errors:
        return 2, {"errors": errors}

    step(6, 6, "generate_and_summary")
    summary = generate_and_summary(config, out_dir, force=force)
    return 0, summary


def _self_test() -> int:
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="wizard_selftest_"))
    try:
        out_dir = tmp / "agente-teste"
        code1, r1 = run_wizard(demo=True, out_dir=out_dir)
        assert code1 == 0, f"1a run deveria passar: {r1}"
        assert (out_dir / "operator-profile.yaml").exists()
        assert (out_dir / "docs" / "plans" / "execucao" / "00-STATE.md").exists()
        assert not r1["no_op"], "1a run NÃO deveria ser no-op (arquivo novo)"

        code2, r2 = run_wizard(demo=True, out_dir=out_dir)
        assert code2 == 0 and r2["no_op"], f"2a run deveria ser no-op (conteúdo idêntico): {r2}"

        bad_config = {"project_name": "", "escada": [], "templates": []}
        errs = validate(bad_config)
        assert len(errs) >= 2, f"config vazia deveria acumular erros: {errs}"

        content = (out_dir / "docs" / "plans" / "execucao" / "00-LEIA-PRIMEIRO.md").read_text(encoding="utf-8")
        assert "agente-teste" in content and "{{project_name}}" not in content, "placeholder não substituído"

        # --- Bug A: --interview (schema) + --answers (não-interativo, sem NotImplementedError) ---
        qs = questions()
        assert len(qs) >= 2 and {"id", "prompt", "type", "default"} <= set(qs[0].keys())
        try:
            configure(demo=False, project_name=None, templates=None, answers=None)
            raise AssertionError("configure sem demo/answers deveria levantar NotImplementedError")
        except NotImplementedError:
            pass

        answers_out = tmp / "agente-via-answers"
        code_a, r_a = run_wizard(demo=False, out_dir=answers_out, answers={"project_name": "via-answers"})
        assert code_a == 0 and r_a["project_name"] == "via-answers", f"--answers deveria configurar sem stdin: {r_a}"
        assert (answers_out / "operator-profile.yaml").exists()

        # --- Bug B: skip-exists — edição manual sobrevive a re-run (nunca clobber sem --force) ---
        edited_file = out_dir / "docs" / "plans" / "execucao" / "00-STATE.md"
        edited_file.write_text("CUSTOMIZAÇÃO DO USUÁRIO — NÃO SOBRESCREVER\n", encoding="utf-8")
        code3, r3 = run_wizard(demo=True, out_dir=out_dir)
        assert code3 == 0
        assert any(s.endswith("00-STATE.md") for s in r3["files_skipped_customized"]), \
            f"edição deveria ser preservada (skip): {r3}"
        assert edited_file.read_text(encoding="utf-8") == "CUSTOMIZAÇÃO DO USUÁRIO — NÃO SOBRESCREVER\n", \
            "generate_and_summary sobrescreveu customização sem --force"

        # --force ignora a proteção de propósito
        code4, r4 = run_wizard(demo=True, out_dir=out_dir, force=True)
        assert code4 == 0 and any(w.endswith("00-STATE.md") for w in r4["files_written"]), f"--force deveria sobrescrever: {r4}"
        assert "agente-teste" in edited_file.read_text(encoding="utf-8"), "--force deveria ter regenerado o arquivo"

        print("self-test OK — 6 passos rodam, 1a run gera, 2a run = no-op, placeholders substituídos, validate pega "
              "config vazia, --interview/--answers sem NotImplementedError, skip-exists preserva edição, --force sobrescreve")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="wizard.py")
    p.add_argument("--demo", action="store_true")
    p.add_argument("--out", default=None)
    p.add_argument("--project-name", default=None)
    p.add_argument("--interview", action="store_true", help="imprime o schema de perguntas (JSON) e sai — não gera nada")
    p.add_argument("--answers", dest="answers_path", default=None, help="arquivo JSON/YAML com respostas ao --interview")
    p.add_argument("--force", action="store_true", help="sobrescreve arquivo customizado (default: nunca sobrescreve)")
    p.add_argument("--self-test", action="store_true")
    return p


def _load_answers(path: str) -> dict:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if p.suffix in (".yaml", ".yml") and yaml is not None:
        return yaml.safe_load(text) or {}
    return json.loads(text) if text.strip() else {}


def main(argv) -> int:
    args = build_parser().parse_args(argv)
    if args.self_test:
        return _self_test()
    if args.interview:
        print(json.dumps({"questions": questions()}, ensure_ascii=False, indent=2))
        return 0
    if not args.out or not (args.demo or args.answers_path):
        print("uso: wizard.py --demo --out <dir> | wizard.py --answers <file> --out <dir> | wizard.py --interview", file=sys.stderr)
        return 2
    answers = _load_answers(args.answers_path) if args.answers_path else None
    code, result = run_wizard(
        demo=args.demo, out_dir=Path(args.out), project_name=args.project_name,
        answers=answers, force=args.force,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    sys.exit(main(sys.argv[1:]))

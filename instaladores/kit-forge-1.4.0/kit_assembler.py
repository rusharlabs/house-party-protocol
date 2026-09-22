#!/usr/bin/env python3
"""
kit_assembler — do manifesto ao kit distribuível, com o ip_pii_linter como GATE inquebrável.

Lê um manifesto YAML, resolve o conjunto de arquivos (include - exclude), copia para um
staging temporário, aplica sanitizações determinísticas, gera LICENSE/SANITIZATION.md (+ o par
SANITIZATION.pt-BR.md)/CHECKSUMS.txt, roda o ip_pii_linter como gate e SÓ ENTÃO troca
atomicamente para o destino final (+ zip determinístico). Não existe --skip-lint — o gate não
tem porta dos fundos.

Uso:
    python kit_assembler.py --manifest <manifest.yaml>
        [--out <dir>]           # default: dist/ ao lado deste script
        [--dry-run]             # imprime o plano (IN/OUT/ações) e para — zero escrita
        [--json <out.json>]     # relatório máquina
        [--strict]              # repassa --strict ao linter
        [--self-test]

Exit: 0 emitido limpo (ou no-op idempotente) · 1 emitido com warns · 2 lint BLOCK (nada emitido) ·
      3 erro (manifesto inválido, plugin.json divergente, IO).

stdlib + PyYAML. v1.0.0 — 2026-07-10 (FASE 1 · kit-forge)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

try:
    import yaml  # PyYAML
except ImportError:
    yaml = None  # type: ignore[assignment]

_ROOT = Path(__file__).resolve().parent
_LINTER = _ROOT / "ip_pii_linter.py"
_ZIP_EPOCH = (2020, 1, 1, 0, 0, 0)  # timestamp fixo -> zip determinístico

# Why (English-first docs): human docs ship English-first with a pt-BR pair. The sanitization
# record is generated, so the pair is generated too — same numbers, same headings, pair link at
# the top — and the Portuguese-only SANITIZACAO.md is no longer emitted. The manifest switch keeps
# its historical name (`generate.sanitizacao_md`): it is a config key, not a file name.
_SANITIZATION_FILES = ("SANITIZATION.md", "SANITIZATION.pt-BR.md")
_SANITIZATION_PAIR_LINK = "[English](SANITIZATION.md) · [Português](SANITIZATION.pt-BR.md)"
_SANITIZATION_TEXT = {
    "SANITIZATION.md": {
        "applied_h": "## Sanitization applied",
        "exclude": "- {n} file exclusion pattern(s) (see the build's internal manifest — not distributed)",
        "replaces": "- {n} text replacement(s) applied",
        "lint_h": "## Lint result",
    },
    "SANITIZATION.pt-BR.md": {
        "applied_h": "## Sanitização aplicada",
        "exclude": "- {n} padrão(ões) de exclusão de arquivo (ver manifesto interno da build — não distribuído)",
        "replaces": "- {n} substituição(ões) de texto aplicada(s)",
        "lint_h": "## Resultado do lint",
    },
}

sys.path.insert(0, str(_ROOT / "hooks"))
try:
    from guard_origins import sweep as _go_sweep, verify as _go_verify
except ImportError:  # noqa: BLE001 — degrade seguro se guard_origins não estiver presente
    _go_sweep = None  # type: ignore[assignment]
    _go_verify = None  # type: ignore[assignment]

_LICENSE_MIT = """MIT License

Copyright (c) {year} {author}

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""


def _glob_to_regex(pattern: str):
    """Converte um glob (suporta ** cross-slash, * e ?) para regex ancorada."""
    tokens = []
    i = 0
    while i < len(pattern):
        c = pattern[i]
        if pattern[i : i + 2] == "**":
            tokens.append(".*")
            i += 2
            if i < len(pattern) and pattern[i] == "/":
                i += 1
        elif c == "*":
            tokens.append("[^/]*")
            i += 1
        elif c == "?":
            tokens.append("[^/]")
            i += 1
        elif c == ".":
            tokens.append(r"\.")
            i += 1
        else:
            tokens.append(re.escape(c))
            i += 1
    return re.compile("^" + "".join(tokens) + "$")


def resolve_fileset(source_root: Path, include: list, exclude: list) -> list:
    include_res = [_glob_to_regex(p) for p in include]
    exclude_res = [_glob_to_regex(p) for p in exclude]
    result = []
    for p in sorted(source_root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(source_root).as_posix()
        if any(r.match(rel) for r in include_res) and not any(r.match(rel) for r in exclude_res):
            result.append(rel)
    return sorted(result)


def load_manifest(path: Path) -> dict:
    if yaml is None:
        raise RuntimeError("PyYAML ausente — instale pyyaml para ler o manifesto")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise RuntimeError("manifesto não é um mapeamento YAML válido")
    return data


def validate_manifest(manifest: dict) -> list:
    """Retorna lista de erros (vazia = válido)."""
    errors = []
    kit = manifest.get("kit")
    if not isinstance(kit, dict):
        return ["seção 'kit' ausente ou inválida"]
    for field in ("name", "version", "license", "author", "source_root"):
        if not kit.get(field):
            errors.append(f"kit.{field} ausente")
    version = kit.get("version", "")
    if version and not re.match(r"^\d+\.\d+\.\d+([-+].*)?$", str(version)):
        errors.append(f"kit.version '{version}' não é semver")
    if not manifest.get("include"):
        errors.append("'include' ausente ou vazio")
    plugin_json = kit.get("_plugin_json_check")  # injetado por quem chama, se aplicável
    if plugin_json:
        if plugin_json.get("version") and plugin_json["version"] != version:
            errors.append(f"plugin.json version ({plugin_json['version']}) diverge do manifesto ({version})")
        if plugin_json.get("license") and plugin_json["license"] != kit.get("license"):
            errors.append("plugin.json license diverge do manifesto")
    return errors


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def write_checksums(staging: Path, files: list) -> Path:
    lines = []
    for rel in sorted(files):
        digest = sha256_file(staging / rel)
        lines.append(f"{digest}  {rel}")
    out = staging / "CHECKSUMS.txt"
    _escreve_lf(out, "\n".join(lines) + "\n")
    return out


def write_zip(staging: Path, files: list, zip_path: Path) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel in sorted(files) + ["LICENSE", *_SANITIZATION_FILES, "CHECKSUMS.txt"]:
            p = staging / rel
            if not p.exists():
                continue
            info = zipfile.ZipInfo(rel, date_time=_ZIP_EPOCH)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, p.read_bytes())


# --- A PROVA DO ARTEFATO QUE VIAJA ------------------------------------------
# Why: o assembler escrevia o .zip e nunca mais o abria, e o kit_doctor verifica o
# CHECKSUMS.txt dentro do DIRETORIO do kit, nao no zip. Um zip truncado, com entrada que
# escapa do diretorio de extracao, ou carregando .bak/.env/ip-ruleset.yaml sairia com
# exit 0. O diretorio e o que foi montado; o zip e o que viaja. Sao dois artefatos, e os
# dois precisam de regua.

# Why: a mesma lista dos 10 manifestos (exclude de .bak) mais o que
# NUNCA pode sair de casa. O ip-ruleset.yaml real carrega nome de cliente e de
# infra interna — so o .example e publicavel.
_ZIP_PROIBIDO = (
    "*.bak",
    "*.bak-*",
    "*.orig",
    "*.rej",
    "*.rebuild*.json",
    "*.build.json",
    "*.pyc",
    "*.pyo",
    "__pycache__",
    ".pytest_cache",
    ".env",
    ".env.*",
    "ip-ruleset.yaml",
    ".DS_Store",
    "Thumbs.db",
    "desktop.ini",
    "*.INVALIDO",
)


def _entrada_proibida(nome: str) -> str | None:
    """Devolve o padrao que reprova a entrada, ou None. Case o BASENAME e cada
    componente de diretorio — `a/__pycache__/b.txt` reprova pelo diretorio."""
    import fnmatch

    partes = nome.split("/")
    base = partes[-1]
    # Why: o .gitignore de distribuicao nega .env.example de proposito; a regua tem
    # de negar junto, senao o gate reprova o arquivo que ele quer que exista.
    if base.endswith(".example"):
        return None
    # Why: fnmatch.fnmatch e case-insensitive so no Windows — "X.BAK" reprovaria o zip aqui e
    # passaria no macOS. A regua do artefato que viaja nao pode depender do SO de quem emite:
    # fnmatchcase sobre minusculas, sempre.
    for padrao in _ZIP_PROIBIDO:
        for parte in partes:
            if fnmatch.fnmatchcase(parte.lower(), padrao.lower()):
                return padrao
    return None


def verify_zip(zip_path: Path, source_dir: Path, expected: list) -> dict:
    """Reabre o .zip emitido e prova que ele e o que deveria ser.

    Quatro provas independentes — uma so nao basta, e cada uma pega um modo de
    falha que as outras nao veem:

      1. INTEGRIDADE  testzip() valida o CRC de cada membro (zip truncado)
      2. FIDELIDADE   sha256 do membro == sha256 do arquivo no disco
      3. ESTRUTURA    nenhum caminho absoluto, nenhuma travessia `..`
      4. HIGIENE      nenhuma entrada proibida (.bak, .env, ip-ruleset.yaml)

    Mais a COMPLETUDE: todo arquivo resolvido pelo manifesto tem de estar la.

    Nunca levanta — devolve {"ok", "entries", "errors"} para o chamador decidir.
    """
    errors: list = []
    nomes: list = []

    if not zip_path.exists():
        return {"ok": False, "entries": 0, "errors": [f"o zip nao existe: {zip_path}"]}

    try:
        with zipfile.ZipFile(zip_path) as zf:
            corrompido = zf.testzip()
            if corrompido is not None:
                errors.append(f"CRC invalido (zip corrompido) em: {corrompido}")

            nomes = zf.namelist()
            for nome in nomes:
                # 3 - ESTRUTURA. Uma entrada que escapa do diretorio de extracao
                # sobrescreve arquivo de quem instala. Nao e higiene, e seguranca.
                if nome.startswith("/") or (len(nome) > 1 and nome[1] == ":"):
                    errors.append(f"caminho absoluto no zip: {nome}")
                    continue
                if ".." in nome.split("/"):
                    errors.append(f"travessia de diretorio no zip: {nome}")
                    continue
                if chr(92) in nome:
                    # Why: chr(92) e a barra invertida. Escrita literal, a sequencia barra-b pode virar o
                    # byte 0x08 (backspace) e o gate para de casar tudo, inclusive os verdadeiros
                    # positivos. Aqui ela nao tem como se perder.
                    errors.append(f"separador Windows no zip: {nome}")
                    continue

                # 4 - HIGIENE
                padrao = _entrada_proibida(nome)
                if padrao is not None:
                    errors.append(f"entrada proibida no zip: {nome} (casa {padrao})")

                # 2 - FIDELIDADE
                disco = source_dir / nome
                if not disco.exists():
                    errors.append(f"entrada do zip sem par no disco: {nome}")
                    continue
                if hashlib.sha256(zf.read(nome)).hexdigest() != sha256_file(disco):
                    errors.append(f"conteudo do zip diverge do disco: {nome}")

            presentes = set(nomes)
            for rel in sorted(expected):
                if rel not in presentes:
                    errors.append(f"arquivo do manifesto ausente do zip: {rel}")
    except zipfile.BadZipFile as exc:
        return {"ok": False, "entries": 0, "errors": [f"zip ilegivel: {exc}"]}

    return {"ok": not errors, "entries": len(nomes), "errors": errors}


# --- SANITIZACAO CONSCIENTE DE ESTRUTURA (A12) ------------------------------
# Why: a deteccao (ip_pii_linter) tem fronteira de palavra; a MUTACAO era
# `text.replace(find, repl)` cru — o mesmo defeito, na metade que escreve. A primeira
# regra de sanitize que alguem escreve e justamente para trocar um nome antes de
# publicar, que e o caso exato em que substring crua destroi a palavra vizinha.
#
# Tres coisas que o `text.replace` cru nao tinha e agora tem:
#   MODO declarado    word (default) | literal | regex — substring crua virou uma ESCOLHA,
#                     nao o comportamento silencioso
#   CONTAGEM          quantos hits por arquivo. Uma regra que esperava 2 e fez 400 fica
#                     visivel no report em vez de virar diff misterioso
#   VACUIDADE         regra com ZERO hits e avisada: ela foi escrita por um motivo e nao
#                     fez nada
_SANITIZE_MODOS = ("word", "literal", "regex")


def _compila_replace(find: str, modo: str):
    """Devolve o padrao compilado, ou None para substring cru."""
    if modo == "regex":
        return re.compile(find)
    if modo == "literal":
        return None
    # "word" — o DEFAULT, e a razao desta funcao existir.
    # A fronteira olha so as PONTAS: o miolo pode ter ponto, espaco ou
    # dois-pontos a vontade, porque re.escape cuida deles. Mesmo criterio do
    # ip_pii_linter, de proposito — deteccao e mutacao nao podem divergir.
    if find and find[0].isalnum() and find[-1].isalnum():
        return re.compile("(?<![0-9A-Za-z])" + re.escape(find) + "(?![0-9A-Za-z])")
    return None


def _le_preservando_quebra(path: Path) -> str:
    # Why: read_text/write_text traduzem quebra de linha. Num checkout com arquivos CRLF,
    # reescrever um arquivo por causa de UMA substituicao converteria o arquivo inteiro em
    # silencio — e `git diff --numstat` e cego a isso.
    with open(path, encoding="utf-8", newline="") as fh:
        return fh.read()


def _escreve_preservando_quebra(path: Path, texto: str) -> None:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(texto)


def _escreve_lf(path: Path, texto: str) -> None:
    """Arquivo GERADO pelo assembler sai sempre em LF — em qualquer SO."""
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(texto)


def _copia_normalizando_eol(src: Path, dst: Path) -> None:
    """Copia para o staging normalizando texto para LF; binario vai byte a byte.

    # Why: um kit emitido no Windows carregava arquivos CRLF (LICENSE/CHECKSUMS/SANITIZACAO
    # gerados por write_text, e fontes que o checkout local mantem em CRLF). Um repo com
    # `* text=auto eol=lf` normaliza tudo para LF no primeiro clone, e o CHECKSUMS.txt — que
    # guarda o hash dos bytes CRLF — passa a reprovar o kit que ele mesmo descreve. E o zip
    # deixa de ser deterministico entre SOs. LF na copia fecha as duas coisas.
    """
    raw = src.read_bytes()
    if b"\x00" in raw[:8000] or src.suffix.lower() in _BINARIOS:
        shutil.copy2(src, dst)
        return
    dst.write_bytes(raw.replace(b"\r\n", b"\n"))
    shutil.copystat(src, dst)


_BINARIOS = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".woff", ".woff2", ".ttf", ".pyc"}


def apply_replaces(staging: Path, regras: list) -> tuple[list, list, list]:
    """Aplica as substituicoes do manifesto. Devolve (aplicadas, avisos, erros).

    Nunca levanta: erro de manifesto vira item em `erros` e o chamador decide.
    """
    aplicadas: list = []
    avisos: list = []
    erros: list = []

    for i, rule in enumerate(regras):
        find = rule.get("find")
        repl = rule.get("replace")
        modo = rule.get("mode", "word")
        arquivos = rule.get("files") or []

        if not find:
            erros.append(
                f"sanitize.replaces[{i}]: 'find' vazio — um find vazio insere o "
                "replace ENTRE CADA CARACTERE do arquivo"
            )
            continue
        if repl is None:
            erros.append(f"sanitize.replaces[{i}]: 'replace' ausente")
            continue
        if modo not in _SANITIZE_MODOS:
            erros.append(
                f"sanitize.replaces[{i}]: mode '{modo}' invalido "
                f"(use um de: {', '.join(_SANITIZE_MODOS)})"
            )
            continue
        if not arquivos:
            erros.append(f"sanitize.replaces[{i}]: 'files' vazio — a regra nao tem alvo")
            continue
        try:
            padrao = _compila_replace(find, modo)
        except re.error as exc:
            erros.append(f"sanitize.replaces[{i}]: regex invalida: {exc}")
            continue

        if modo == "word" and padrao is None:
            # Why: find com ponta nao-alfanumerica ("-core", "/x/", "@org/") nao tem fronteira
            # possivel e cai em substring crua — e o report ainda dizia mode "word". O report diz o
            # que ACONTECEU.
            avisos.append(
                f"sanitize.replaces[{i}]: mode 'word' pedido, mas o 'find' comeca ou termina em "
                "nao-alfanumerico — nao ha fronteira de palavra possivel; aplicado como 'literal' "
                "(substring). Declare mode: literal se e isso que quer."
            )
        if modo != "regex" and find in repl:
            avisos.append(
                f"sanitize.replaces[{i}]: o 'replace' CONTEM o 'find' — "
                "a regra deixa de ser idempotente e a 2a build re-substitui"
            )

        total = 0
        for rel_file in arquivos:
            target = staging / rel_file
            if not target.exists():
                avisos.append(f"sanitize.replaces[{i}]: arquivo ausente do staging: {rel_file}")
                continue
            text = _le_preservando_quebra(target)
            if padrao is None:
                novo = text.replace(find, repl)
                n = text.count(find)
            elif modo == "regex":
                # backreferencia permitida — quem pediu regex pediu isto
                novo, n = padrao.subn(repl, text)
            else:
                # funcao de substituicao: o texto vai VERBATIM, sem o re
                # interpretar escape nenhum dentro dele
                novo, n = padrao.subn(lambda _m: repl, text)
            if n:
                _escreve_preservando_quebra(target, novo)
                aplicadas.append(
                    {"file": rel_file, "find": find, "replace": repl,
                     # Why: o relatorio registra o modo aplicado, nao apenas o solicitado.
                     "mode": ("literal (degradado de word)" if modo == "word" and padrao is None else modo),
                     "hits": n}
                )
                total += n

        if total == 0:
            avisos.append(
                f"sanitize.replaces[{i}]: ZERO ocorrencias em {len(arquivos)} arquivo(s) — "
                "regra VACUA, foi escrita por um motivo e nao fez nada"
            )

    return aplicadas, avisos, erros


def run_pipeline(manifest: dict, manifest_dir: Path, out_dir: Path, dry_run: bool, strict: bool, plugin_json: dict | None = None):
    """Executa o pipeline. Retorna (exit_code, report_dict)."""
    manifest = dict(manifest)
    if plugin_json is None:
        # Why: a checagem de versao existia em validate_manifest e nenhum call site a alimentava
        # — um kit podia sair declarando no plugin.json uma versao diferente da do manifesto. Sem
        # carregar o plugin.json da fonte, o gate e vacuo.
        kit0 = manifest.get("kit") or {}
        if kit0.get("source_root"):
            cand = (manifest_dir / kit0["source_root"]).resolve() / ".claude-plugin" / "plugin.json"
            if cand.is_file():
                try:
                    plugin_json = json.loads(cand.read_text(encoding="utf-8"))
                except (OSError, ValueError) as e:
                    return 3, {"status": "error", "errors": [f"plugin.json ilegível em {cand}: {e}"]}
    if plugin_json is not None:
        manifest.setdefault("kit", {})["_plugin_json_check"] = plugin_json

    errors = validate_manifest(manifest)
    if errors:
        return 3, {"status": "error", "errors": errors}

    kit = manifest["kit"]
    name = kit["name"]
    version = kit["version"]
    source_root = (manifest_dir / kit["source_root"]).resolve()
    if not source_root.is_dir():
        return 3, {"status": "error", "errors": [f"source_root não existe: {source_root}"]}

    include = manifest.get("include", [])
    exclude = manifest.get("exclude", []) or []
    files = resolve_fileset(source_root, include, exclude)

    plan = {
        "kit": name,
        "version": version,
        "source_root": str(source_root),
        "files_in": len(files),
        "files": files,
    }
    if dry_run:
        return 0, {"status": "dry-run", **plan}

    ts = str(int(time.time() * 1000))
    staging = out_dir / f".staging-{name}-{ts}"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    try:
        origin_snapshot = _go_sweep(source_root, files) if _go_sweep else None

        for rel in files:
            dst = staging / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            _copia_normalizando_eol(source_root / rel, dst)

        if _go_verify and origin_snapshot is not None:
            drift = _go_verify(origin_snapshot, source_root, files)
            if drift:
                shutil.rmtree(staging, ignore_errors=True)
                return 3, {"status": "error", "errors": [
                    f"fonte mudou durante a montagem (guard_origins): {drift}"
                ]}

        sanitize = manifest.get("sanitize", {}) or {}
        applied_replaces, sanitize_avisos, sanitize_erros = apply_replaces(
            staging, sanitize.get("replaces", []) or []
        )
        if sanitize_erros:
            shutil.rmtree(staging, ignore_errors=True)
            return 3, {"status": "error", "errors": sanitize_erros}

        generate = manifest.get("generate", {}) or {}
        if generate.get("license", True):
            _escreve_lf(staging / "LICENSE", _LICENSE_MIT.format(year=kit.get("year", 2026), author=kit["author"]))

        lint_conf = manifest.get("lint", {}) or {}
        ruleset_path = lint_conf.get("ruleset")
        lint_report_path = staging / ".lint-report.json"
        cmd = [sys.executable, str(_LINTER), str(staging), "--json", str(lint_report_path)]
        if ruleset_path:
            cmd += ["--ruleset", str((manifest_dir / ruleset_path).resolve())]
        if strict:
            cmd.append("--strict")
        proc = subprocess.run(cmd, capture_output=True, text=True)
        lint_report = {}
        if lint_report_path.exists():
            lint_report = json.loads(lint_report_path.read_text(encoding="utf-8"))
            lint_report_path.unlink()

        fail_on = lint_conf.get("fail_on", "block")
        lint_status = lint_report.get("status", "error" if proc.returncode == 3 else "unknown")

        if proc.returncode == 2 or lint_status == "block":
            shutil.rmtree(staging, ignore_errors=True)
            return 2, {"status": "block", "lint": lint_report, "stderr": proc.stderr}
        if proc.returncode == 3:
            shutil.rmtree(staging, ignore_errors=True)
            return 3, {"status": "error", "errors": ["lint falhou ao executar"], "stderr": proc.stderr}
        if lint_status == "warn" and fail_on == "warn":
            shutil.rmtree(staging, ignore_errors=True)
            return 2, {"status": "block", "lint": lint_report, "reason": "fail_on=warn"}

        if generate.get("sanitizacao_md", True):
            # NUNCA ecoar os padroes de 'exclude' literalmente aqui: um exclude existe
            # justamente para OCULTAR um nome sensivel (ex.: um script/arquivo com IP de
            # terceiro) -- imprimir o padrao de volta no artefato publico anularia a propria
            # exclusao (o nome do que foi escondido vazaria no relatorio). Só a CONTAGEM
            # é reportada; o mesmo vale para 'replaces' (o 'find' pode conter o texto
            # sensível que está sendo substituído).
            for fname in _SANITIZATION_FILES:
                t = _SANITIZATION_TEXT[fname]
                lines = [_SANITIZATION_PAIR_LINK, "", f"# {fname}", "", f"Kit: {name} {version}", "",
                         t["applied_h"],
                         t["exclude"].format(n=len(exclude)),
                         t["replaces"].format(n=len(applied_replaces)),
                         "", t["lint_h"], f"- status: {lint_status}", f"- counts: {lint_report.get('counts', {})}"]
                _escreve_lf(staging / fname, "\n".join(lines) + "\n")

        emitted_files = files + (["LICENSE"] if generate.get("license", True) else [])
        if generate.get("sanitizacao_md", True):
            emitted_files = emitted_files + list(_SANITIZATION_FILES)
        if generate.get("checksums", True):
            write_checksums(staging, emitted_files)
            emitted_files = emitted_files + ["CHECKSUMS.txt"]

        if _go_verify and origin_snapshot is not None:
            drift_final = _go_verify(origin_snapshot, source_root, files)
            if drift_final:
                shutil.rmtree(staging, ignore_errors=True)
                return 3, {"status": "error", "errors": [
                    f"fonte mudou durante a montagem, detectado antes do swap final (guard_origins): {drift_final}"
                ]}

        final_dir = out_dir / f"{name}-{version}"
        new_checksums = (staging / "CHECKSUMS.txt").read_text(encoding="utf-8") if generate.get("checksums", True) else None
        if final_dir.exists() and new_checksums is not None:
            old_checksums_path = final_dir / "CHECKSUMS.txt"
            if old_checksums_path.exists() and old_checksums_path.read_text(encoding="utf-8") == new_checksums:
                shutil.rmtree(staging, ignore_errors=True)
                return 0, {"status": "no-op", "kit": name, "version": version, "reason": "CHECKSUMS idêntico"}

        if final_dir.exists():
            shutil.rmtree(final_dir)
        staging.rename(final_dir)

        zip_path = None
        zip_check = None
        if generate.get("zip", True):
            zip_path = out_dir / f"{name}-{version}.zip"
            write_zip(final_dir, files, zip_path)

            # Why: escrever nao e provar. O zip e o artefato que viaja, e precisa ser reaberto depois
            # de escrito.
            zip_check = verify_zip(zip_path, final_dir, files)
            if not zip_check["ok"]:
                # Parado, nao apagado: um zip que reprovou e EVIDENCIA. Mas ele
                # nao pode ficar com o nome do artefato bom, ou alguem instala.
                invalido = zip_path.parent / (zip_path.name + ".INVALIDO")
                if invalido.exists():
                    invalido.unlink()
                zip_path.rename(invalido)
                return 2, {
                    "status": "zip-reprovado",
                    "kit": name,
                    "version": version,
                    "out": str(final_dir),
                    "zip": None,
                    "zip_parado_em": str(invalido),
                    "files": len(emitted_files),
                    "lint": lint_report,
                    "zip_errors": zip_check["errors"],
                }

        report = {
            "status": "emitted",
            "kit": name,
            "version": version,
            "out": str(final_dir),
            "zip": str(zip_path) if zip_path else None,
            "zip_entries": zip_check["entries"] if zip_check else None,
            "files": len(emitted_files),
            "lint": lint_report,
            # Why: os valores de find/replace ficam FORA do report pelo mesmo
            # motivo que ficam fora do SANITIZATION.md — o 'find' costuma ser
            # exatamente o texto sensivel que se esta escondendo.
            "sanitize": {
                "aplicadas": [
                    {"file": a["file"], "mode": a["mode"], "hits": a["hits"]}
                    for a in applied_replaces
                ],
                "avisos": sanitize_avisos,
            },
        }
        return (1 if lint_status == "warn" else 0), report
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


def _self_test() -> int:
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="kit_assembler_selftest_"))
    try:
        src = tmp / "src"
        src.mkdir()
        (src / "README.md").write_text("# Fixture Kit\nnada de suspeito\n", encoding="utf-8")
        (src / "scripts").mkdir()
        (src / "scripts" / "hello.py").write_text("print('hello')\n", encoding="utf-8")
        (src / "operator-profile.yaml").write_text("real: true\n", encoding="utf-8")

        ruleset = tmp / "ip-ruleset.example.yaml"
        ruleset.write_text("version: 1\nbanned_terms: {clients: [], infra: [], identity: []}\nderived: {filenames: [], content: []}\n", encoding="utf-8")

        manifest = {
            "kit": {"name": "fixture-kit", "version": "1.0.0", "license": "MIT", "author": "Test Author", "year": 2026, "source_root": "src"},
            "include": ["**"],
            "exclude": ["operator-profile.yaml"],
            "generate": {"license": True, "sanitizacao_md": True, "checksums": True, "zip": True},
            "lint": {"ruleset": "ip-ruleset.example.yaml", "fail_on": "block"},
        }

        out_dir = tmp / "dist"
        out_dir.mkdir()

        code, report = run_pipeline(manifest, tmp, out_dir, dry_run=True, strict=False)
        assert code == 0 and report["status"] == "dry-run", f"dry-run falhou: {report}"
        assert "operator-profile.yaml" not in report["files"], "exclude não funcionou no dry-run"
        assert "README.md" in report["files"] and "scripts/hello.py" in report["files"]

        code1, report1 = run_pipeline(manifest, tmp, out_dir, dry_run=False, strict=False)
        assert code1 == 0, f"1a emissão deveria ser exit 0: {report1}"
        final_dir = Path(report1["out"])
        assert (final_dir / "LICENSE").exists(), "LICENSE não gerado"
        for fname in _SANITIZATION_FILES:
            assert (final_dir / fname).exists(), f"{fname} não gerado"
        assert not (final_dir / "SANITIZACAO.md").exists(), "o nome antigo voltou a ser emitido"
        assert (final_dir / "CHECKSUMS.txt").exists(), "CHECKSUMS.txt não gerado"
        assert not (final_dir / "operator-profile.yaml").exists(), "arquivo excluído vazou pro kit"
        assert Path(report1["zip"]).exists(), "zip não gerado"

        code2, report2 = run_pipeline(manifest, tmp, out_dir, dry_run=False, strict=False)
        assert code2 == 0 and report2["status"] == "no-op", f"2a emissão deveria ser no-op: {report2}"

        (src / "scripts" / "hello.py").write_text("print('hello v2')\n", encoding="utf-8")
        code3, report3 = run_pipeline(manifest, tmp, out_dir, dry_run=False, strict=False)
        assert code3 == 0 and report3["status"] == "emitted", f"mudança real deveria re-emitir: {report3}"

        (src / "scripts" / "leak.py").write_text('token = "sk-ant-FAKE1234567890abcd"\n', encoding="utf-8")
        code4, report4 = run_pipeline(manifest, tmp, out_dir, dry_run=False, strict=False)
        assert code4 == 2, f"sabotagem deveria bloquear: {report4}"
        assert not any(p.name.startswith(".staging-") for p in out_dir.iterdir()), "staging temporário vazou (não foi limpo)"
        (src / "scripts" / "leak.py").unlink()

        bad_manifest = {"kit": {"name": "x"}, "include": []}
        code5, report5 = run_pipeline(bad_manifest, tmp, out_dir, dry_run=False, strict=False)
        assert code5 == 3, f"manifesto inválido deveria dar exit 3: {report5}"

        # O teste que FORCA A REPROVAR (gateguard § NASCIMENTO DE GATE): plugin.json na fonte
        # com versao divergente do manifesto tem de dar exit 3 SEM ninguem injetar plugin_json.
        (src / ".claude-plugin").mkdir()
        (src / ".claude-plugin" / "plugin.json").write_text('{"name": "fixture-kit", "version": "9.9.9"}\n', encoding="utf-8")
        code6, report6 = run_pipeline(manifest, tmp, out_dir, dry_run=True, strict=False)
        assert code6 == 3 and any("diverge" in e for e in report6.get("errors", [])), f"plugin.json divergente deveria dar exit 3: {report6}"
        (src / ".claude-plugin" / "plugin.json").write_text('{"name": "fixture-kit", "version": "1.0.0"}\n', encoding="utf-8")
        code7, report7 = run_pipeline(manifest, tmp, out_dir, dry_run=True, strict=False)
        assert code7 == 0 and report7["status"] == "dry-run", f"plugin.json igual ao manifesto deveria passar: {report7}"

        print("self-test OK — dry-run, emissão, no-op, re-emissão, sabotagem, manifesto inválido e plugin.json divergente cobertos")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="kit_assembler.py")
    p.add_argument("--manifest", default=None)
    p.add_argument("--out", default=None)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--json", dest="json_out", default=None)
    p.add_argument("--strict", action="store_true")
    p.add_argument("--self-test", action="store_true")
    return p


def main(argv) -> int:
    args = build_parser().parse_args(argv)

    if args.self_test:
        return _self_test()

    if not args.manifest:
        print("uso: kit_assembler.py --manifest <manifest.yaml> [--out dir] [--dry-run] [--json out.json] [--strict]", file=sys.stderr)
        return 3

    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        print(f"kit_assembler: manifesto não encontrado: {manifest_path}", file=sys.stderr)
        return 3

    try:
        manifest = load_manifest(manifest_path)
    except Exception as e:  # noqa: BLE001
        print(f"kit_assembler: manifesto inválido: {e}", file=sys.stderr)
        return 3

    out_dir = Path(args.out) if args.out else (_ROOT / "dist")
    out_dir.mkdir(parents=True, exist_ok=True)

    code, report = run_pipeline(manifest, manifest_path.parent, out_dir, args.dry_run, args.strict)

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))

    return code


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    sys.exit(main(sys.argv[1:]))

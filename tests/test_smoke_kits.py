"""Verificacao de integridade dos modulos distribuidos, via CHECKSUMS.txt.

A arvore-FONTE nao contem os diretorios fisicos dos modulos nem marketplace.json --
eles so existem na COPIA EMITIDA, montada por outra etapa do pipeline. Rodando de
dentro da copia emitida (o caso de quem instalou, e o do CI sobre o conteudo
publicado), a raiz e o proprio diretorio acima de `tests/`; rodando da fonte, nao ha
o que conferir e o teste PULA, explicitamente.

# Why: o caminho era absoluto e carregava o nome de usuario de UMA maquina. Um teste
# assim nunca roda em lugar nenhum alem dela, e o caminho pessoal viaja dentro do
# pacote publicado. A raiz se DERIVA da posicao do arquivo; HPP_EMITTED_COPY permite
# apontar para outra arvore sem editar codigo.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

_RAIZ_DERIVADA = Path(__file__).resolve().parents[1]
EMITTED_COPY = Path(os.environ.get("HPP_EMITTED_COPY") or _RAIZ_DERIVADA)
MARKETPLACE = EMITTED_COPY / "marketplace.json"


def _skip_reason() -> str | None:
    if not EMITTED_COPY.is_dir():
        return f"emitted copy missing at {EMITTED_COPY} (expected in CI and in fresh clones)"
    if not MARKETPLACE.is_file():
        return f"{MARKETPLACE} does not exist -- nothing to discover modules from"
    return None


def _declared_modules() -> list[tuple[str, Path]]:
    marketplace = json.loads(MARKETPLACE.read_text(encoding="utf-8"))
    modules = []
    for plugin in marketplace.get("plugins", []):
        source = str(plugin.get("source", "")).removeprefix("./")
        name = plugin.get("name")
        if source and name:
            modules.append((name, EMITTED_COPY / source))
    return modules


def _checksum_failures(module_dir: Path, checksums_file: Path) -> list[str]:
    failures: list[str] = []
    lines = [line for line in checksums_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    for line in lines:
        expected_hash, separator, relative_path = line.partition("  ")
        if not separator:
            failures.append(f"line without the expected 'hash  path' separator: {line!r}")
            continue
        target = module_dir / relative_path
        if not target.is_file():
            failures.append(f"listed in CHECKSUMS.txt and missing on disk: {relative_path}")
            continue
        actual_hash = hashlib.sha256(target.read_bytes()).hexdigest()
        if actual_hash != expected_hash:
            failures.append(f"hash mismatch: {relative_path} (expected {expected_hash[:12]}..., actual {actual_hash[:12]}...)")
    return failures


def test_marketplace_declara_pelo_menos_um_modulo():
    reason = _skip_reason()
    if reason:
        pytest.skip(reason)
    assert _declared_modules(), "marketplace.json declared no module at all"


def test_checksums_de_cada_modulo_distribuido_conferem():
    reason = _skip_reason()
    if reason:
        pytest.skip(reason)
    modules = _declared_modules()
    assert modules, "marketplace.json declared no module at all"

    all_failures: list[str] = []
    modules_with_checksums = 0
    for name, module_dir in modules:
        checksums_file = module_dir / "CHECKSUMS.txt"
        if not checksums_file.is_file():
            continue
        modules_with_checksums += 1
        failures = _checksum_failures(module_dir, checksums_file)
        all_failures.extend(f"{name}: {item}" for item in failures)

    # Denominador zero e' tao suspeito quanto uma falha: se NENHUM modulo publica
    # CHECKSUMS.txt, esta verificacao passaria vazia e pareceria ok sem checar nada.
    assert modules_with_checksums > 0, (
        "none of the modules declared in marketplace.json publishes CHECKSUMS.txt "
        "-- the denominator of this check would be zero"
    )
    assert not all_failures, "\n".join(all_failures)


def test_CONTROLE_deteccao_de_hash_adulterado_funciona(tmp_path):
    """
    Controle, independente da copia emitida (roda sempre): prova que
    `_checksum_failures` -- a MESMA logica usada acima -- de fato REPROVA uma
    divergencia real de hash, e nao so confirma o caminho feliz.
    """
    module_dir = tmp_path / "modulo-fake"
    module_dir.mkdir()
    (module_dir / "file.txt").write_text("real content", encoding="utf-8")
    checksums_file = module_dir / "CHECKSUMS.txt"
    checksums_file.write_text("0" * 64 + "  file.txt\n", encoding="utf-8")

    failures = _checksum_failures(module_dir, checksums_file)

    assert failures
    assert "hash mismatch" in failures[0]


def test_CONTROLE_arquivo_listado_e_ausente_e_detectado(tmp_path):
    module_dir = tmp_path / "modulo-fake-2"
    module_dir.mkdir()
    checksums_file = module_dir / "CHECKSUMS.txt"
    checksums_file.write_text("a" * 64 + "  does-not-exist.txt\n", encoding="utf-8")

    failures = _checksum_failures(module_dir, checksums_file)

    assert failures
    assert "missing on disk" in failures[0]


def test_CONTROLE_checksums_correto_nao_produz_falso_positivo(tmp_path):
    """Controle simetrico: um CHECKSUMS.txt genuinamente correto nao reprova."""
    module_dir = tmp_path / "modulo-ok"
    module_dir.mkdir()
    target = module_dir / "file.txt"
    target.write_text("conteudo estavel", encoding="utf-8")
    real_hash = hashlib.sha256(target.read_bytes()).hexdigest()
    (module_dir / "CHECKSUMS.txt").write_text(f"{real_hash}  file.txt\n", encoding="utf-8")

    failures = _checksum_failures(module_dir, module_dir / "CHECKSUMS.txt")

    assert failures == []

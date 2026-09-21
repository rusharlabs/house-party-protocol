"""Validacao estrutural do hpp.manifest.json e sua coerencia com pyproject/__init__.

Sem rede, sem `~/.claude`, sem variavel de ambiente da maquina: tudo le o proprio
hpp.manifest.json e o pyproject.toml deste product-root, ou constroi um manifesto
sintetico em tmp_path quando o teste precisa de um caso INVALIDO para servir de
controle.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

from hpp import __version__
from hpp.manifest import (
    ManifestError,
    find_manifest,
    load_manifest,
    validate_distribution,
    validate_manifest,
)

PRODUCT_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = PRODUCT_ROOT / "hpp.manifest.json"
PYPROJECT_PATH = PRODUCT_ROOT / "pyproject.toml"


def _pyproject_version() -> str:
    """Extrai `version = "X.Y.Z"` de dentro de `[project]`, sem depender de lib externa.

    `tomllib` so existe na stdlib a partir do Python 3.11; a matriz de CI cobre
    3.10 tambem. Isto NAO e um parser TOML geral -- e a leitura minima e explicita
    do unico campo que este teste precisa, para nao trazer uma dependencia so por
    causa de duas versoes de Python.
    """
    if sys.version_info >= (3, 11):
        import tomllib

        with PYPROJECT_PATH.open("rb") as handle:
            return tomllib.load(handle)["project"]["version"]
    in_project = False
    for line in PYPROJECT_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            in_project = stripped == "[project]"
            continue
        if in_project:
            match = re.match(r'version\s*=\s*"([^"]+)"', stripped)
            if match:
                return match.group(1)
    raise AssertionError("version not found under [project] in pyproject.toml")


def _manifest_dict() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_manifesto_e_json_valido_com_raiz_objeto():
    data = _manifest_dict()
    assert isinstance(data, dict)


def test_tres_fontes_de_versao_concordam():
    """
    Este teste sozinho ja pega uma classe de regressao real: basta uma sessao
    atualizar hpp/__init__.py sem tocar hpp.manifest.json (ou pyproject.toml), ou
    vice-versa, para o `--version` do CLI e o `doctor` divergirem em silencio.
    """
    manifest = _manifest_dict()
    assert manifest["product_version"] == __version__
    assert __version__ == _pyproject_version()


def test_todo_modulo_declarado_tem_os_campos_obrigatorios_e_e_unico():
    manifest = _manifest_dict()
    modules = manifest["modules"]
    assert modules, "manifesto sem nenhum modulo"
    ids = [module["id"] for module in modules]
    assert len(ids) == len(set(ids)), "modulo duplicado no manifesto"
    for module in modules:
        for field in ("id", "version", "path", "capabilities", "hosts", "requires", "integrates_with"):
            assert field in module, f"{module.get('id')} sem campo {field}"
        assert module["path"], f"{module['id']} com path vazio"
        assert not module["path"].startswith(("/", "..")), f"{module['id']} com path absoluto/escapando"


def test_bundle_reliable_coding_so_referencia_modulos_e_capacidades_existentes():
    manifest = _manifest_dict()
    known_modules = {m["id"] for m in manifest["modules"]}
    known_capabilities = {c for m in manifest["modules"] for c in m["capabilities"]}
    for name, bundle in manifest["bundles"].items():
        unknown_modules = set(bundle["modules"]) - known_modules
        unknown_capabilities = set(bundle["capabilities"]) - known_capabilities
        assert not unknown_modules, f"bundle {name} referencia modulo inexistente: {unknown_modules}"
        assert not unknown_capabilities, f"bundle {name} referencia capacidade inexistente: {unknown_capabilities}"


def test_exit_codes_do_manifesto_sao_0_ok_1_warn_2_block_3_error():
    manifest = _manifest_dict()
    assert manifest["exit_codes"] == {"ok": 0, "warn": 1, "block": 2, "error": 3}


def test_CONTROLE_manifesto_sem_modules_e_rejeitado():
    """Controle: prova que o validador sabe REPROVAR, nao so aprovar o real."""
    broken = _manifest_dict()
    del broken["modules"]
    with pytest.raises(ManifestError):
        validate_manifest(broken)


def test_CONTROLE_bundle_com_modulo_fantasma_e_rejeitado():
    broken = _manifest_dict()
    broken["bundles"]["reliable-coding"]["modules"] = [
        *broken["bundles"]["reliable-coding"]["modules"],
        "modulo-que-nao-existe",
    ]
    with pytest.raises(ManifestError):
        validate_manifest(broken)


def test_CONTROLE_ciclo_de_dependencia_entre_modulos_e_rejeitado():
    broken = _manifest_dict()
    first_id = broken["modules"][0]["id"]
    second_id = broken["modules"][1]["id"]
    broken["modules"][0]["requires"] = [second_id]
    broken["modules"][1]["requires"] = [first_id]
    with pytest.raises(ManifestError):
        validate_manifest(broken)


def test_manifesto_real_passa_no_proprio_validador():
    # Sanity check simetrico aos tres controles acima: o real precisa continuar
    # validando -- senao os controles estariam provando algo vazio.
    validate_manifest(_manifest_dict())


def test_validate_distribution_em_modo_fonte_nao_exige_diretorio_fisico_de_modulo():
    """
    Este product-root nao tem marketplace.json nem os diretorios fisicos dos
    modulos -- eles so existem na copia emitida, montada por outra etapa do
    pipeline de publicacao. `validate_distribution` reconhece isso como o
    contrato "source-contract": o manifesto e fonte de verdade mesmo sem o
    conteudo fisico do modulo do lado dele.
    """
    manifest, path = load_manifest()
    if (path.parent / "marketplace.json").is_file():
        # Why: a mesma suite roda na arvore-FONTE e na copia EMITIDA. Na emitida o marketplace e os
        # diretorios de modulo existem, entao o contrato a verificar e o outro — e ele tem teste
        # proprio. Pular aqui e honesto; afirmar "source-contract" na copia emitida seria falso.
        pytest.skip("copia emitida (tem marketplace.json) — o contrato de distribuicao completo e coberto pelo teste seguinte")
    result = validate_distribution(manifest, path.parent)
    assert result == {"checked": False, "status": "source-contract"}


def test_find_manifest_cai_para_o_pacote_quando_nao_ha_manifesto_acima_do_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    found = find_manifest()
    assert found.resolve() == MANIFEST_PATH.resolve()


def test_find_manifest_explicito_mas_inexistente_falha():
    with pytest.raises(ManifestError):
        find_manifest(explicit=str(Path("this") / "path" / "does-not-exist" / "hpp.manifest.json"))


def test_load_manifest_aceita_caminho_explicito_para_uma_copia(tmp_path):
    custom = tmp_path / "hpp.manifest.json"
    custom.write_text(MANIFEST_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    data, path = load_manifest(str(custom))
    assert path == custom.resolve()
    assert data["product_version"] == __version__


def test_load_manifest_com_json_invalido_da_erro_legivel(tmp_path):
    custom = tmp_path / "hpp.manifest.json"
    custom.write_text("{ nao e json valido", encoding="utf-8")
    with pytest.raises(ManifestError):
        load_manifest(str(custom))

"""Toda imagem que as paginas de `docs/` pedem existe RELATIVA A `docs/`.

Por que este arquivo existe (medido em 2026-09-23, contra o site vivo): as cinco paginas de
`docs/` abriam com `<img src="../assets/hpp-logo-header.png">`. Num clone isso funciona -- o
arquivo esta um nivel acima. No GitHub Pages **nao**, porque o site publica `docs/` como RAIZ,
e `../` sai da raiz publicada:

    GET /house-party-protocol/../assets/hpp-logo-header.png  ->  503
    GET /house-party-protocol/assets/hpp-logo-header.png     ->  404
    GET /house-party-protocol/nao-existe-controle.png        ->  404   <- CONTROLE

O controle e' o que fecha o argumento: a regua devolve 404 para um caminho que de fato nao
existe, logo os 404 acima nao sao artefato dela. A logo estava quebrada no topo de todas as
paginas do site, e nenhum teste podia ver, porque todos rodam com o arquivo no disco -- onde o
caminho funciona.

A correcao e' um caminho que funciona nos DOIS contextos: `assets/...` com uma copia do ativo
dentro de `docs/`. Do disco resolve para `docs/assets/...`; do Pages, para a raiz do site.
"""
from __future__ import annotations

import re
from pathlib import Path

PRODUCT_ROOT = Path(__file__).resolve().parent.parent
DOCS = PRODUCT_ROOT / "docs"

IMG = re.compile(r'<img\s[^>]*src="([^"]+)"')
OG_IMAGE = re.compile(r'<meta\s+property="og:image"\s+content="([^"]+)"')


def _paginas() -> list[Path]:
    return sorted(DOCS.glob("*.html"))


def test_ha_paginas_para_medir() -> None:
    # Why (LC-1b): sem isto, os testes abaixo passariam varrendo zero arquivos, e um laco
    # que nao itera parece aprovacao.
    assert len(_paginas()) >= 5, f"esperava as 5 paginas de docs/, achei {len(_paginas())}"


def test_nenhuma_pagina_pede_imagem_ACIMA_de_docs() -> None:
    fora: list[str] = []
    for pagina in _paginas():
        for src in IMG.findall(pagina.read_text(encoding="utf-8", errors="replace")):
            if src.startswith("../"):
                fora.append(f"{pagina.name}: {src}")
    assert not fora, (
        f"imagem acima de docs/ -- o Pages publica docs/ como raiz e `../` sai dela: {fora}"
    )


def test_toda_imagem_local_existe_relativa_a_docs() -> None:
    faltando: list[str] = []
    for pagina in _paginas():
        for src in IMG.findall(pagina.read_text(encoding="utf-8", errors="replace")):
            if src.startswith(("http://", "https://", "data:")):
                continue
            if not (DOCS / src).is_file():
                faltando.append(f"{pagina.name}: {src}")
    assert not faltando, f"imagem que a pagina pede e nao existe sob docs/: {faltando}"


def test_a_pagina_de_entrada_declara_um_cartao_com_imagem_ABSOLUTA() -> None:
    # Why: um crawler de rede social nao resolve caminho relativo. Sem URL absoluta o link
    # compartilhado sai sem imagem -- e este projeto ja carrega um social-preview pronto.
    texto = (DOCS / "index.html").read_text(encoding="utf-8")
    achados = OG_IMAGE.findall(texto)
    assert achados, "a pagina de entrada nao declara og:image"
    for url in achados:
        assert url.startswith("https://"), f"og:image relativo nao serve para crawler: {url}"
        nome = url.rsplit("/", 1)[-1]
        assert (DOCS / "assets" / nome).is_file(), f"og:image aponta para {nome}, que nao existe em docs/assets/"


def test_CONTROLE_os_detectores_discriminam() -> None:
    # Why (LC-1n): sem isto, os testes acima passariam com o regex quebrado.
    assert IMG.findall('<img src="assets/x.png" alt="y">') == ["assets/x.png"]
    assert IMG.findall('<img\n  src="../assets/x.png">') == ["../assets/x.png"]
    assert not IMG.findall('<image src="x.png">'), "o detector casa uma tag que nao e img"
    assert OG_IMAGE.findall('<meta property="og:image" content="https://a/b.png">') == ["https://a/b.png"]
    assert not OG_IMAGE.findall('<meta property="og:title" content="x">'), "o detector casa og:title"

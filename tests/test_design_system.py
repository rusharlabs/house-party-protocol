"""The stylesheet is a file, it matches every page, and its palette IS the brand's.

Why this file exists: the CSS that every published page renders with lived as a 3.294-character
string inside `tools/catalog_md.py`. Nothing was wrong with it -- measured, it uses exactly the
four hex values `docs/BRAND.md` declares and no fifth -- but nothing held it there either, and a
contributor who wanted to build in the project's language had to open a Python file and copy a
literal out of it.

The stylesheet is now emitted as `docs/hpp.css` from the same constant the pages inline, so the
two cannot drift by construction. These tests lock the part that a future edit could still break:
that the palette stays the brand's, that no fifth colour arrives through an `rgba()`, and that no
page starts fetching a font or a stylesheet from someone else's domain.
"""
from __future__ import annotations

import re
from pathlib import Path

PRODUCT_ROOT = Path(__file__).resolve().parent.parent
DOCS = PRODUCT_ROOT / "docs"
CSS = DOCS / "hpp.css"
BRAND = DOCS / "BRAND.md"
# Why: as paginas GERADAS embutem a folha do gerador; o MANUAL e' escrito A MAO na fonte
# (`scripts/kits/product-root/docs/`) e carrega o proprio CSS. Sao invariantes diferentes, e
# juntar as duas num teste so' produziu uma falha que parecia defeito do produto e era da
# assercao. Quem mover o MANUAL para o gerador muda esta lista -- e o teste cobra.
GERADAS = ("CATALOG.html", "CATALOG.pt-BR.html", "index.html")
A_MAO = ("MANUAL.html", "MANUAL.pt-BR.html")

HEX = re.compile(r"#[0-9a-fA-F]{6}\b")
# Why: BRAND.md allows a token at reduced alpha explicitly -- "a lighter step is the same token
# at reduced opacity" -- and the stylesheet uses two of them that way, the ink AND the paper. Any
# OTHER rgb triple is a fifth colour arriving through the side door, where a hex scan never sees
# it. The allowed triples are DERIVED from BRAND.md rather than written here: a hard-coded list
# would have to be edited whenever the palette moves, and the edit is what would be forgotten.
RGBA = re.compile(r"rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})")
# Why: BRAND.md — "No published asset carries a webfont: the stack is system-only, and the
# self-contained material makes no external request."
EXTERNO = re.compile(r"@import|url\(\s*['\"]?https?://|@font-face")


def _paleta(texto: str) -> set[str]:
    return {h.upper() for h in HEX.findall(texto)}


def test_a_folha_de_estilo_e_um_arquivo() -> None:
    assert CSS.is_file(), "docs/hpp.css nao existe — o CSS voltou a viver so' dentro do gerador"
    assert CSS.stat().st_size > 1000, "hpp.css existe mas esta vazio ou truncado"


def test_a_paleta_do_CSS_e_exatamente_a_do_BRAND() -> None:
    do_css = _paleta(CSS.read_text(encoding="utf-8"))
    do_brand = _paleta(BRAND.read_text(encoding="utf-8"))
    assert do_brand, "BRAND.md deixou de declarar hex — sem isso nao ha com o que comparar"
    assert do_css == do_brand, (
        f"a paleta divergiu · so no CSS: {sorted(do_css - do_brand)} · "
        f"so no BRAND: {sorted(do_brand - do_css)}"
    )


def _triplas_do_brand() -> set[tuple[str, str, str]]:
    """Os hex do BRAND.md como triplas decimais — o universo permitido para um rgb()."""
    out = set()
    for h in _paleta(BRAND.read_text(encoding="utf-8")):
        out.add(tuple(str(int(h[i:i + 2], 16)) for i in (1, 3, 5)))
    return out


def test_nenhuma_quinta_cor_entra_por_rgba() -> None:
    permitidas = _triplas_do_brand()
    assert permitidas, "sem hex no BRAND.md nao ha universo permitido — nao reportavel"
    fora = [t for t in RGBA.findall(CSS.read_text(encoding="utf-8")) if t not in permitidas]
    assert not fora, f"rgb() que nao e token do BRAND: {fora}"


def test_o_CSS_nao_faz_pedido_externo() -> None:
    achados = EXTERNO.findall(CSS.read_text(encoding="utf-8"))
    assert not achados, f"pedido externo na folha de estilo: {achados}"


def test_toda_pagina_embute_a_MESMA_folha() -> None:
    # Why: as paginas continuam autossuficientes (inline), e o arquivo existe para quem
    # contribui. Sao dois consumidores da mesma constante; este teste e' o que prova que
    # continuam sendo a mesma coisa depois de qualquer edicao.
    folha = CSS.read_text(encoding="utf-8").strip()
    for nome in GERADAS:
        p = DOCS / nome
        assert p.is_file(), f"{nome} nao existe"
        assert folha in p.read_text(encoding="utf-8"), f"{nome} embute um CSS diferente do arquivo"


def test_a_pagina_escrita_a_mao_usa_a_MESMA_paleta() -> None:
    # Why: o MANUAL nao vem do gerador, entao nao se pode exigir a folha inteira. O que se pode
    # exigir -- e e' o que importa -- e' que ele nao invente cor: a paleta dele tem de caber na
    # do BRAND. Sem este teste, uma quinta cor entraria pela unica porta que o resto nao cobre.
    do_brand = _paleta(BRAND.read_text(encoding="utf-8"))
    for nome in A_MAO:
        p = DOCS / nome
        assert p.is_file(), f"{nome} nao existe"
        fora = _paleta(p.read_text(encoding="utf-8")) - do_brand
        assert not fora, f"{nome} usa cor fora do BRAND: {sorted(fora)}"


def test_CONTROLE_os_detectores_acusam_quando_ha() -> None:
    # Why (LC-1n): sem isto, os quatro testes acima passariam com os regex quebrados — padrao
    # que nao casa nada devolve conjunto vazio, e vazio parece aprovacao.
    assert _paleta("cor: #AABBCC;") == {"#AABBCC"}, "o detector de hex nao ve um hex"
    assert RGBA.findall("rgba(1,2,3,.5)") == [("1", "2", "3")], "o detector de rgb nao ve um rgb"
    assert EXTERNO.findall("@import url('https://x/y.css')"), "o detector de externo nao ve @import"
    assert not EXTERNO.findall("background:url(../assets/x.png)"), "o detector acusa asset local"

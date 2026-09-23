"""The docs folder has a landing page, and it is generated — not written by hand.

Why this file exists: GitHub does not render `.html` from a repository; it shows the source.
Measured before the page existed: the four catalogue and manual pages were reachable only by
someone who cloned, and the Pages root answered 404. The landing page is what makes them a site.

It is asserted here rather than only in the generator's self-test because the self-test proves
the tool can build a page, while this proves the page that SHIPPED is the one the tool builds
and that it points at files which exist next to it.
"""
from __future__ import annotations

import re
from pathlib import Path

PRODUCT_ROOT = Path(__file__).resolve().parent.parent
DOCS = PRODUCT_ROOT / "docs"
INDEX = DOCS / "index.html"

# Why: a site that fetches a stylesheet or a script from someone else's domain stops being
# self-contained the day that domain does. The four pages carry their CSS inline; the landing
# page has to hold the same line.
EXTERNO = re.compile(r'(?:src|href)="https?://[^"]+\.(?:js|css)"')
HREF = re.compile(r'href="([^"]+)"')


def _texto() -> str:
    return INDEX.read_text(encoding="utf-8")


def test_a_pagina_de_entrada_existe() -> None:
    assert INDEX.is_file(), "docs/index.html nao existe — a raiz do Pages responderia 404"


def test_ela_aponta_para_as_quatro_paginas_e_todas_existem() -> None:
    alvos = {"CATALOG.html", "CATALOG.pt-BR.html", "MANUAL.html", "MANUAL.pt-BR.html"}
    hrefs = set(HREF.findall(_texto()))
    faltando = alvos - hrefs
    assert not faltando, f"a pagina de entrada nao linka: {sorted(faltando)}"
    for alvo in alvos:
        assert (DOCS / alvo).is_file(), f"a pagina de entrada linka {alvo}, que nao existe"


def test_nao_busca_css_nem_js_de_terceiro() -> None:
    achados = EXTERNO.findall(_texto())
    assert not achados, f"dependencia externa na pagina de entrada: {achados}"


def test_declara_idioma_nas_duas_secoes() -> None:
    # Why: as duas linguas convivem na mesma pagina; sem `lang` o leitor de tela le portugues
    # com fonemas ingleses, e um crawler indexa as duas como uma.
    texto = _texto()
    assert 'lang="en"' in texto and 'lang="pt-BR"' in texto


def test_CONTROLE_o_detector_de_externo_acusa_quando_ha() -> None:
    # Why (LC-1n): sem isto, `test_nao_busca_css_nem_js_de_terceiro` passaria com o regex
    # quebrado — um padrao que nao casa nada devolve lista vazia, e vazio parece aprovacao.
    assert EXTERNO.findall('<link href="https://cdn.example/x.css">'), "o detector nao ve um CSS externo"
    assert not EXTERNO.findall('<link href="style.css">'), "o detector acusa um CSS local"

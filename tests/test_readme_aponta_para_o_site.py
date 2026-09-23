"""O README manda o leitor para uma pagina que ele consegue LER.

Por que este arquivo existe (medido em 2026-09-23): os dois README linkavam
`docs/MANUAL.html` e `docs/CATALOG.html` como caminho do repositorio. O GitHub nao
renderiza HTML de dentro de um repositorio -- ele mostra o CODIGO-FONTE. Quem clicasse
em "manual" a partir da pagina do projeto recebia uma parede de markup, nao o manual.
E o README em portugues linkava `MANUAL.html`, a versao em INGLES, existindo o
`MANUAL.pt-BR.html` ao lado.

O conserto so' virou possivel quando o Pages entrou no ar, porque ai as mesmas paginas
passaram a existir num endereco que RENDERIZA. Este teste e' o que impede a volta:
publicar HTML por caminho de repositorio parece certo, ate alguem clicar.
"""
from __future__ import annotations

import re
from pathlib import Path

PRODUCT_ROOT = Path(__file__).resolve().parent.parent
SITE = "https://rusharlabs.github.io/house-party-protocol/"
READMES = ("README.md", "README.pt-BR.md")

# Um link markdown para um .html DENTRO do repositorio. O `(?!http)` e' o que separa
# "caminho do repo" de "endereco do site" -- o segundo renderiza, o primeiro nao.
HTML_DO_REPO = re.compile(r"\]\((?!http)([^)]*\.html)\)")
# Uma pagina renderizada que existe em ingles E em portugues. No README pt-BR, linkar a
# forma sem `pt-BR` entrega o material no idioma errado.
SO_EM_INGLES = re.compile(r"/(MANUAL|CATALOG)\.html")


def _texto(nome: str) -> str:
    return (PRODUCT_ROOT / nome).read_text(encoding="utf-8")


def test_os_dois_readme_linkam_o_site() -> None:
    for nome in READMES:
        assert SITE in _texto(nome), f"{nome} nao linka o site do projeto ({SITE})"


def test_nenhum_readme_linka_html_por_caminho_de_repositorio() -> None:
    for nome in READMES:
        achados = HTML_DO_REPO.findall(_texto(nome))
        assert not achados, (
            f"{nome} linka HTML por caminho de repositorio: {achados}. "
            "O GitHub mostra o codigo-fonte desses arquivos; use o endereco do site."
        )


def test_o_readme_em_portugues_nao_manda_o_leitor_para_a_pagina_em_ingles() -> None:
    achados = SO_EM_INGLES.findall(_texto("README.pt-BR.md"))
    assert not achados, (
        f"README.pt-BR.md aponta para a versao em ingles de: {achados}. "
        "As duas paginas existem com sufixo .pt-BR.html."
    )


def test_a_grafia_do_endereco_e_a_MESMA_nos_dois() -> None:
    # Why: um erro de digitacao em um dos dois produz 404 so' para metade dos leitores,
    # e ninguem que le no seu proprio idioma percebe.
    hosts = {
        m for nome in READMES
        for m in re.findall(r"https://[a-z0-9.-]+\.github\.io/[a-z0-9./-]*", _texto(nome))
    }
    fora = {h for h in hosts if not h.startswith(SITE.rstrip("/"))}
    assert not fora, f"endereco de site divergente: {sorted(fora)}"


def test_CONTROLE_os_detectores_acusam_quando_ha_o_que_acusar() -> None:
    # Why (LC-1n): sem isto, os dois testes acima passariam com o regex quebrado --
    # um padrao que nao casa nada devolve lista vazia, e vazio parece aprovacao.
    assert HTML_DO_REPO.findall("[manual](docs/MANUAL.html)"), "o detector nao ve HTML do repo"
    assert not HTML_DO_REPO.findall(f"[manual]({SITE}MANUAL.html)"), "o detector acusa o site"
    assert not HTML_DO_REPO.findall("[tips](docs/TIPS.md)"), "o detector acusa um .md"
    assert SO_EM_INGLES.findall(f"{SITE}MANUAL.html"), "o detector nao ve a pagina em ingles"
    assert not SO_EM_INGLES.findall(f"{SITE}MANUAL.pt-BR.html"), "o detector acusa a pt-BR"

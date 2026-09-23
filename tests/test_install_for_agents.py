"""The agent-facing install guide cannot drift from the README, the CLI or the version.

Why this file exists: `INSTALL_FOR_AGENTS.md` is the fourth place in this repository that tells
someone how to install the harness -- after the README, `hpp init` and `hpp.manifest.json`. A
fourth copy with nothing tying it down is the copy that rots, and a rotted install guide is
worse than none: an agent follows it, installs a version that is not the one shipped, and
reports success. The suggestion to add the guide came with this condition attached.

The install command is compared as an exact string, not parsed. The point is not that both
files mention `pip`; it is that a person who fixes the README and forgets this file gets a red
test in the same run.
"""
from __future__ import annotations

import re
from pathlib import Path

from hpp import __version__

PRODUCT_ROOT = Path(__file__).resolve().parent.parent
GUIA_EN = PRODUCT_ROOT / "INSTALL_FOR_AGENTS.md"
GUIA_PT = PRODUCT_ROOT / "INSTALL_FOR_AGENTS.pt-BR.md"
README_EN = PRODUCT_ROOT / "README.md"
README_PT = PRODUCT_ROOT / "README.pt-BR.md"
AGENTS = PRODUCT_ROOT / "AGENTS.md"

# Why a full-line anchor: the bump script rewrites the pinned tag as a whole line. A pattern
# that matched mid-line would also match prose about an older release and pass on a stale file.
INSTALL_LINE = re.compile(
    r"^pip install git\+https://github\.com/rusharlabs/house-party-protocol@v(?P<version>[0-9]+\.[0-9]+\.[0-9]+)$",
    re.M,
)
EXIT_CODES = "`0` ok · `1` warn/manual · `2` block · `3` error."


def _ler(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _comandos_de_instalacao(texto: str) -> list[str]:
    return INSTALL_LINE.findall(texto)


def test_os_quatro_arquivos_existem() -> None:
    for p in (GUIA_EN, GUIA_PT, README_EN, README_PT):
        assert p.is_file(), f"{p.name} nao existe"


def test_a_versao_pinada_no_guia_e_a_que_embarca() -> None:
    for guia in (GUIA_EN, GUIA_PT):
        achados = _comandos_de_instalacao(_ler(guia))
        assert achados, f"{guia.name}: nenhum comando de instalacao no formato esperado"
        assert set(achados) == {__version__}, (
            f"{guia.name} pina {sorted(set(achados))}, o pacote e {__version__}"
        )


def test_o_guia_e_o_readme_pinam_a_MESMA_versao() -> None:
    do_readme = set(_comandos_de_instalacao(_ler(README_EN))) | set(
        _comandos_de_instalacao(_ler(README_PT))
    )
    do_guia = set(_comandos_de_instalacao(_ler(GUIA_EN))) | set(
        _comandos_de_instalacao(_ler(GUIA_PT))
    )
    assert do_readme, "o README deixou de carregar o comando de instalacao"
    assert do_readme == do_guia, f"README pina {sorted(do_readme)}, guia pina {sorted(do_guia)}"


def test_os_codigos_de_saida_batem_com_AGENTS_md() -> None:
    # Why: um agente decide se para ou segue pelo exit code. Duas tabelas divergentes na mesma
    # arvore fazem ele parar no caso errado, e nenhuma das duas parece errada isolada.
    assert EXIT_CODES in _ler(AGENTS), "AGENTS.md mudou a tabela de exit codes"
    for guia in (GUIA_EN, GUIA_PT):
        assert EXIT_CODES in _ler(guia), f"{guia.name} divergiu da tabela de AGENTS.md"


def test_o_guia_exige_o_plano_antes_do_apply() -> None:
    # Why: este e' o unico passo do guia que protege a pessoa. Se ele sair numa reescrita, o
    # guia passa a ensinar um instalador que escreve antes de alguem ler -- a falha que o
    # proprio produto existe para impedir.
    assert "DO NOT SKIP" in _ler(GUIA_EN)
    assert "NÃO PULE" in _ler(GUIA_PT)
    for guia in (GUIA_EN, GUIA_PT):
        texto = _ler(guia)
        sem_apply = texto.index("hpp init --target")
        com_apply = texto.index("--apply", sem_apply)
        assert sem_apply < com_apply, f"{guia.name}: o --apply aparece antes do plano"


def test_o_README_aponta_para_o_guia() -> None:
    # Why: nenhum agente le este arquivo por convencao -- o nome nao e' padrao em lugar nenhum.
    # Ele so' e' encontrado se o README o anunciar, entao o ponteiro E' a feature.
    for readme in (README_EN, README_PT):
        assert "INSTALL_FOR_AGENTS" in _ler(readme), f"{readme.name} nao aponta para o guia"


def test_CONTROLE_o_detector_reprova_uma_versao_divergente() -> None:
    # Why (LC-1n): sem este controle, os testes acima passariam com o regex quebrado -- um
    # padrao que nao casa nada devolve lista vazia, e "vazio == vazio" e' verdadeiro.
    falso = "pip install git+https://github.com/rusharlabs/house-party-protocol@v0.0.1"
    assert _comandos_de_instalacao(falso) == ["0.0.1"], "o detector nao le a versao"
    assert _comandos_de_instalacao("pip install house-party-protocol") == [], (
        "o detector casa uma linha que nao e' a forma pinada"
    )

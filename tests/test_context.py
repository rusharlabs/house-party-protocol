"""Compilacao de contexto: orcamento nunca estoura, o numero publicado e o
tamanho real do texto produzido, e material parecido com segredo e recusado.
"""
from __future__ import annotations

import pytest

from hpp.context import ContextError, compile_context


def _item(source, priority, content):
    return {"source": source, "priority": priority, "content": content}


def test_todo_input_que_cabe_e_incluido_por_inteiro_e_o_orcamento_nunca_estoura():
    inputs = [_item("a", 10, "x" * 50), _item("b", 5, "y" * 50)]
    result = compile_context(inputs, budget=200)
    assert result["used"] <= result["budget"]
    assert result["used"] + result["remaining"] == result["budget"]
    assert [record["source"] for record in result["included"]] == ["a", "b"]
    assert result["omitted"] == []


def test_item_que_nao_cabe_e_omitido_por_inteiro_nunca_fatiado():
    big = _item("big", 10, "x" * 100)
    small = _item("small", 5, "y" * 10)
    result = compile_context([big, small], budget=50)
    included_sources = {record["source"] for record in result["included"]}
    omitted_sources = {record["source"] for record in result["omitted"]}
    assert included_sources | omitted_sources == {"big", "small"}
    assert included_sources.isdisjoint(omitted_sources)
    for record in result["included"]:
        assert record["chars"] <= result["budget"]


def test_prioridade_maior_entra_primeiro_quando_o_orcamento_aperta():
    high = _item("high", 100, "x" * 30)
    low = _item("low", 1, "y" * 30)
    result = compile_context([low, high], budget=30)  # so cabe um dos dois
    assert [record["source"] for record in result["included"]] == ["high"]
    assert [record["source"] for record in result["omitted"]] == ["low"]


def test_numero_de_chars_e_o_texto_final_batem_com_o_conteudo_real():
    inputs = [_item("a", 10, "abc"), _item("b", 5, "defgh")]
    result = compile_context(inputs, budget=1000)
    by_source = {record["source"]: record["content"] for record in inputs}
    for record in result["included"]:
        assert record["chars"] == len(by_source[record["source"]])
    expected_text = "\n\n".join(by_source[record["source"]] for record in result["included"])
    assert result["text"] == expected_text
    # "used" e' o numero PUBLICADO como custo de orcamento -- ele tem de bater com
    # o tamanho REAL do texto produzido (inclusive os separadores entre blocos),
    # nao so a soma dos "chars" de cada item isolado: e' esse numero que decide
    # se um proximo item ainda cabe, entao ele nao pode subestimar o texto real.
    assert result["used"] == len(result["text"])
    assert result["used"] >= sum(record["chars"] for record in result["included"])


def test_separador_entre_blocos_e_cobrado_do_orcamento_nao_so_o_conteudo():
    """
    Dois itens de 5 chars cada cabem em budget=10 olhando so' o conteudo, mas o
    texto final leva um separador de 2 chars entre eles ("\\n\\n") -- se esse
    custo nao fosse cobrado, o texto produzido estouraria o orcamento declarado
    sem que "used"/"remaining" acusassem isso.
    """
    inputs = [_item("a", 10, "12345"), _item("b", 5, "67890")]
    result = compile_context(inputs, budget=10)
    assert [record["source"] for record in result["included"]] == ["a"]
    assert [record["source"] for record in result["omitted"]] == ["b"]
    assert result["used"] == len(result["text"]) == 5
    assert result["used"] <= result["budget"]


SECRET_LIKE_CONTENT = [
    "api_key: sk-ABCDEFGH12345678",
    "access_token=abcd1234efgh5678",
    "password: hunter2-secret-value",
    "-----BEGIN " + "PRIVATE KEY-----\nMIIB...\n-----END PRIVATE KEY-----",
    "SECRET=abcdefghijklmnop",
]


@pytest.mark.parametrize("content", SECRET_LIKE_CONTENT)
def test_material_parecido_com_segredo_e_recusado(content):
    with pytest.raises(ContextError, match="secret-like material"):
        compile_context([_item("leak", 1, content)], budget=10_000)


def test_CONTROLE_prosa_comum_mencionando_as_mesmas_palavras_nao_e_falso_positivo():
    """Controle: a recusa e por FORMA (chave=valor, bloco PEM, prefixo sk-), nao
    por conter a palavra 'secret'/'password' em prosa comum."""
    content = "This document explains our secret sauce for onboarding; no password involved."
    result = compile_context([_item("prosa", 1, content)], budget=10_000)
    assert [record["source"] for record in result["included"]] == ["prosa"]


def test_budget_negativo_e_rejeitado():
    with pytest.raises(ContextError):
        compile_context([_item("a", 1, "x")], budget=-1)


def test_fonte_duplicada_e_rejeitada():
    with pytest.raises(ContextError, match="duplicate context source"):
        compile_context([_item("dup", 1, "a"), _item("dup", 2, "b")], budget=100)


def test_budget_zero_omite_tudo_sem_lancar_erro():
    result = compile_context([_item("a", 1, "x")], budget=0)
    assert result["included"] == []
    assert [record["source"] for record in result["omitted"]] == ["a"]
    assert result["used"] == 0
    assert result["text"] == ""


def test_input_sem_lista_e_rejeitado():
    with pytest.raises(ContextError):
        compile_context({"source": "a"}, budget=100)  # dict, nao list

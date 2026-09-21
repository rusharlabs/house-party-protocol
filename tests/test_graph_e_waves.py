"""WorkGraph: rejeita ciclo (direto, indireto e auto-dependencia) e produz waves
topologicas estaveis e deterministicas entre execucoes.
"""
from __future__ import annotations

import pytest

from hpp.workgraph import WorkGraphError, compile_workgraph


def _spec(*items):
    return {"work": list(items)}


def _item(item_id, depends_on=None, tier="economy"):
    return {"id": item_id, "depends_on": depends_on or [], "acceptance": [f"{item_id} done"], "tier": tier}


def test_waves_respeitam_dependencia_em_ordem_topologica():
    spec = _spec(
        _item("spec"),
        _item("build", depends_on=["spec"], tier="balanced"),
        _item("docs", depends_on=["spec"]),
        _item("verify", depends_on=["build", "docs"], tier="frontier"),
    )
    compiled = compile_workgraph(spec)
    assert compiled["waves"] == [
        {"index": 1, "work": ["spec"]},
        {"index": 2, "work": ["build", "docs"]},
        {"index": 3, "work": ["verify"]},
    ]
    assert compiled["tier_counts"] == {"economy": 2, "balanced": 1, "frontier": 1}
    assert {edge["from"] for edge in compiled["edges"]} <= {"spec", "build", "docs"}


def test_ordem_dentro_da_mesma_wave_e_alfabetica_e_deterministica_entre_execucoes():
    spec = _spec(
        _item("z"),
        _item("a"),
        _item("m", depends_on=["z", "a"]),
    )
    first = compile_workgraph(spec)
    second = compile_workgraph(spec)
    assert first == second
    assert first["waves"][0] == {"index": 1, "work": ["a", "z"]}
    assert first["waves"][1] == {"index": 2, "work": ["m"]}


def test_ciclo_direto_entre_dois_itens_e_rejeitado():
    spec = _spec(
        _item("a", depends_on=["b"]),
        _item("b", depends_on=["a"]),
    )
    with pytest.raises(WorkGraphError, match="dependency cycle"):
        compile_workgraph(spec)


def test_ciclo_indireto_de_tres_itens_e_rejeitado():
    spec = _spec(
        _item("a", depends_on=["c"]),
        _item("b", depends_on=["a"]),
        _item("c", depends_on=["b"]),
    )
    with pytest.raises(WorkGraphError, match="dependency cycle"):
        compile_workgraph(spec)


def test_auto_dependencia_e_um_ciclo_de_tamanho_um():
    spec = _spec(_item("a", depends_on=["a"]))
    with pytest.raises(WorkGraphError, match="dependency cycle"):
        compile_workgraph(spec)


def test_dependencia_para_item_inexistente_e_rejeitada():
    spec = _spec(_item("a", depends_on=["fantasma"]))
    with pytest.raises(WorkGraphError, match="unknown dependency"):
        compile_workgraph(spec)


def test_id_duplicado_e_rejeitado():
    spec = _spec(_item("a"), {"id": "a", "acceptance": ["outro"], "tier": "economy"})
    with pytest.raises(WorkGraphError, match="duplicate work id"):
        compile_workgraph(spec)


def test_item_sem_criterio_de_aceitacao_e_rejeitado():
    spec = _spec({"id": "a", "acceptance": [], "tier": "economy"})
    with pytest.raises(WorkGraphError):
        compile_workgraph(spec)


def test_item_com_tier_invalido_e_rejeitado():
    spec = _spec({"id": "a", "acceptance": ["x"], "tier": "premium"})
    with pytest.raises(WorkGraphError, match="invalid tier"):
        compile_workgraph(spec)


def test_lista_de_trabalho_vazia_e_rejeitada():
    with pytest.raises(WorkGraphError):
        compile_workgraph({"work": []})


def test_CONTROLE_spec_sem_ciclo_compila_normalmente():
    """Controle: prova que o detector so reprova quando ha ciclo de verdade --
    uma cadeia linear legitima passa."""
    spec = _spec(_item("a"), _item("b", depends_on=["a"]), _item("c", depends_on=["b"]))
    compiled = compile_workgraph(spec)
    assert compiled["waves"] == [
        {"index": 1, "work": ["a"]},
        {"index": 2, "work": ["b"]},
        {"index": 3, "work": ["c"]},
    ]


def test_CONTROLE_dependencia_compartilhada_nao_e_confundida_com_ciclo():
    """Controle: dois itens dependendo do MESMO item, sem depender um do outro,
    nao e ciclo -- devem cair na mesma wave."""
    spec = _spec(_item("base"), _item("left", depends_on=["base"]), _item("right", depends_on=["base"]))
    compiled = compile_workgraph(spec)
    assert compiled["waves"][1]["work"] == ["left", "right"]

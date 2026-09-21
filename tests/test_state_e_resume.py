"""Event log append-only, projecao de status e resume que nunca reexecuta um
passo ja concluido.

Todo teste passa `tmp_path` explicitamente para `event_path`/`append_event` --
nenhum depende do cwd real nem de ordem de execucao entre si.
"""
from __future__ import annotations

import json

import pytest

from hpp.manifest import load_manifest
from hpp.state import StateError, append_event, event_path, project, read_events


@pytest.fixture()
def manifest():
    data, _ = load_manifest()
    return data


def test_event_path_deriva_do_workspace_informado_nao_do_cwd(tmp_path):
    assert event_path(tmp_path) == tmp_path.resolve() / ".hpp" / "events.jsonl"


def test_log_ausente_projeta_o_estado_inicial_declarado_pelo_manifesto(manifest, tmp_path):
    path = event_path(tmp_path)
    assert not path.exists()
    status = project(read_events(path), manifest)
    assert status["state"] == manifest["loop"]["initial"]
    assert status["event_count"] == 0
    assert status["history"] == []
    assert status["next_step"]


def test_sequencia_completa_avanca_ate_o_ultimo_estado_do_loop(manifest, tmp_path):
    path = event_path(tmp_path)
    ordered_events = [transition["event"] for transition in manifest["loop"]["transitions"]]
    result = None
    for event_type in ordered_events:
        result = append_event(path, event_type, manifest)
    assert result["state"] == manifest["loop"]["transitions"][-1]["to"]
    assert result["event_count"] == len(ordered_events)
    assert result["evidence_count"] >= 1


def test_event_log_e_append_only_registros_antigos_nunca_sao_reescritos(manifest, tmp_path):
    path = event_path(tmp_path)
    append_event(path, "work_started", manifest)
    append_event(path, "evidence_recorded", manifest)
    lines_after_two = path.read_text(encoding="utf-8").splitlines()
    assert len(lines_after_two) == 2
    first_record = json.loads(lines_after_two[0])
    second_record = json.loads(lines_after_two[1])
    assert first_record == {"seq": 1, "id": "event:1", "type": "work_started", "data": {}}
    assert second_record["seq"] == 2 and second_record["id"] == "event:2"

    append_event(path, "check_passed", manifest)
    lines_after_three = path.read_text(encoding="utf-8").splitlines()
    assert len(lines_after_three) == 3
    # as duas primeiras linhas continuam byte-a-byte identicas: append-only de verdade
    assert lines_after_three[0] == lines_after_two[0]
    assert lines_after_three[1] == lines_after_two[1]


def test_transicao_que_pula_etapas_do_loop_e_rejeitada_e_nada_e_escrito(manifest, tmp_path):
    path = event_path(tmp_path)
    with pytest.raises(StateError):
        append_event(path, "human_approved", manifest)  # do estado inicial direto pro fim
    assert not path.exists()


def test_resume_nao_reexecuta_um_evento_ja_aplicado(manifest, tmp_path):
    """
    'resume' deriva o proximo passo do log de eventos, nunca de uma lista de
    tarefas externa -- entao reaplicar um evento que ja levou o loop adiante nao
    e uma transicao valida a partir do estado atual, e o log permanece intacto.
    """
    path = event_path(tmp_path)
    append_event(path, "work_started", manifest)
    status_before = project(read_events(path), manifest)

    with pytest.raises(StateError):
        append_event(path, "work_started", manifest)  # 'active' nao aceita 'work_started' de novo

    status_after = project(read_events(path), manifest)
    assert status_after == status_before


def test_verified_exige_evidencia_mesmo_sob_um_loop_customizado_com_atalho():
    """
    Sob as transicoes do manifesto real, este caminho e inalcancavel (o unico
    jeito de chegar em 'approved' passa por 'evidenced', que exige
    'evidence_recorded'). O invariante em `project()` e testado aqui isolado,
    direto na funcao, com um loop minimo que declara um atalho sem evidencia --
    prova que a checagem nao depende da topologia do manifesto real para valer.
    """
    shortcut_manifest = {
        "loop": {
            "initial": "planned",
            "transitions": [
                {"from": "planned", "event": "work_started", "to": "active", "gate": "scope"},
                {"from": "active", "event": "verified", "to": "verified", "gate": "shortcut"},
            ],
        }
    }
    events = [{"type": "work_started"}, {"type": "verified"}]
    with pytest.raises(StateError, match="evidence"):
        project(events, shortcut_manifest)


def test_CONTROLE_log_com_linha_json_corrompida_e_detectado(tmp_path):
    path = event_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("isto nao e json\n", encoding="utf-8")
    with pytest.raises(StateError):
        read_events(path)


def test_CONTROLE_seq_nao_contiguo_e_rejeitado(tmp_path):
    path = event_path(tmp_path)
    path.parent.mkdir(parents=True)
    record = json.dumps({"seq": 5, "id": "event:5", "type": "work_started"})
    path.write_text(record + "\n", encoding="utf-8")
    with pytest.raises(StateError):
        read_events(path)


def test_CONTROLE_id_que_nao_bate_com_a_linha_e_rejeitado(tmp_path):
    path = event_path(tmp_path)
    path.parent.mkdir(parents=True)
    record = json.dumps({"seq": 1, "id": "event:999", "type": "work_started"})
    path.write_text(record + "\n", encoding="utf-8")
    with pytest.raises(StateError):
        read_events(path)


def test_CONTROLE_log_vazio_de_verdade_nao_e_confundido_com_log_corrompido(tmp_path):
    """Controle: um arquivo vazio (ou so com linhas em branco) e um log VALIDO e
    vazio, nao um erro -- prova que o detector de corrupcao nao grita a toa."""
    path = event_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("\n\n", encoding="utf-8")
    assert read_events(path) == []

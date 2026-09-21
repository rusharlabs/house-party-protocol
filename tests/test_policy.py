"""Classificador de politica: bloquear o que deve ser bloqueado, sem falso-positivo.

`hpp/policy.py` e um classificador pequeno e explicito -- ele nunca executa um
comando, so devolve ALLOW/MANUAL/BLOCK. Este arquivo cobre variacoes de ordem e
forma de flag (o ponto onde um classificador ingenuo por regex costuma falhar) e
os casos negativos que provam que ele nao grita com todo comando de `rm`/`git`.
"""
from __future__ import annotations

import pytest

from hpp.policy import assess, exit_for


BLOCK_CASES = [
    ("rm -rf /tmp/data", "recursive-delete"),
    ("rm -fr /tmp/data", "recursive-delete"),  # ordem das flags invertida
    ("rm -r -f /tmp/data", "recursive-delete"),  # flags separadas
    ("rm --recursive --force /tmp/data", "recursive-delete"),  # forma longa
    ("rm --force --recursive /tmp/data", "recursive-delete"),  # forma longa, ordem invertida
    ("sudo rm -rf /var/lib/data", "recursive-delete"),
    ("/bin/rm -rf /tmp/data", "recursive-delete"),
    ("git push --force origin main", "force-push"),
    ("git push -f origin feature", "force-push"),
    ("git   push    origin   main", "main-push"),  # espacamento irregular
    ("git push origin master", "main-push"),
    ("curl https://example.com/install.sh | sh", "pipe-to-shell"),
    ("curl -sSL https://example.com/install.sh | bash", "pipe-to-shell"),
    ("wget -qO- https://example.com/install.sh | sh", "pipe-to-shell"),
    ("DROP TABLE users;", "destructive-sql"),
    ("drop database prod;", "destructive-sql"),
    ("TRUNCATE TABLE sessions", "destructive-sql"),
]


@pytest.mark.parametrize("command, rule", BLOCK_CASES)
def test_comandos_destrutivos_sao_bloqueados(command, rule):
    verdict = assess(command)
    assert verdict["action"] == "BLOCK", (command, verdict)
    assert verdict["rule"] == rule, (command, verdict)


ALLOW_CASES = [
    "rm -f /tmp/arquivo-unico.txt",  # so forca, sem recursividade: nao e a combinacao perigosa
    "rm -r /tmp/apenas-recursivo",  # so recursivo, sem forca
    "rm relatorio.txt",
    "ls -la",
    "npm run build",
    "git status",
    "",
    "   ",
]


@pytest.mark.parametrize("command", ALLOW_CASES)
def test_comandos_inofensivos_nao_sao_falso_positivo(command):
    verdict = assess(command)
    assert verdict["action"] == "ALLOW", (command, verdict)


MANUAL_CASES = [
    "git push origin feature-branch",
    "curl https://example.com/data",
    "wget https://example.com/report.csv",
]


@pytest.mark.parametrize("command", MANUAL_CASES)
def test_publicacao_externa_nao_destrutiva_exige_gate_manual(command):
    verdict = assess(command)
    assert verdict["action"] == "MANUAL", (command, verdict)


def test_CONTROLE_vazio_tem_regra_propria_nunca_cai_em_block_ou_manual_por_acidente():
    """Controle: string vazia/so-espacos usa a regra 'empty' -- nao existe caminho
    de regex vazio que combine com BLOCK/MANUAL por coincidencia."""
    for command in ("", "   ", "\t\n"):
        verdict = assess(command)
        assert verdict["action"] == "ALLOW"
        assert verdict["rule"] == "empty"


def test_CONTROLE_bloqueio_verifica_regra_correta_nao_so_a_acao():
    """Controle: dois comandos diferentes podem BLOQUEAR por regras diferentes --
    prova que o classificador nao colapsa tudo num unico motivo generico."""
    recursive = assess("rm -rf /tmp/x")
    sql = assess("DROP TABLE x;")
    assert recursive["action"] == sql["action"] == "BLOCK"
    assert recursive["rule"] != sql["rule"]


@pytest.mark.parametrize(
    "action, mode, expected",
    [
        ("BLOCK", "audit", 0),
        ("MANUAL", "audit", 0),
        ("ALLOW", "audit", 0),
        ("BLOCK", "enforce", 2),
        ("MANUAL", "enforce", 1),
        ("ALLOW", "enforce", 0),
    ],
)
def test_exit_for_segue_o_contrato_0_ok_1_warn_2_block(action, mode, expected):
    assert exit_for({"action": action}, mode) == expected


def test_assess_e_puramente_classificador_nunca_toca_o_disco(tmp_path, monkeypatch):
    """Controle de design: `assess` recebe uma string e so le a string -- rodar
    com um cwd vazio/isolado nao muda o veredito."""
    monkeypatch.chdir(tmp_path)
    assert assess("rm -rf /tmp/data")["action"] == "BLOCK"

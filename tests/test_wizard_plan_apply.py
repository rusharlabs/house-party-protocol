"""`hpp init`: plano nao escreve, --apply escreve UM arquivo dentro do alvo, a segunda
rodada e no-op, conflito nunca sobrescreve, e cada codigo de saida do contrato
(0 ok · 1 warn · 2 block · 3 erro) e produzido por um caminho real.

A prova de "nao escreveu" e um hash da arvore do alvo antes e depois -- nao a
ausencia de um arquivo especifico. O controle no fim mostra que o hash de fato
muda quando algo e escrito, senao a comparacao seria vacua.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from hpp import cli, wizard
from hpp.manifest import load_manifest

PRODUCT_ROOT = Path(__file__).resolve().parent.parent


def _tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        if path.is_file():
            digest.update(path.read_bytes())
    return digest.hexdigest()


def _init(target: Path, *extra: str) -> int:
    return cli.main(["init", "--target", str(target), "--no-benchmark", "--no-animation", *extra])


@pytest.fixture()
def exit_codes():
    manifest, _ = load_manifest()
    return manifest["exit_codes"]


@pytest.fixture()
def target(tmp_path):
    workspace = tmp_path / "project"
    workspace.mkdir()
    return workspace


def test_plano_sem_apply_nao_escreve_nada_no_alvo(target, exit_codes, capsys):
    before = _tree_hash(target)
    code = _init(target)
    out = capsys.readouterr().out
    assert code == exit_codes["ok"]
    assert _tree_hash(target) == before
    assert "PLAN" in out and "nothing was written" in out
    assert not (target / ".hpp").exists()


def test_plano_nao_escreve_fora_do_alvo(tmp_path, target, capsys):
    outside = tmp_path / "sibling"
    outside.mkdir()
    (outside / "keep.txt").write_text("untouched", encoding="utf-8")
    registry = Path.home() / ".claude-kits" / "registry.json"
    registry_state = (registry.exists(), registry.stat().st_mtime_ns if registry.exists() else None)
    before = _tree_hash(outside)
    _init(target, "--apply", "--yes")
    capsys.readouterr()
    assert _tree_hash(outside) == before
    assert (registry.exists(), registry.stat().st_mtime_ns if registry.exists() else None) == registry_state


def test_apply_escreve_exatamente_o_profile_dentro_do_alvo(target, exit_codes, capsys):
    code = _init(target, "--apply", "--non-interactive")
    out = capsys.readouterr().out
    assert code == exit_codes["ok"]
    written = sorted(path.relative_to(target).as_posix() for path in target.rglob("*") if path.is_file())
    assert written == [".hpp/profile.json"]
    profile = json.loads((target / ".hpp" / "profile.json").read_text(encoding="utf-8"))
    manifest, _ = load_manifest()
    assert profile["schema"] == wizard.PROFILE_SCHEMA
    assert profile["host"] in manifest["hosts"]
    assert profile["modules"] == manifest["bundles"][profile["bundle"]]["modules"]
    assert "APPLIED" in out and "1 file(s) written" in out


def test_segundo_apply_e_no_op_e_nao_muda_um_byte(target, exit_codes, capsys):
    _init(target, "--apply", "--yes")
    capsys.readouterr()
    after_first = _tree_hash(target)
    code = _init(target, "--apply", "--yes", "--json")
    report = json.loads(capsys.readouterr().out)
    assert code == exit_codes["ok"]
    assert report["mode"] == "no-op"
    assert report["status"] == "no-op"
    assert report["writes"] == 0
    assert _tree_hash(target) == after_first
    detect = next(stage for stage in report["stages"] if stage["stage"] == "detect")
    assert detect["detail"]["classification"] == "re-run"
    assert any("nothing to do" in step for step in report["next"])


def test_conflito_com_profile_existente_e_warn_e_nunca_sobrescreve(target, exit_codes, capsys):
    _init(target, "--apply", "--yes", "--host", "claude-code")
    capsys.readouterr()
    profile_path = target / ".hpp" / "profile.json"
    original = profile_path.read_bytes()
    code = _init(target, "--apply", "--yes", "--host", "codex", "--json")
    report = json.loads(capsys.readouterr().out)
    assert code == exit_codes["warn"]
    assert report["status"] == "warn"
    assert profile_path.read_bytes() == original
    profile = next(stage for stage in report["stages"] if stage["stage"] == "profile")
    assert profile["detail"]["action"] == "conflict"
    assert profile["problems"] and "host" in profile["problems"][0]["measured"]


def test_apply_nao_toca_settings_do_claude_nem_agents_md_existentes(target, capsys):
    claude_dir = target / ".claude"
    claude_dir.mkdir()
    settings = claude_dir / "settings.local.json"
    settings.write_text(json.dumps({"hooks": {"Stop": []}}), encoding="utf-8")
    agents = target / "AGENTS.md"
    agents.write_text("# mine\n", encoding="utf-8")
    settings_bytes, agents_bytes = settings.read_bytes(), agents.read_bytes()
    code = _init(target, "--apply", "--yes", "--json")
    report = json.loads(capsys.readouterr().out)
    assert code == 0
    assert settings.read_bytes() == settings_bytes
    assert agents.read_bytes() == agents_bytes
    wire = next(stage for stage in report["stages"] if stage["stage"] == "wire-suggest")
    assert wire["detail"]["writes"] == 0
    detect = next(stage for stage in report["stages"] if stage["stage"] == "detect")
    assert detect["detail"]["classification"] == "in-progress"
    assert any("settings.local.json" in item for item in detect["detail"]["existing_config"])


# ---------------------------------------------------------------------------
# Codigos de saida: cada um por um caminho real do wizard.
# ---------------------------------------------------------------------------


def test_exit_0_no_plano_limpo(target, exit_codes, capsys):
    assert _init(target) == exit_codes["ok"]


def test_exit_1_quando_o_smoke_reprova(target, exit_codes, capsys, monkeypatch):
    """Um classificador de politica que deixa `rm -rf` passar e' exatamente o que o smoke
    existe para pegar: o estagio reprova, a sequencia nao para (e' o ultimo), e o
    contrato do instalador manda exit 1 para smoke reprovado."""
    monkeypatch.setattr(wizard, "assess", lambda command: {"action": "ALLOW", "rule": "allow", "reason": "broken"})
    code = _init(target, "--json")
    report = json.loads(capsys.readouterr().out)
    assert code == exit_codes["warn"]
    smoke = report["stages"][-1]
    assert smoke["stage"] == "smoke" and smoke["status"] == "fail"
    assert smoke["problems"][0]["next_step"].startswith("python -m hpp policy check")
    policy_item = next(item for item in report["readiness"]["items"] if item["id"] == "policy")
    assert policy_item["status"] == "failed"


def test_exit_2_quando_um_modulo_nao_e_suportado_no_host(target, exit_codes, capsys):
    manifest, _ = load_manifest()
    unsupported = next(module["id"] for module in manifest["modules"] if module["hosts"].get("codex") == "unsupported")
    code = _init(target, "--host", "codex", "--modules", unsupported, "--json")
    report = json.loads(capsys.readouterr().out)
    assert code == exit_codes["block"]
    assert report["status"] == "halted"
    names = [(stage["stage"], stage["status"]) for stage in report["stages"]]
    assert names[3] == ("configure", "fail")
    assert names[4] == ("wire-suggest", "skipped") and names[5] == ("smoke", "skipped")
    assert report["writes"] == 0


def test_exit_2_para_bundle_desconhecido_via_main(target, exit_codes, capsys):
    code = _init(target, "--bundle", "does-not-exist")
    assert code == exit_codes["block"]
    assert "unknown bundle" in capsys.readouterr().err


def test_exit_3_quando_o_alvo_nao_e_diretorio(tmp_path, exit_codes, capsys):
    code = cli.main(["init", "--target", str(tmp_path / "missing"), "--no-benchmark"])
    assert code == exit_codes["error"]
    assert "not a directory" in capsys.readouterr().err


def test_exit_3_quando_o_arquivo_de_profile_nao_e_json(target, exit_codes, capsys):
    answers = target.parent / "answers.json"
    answers.write_text("{not json", encoding="utf-8")
    code = _init(target, "--profile", str(answers))
    assert code == exit_codes["error"]
    assert "not valid JSON" in capsys.readouterr().err


def test_CONTROLE_hash_da_arvore_detecta_uma_escrita(target):
    """Controle: o hash usado acima muda quando um arquivo aparece -- sem isto,
    'plano nao escreve' poderia passar com um hash que ignora o conteudo."""
    before = _tree_hash(target)
    (target / "novo.txt").write_text("x", encoding="utf-8")
    assert _tree_hash(target) != before


def test_CONTROLE_profile_diferente_e_detectado_como_conflito_pelo_proprio_estagio(target, capsys):
    """Controle simetrico: o estagio profile distingue 'igual' de 'diferente' -- prova que
    o no-op acima nao e' um estagio que sempre diz unchanged."""
    _init(target, "--apply", "--yes")
    capsys.readouterr()
    path = target / ".hpp" / "profile.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["policy_mode"] = "enforce" if data["policy_mode"] == "audit" else "audit"
    path.write_text(json.dumps(data), encoding="utf-8")
    _init(target, "--apply", "--yes", "--json")
    report = json.loads(capsys.readouterr().out)
    assert next(stage for stage in report["stages"] if stage["stage"] == "profile")["detail"]["action"] == "conflict"
    assert os.path.getsize(path) == len(json.dumps(data).encode("utf-8"))

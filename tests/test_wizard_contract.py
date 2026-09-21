"""Contrato do instalador aplicado ao `hpp init`: seis estagios em ordem fixa, o bloqueio
pula os estagios seguintes em vez de fingir que rodaram, `wire-suggest` nao executa
UMA operacao de escrita (guarda em `open`/`write_text`/`mkdir`), o bloco a colar
distingue host nativo de comando explicito, e `--help` expoe todas as flags.

O controle prova que a guarda anti-escrita pega uma escrita real: aplicada ao
estagio `profile` em modo --apply, ela estoura.
"""
from __future__ import annotations

import builtins
import json
import pathlib
import subprocess
import sys
from pathlib import Path

import pytest

from hpp import cli, wizard
from hpp.manifest import load_manifest

PRODUCT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def target(tmp_path):
    workspace = tmp_path / "project"
    workspace.mkdir()
    return workspace


@pytest.fixture()
def loaded():
    return load_manifest()


def _options(target: Path, **overrides) -> wizard.InitOptions:
    base = dict(target=target, target_label=str(target), benchmark_k=0)
    base.update(overrides)
    return wizard.InitOptions(**base)


def _context(target: Path, loaded, **overrides) -> wizard._Context:
    manifest, manifest_path = loaded
    return wizard._Context(options=_options(target, **overrides), manifest=manifest, manifest_path=manifest_path)


class _WriteGuard:
    """Faz qualquer escrita em disco estourar enquanto ativa."""

    def __init__(self, monkeypatch):
        real_open = builtins.open

        def guarded_open(file, mode="r", *args, **kwargs):
            if any(flag in mode for flag in "wax+"):
                raise AssertionError(f"write attempted: open({file!r}, {mode!r})")
            return real_open(file, mode, *args, **kwargs)

        def forbidden(*args, **kwargs):
            raise AssertionError(f"write attempted: {args!r}")

        monkeypatch.setattr(builtins, "open", guarded_open)
        monkeypatch.setattr(pathlib.Path, "write_text", forbidden)
        monkeypatch.setattr(pathlib.Path, "write_bytes", forbidden)
        monkeypatch.setattr(pathlib.Path, "mkdir", forbidden)
        monkeypatch.setattr(pathlib.Path, "touch", forbidden)


def test_os_seis_estagios_rodam_nesta_ordem_e_so_nesta(target, loaded, capsys):
    manifest, manifest_path = loaded
    report = wizard.run_init(_options(target), manifest, manifest_path)
    assert wizard.STAGES == ("detect", "prereqs", "profile", "configure", "wire-suggest", "smoke")
    assert [stage["stage"] for stage in report["stages"]] == list(wizard.STAGES)
    assert set(wizard.STAGE_FUNCTIONS) == set(wizard.STAGES)
    assert set(wizard.BOOT_LINES) == set(wizard.STAGES)


def test_callbacks_de_boot_disparam_um_begin_e_um_end_por_estagio_na_ordem(target, loaded):
    manifest, manifest_path = loaded
    trace: list[tuple[str, str]] = []
    wizard.run_init(_options(target), manifest, manifest_path,
                    on_begin=lambda name: trace.append(("begin", name)),
                    on_end=lambda result: trace.append(("end", result["stage"])))
    expected = [item for name in wizard.STAGES for item in (("begin", name), ("end", name))]
    assert trace == expected


def test_bloqueio_para_a_sequencia_e_os_estagios_seguintes_ficam_skipped(target, loaded):
    manifest, manifest_path = loaded
    unsupported = next(module["id"] for module in manifest["modules"] if module["hosts"].get("codex") == "unsupported")
    options = _options(target, answers={"host": "codex", "modules": [unsupported]}, sources={"host": "flag", "modules": "flag"})
    ran: list[str] = []
    report = wizard.run_init(options, manifest, manifest_path, on_begin=ran.append)
    assert ran == ["detect", "prereqs", "profile", "configure"]
    assert [stage["status"] for stage in report["stages"]] == ["ok", "ok", "ok", "fail", "skipped", "skipped"]
    assert report["status"] == "halted" and report["exit_code"] == 2
    assert all("configure failed" in stage["summary"] for stage in report["stages"][4:])


def test_wire_suggest_nao_executa_nenhuma_escrita(target, loaded, monkeypatch):
    ctx = _context(target, loaded)
    wizard.stage_detect(ctx)
    wizard.stage_prereqs(ctx)
    wizard.stage_profile(ctx)
    wizard.stage_configure(ctx)
    _WriteGuard(monkeypatch)
    result = wizard.stage_wire_suggest(ctx)
    assert result["status"] == "ok"
    assert result["detail"]["writes"] == 0
    assert result["detail"]["settings_path"] == ".claude/settings.local.json"
    assert "hooks" in result["detail"]["manual_gates"]


def test_bloco_claude_code_instala_nativos_e_manda_o_instalador_para_os_explicitos(target, loaded):
    manifest, _ = loaded
    ctx = _context(target, loaded, answers={"host": "claude-code"}, sources={"host": "flag"})
    for stage in (wizard.stage_detect, wizard.stage_prereqs, wizard.stage_profile, wizard.stage_configure):
        stage(ctx)
    lines = wizard.stage_wire_suggest(ctx)["detail"]["lines"]
    bundle = manifest["bundles"]["reliable-coding"]["modules"]
    by_id = {module["id"]: module for module in manifest["modules"]}
    native = [module_id for module_id in bundle if by_id[module_id]["hosts"]["claude-code"] == "native"]
    explicit = [module_id for module_id in bundle if by_id[module_id]["hosts"]["claude-code"] != "native"]
    assert f"/plugin marketplace add {wizard.DEFAULT_MARKETPLACE}" in lines
    for module_id in native:
        assert f"/plugin install {module_id}@{manifest['name']}" in lines
    for module_id in explicit:
        assert not any(line == f"/plugin install {module_id}@{manifest['name']}" for line in lines)
        assert any(by_id[module_id]["path"] in line and "--host claude-code" in line for line in lines)
    assert any(line.startswith("# .claude/settings.local.json") and "wrote nothing" in line for line in lines)


def test_bloco_codex_tem_uma_linha_do_instalador_por_modulo_e_hooks_desligados(target, loaded):
    manifest, _ = loaded
    ctx = _context(target, loaded, answers={"host": "codex"}, sources={"host": "flag"})
    for stage in (wizard.stage_detect, wizard.stage_prereqs, wizard.stage_profile, wizard.stage_configure):
        stage(ctx)
    lines = wizard.stage_wire_suggest(ctx)["detail"]["lines"]
    installer = manifest["installer"]["path"]
    commands = [line for line in lines if line.startswith(f"python {installer} install")]
    assert len(commands) == len(manifest["bundles"]["reliable-coding"]["modules"])
    assert all("--host codex" in line and "--apply" in line for line in commands)
    assert any(".agents/skills" in line and ".agents/hpp" in line for line in lines)
    assert any("hooks stay off" in line for line in lines)
    assert not any(line.startswith("/plugin") for line in lines)


def test_marketplace_e_substituivel_por_flag(target, capsys):
    code = cli.main(["init", "--target", str(target), "--no-benchmark", "--marketplace", "me/fork", "--json"])
    report = json.loads(capsys.readouterr().out)
    assert code == 0
    lines = next(stage for stage in report["stages"] if stage["stage"] == "wire-suggest")["detail"]["lines"]
    assert "/plugin marketplace add me/fork" in lines


def test_json_mode_e_parseavel_e_sem_ansi(target):
    result = subprocess.run([sys.executable, "-m", "hpp", "init", "--target", str(target), "--no-benchmark", "--json"],
                            cwd=PRODUCT_ROOT, capture_output=True, timeout=60)
    assert result.returncode == 0
    assert b"\x1b" not in result.stdout
    report = json.loads(result.stdout.decode("ascii"))
    assert report["schema"] == wizard.REPORT_SCHEMA
    assert report["mode"] == "plan" and report["writes"] == 0


def test_help_expoe_todas_as_flags_do_contrato():
    result = subprocess.run([sys.executable, "-m", "hpp", "init", "--help"], cwd=PRODUCT_ROOT, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0
    for flag in ("--apply", "--yes", "--profile", "--modules", "--non-interactive", "--no-animation", "--json", "--target", "--host", "--bundle"):
        assert flag in result.stdout
    assert "detect, prereqs, profile, configure, wire-suggest, smoke" in result.stdout


def test_CONTROLE_a_guarda_anti_escrita_pega_o_estagio_profile_em_apply(target, loaded, monkeypatch):
    """Controle: a mesma guarda usada para provar que wire-suggest nao escreve ESTOURA
    quando o estagio profile tenta gravar em --apply -- logo ela pega escrita real."""
    ctx = _context(target, loaded, apply=True)
    wizard.stage_detect(ctx)
    wizard.stage_prereqs(ctx)
    _WriteGuard(monkeypatch)
    with pytest.raises(AssertionError, match="write attempted"):
        wizard.stage_profile(ctx)

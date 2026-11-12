"""Consumer-facing batch boundaries, including zero-write and partial recovery."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from hpp import __version__
from hpp.cli import main
from hpp import setup


ENGINE = """import json,sys
from pathlib import Path
a=sys.argv
kit=Path(a[a.index('--kit')+1]); target=Path(a[a.index('--target')+1])
host=a[a.index('--host')+1]; apply='--apply' in a
name=json.loads((kit/'.claude-plugin/plugin.json').read_text())['name']
mode=(kit/'mode.txt').read_text().strip() if (kit/'mode.txt').exists() else 'ok'
if apply:
    for seed in kit.glob('*.example.*'):
        dest=target/seed.name.replace('.example.','.')
        if not dest.exists(): dest.write_bytes(seed.read_bytes())
    if host=='codex':
        for item in kit.rglob('*'):
            if item.is_file() and item.name not in {'operator-profile.yaml','ip-ruleset.yaml','HANDOVER.md'}:
                dest=target/'.agents/hpp'/name/item.relative_to(kit)
                if not dest.exists():
                    dest.parent.mkdir(parents=True,exist_ok=True); dest.write_bytes(item.read_bytes())
if mode=='fail-apply' and apply:
    print(json.dumps({'status':'fail'})); sys.exit(1)
print(json.dumps({'status':'ok','stages':[{'status':'warn' if mode=='nested-warn' else 'ok'}]}))
"""


def seal(kit):
    lines = []
    for p in sorted(kit.rglob("*")):
        if p.is_file() and p.name != "CHECKSUMS.txt":
            lines.append(
                hashlib.sha256(p.read_bytes()).hexdigest()
                + "  "
                + p.relative_to(kit).as_posix()
            )
    (kit / "CHECKSUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.fixture
def distribution(tmp_path):
    source = tmp_path / "full source with spaces"
    source.mkdir()
    manifest = json.loads(
        (Path(__file__).resolve().parents[1] / "hpp.manifest.json").read_text(
            encoding="utf-8"
        )
    )
    manifest["product_version"] = __version__
    (source / "hpp.manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    plugins = []
    for m in manifest["modules"]:
        kit = source / m["path"]
        (kit / ".claude-plugin").mkdir(parents=True)
        (kit / ".claude-plugin/plugin.json").write_text(
            json.dumps({"name": m["id"], "version": m["version"]})
        )
        (kit / f"{m['id']}.example.json").write_text("{}\n")
        (kit / "README.md").write_text("module\n")
        if m["id"] == "kit-forge":
            (kit / "kit_doctor.py").write_text(ENGINE, encoding="utf-8")
        seal(kit)
        plugins.append(
            {"name": m["id"], "source": "./" + m["path"], "version": m["version"]}
        )
    (source / "marketplace.json").write_text(
        json.dumps(
            {"name": manifest["name"], "version": __version__, "plugins": plugins}
        )
    )
    target = tmp_path / "consumer with spaces & $(no shell)"
    target.mkdir()
    return source, target, manifest


def snapshot(root):
    return {
        p.relative_to(root).as_posix(): (p.stat().st_mtime_ns, p.read_bytes())
        for p in root.rglob("*")
        if p.is_file()
    }


def kit_of(source, manifest, name):
    return source / next(m["path"] for m in manifest["modules"] if m["id"] == name)


@pytest.mark.parametrize(
    "host,all_compatible,count,skipped",
    [
        ("claude-code", False, 6, 0),
        ("codex", False, 6, 0),
        ("claude-code", True, 10, 0),
        ("codex", True, 9, 1),
    ],
)
def test_selection_and_zero_writes(
    distribution, monkeypatch, host, all_compatible, count, skipped
):
    source, target, _ = distribution
    before = snapshot(source), snapshot(target)
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **kw: pytest.fail("plan ran a subprocess")
    )
    report = setup.run_setup(source, target, host, all_compatible=all_compatible)
    assert report["status"] == "planned", report
    assert len(report["selected_modules"]) == count
    assert len(report["skipped_modules"]) == skipped
    assert (snapshot(source), snapshot(target)) == before
    assert (
        report["activation_commands"] == []
        if host == "codex"
        else report["activation_commands"]
    )


@pytest.mark.parametrize(
    "modules",
    ["unknown", "operator-kit,unknown", "claude-dev-kit", "operator-kit,operator-kit"],
)
def test_explicit_invalid_modules(distribution, modules):
    source, target, _ = distribution
    report = setup.run_setup(source, target, "codex", modules=modules, apply=True)
    assert report["status"] == "error"
    assert not list(target.iterdir())


def test_checksum_and_installer_tamper_before_execution(distribution, monkeypatch):
    source, target, manifest = distribution
    kit = kit_of(source, manifest, "kit-forge")
    (kit / "kit_doctor.py").write_text('raise SystemExit("should not execute")')
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **kw: pytest.fail("executed unvalidated source")
    )
    report = setup.run_setup(
        source, target, "claude-code", modules="operator-kit", apply=True
    )
    assert "checksum" in report["error"]
    assert not list(target.iterdir())


def test_checksum_traversal_is_refused(distribution):
    source, target, manifest = distribution
    kit = kit_of(source, manifest, "operator-kit")
    with (kit / "CHECKSUMS.txt").open("a") as stream:
        stream.write("0" * 64 + "  ../../outside\n")
    report = setup.run_setup(source, target, "codex")
    assert "unsafe relative path" in report["error"]


def test_manifest_source_traversal(distribution):
    source, target, manifest = distribution
    manifest["modules"][0]["path"] = "frameworks/../../outside"
    (source / "hpp.manifest.json").write_text(json.dumps(manifest))
    report = setup.run_setup(source, target, "codex")
    assert "unsafe relative path" in report["error"]


@pytest.mark.parametrize("kind", ["target", "source", "destination"])
def test_links_refused(distribution, tmp_path, kind):
    source, target, _ = distribution
    outside = tmp_path / "outside"
    outside.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        if sys.platform != "win32":
            pytest.skip("symlink unavailable")
        proc = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "New-Item -ItemType Junction -Path $env:HPP_TEST_LINK -Value $env:HPP_TEST_REAL | Out-Null",
            ],
            env=dict(os.environ, HPP_TEST_LINK=str(link), HPP_TEST_REAL=str(outside)),
            capture_output=True,
        )
        if proc.returncode:
            pytest.skip(
                "junction unavailable: " + proc.stderr.decode(errors="replace")[-300:]
            )
    if kind == "target":
        target = link
    elif kind == "source":
        source = link
    else:
        (target / ".agents").mkdir()
        link.rename(target / ".agents/hpp")
    before = snapshot(outside)
    report = setup.run_setup(source, target, "codex", apply=True)
    assert report["status"] == "error", report
    assert "linked/reparse" in report["error"]
    assert snapshot(outside) == before


@pytest.mark.parametrize("kind", ["hpp-profile", "runtime"])
def test_existing_conflicts_refused_before_apply(distribution, kind, monkeypatch):
    source, target, _ = distribution
    if kind == "hpp-profile":
        (target / ".hpp").mkdir()
        (target / ".hpp/profile.json").write_text("{}")
    else:
        path = target / ".agents/hpp/operator-kit/user.txt"
        path.parent.mkdir(parents=True)
        path.write_text("owned by consumer")
    before = snapshot(target)
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **kw: pytest.fail("conflict reached subprocess")
    )
    report = setup.run_setup(source, target, "codex", apply=True)
    assert report["status"] == "error", report
    assert snapshot(target) == before


def test_customized_module_profile_preserved(distribution, monkeypatch):
    source, target, _ = distribution
    path = target / "operator-kit.json"
    path.write_text("consumer-customized configuration")
    before = (path.stat().st_mtime_ns, path.read_bytes())
    monkeypatch.setattr(setup, "_probe_python", lambda *a: None)
    result = setup.run_setup(source, target, "codex", apply=True)
    assert result["status"] == "prepared", result
    assert result["customized_profiles"] == ["operator-kit.json"]
    assert (path.stat().st_mtime_ns, path.read_bytes()) == before
    assert "operator-kit.json" not in result["owned_files"]
    assert "consumer-customized configuration" not in json.dumps(result)


def test_plan_cli_json(distribution, capsys):
    source, target, _ = distribution
    assert (
        main(
            [
                "setup",
                "--source",
                str(source),
                "--target",
                str(target),
                "--host",
                "codex",
                "--all-compatible",
                "--json",
            ]
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    assert len(report["selected_modules"]) == 9
    assert report["exit_code"] == 0


def test_preflight_nested_warning_refuses_whole_batch(distribution, monkeypatch):
    source, target, manifest = distribution
    kit = kit_of(source, manifest, "health-kit")
    (kit / "mode.txt").write_text("nested-warn")
    seal(kit)
    monkeypatch.setattr(setup, "_probe_python", lambda *a: None)
    report = setup.run_setup(source, target, "claude-code", apply=True)
    assert report["status"] == "error", report
    assert not list(target.iterdir())


@pytest.mark.parametrize("host", ["claude-code", "codex"])
def test_apply_scoped_no_settings_argv_and_idempotent(distribution, monkeypatch, host):
    source, target, _ = distribution
    monkeypatch.setattr(setup, "_probe_python", lambda *a: None)
    source_before = snapshot(source)
    for rel in [
        ".claude/settings.json",
        ".claude/settings.local.json",
        ".codex/config.toml",
        "AGENTS.md",
    ]:
        path = target / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("consumer content")
    preserved = snapshot(target)
    report = setup.run_setup(source, target, host, apply=True)
    assert report["status"] == "prepared", report
    assert all(m["status"] == "prepared" for m in report["modules"])
    assert all(
        "--no-register" in m["argv"] and "--apply" not in m["argv"]
        for m in report["modules"]
    )
    for rel, state in preserved.items():
        assert snapshot(target)[rel] == state
    assert snapshot(source) == source_before
    assert not (target / ".claude-kits").exists()
    assert report["owned_files"]
    assert all(
        setup._sha(target / rel) == digest
        for rel, digest in report["owned_files"].items()
    )
    before = snapshot(target)
    monkeypatch.setattr(
        setup, "_execute", lambda *a: pytest.fail("completed module re-executed")
    )
    rerun = setup.run_setup(source, target, host, apply=True)
    assert rerun["status"] == "prepared", rerun
    assert rerun["rerun_verified"] is True
    assert snapshot(target) == before
    if host == "claude-code":
        assert report["activation_commands"][0][-3] == str(source)
        assert all(
            a[-2:] == ["--scope", "project"] for a in report["activation_commands"]
        )
    else:
        assert not report["activation_commands"]


def test_failed_partial_receipt_and_resume(distribution, monkeypatch):
    source, target, manifest = distribution
    monkeypatch.setattr(setup, "_probe_python", lambda *a: None)
    real_execute = setup._execute
    failed = [False]

    def once(argv, cwd):
        if (
            "--apply" in argv
            and "health-kit" in argv[argv.index("--kit") + 1]
            and not failed[0]
        ):
            failed[0] = True
            real_execute(argv, cwd)
            raise setup.SetupError(
                "simulated interrupted module after files were copied"
            )
        return real_execute(argv, cwd)

    monkeypatch.setattr(setup, "_execute", once)
    first = setup.run_setup(source, target, "codex", apply=True)
    assert first["status"] == "partial"
    assert json.loads((target / setup.RECEIPT).read_text())["status"] == "partial"
    assert (
        next(m for m in first["modules"] if m["id"] == "health-kit")["status"]
        == "failed"
    )
    completed = {m["id"] for m in first["modules"] if m["status"] == "prepared"}
    called = []

    def resumed(argv, cwd):
        if "--apply" in argv:
            called.append(argv[argv.index("--kit") + 1])
        return real_execute(argv, cwd)

    monkeypatch.setattr(setup, "_execute", resumed)
    report = setup.run_setup(source, target, "codex", apply=True)
    assert report["status"] == "prepared", report
    assert not any(m in p for m in completed for p in called)


def test_changed_owned_file_refuses_resume(distribution, monkeypatch):
    source, target, _ = distribution
    monkeypatch.setattr(setup, "_probe_python", lambda *a: None)
    report = setup.run_setup(source, target, "codex", apply=True)
    assert report["status"] == "prepared"
    rel = next(iter(report["owned_files"]))
    (target / rel).write_text("consumer modification")
    before = snapshot(target)
    report = setup.run_setup(source, target, "codex", apply=True)
    assert report["status"] == "error"
    assert "changed or missing" in report["error"]
    assert snapshot(target) == before


def test_missing_yaml_runtime_leaves_target_untouched(distribution, monkeypatch):
    source, target, _ = distribution

    def unavailable(*a):
        raise setup.SetupError("PyYAML unavailable in module runtime")

    monkeypatch.setattr(setup, "_probe_python", unavailable)
    report = setup.run_setup(source, target, "codex", apply=True)
    assert report["status"] == "error"
    assert not list(target.iterdir())


def test_wrong_version_and_incomplete_source(distribution):
    source, target, manifest = distribution
    (source / "marketplace.json").unlink()
    assert setup.run_setup(source, target, "codex")["status"] == "error"
    manifest["product_version"] = "0.0.0"
    (source / "hpp.manifest.json").write_text(json.dumps(manifest))
    report = setup.run_setup(source, target, "codex")
    assert "differs from CLI" in report["error"]


def test_actual_runtime_probe_and_shadowing(distribution, tmp_path, monkeypatch):
    source, target, _ = distribution
    shadow = tmp_path / "shadow"
    shadow.mkdir()
    (shadow / "json.py").write_text(
        'raise RuntimeError("PYTHONPATH must not be trusted")'
    )
    (target / "json.py").write_text(
        'raise RuntimeError("consumer cwd must not be imported")'
    )
    (target / "hpp.py").write_text(
        'raise RuntimeError("consumer cwd must not be imported")'
    )
    monkeypatch.setenv("PYTHONPATH", str(shadow))
    result = setup.run_setup(source, target, "codex", modules="health-kit", apply=True)
    if importlib.util.find_spec("yaml") is None:
        assert result["status"] == "error", result
        assert "yaml" in result["error"].lower()
        assert not (target / ".hpp").exists()
    else:
        assert result["status"] == "prepared", result


def test_shared_profile_precedence_is_canonical(distribution, monkeypatch):
    source, target, manifest = distribution
    for module_id, value in [("operator-kit", "first"), ("health-kit", "later")]:
        kit = kit_of(source, manifest, module_id)
        (kit / f"{module_id}.example.json").unlink()
        (kit / "shared.example.json").write_text(value)
        seal(kit)
    monkeypatch.setattr(setup, "_probe_python", lambda *a: None)
    result = setup.run_setup(
        source, target, "claude-code", modules="health-kit,operator-kit", apply=True
    )
    assert result["status"] == "prepared", result
    assert result["selected_modules"] == ["operator-kit", "health-kit"]
    assert (target / "shared.json").read_text() == "first"
    assert result["shared_profile_seeds"][0]["module"] == "health-kit"
    assert (
        setup.run_setup(
            source, target, "claude-code", modules="health-kit,operator-kit", apply=True
        )["status"]
        == "prepared"
    )


@pytest.mark.parametrize(
    "mode", ["non-list-modules", "unowned-settings", "changed-source"]
)
def test_malformed_or_conflicting_receipt_refused(distribution, monkeypatch, mode):
    source, target, manifest = distribution
    monkeypatch.setattr(setup, "_probe_python", lambda *a: None)
    result = setup.run_setup(source, target, "codex", modules="health-kit", apply=True)
    assert result["status"] == "prepared"
    receipt = json.loads((target / setup.RECEIPT).read_text())
    if mode == "non-list-modules":
        receipt["modules"] = "not a list"
    elif mode == "unowned-settings":
        path = target / ".claude/settings.json"
        path.parent.mkdir()
        path.write_text("{}")
        receipt["owned_files"][".claude/settings.json"] = setup._sha(path)
    else:
        kit = kit_of(source, manifest, "health-kit")
        (kit / "README.md").write_text("new source, same version")
        seal(kit)
    (target / setup.RECEIPT).write_text(json.dumps(receipt))
    before = snapshot(target)
    result = setup.run_setup(source, target, "codex", modules="health-kit", apply=True)
    assert result["status"] == "error", result
    assert snapshot(target) == before


def test_reparse_attribute_on_python310(monkeypatch, tmp_path):
    from types import SimpleNamespace

    root = tmp_path / "junction"
    original = Path.lstat

    def reparse(path, *args, **kwargs):
        if path == root:
            return SimpleNamespace(st_mode=0, st_file_attributes=0x400)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", reparse)
    with pytest.raises(setup.SetupError, match="linked/reparse"):
        setup._no_links(root)


def test_conflicting_duplicate_checksum_refused(distribution):
    source, target, manifest = distribution
    kit = kit_of(source, manifest, "health-kit")
    with (kit / "CHECKSUMS.txt").open("a") as stream:
        stream.write("0" * 64 + "  README.md\n")
    result = setup.run_setup(source, target, "codex", modules="health-kit")
    assert "conflicting duplicate checksum" in result["error"]


def test_profile_loader_cannot_escape_or_wire_host(distribution):
    source, target, manifest = distribution
    kit = kit_of(source, manifest, "health-kit")
    (kit / "health-kit.example.json").unlink()
    (kit / "profile.example.yaml").write_text("hooks: {}")
    (kit / "_lib").mkdir()
    (kit / "_lib/profile_loader.py").write_text(
        '_NAMES = (".claude/settings.local.json",)'
    )
    seal(kit)
    result = setup.run_setup(
        source, target, "claude-code", modules="health-kit", apply=True
    )
    assert result["status"] == "error"
    assert "host configuration/instructions" in result["error"]
    assert not list(target.iterdir())


@pytest.mark.parametrize("helper_dir", [".", "_lib"])
def test_unchecked_hash_cache_cannot_execute_before_apply(
    distribution, tmp_path, monkeypatch, helper_dir
):
    """Control proves -I/-B loads the planted cache; setup must refuse it first."""
    import py_compile

    source, target, manifest = distribution
    kit = kit_of(source, manifest, "kit-forge")
    directory = kit / helper_dir
    directory.mkdir(exist_ok=True)
    helper = directory / "setup_helper.py"
    helper.write_text('VALUE="safe source"\n')
    prefix = (
        "import sys\nfrom pathlib import Path\n"
        f"sys.path.insert(0,str(Path(__file__).parent / {helper_dir!r}))\nimport setup_helper\n"
    )
    installer = kit / "kit_doctor.py"
    installer.write_text(prefix + ENGINE)
    seal(kit)
    payload = tmp_path / "cache_payload.py"
    payload.write_text(
        'import os\nfrom pathlib import Path\nPath(os.environ["HPP_SETUP_CACHE_MARKER"]).write_text("cached code ran")\n'
    )
    cache = Path(importlib.util.cache_from_source(str(helper)))
    cache.parent.mkdir(exist_ok=True)
    py_compile.compile(
        str(payload),
        cfile=str(cache),
        doraise=True,
        invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH,
    )
    control = tmp_path / "control"
    control.mkdir()
    control_marker = tmp_path / "control-executed"
    proc = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(installer),
            "install",
            "--kit",
            str(kit),
            "--target",
            str(control),
            "--host",
            "claude-code",
        ],
        env=dict(os.environ, HPP_SETUP_CACHE_MARKER=str(control_marker)),
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert control_marker.read_text() == "cached code ran"
    actual_marker = tmp_path / "must-not-execute"
    monkeypatch.setenv("HPP_SETUP_CACHE_MARKER", str(actual_marker))
    monkeypatch.setattr(setup, "_probe_python", lambda *a: None)
    before = snapshot(source), snapshot(target)
    # lane-only still verifies every installer dependency in kit-forge.
    result = setup.run_setup(
        source, target, "claude-code", modules="lane-kit", apply=True
    )
    assert result["status"] == "error", result
    assert "cache/bytecode" in result["error"]
    assert not actual_marker.exists()
    assert (snapshot(source), snapshot(target)) == before


@pytest.mark.parametrize(
    "relative", ["extra.pyc", "nested/extra.pyo", "nested/__pycache__"]
)
def test_source_bytecode_refused_even_when_tracked(distribution, relative):
    source, target, manifest = distribution
    kit = kit_of(source, manifest, "health-kit")
    path = kit / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix:
        path.write_bytes(b"executable cache")
    else:
        path.mkdir()
    seal(kit)
    result = setup.run_setup(source, target, "codex", modules="health-kit")
    assert result["status"] == "error"
    assert "cache/bytecode" in result["error"]
    assert not list(target.iterdir())


def test_unowned_runtime_cache_refuses_completed_resume(distribution, monkeypatch):
    source, target, _ = distribution
    monkeypatch.setattr(setup, "_probe_python", lambda *a: None)
    result = setup.run_setup(source, target, "codex", modules="health-kit", apply=True)
    assert result["status"] == "prepared", result
    cache = target / ".agents/hpp/health-kit/__pycache__/unowned.pyc"
    cache.parent.mkdir()
    cache.write_bytes(b"unowned executable cache")
    before = snapshot(target)
    result = setup.run_setup(source, target, "codex", modules="health-kit", apply=True)
    assert result["status"] == "error", result
    assert "cache/bytecode" in result["error"]
    assert snapshot(target) == before


def test_plan_exposes_all_module_destinations_without_execution(
    distribution, monkeypatch
):
    source, target, manifest = distribution
    kit = kit_of(source, manifest, "health-kit")
    skill = kit / "skills/health-audit"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: health-audit\n---\nRun ${CLAUDE_PLUGIN_ROOT}/probe.py\n"
    )
    (skill / "probe.py").write_text('print("probe")\n')
    seal(kit)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **kw: pytest.fail("destination planning executed code"),
    )
    before = snapshot(source), snapshot(target)
    result = setup.run_setup(source, target, "codex", modules="health-kit")
    assert result["status"] == "planned", result
    files = {p["destination"]: p for p in result["planned_files"]}
    assert files[".hpp/profile.json"]["kind"] == "project-profile"
    assert files[".hpp/setup-receipt.json"]["kind"] == "setup-receipt"
    assert files["health-kit.json"]["kind"] == "module-profile"
    assert files[".agents/hpp/health-kit/README.md"]["kind"] == "runtime-copy"
    assert (
        files[".agents/skills/hpp-health-kit-health-audit/SKILL.md"]["kind"]
        == "codex-skill-transform"
    )
    assert files[".agents/skills/hpp-health-kit-health-audit/probe.py"][
        "source"
    ] == str(skill / "probe.py")
    assert all(p["action"] == "create" for p in files.values())
    assert (snapshot(source), snapshot(target)) == before


@pytest.mark.parametrize(
    "mode",
    ["missing-profile", "missing-runtime-file", "omitted-ownership", "wrong-target"],
)
def test_completed_receipt_requires_real_artifact_coverage(
    distribution, monkeypatch, mode
):
    source, target, _ = distribution
    monkeypatch.setattr(setup, "_probe_python", lambda *a: None)
    result = setup.run_setup(source, target, "codex", modules="health-kit", apply=True)
    assert result["status"] == "prepared", result
    receipt = json.loads((target / setup.RECEIPT).read_text())
    if mode == "missing-profile":
        (target / ".hpp/profile.json").unlink()
        receipt["owned_files"].pop(".hpp/profile.json")
    elif mode == "missing-runtime-file":
        rel = ".agents/hpp/health-kit/README.md"
        (target / rel).unlink()
        receipt["owned_files"].pop(rel)
    elif mode == "omitted-ownership":
        receipt["owned_files"] = {}
    else:
        receipt["target"] = "another-project"
    (target / setup.RECEIPT).write_text(json.dumps(receipt))
    before = snapshot(target)
    result = setup.run_setup(source, target, "codex", modules="health-kit", apply=True)
    assert result["status"] == "error", result
    assert not result.get("rerun_verified")
    assert snapshot(target) == before


@pytest.mark.parametrize("host", ["claude-code", "codex"])
def test_plan_discloses_manifest_hook_capabilities_without_execution(
    distribution, monkeypatch, capsys, host
):
    source, target, manifest = distribution
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **kw: pytest.fail("capability planning executed a subprocess"),
    )
    before = snapshot(source), snapshot(target)
    report = setup.run_setup(source, target, host)
    assert report["status"] == "planned", report
    selected = set(report["selected_modules"])
    expected = [hook for hook in manifest["hooks"] if hook["module"] in selected]
    assert report["hook_capabilities"] == expected
    assert report["host_activation"] == "not-measured"
    assert report["native_activation_status"] == (
        "manual-required" if host == "claude-code" else "not-applicable"
    )
    assert (
        main(
            [
                "setup",
                "--source",
                str(source),
                "--target",
                str(target),
                "--host",
                host,
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "Declared hook capabilities (not enabled by setup)" in output
    assert "Host activation is not measured" in output
    for hook in expected:
        for field in ("id", "module", "exit_policy"):
            assert hook[field] in output
        for value in hook["events"] + hook["capabilities"]:
            assert value in output
    assert (snapshot(source), snapshot(target)) == before


def test_module_children_do_not_inherit_profiles_credentials_or_real_host_path(
    tmp_path, monkeypatch
):
    host_bin = tmp_path / "real host commands"
    host_bin.mkdir()
    for host in ("claude", "codex"):
        for suffix in ("", ".exe", ".cmd", ".ps1"):
            (host_bin / (host + suffix)).write_text("must never execute")
    safe_bin = tmp_path / "ordinary tools"
    safe_bin.mkdir()
    names = [
        "OPERATOR_PROFILE",
        "CLAUDE_PROJECT_DIR",
        "CLAUDE_PLUGIN_ROOT",
        "CLAUDE_CODE_OAUTH_TOKEN",
        "CLAUDECODE",
        "CODEX_HOME",
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "LANE_KIT_CONFIG",
        "LANE_BOARD_SUITE_COMMAND",
        "GOTCHA_STORE_DIR",
        "SESSION_BOOT_STATE_DOC",
        "HPP_CHECKPOINT_STATE_DIR",
        "HPP_FACT_FORCE_STATE_DIR",
        "EXPECTED_ROOT",
        "ALLOW_CROSS_ROOT",
        "SNAPSHOT_CONFIRMED",
        "GUARD_ORIGINS",
        "GIT_CONFIG_PARAMETERS",
        "BASH_ENV",
        "NODE_OPTIONS",
        "PYTHONPATH",
        "PYTHONHOME",
    ]
    for name in names:
        monkeypatch.setenv(name, "caller-state-must-not-escape")
    monkeypatch.setenv("PATH", str(host_bin) + os.pathsep + str(safe_bin))
    before = dict(os.environ)
    env = setup._module_environment()
    assert all(name not in env for name in names)
    assert env["PATH"] == str(safe_bin)
    assert env["GIT_CONFIG_GLOBAL"] == os.devnull
    assert env["GIT_CONFIG_NOSYSTEM"] == "1"
    assert dict(os.environ) == before
    # Actual child checks discovery; no fake CLI is put on PATH to satisfy it.
    script = (
        "import json,os,shutil; "
        "print(json.dumps({'status':'ok','claude':shutil.which('claude'),"
        "'codex':shutil.which('codex'),'profile':os.environ.get('OPERATOR_PROFILE')}))"
    )
    result = setup._execute([sys.executable, "-I", "-B", "-c", script], tmp_path)
    assert result == {"status": "ok", "claude": None, "codex": None, "profile": None}
    assert dict(os.environ) == before


def test_module_path_prepending_keeps_lexical_venv_interpreter(tmp_path, monkeypatch):
    """Resolving a venv's Python symlink would prepend the base interpreter dir."""
    interpreter = tmp_path / "managed venv/bin/python"
    interpreter.parent.mkdir(parents=True)
    interpreter.write_bytes(b"venv interpreter alias")
    base = tmp_path / "base interpreter/python"
    base.parent.mkdir()
    base.write_bytes(b"base interpreter")
    original = Path.resolve

    def resolve(path, *args, **kwargs):
        return base if path == interpreter else original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", resolve)
    env = setup._module_environment(str(interpreter))
    assert env["PATH"].split(os.pathsep)[0] == str(interpreter.parent)
    assert env["PATH"].split(os.pathsep)[0] != str(base.parent)

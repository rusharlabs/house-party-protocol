#!/usr/bin/env python3
"""browse.py - menu interativo do marketplace House Party Protocol.

Le marketplace.json (raiz do marketplace), lista os kits com descricao+categoria,
deixa escolher por numero, e delega a instalacao real para kit_doctor.py install
(--human primeiro, depois --apply so com confirmacao explicita). Nao reimplementa
nenhuma logica de instalacao -- e so um menu fino sobre o mecanismo que ja existe.

Uso:
    python tools/browse.py [--marketplace PATH] [--target PATH]
    python tools/browse.py --self-test
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path


def _find_marketplace(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    # tools/ -> instaladores/kit-forge-X.Y.Z/ -> raiz do marketplace
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "marketplace.json"
        if candidate.is_file():
            return candidate
    raise SystemExit("marketplace.json nao encontrado (suba --marketplace explicito)")


def _load_plugins(marketplace_path: Path) -> list[dict]:
    data = json.loads(marketplace_path.read_text(encoding="utf-8"))
    return data.get("plugins", [])


def _print_menu(plugins: list[dict]) -> None:
    print()
    print(f"=== marketplace: {len(plugins)} kits ===")
    for i, p in enumerate(plugins, start=1):
        print(f"  {i}. {p['name']:24s} [{p.get('category', '?'):12s}] v{p.get('version', '?')}")
        desc = p.get("description", "")
        if desc:
            wrapped = desc if len(desc) <= 100 else desc[:97] + "..."
            print(f"       {wrapped}")
    print("  0. sair")
    print()


def _resolve_kit_doctor(marketplace_path: Path) -> Path:
    root = marketplace_path.parent
    candidates = sorted(root.glob("instaladores/kit-forge-*/kit_doctor.py"))
    if not candidates:
        raise SystemExit("kit_doctor.py nao encontrado em instaladores/kit-forge-*/")
    return candidates[-1]


def run_menu(marketplace_path: Path, target: str, input_fn=input, run_fn=subprocess.run) -> int:
    plugins = _load_plugins(marketplace_path)
    if not plugins:
        print("marketplace vazio.")
        return 1
    kit_doctor = _resolve_kit_doctor(marketplace_path)
    _print_menu(plugins)
    choice = input_fn("Escolha um kit pelo numero (0 pra sair): ").strip()
    if choice == "0" or choice == "":
        print("Saindo.")
        return 0
    try:
        idx = int(choice) - 1
        plugin = plugins[idx]
    except (ValueError, IndexError):
        print("Escolha invalida.")
        return 2

    kit_dir = (marketplace_path.parent / plugin["source"]).resolve()
    print(f"\n--- Plano de instalacao de '{plugin['name']}' (--human, zero escrita) ---")
    plan = run_fn(
        [sys.executable, str(kit_doctor), "install", str(kit_dir), "--target", target, "--human"],
        capture_output=True, text=True,
    )
    print(plan.stdout)
    if plan.stderr:
        print(plan.stderr, file=sys.stderr)

    confirm = input_fn(f"\nAplicar de verdade a instalacao de '{plugin['name']}'? [s/N]: ").strip().lower()
    if confirm != "s":
        print("Nao aplicado. Nenhum arquivo tocado.")
        return 0

    apply_run = run_fn(
        [sys.executable, str(kit_doctor), "install", str(kit_dir), "--target", target, "--apply"],
        capture_output=True, text=True,
    )
    print(apply_run.stdout)
    if apply_run.stderr:
        print(apply_run.stderr, file=sys.stderr)
    return apply_run.returncode


def _self_test() -> int:
    """Self-test isolado: cria um marketplace.json fake + 1 plugin fake, roda o menu
    em modo nao-interativo (input_fn/run_fn falsos), confirma que lista e escolhe certo."""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "instaladores" / "kit-forge-9.9.9").mkdir(parents=True)
        (root / "instaladores" / "kit-forge-9.9.9" / "kit_doctor.py").write_text("# fake\n", encoding="utf-8")
        (root / "fake-kit-1.0.0").mkdir()
        mp = root / "marketplace.json"
        mp.write_text(json.dumps({
            "name": "self-test-marketplace",
            "plugins": [
                {"name": "fake-kit", "version": "1.0.0", "category": "test",
                 "description": "kit fake pro self-test", "source": "./fake-kit-1.0.0"}
            ],
        }), encoding="utf-8")

        calls = []

        def fake_input(prompt):
            calls.append(("input", prompt))
            if "numero" in prompt:
                return "1"
            if "Aplicar" in prompt:
                return "n"
            return ""

        class FakeCompleted:
            stdout = "plano fake ok\n"
            stderr = ""
            returncode = 0

        def fake_run(*a, **kw):
            calls.append(("run", a[0]))
            return FakeCompleted()

        rc = run_menu(mp, target=str(root), input_fn=fake_input, run_fn=fake_run)
        assert rc == 0, f"esperava rc=0, veio {rc}"
        assert any("kit_doctor.py" in str(c[1]) for c in calls if c[0] == "run"), "nao chamou kit_doctor.py"
        assert not any("--apply" in str(c[1]) for c in calls if c[0] == "run"), "chamou --apply sem confirmacao 's'"
        print("self-test OK — lista o marketplace, monta o comando certo do kit_doctor.py,")
        print("respeita 'n' na confirmacao (nunca aplica sem 's' explicito)")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--marketplace", default=None)
    parser.add_argument("--target", default=".")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return _self_test()

    marketplace_path = _find_marketplace(args.marketplace)
    return run_menu(marketplace_path, args.target)


if __name__ == "__main__":
    raise SystemExit(main())

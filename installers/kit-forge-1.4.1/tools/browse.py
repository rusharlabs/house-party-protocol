#!/usr/bin/env python3
"""browse.py - interactive menu for the House Party Protocol marketplace.

Reads marketplace.json (marketplace root), lists the kits with description+category,
lets you choose by number, and delegates the real install to kit_doctor.py install
(--human first, then --apply only with explicit confirmation). Does not reimplement
any install logic -- it is just a thin menu over the mechanism that already exists.

Usage:
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
    # tools/ -> installers/kit-forge-X.Y.Z/ -> marketplace root
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "marketplace.json"
        if candidate.is_file():
            return candidate
    raise SystemExit("marketplace.json not found (pass an explicit --marketplace)")


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
    print("  0. quit")
    print()


def _resolve_kit_doctor(marketplace_path: Path) -> Path:
    root = marketplace_path.parent
    candidates = sorted(root.glob("installers/kit-forge-*/kit_doctor.py"))
    if not candidates:
        raise SystemExit("kit_doctor.py not found under installers/kit-forge-*/")
    return candidates[-1]


def run_menu(marketplace_path: Path, target: str, input_fn=input, run_fn=subprocess.run) -> int:
    plugins = _load_plugins(marketplace_path)
    if not plugins:
        print("empty marketplace.")
        return 1
    kit_doctor = _resolve_kit_doctor(marketplace_path)
    _print_menu(plugins)
    choice = input_fn("Pick a kit by number (0 to quit): ").strip()
    if choice == "0" or choice == "":
        print("Quitting.")
        return 0
    try:
        idx = int(choice) - 1
        plugin = plugins[idx]
    except (ValueError, IndexError):
        print("Invalid choice.")
        return 2

    kit_dir = (marketplace_path.parent / plugin["source"]).resolve()
    print(f"\n--- Install plan for '{plugin['name']}' (--human, zero writes) ---")
    plan = run_fn(
        [sys.executable, str(kit_doctor), "install", str(kit_dir), "--target", target, "--human"],
        capture_output=True, text=True,
    )
    print(plan.stdout)
    if plan.stderr:
        print(plan.stderr, file=sys.stderr)

    confirm = input_fn(f"\nReally apply the install of '{plugin['name']}'? [y/N]: ").strip().lower()
    if confirm != "y":
        print("Not applied. No file touched.")
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
    """Isolated self-test: creates a fake marketplace.json + 1 fake plugin, runs the menu
    in non-interactive mode (fake input_fn/run_fn), confirms it lists and picks correctly."""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        # Why: the fixture has to use the SAME directory name `_resolve_kit_doctor` globs for.
        # It said `instaladores/` - the layout name that 2.5.0 renamed to `installers/` - so this
        # self-test has raised SystemExit on every run since that release, and nothing noticed
        # because it is not part of the pytest suite. A rename that updates the code and forgets
        # the fixture leaves a test that is red for a reason nobody reads.
        (root / "installers" / "kit-forge-9.9.9").mkdir(parents=True)
        (root / "installers" / "kit-forge-9.9.9" / "kit_doctor.py").write_text("# fake\n", encoding="utf-8")
        (root / "fake-kit-1.0.0").mkdir()
        mp = root / "marketplace.json"
        mp.write_text(json.dumps({
            "name": "self-test-marketplace",
            "plugins": [
                {"name": "fake-kit", "version": "1.0.0", "category": "test",
                 "description": "fake kit for the self-test", "source": "./fake-kit-1.0.0"}
            ],
        }), encoding="utf-8")

        calls = []

        def fake_input(prompt):
            calls.append(("input", prompt))
            if "number" in prompt:
                return "1"
            if "apply" in prompt:
                return "n"
            return ""

        class FakeCompleted:
            stdout = "fake plan ok\n"
            stderr = ""
            returncode = 0

        def fake_run(*a, **kw):
            calls.append(("run", a[0]))
            return FakeCompleted()

        rc = run_menu(mp, target=str(root), input_fn=fake_input, run_fn=fake_run)
        assert rc == 0, f"expected rc=0, got {rc}"
        assert any("kit_doctor.py" in str(c[1]) for c in calls if c[0] == "run"), "it did not call kit_doctor.py"
        assert not any("--apply" in str(c[1]) for c in calls if c[0] == "run"), "it called --apply without an explicit 'y'"
        print("self-test OK — lists the marketplace, builds the right kit_doctor.py command,")
        print("honours 'n' at the prompt (never applies without an explicit 'y')")
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

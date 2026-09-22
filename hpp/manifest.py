"""Manifest loading and structural validation for the HPP harness."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable


# The one place the protocol version lives in code. Why (cross-model review of 2.5.0): the bump
# to 2.1 left the wizard's prerequisite check saying "protocol 2.0, validated" — the string
# rendered on failure was a literal in a second file, so the contract had two spellings.
PROTOCOL_VERSION = "2.1"


class ManifestError(ValueError):
    """A public manifest violates a harness invariant."""


def find_manifest(explicit: str | None = None, start: Path | None = None) -> Path:
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if not path.is_file():
            raise ManifestError(f"manifest not found: {path}")
        return path
    for base in (start or Path.cwd()).resolve(), * (start or Path.cwd()).resolve().parents:
        candidate = base / "hpp.manifest.json"
        if candidate.is_file():
            return candidate
    package_dir = Path(__file__).resolve().parent
    # Why (pip install shipped no manifest, 2026-09-21): the root file only exists in a source
    # checkout or an editable install, where its parent is the distribution root the wizard
    # verifies. Inside site-packages that parent holds no manifest, so the copy the wheel carries
    # as package data is the last resort — checked last so a real checkout always wins.
    for packaged in (package_dir.parent / "hpp.manifest.json", package_dir / "hpp.manifest.json"):
        if packaged.is_file():
            return packaged
    raise ManifestError("hpp.manifest.json not found from current directory, source root or installed package")


def load_manifest(path: str | None = None) -> tuple[dict[str, Any], Path]:
    manifest_path = find_manifest(path)
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ManifestError(f"invalid JSON manifest: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise ManifestError("manifest root must be an object")
    validate_manifest(data)
    return data, manifest_path


def validate_distribution(data: dict[str, Any], root: Path) -> dict[str, Any]:
    """Cross-check an emitted product when a marketplace is present beside the manifest."""
    marketplace_path = root / "marketplace.json"
    if not marketplace_path.is_file():
        return {"checked": False, "status": "source-contract"}
    try:
        marketplace = json.loads(marketplace_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ManifestError(f"invalid marketplace JSON: {exc.msg}") from exc
    if not isinstance(marketplace, dict):
        raise ManifestError("marketplace root must be an object")
    if marketplace.get("version") != data.get("product_version"):
        raise ManifestError("product version diverges between manifest and marketplace")
    plugins = marketplace.get("plugins")
    if not isinstance(plugins, list):
        raise ManifestError("marketplace plugins must be a list")
    by_name = {
        plugin.get("name"): plugin
        for plugin in plugins
        if isinstance(plugin, dict) and isinstance(plugin.get("name"), str)
    }
    expected = {module["id"] for module in data["modules"]}
    if set(by_name) != expected:
        raise ManifestError("module set diverges between manifest and marketplace")
    checked_paths = 0
    for module in data["modules"]:
        plugin = by_name[module["id"]]
        source = str(plugin.get("source", "")).removeprefix("./")
        if source != module["path"] or plugin.get("version") != module["version"]:
            raise ManifestError(f"distribution diverges for module {module['id']}")
        module_path = (root / module["path"]).resolve()
        if module_path.parent == root.resolve() or root.resolve() in module_path.parents:
            if not module_path.is_dir():
                raise ManifestError(f"distribution path missing for module {module['id']}")
        else:
            raise ManifestError(f"distribution path escapes product root for module {module['id']}")
        plugin_manifest = module_path / ".claude-plugin" / "plugin.json"
        if plugin_manifest.is_file():
            try:
                plugin_data = json.loads(plugin_manifest.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ManifestError(f"invalid plugin manifest for {module['id']}: {exc.msg}") from exc
            if plugin_data.get("name") != module["id"] or plugin_data.get("version") != module["version"]:
                raise ManifestError(f"plugin manifest diverges for module {module['id']}")
        _check_wired_hooks_are_declared(data, module["id"], module_path)
        checked_paths += 1
    return {"checked": True, "status": "ok", "modules": checked_paths}


_SCRIPT_IN_COMMAND = re.compile(r"hooks/([A-Za-z0-9_.-]+\.(?:py|sh))")


def _check_wired_hooks_are_declared(data: dict[str, Any], module_id: str, module_path: Path) -> None:
    """Every script a module WIRES in `hooks/hooks.json` must be DECLARED in the manifest.

    Why (cross-model review of 2.5.0): the capability table was only checked against itself — a
    hook listed in the manifest with a missing field failed, but a module that wired three scripts
    and declared one passed `hpp doctor`, because doctor never opened the file the host actually
    reads. The wired-versus-declared coverage lived in a source-tree test that does not ship. The
    user asked "what will the hooks I am about to paste do?" and the answer could be missing a hook
    without the product noticing. Now the emitted tree is the ruler: absent from the table means
    undeclared, never "no capabilities".
    """
    hooks_json = module_path / "hooks" / "hooks.json"
    if not hooks_json.is_file():
        return
    try:
        wiring = json.loads(hooks_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ManifestError(f"invalid hooks.json for module {module_id}: {exc.msg}") from exc
    events = wiring.get("hooks", wiring) if isinstance(wiring, dict) else {}
    wired: set[str] = set()
    for entries in events.values() if isinstance(events, dict) else []:
        for entry in entries if isinstance(entries, list) else []:
            for hook in entry.get("hooks", []) if isinstance(entry, dict) else []:
                command = str(hook.get("command", "")) if isinstance(hook, dict) else ""
                for script in _SCRIPT_IN_COMMAND.findall(command):
                    if script != "pyrun.sh":  # the interpreter shim, never a hook of its own
                        wired.add(f"hooks/{script}")
    declared = {
        hook["script"] for hook in data.get("hooks", [])
        if isinstance(hook, dict) and hook.get("module") == module_id
    }
    missing = sorted(wired - declared)
    if missing:
        raise ManifestError(
            f"module {module_id} wires {len(missing)} hook(s) with no capability declaration: "
            + ", ".join(missing))


def _unique(values: Iterable[str], label: str) -> None:
    items = list(values)
    duplicates = sorted({value for value in items if items.count(value) > 1})
    if duplicates:
        raise ManifestError(f"duplicate {label}: {', '.join(duplicates)}")


def _cycles(modules: dict[str, dict[str, Any]]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(module_id: str) -> None:
        if module_id in visiting:
            raise ManifestError(f"dependency cycle: {module_id}")
        if module_id in visited:
            return
        visiting.add(module_id)
        for dependency in modules[module_id].get("requires", []):
            if dependency not in modules:
                raise ManifestError(f"unknown module dependency: {module_id} -> {dependency}")
            visit(dependency)
        visiting.remove(module_id)
        visited.add(module_id)

    for module_id in sorted(modules):
        visit(module_id)


EXIT_POLICIES = frozenset({"observe", "warn", "block"})


def _validate_hooks(data: dict[str, Any], modules: dict[str, dict[str, Any]]) -> None:
    """Every hook the product installs declares what it is capable of.

    Absent is never read as empty: a hook with no `capabilities` key, an empty list, or a
    module that declares the `hooks` component with nothing declared for it are all refused.
    A missing declaration that validated as "does nothing" would be the widest permission in
    the manifest written as silence.
    """
    vocabulary = data.get("hook_capabilities")
    if (not isinstance(vocabulary, list) or not vocabulary
            or not all(isinstance(item, str) and item for item in vocabulary)):
        raise ManifestError("hook_capabilities must be a non-empty list of capability groups")
    _unique(vocabulary, "hook capability")
    allowed = set(vocabulary)

    hooks = data.get("hooks")
    if not isinstance(hooks, list) or not hooks:
        raise ManifestError("hooks must be a non-empty list of hook declarations")
    hook_ids: list[str] = []
    declaring: set[str] = set()
    for hook in hooks:
        if not isinstance(hook, dict) or not isinstance(hook.get("id"), str) or not hook["id"]:
            raise ManifestError("every hook needs a string id")
        hook_id = hook["id"]
        hook_ids.append(hook_id)
        module_id = hook.get("module")
        if module_id not in modules:
            raise ManifestError(f"hook {hook_id} names unknown module: {module_id}")
        declaring.add(module_id)
        script = hook.get("script")
        if not isinstance(script, str) or not script or script.startswith(("/", "..")):
            raise ManifestError(f"hook {hook_id} needs a relative script path")
        events = hook.get("events")
        if (not isinstance(events, list) or not events
                or not all(isinstance(event, str) and event for event in events)):
            raise ManifestError(f"hook {hook_id} needs a non-empty events list")
        _unique(events, f"event in {hook_id}")
        capabilities = hook.get("capabilities")
        if (not isinstance(capabilities, list) or not capabilities
                or not all(isinstance(item, str) and item for item in capabilities)):
            raise ManifestError(f"hook {hook_id} needs non-empty capabilities")
        _unique(capabilities, f"capability in {hook_id}")
        unknown = sorted(set(capabilities) - allowed)
        if unknown:
            raise ManifestError(f"hook {hook_id} declares unknown capability: {', '.join(unknown)}")
        if hook.get("exit_policy") not in EXIT_POLICIES:
            raise ManifestError(
                f"hook {hook_id} needs an exit_policy of {', '.join(sorted(EXIT_POLICIES))}")
    _unique(hook_ids, "hook")
    silent = sorted(module_id for module_id, module in modules.items()
                    if "hooks" in module.get("components", []) and module_id not in declaring)
    if silent:
        raise ManifestError(
            f"module declares the hooks component and declares no hook: {', '.join(silent)}")


def hook_capability_census(data: dict[str, Any]) -> dict[str, Any]:
    """Counts per capability group, with every group present even when it counts zero."""
    counts = {group: 0 for group in data["hook_capabilities"]}
    for hook in data["hooks"]:
        for group in hook["capabilities"]:
            counts[group] += 1
    return {"declared": len(data["hooks"]), "by_capability": counts,
            "by_exit_policy": {policy: sum(1 for hook in data["hooks"]
                                           if hook["exit_policy"] == policy)
                               for policy in sorted(EXIT_POLICIES)}}


def hooks_for_modules(data: dict[str, Any], module_ids: Iterable[str]) -> list[dict[str, Any]]:
    """The declarations of the modules being installed, in manifest order."""
    wanted = set(module_ids)
    return [hook for hook in data.get("hooks", []) if hook["module"] in wanted]


def validate_manifest(data: dict[str, Any]) -> None:
    if data.get("protocol_version") != PROTOCOL_VERSION:
        raise ManifestError(f"protocol_version must be {PROTOCOL_VERSION}")
    hosts = data.get("hosts")
    if not isinstance(hosts, list) or not hosts:
        raise ManifestError("hosts must be a non-empty list")
    _unique(hosts, "host")
    raw_modules = data.get("modules")
    if not isinstance(raw_modules, list) or not raw_modules:
        raise ManifestError("modules must be a non-empty list")
    modules: dict[str, dict[str, Any]] = {}
    module_paths: list[str] = []
    for module in raw_modules:
        if not isinstance(module, dict) or not isinstance(module.get("id"), str):
            raise ManifestError("every module needs a string id")
        module_id = module["id"]
        if module_id in modules:
            raise ManifestError(f"duplicate module: {module_id}")
        capabilities = module.get("capabilities")
        if not isinstance(capabilities, list) or not capabilities or not all(isinstance(x, str) for x in capabilities):
            raise ManifestError(f"module {module_id} needs non-empty capabilities")
        _unique(capabilities, f"capability in {module_id}")
        if not isinstance(module.get("version"), str) or not module["version"]:
            raise ManifestError(f"module {module_id} needs a version")
        if not isinstance(module.get("path"), str) or not module["path"] or module["path"].startswith(("/", "..")):
            raise ManifestError(f"module {module_id} needs a relative distribution path")
        module_paths.append(module["path"])
        for relation in ("requires", "integrates_with"):
            values = module.get(relation)
            if not isinstance(values, list) or not all(isinstance(value, str) and value for value in values):
                raise ManifestError(f"module {module_id} needs a {relation} list")
            _unique(values, f"{relation} in {module_id}")
        coverage = module.get("hosts")
        if not isinstance(coverage, dict):
            raise ManifestError(f"module {module_id} needs host coverage")
        for host in coverage:
            if host not in hosts:
                raise ManifestError(f"module {module_id} names unknown host: {host}")
        for host in hosts:
            if coverage.get(host) not in {"native", "explicit-command", "unsupported"}:
                raise ManifestError(f"module {module_id} has invalid coverage for {host}")
        modules[module_id] = module
    _unique(module_paths, "module path")
    for module_id, module in modules.items():
        for relation in ("requires", "integrates_with"):
            unknown = sorted(set(module[relation]) - set(modules))
            if unknown:
                raise ManifestError(f"unknown {relation}: {module_id} -> {', '.join(unknown)}")
    _cycles(modules)
    _validate_hooks(data, modules)
    capability_set = {capability for module in modules.values() for capability in module["capabilities"]}
    bundles = data.get("bundles")
    if not isinstance(bundles, dict) or not bundles:
        raise ManifestError("bundles must be a non-empty object")
    for name, bundle in bundles.items():
        if not isinstance(bundle, dict):
            raise ManifestError(f"bundle {name} must be an object")
        module_ids = bundle.get("modules")
        capability_ids = bundle.get("capabilities")
        if not isinstance(module_ids, list) or not module_ids:
            raise ManifestError(f"bundle {name} needs modules")
        if not isinstance(capability_ids, list) or not capability_ids:
            raise ManifestError(f"bundle {name} needs capabilities")
        unknown_modules = sorted(set(module_ids) - set(modules))
        unknown_capabilities = sorted(set(capability_ids) - capability_set)
        if unknown_modules:
            raise ManifestError(f"bundle {name} has unknown module: {', '.join(unknown_modules)}")
        if unknown_capabilities:
            raise ManifestError(f"bundle {name} has unknown capability: {', '.join(unknown_capabilities)}")
    if data.get("exit_codes") != {"ok": 0, "warn": 1, "block": 2, "error": 3}:
        raise ManifestError("exit_codes must be 0 ok, 1 warn, 2 block and 3 error")
    routing = data.get("routing")
    if not isinstance(routing, dict) or routing.get("tiers") != ["economy", "balanced", "frontier"]:
        raise ManifestError("routing tiers must be economy, balanced and frontier")
    maps = data.get("maps")
    if not isinstance(maps, list) or not maps or not all(isinstance(item, str) and item for item in maps):
        raise ManifestError("maps must be a non-empty list")
    _unique(maps, "map")
    installer = data.get("installer")
    if not isinstance(installer, dict) or not isinstance(installer.get("path"), str) or not installer["path"]:
        raise ManifestError("installer needs a path")
    monitors = data.get("monitors")
    if not isinstance(monitors, list) or not monitors:
        raise ManifestError("monitors must be a non-empty list")
    monitor_ids: list[str] = []
    for monitor in monitors:
        if not isinstance(monitor, dict):
            raise ManifestError("every monitor must be an object")
        for field in ("id", "target", "type", "severity", "cost", "consumer_gate"):
            if not isinstance(monitor.get(field), str) or not monitor[field]:
                raise ManifestError(f"monitor needs {field}")
        for field in ("cadence", "freshness"):
            if not isinstance(monitor.get(field), int) or monitor[field] <= 0:
                raise ManifestError(f"monitor {monitor['id']} needs positive {field}")
        monitor_ids.append(monitor["id"])
    _unique(monitor_ids, "monitor")

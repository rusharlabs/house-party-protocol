"""Offline, project-scoped composition of the existing module installer.

Planning reads files only. Applying executes a checksummed kit doctor with argv,
preflights the entire batch, and records owned files after every module. Native
host activation remains a separate, explicit action.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path, PureWindowsPath
from typing import Any

from hpp import __version__
from hpp.install import installation_plan
from hpp.manifest import hooks_for_modules, load_manifest, validate_distribution
from hpp.wizard import InitOptions, _Context, stage_profile

SCHEMA = "hpp.setup/v1"
RECEIPT = Path(".hpp/setup-receipt.json")
_IGNORE_DIRS = {"__pycache__", ".pytest_cache"}
_SCAN_SUFFIXES = {".py", ".md", ".yaml", ".yml", ".json", ".sh"}


class SetupError(ValueError):
    """The batch cannot be prepared safely."""

    def __init__(self, message: str, result: dict[str, Any] | None = None):
        super().__init__(message)
        self.result = result


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _safe_rel(value: str) -> Path:
    win = PureWindowsPath(value)
    if (not value or win.drive or win.root or "\\" in value
            or any(p in {"", ".", ".."} for p in value.split("/"))):
        raise SetupError(f"unsafe relative path: {value!r}")
    return Path(value)


def _no_links(path: Path) -> None:
    # lstat is available on the Python 3.10 floor, unlike Path.is_junction.
    for part in (path, *path.parents):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise SetupError(f"linked/reparse path refused: {part}")


def _files(root: Path) -> dict[str, str]:
    """Hash regular files without traversing links, including existing destinations."""
    _no_links(root)
    if not root.exists():
        return {}
    if not root.is_dir():
        raise SetupError(f"directory required: {root}")
    result: dict[str, str] = {}
    stack = [root]
    while stack:
        for child in sorted(stack.pop().iterdir()):
            _no_links(child)
            # -B prevents new bytecode; it does not stop Python reading an
            # unchecked-hash or sourceless cache. Neither checksummed source
            # nor a previously copied runtime may hide executable inventory.
            if child.name in _IGNORE_DIRS or child.suffix.lower() in {".pyc", ".pyo"}:
                raise SetupError(f"cache/bytecode path refused; preserve and reconcile it: {child}")
            if child.is_dir():
                stack.append(child)
            elif child.is_file():
                result[child.relative_to(root).as_posix()] = _sha(child)
            else:
                raise SetupError(f"non-regular file refused: {child}")
    return result


def _verify_kit(root: Path) -> dict[str, str]:
    actual = _files(root)
    inventory = root / "CHECKSUMS.txt"
    if "CHECKSUMS.txt" not in actual:
        raise SetupError(f"CHECKSUMS.txt missing: {root}")
    expected: dict[str, str] = {}
    for line in inventory.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        match = re.fullmatch(r"([0-9a-fA-F]{64})\s{1,2}(.+)", line)
        if not match:
            raise SetupError(f"invalid checksum entry in {inventory}")
        digest, rel = match.groups()
        _safe_rel(rel)
        if rel in expected and expected[rel] != digest.lower():
            raise SetupError(f"conflicting duplicate checksum entry: {rel}")
        expected[rel] = digest.lower()
    if not expected:
        raise SetupError(f"empty checksum inventory: {inventory}")
    for rel, digest in expected.items():
        if actual.get(rel) != digest:
            raise SetupError(f"checksum mismatch or missing file: {root / rel}")
    extras = set(actual) - set(expected) - {"CHECKSUMS.txt", ".lint-report.json"}
    if extras:
        raise SetupError(f"untracked module files in {root}: {', '.join(sorted(extras))}")
    return actual


def _profile_offers(kit: Path) -> list[tuple[Path, str]]:
    """Mirror kit_doctor's read-only seed discovery without importing source code."""
    loader = kit / "_lib/profile_loader.py"
    match = re.search(r"^_NAMES\s*=\s*\(\s*['\"]([^'\"]+)['\"]",
                      loader.read_text(encoding="utf-8") if loader.is_file() else "", re.M)
    result = []
    for seed in sorted(kit.glob("*.example.*")):
        name = seed.name.replace(".example.", ".")
        if match and seed.name.split(".example.")[0] == "profile":
            name = match.group(1)
        result.append((seed, name))
    for seed in sorted((kit / "templates").glob("*.example.*")):
        name = seed.name.replace(".example.", ".")
        if any(name in p.read_text(encoding="utf-8", errors="replace")
               for p in kit.rglob("*") if p != seed and p.is_file() and p.suffix in _SCAN_SUFFIXES
               and not _IGNORE_DIRS.intersection(p.relative_to(kit).parts)):
            result.append((seed, name))
    for _, name in result:
        path = _safe_rel(name)
        if len(path.parts) != 1 or name.startswith(".") or name in {
                "AGENTS.md", "CLAUDE.md", "settings.json", "settings.local.json", "hooks.json", "config.toml"}:
            raise SetupError(f"module profile cannot write host configuration/instructions: {name}")
    return result


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SetupError(f"JSON object required: {path}")
    return value


def _owned_ok(target: Path, receipt: dict[str, Any]) -> None:
    owned = receipt.get("owned_files", {})
    if not isinstance(owned, dict):
        raise SetupError("invalid owned_files in setup receipt")
    for rel, digest in owned.items():
        path = target / _safe_rel(rel)
        _no_links(path)
        if not path.is_file() or _sha(path) != digest:
            raise SetupError(f"previously prepared file changed or missing: {rel}")


def _bad_report(value: Any) -> bool:
    # kit_doctor has legacy exits that can be zero for warnings, and smoke's
    # overall status can omit nested errors. Inspect the actual result too.
    if isinstance(value, dict):
        if value.get("status") is not None and not isinstance(value.get("status"), str):
            return True
        if value.get("status") in {"warn", "fail", "error", "block", "corrupt", "timeout"}:
            return True
        if value.get("conflicts") or value.get("links_ignored") or value.get("failed_count", 0):
            return True
        return any(_bad_report(v) for v in value.values())
    if isinstance(value, list):
        return any(_bad_report(v) for v in value)
    return False


def _module_environment(python: str | None = None) -> dict[str, str]:
    """Keep module self-tests outside caller profiles, sessions and paid CLIs.

    Remove complete PATH entries containing real host commands instead of
    inserting executable stubs that could make which() falsely report a host.
    This is a child-process environment only; host launchers keep their PATH.
    """
    prefixes = ("ANTHROPIC_", "CLAUDE_", "CODEX_", "OPENAI_", "OPENROUTER_", "TYPESAFE_",
                "HPP_", "LANE_", "GOTCHA_", "SESSION_BOOT_", "SUPABASE_", "GIT_")
    names = {"OPERATOR_PROFILE", "EXPECTED_ROOT", "ALLOW_CROSS_ROOT", "SNAPSHOT_CONFIRMED",
             "GUARD_ORIGINS", "CLAUDECODE", "PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP",
             "PYTHONUSERBASE", "PYTHONINSPECT", "BASH_ENV", "ENV", "NODE_OPTIONS", "NODE_PATH"}
    env = {key: value for key, value in os.environ.items()
           if not key.upper().startswith(prefixes) and key.upper() not in names
           and not key.upper().endswith(("_API_KEY", "_TOKEN", "_SECRET", "_PASSWORD"))}
    extensions = ("", ".exe", ".com", ".cmd", ".bat", ".ps1")
    def has_host(directory: Path) -> bool:
        return any((directory / (host + extension)).is_file()
                   for host in ("claude", "codex") for extension in extensions)
    entries = []
    for entry in env.get("PATH", "").split(os.pathsep):
        directory = Path(entry.strip('"'))
        if not entry or not directory.is_absolute() or entry.startswith(("\\\\", "//")):
            continue
        if has_host(directory):
            continue
        entries.append(entry)
    if python and Path(python).is_absolute() and Path(python).is_file():
        directory = Path(python).absolute().parent
        if has_host(directory):
            raise SetupError("module Python directory contains a host CLI; use an isolated HPP Python environment")
        entries.insert(0, str(directory))
    env.update(PATH=os.pathsep.join(entries), PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1",
               GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1", GIT_TERMINAL_PROMPT="0")
    return env


def _execute(argv: list[str], cwd: Path) -> dict[str, Any]:
    env = _module_environment(argv[0])
    proc = subprocess.run(argv, cwd=str(cwd), env=env, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=1800, shell=False)
    try:
        value = json.loads(proc.stdout)
    except ValueError as exc:
        raise SetupError(f"installer returned invalid JSON (exit {proc.returncode}): {(proc.stdout + proc.stderr)[-1000:]}") from exc
    if not isinstance(value, dict) or proc.returncode != 0 or _bad_report(value):
        raise SetupError(f"installer refused or failed (exit {proc.returncode})",
                         value if isinstance(value, dict) else {"output": value})
    return value


def _probe_python(python: str, target: Path) -> None:
    # No import of the emitted installer until its inventory has been verified.
    script = "import json,sys,yaml; print(json.dumps({'status':'ok','supported':sys.version_info >= (3,10)}))"
    result = _execute([python, "-I", "-B", "-X", "utf8", "-c", script], target)
    if not result.get("supported"):
        raise SetupError("module runtime requires Python >=3.10 and PyYAML")


def _save(target: Path, report: dict[str, Any]) -> None:
    path = target / RECEIPT
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    _no_links(temporary)
    with temporary.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def _destination_plan(source: Path, target: Path, host: str, selected: list[str],
                      by_id: dict[str, Any], verified: dict[str, dict[str, str]],
                      profiles: dict[str, str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Enumerate the existing engine's destinations without executing source.

    Skills change frontmatter and runtime references in codex_skills.py; the
    map identifies that transformation, never mislabels source hashes as the
    transformed destination's expected hash.
    """
    files: dict[str, dict[str, Any]] = {}
    actions: list[dict[str, Any]] = []

    def add(destination: str, origin: str, kind: str, module: str | None = None) -> None:
        _safe_rel(destination)
        path = target / destination
        _no_links(path)
        files[destination] = {"destination": destination, "source": origin,
            "kind": kind, "module": module, "action": "preserve" if path.exists() else "create"}

    add(".hpp/profile.json", "generated:hpp.init/v1", "project-profile")
    add(RECEIPT.as_posix(), "generated:hpp.setup/v1", "setup-receipt")
    if (target / RECEIPT).exists():
        files[RECEIPT.as_posix()]["action"] = "update-checkpoint-or-verify-completed"
    for destination, origin in profiles.items():
        add(destination, origin, "module-profile")
    # Keep this small discovery seam aligned with codex_skills._ignored/_slug.
    ignored = {"__pycache__", ".pytest_cache", "ip-ruleset.yaml", "operator-profile.yaml", "HANDOVER.md"}
    def included(rel: str) -> bool:
        return not any(part in ignored or part.startswith("_superseded") for part in Path(rel).parts)
    def slug(value: str) -> str:
        return re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")
    if host == "codex":
        for module_id in selected:
            kit = source / by_id[module_id]["path"]
            runtime = f".agents/hpp/{module_id}"
            actions.append({"module": module_id, "kind": "runtime", "destination": runtime,
                            "action": "verify-existing" if (target / runtime).exists() else "copy-runtime"})
            for rel in sorted(verified[module_id]):
                if included(rel):
                    add(f"{runtime}/{rel}", str(kit / rel), "runtime-copy", module_id)
            owners: dict[str, str] = {}
            skill_root = kit / "skills"
            for skill in sorted(skill_root.iterdir()) if skill_root.is_dir() else []:
                if not skill.is_dir() or not (skill / "SKILL.md").is_file():
                    continue
                destination = f".agents/skills/hpp-{slug(module_id)}-{slug(skill.name)}"
                if destination in owners:
                    raise SetupError(f"skill destination collision: {owners[destination]} and {skill.name} -> {destination}")
                owners[destination] = skill.name
                actions.append({"module": module_id, "kind": "skill", "destination": destination,
                                "action": "verify-existing" if (target / destination).exists() else "copy-transformed-skill"})
                prefix = skill.relative_to(kit).as_posix() + "/"
                for rel in sorted(verified[module_id]):
                    if rel.startswith(prefix) and included(rel[len(prefix):]):
                        add(f"{destination}/{rel[len(prefix):]}", str(kit / rel), "codex-skill-transform", module_id)
    return [files[rel] for rel in sorted(files)], actions


def run_setup(source: Path, target: Path, host: str, *, bundle: str = "reliable-coding",
              all_compatible: bool = False, modules: str | list[str] | None = None,
              apply: bool = False, python: str | None = None) -> dict[str, Any]:
    """Return a machine-readable report; errors never claim host activation."""
    report: dict[str, Any] = {"schema": SCHEMA, "status": "error", "exit_code": 2,
        "mode": "apply" if apply else "plan", "version": __version__, "host": host,
        "selected_modules": [], "modules": [], "skipped_modules": [],
        "planned_files": [], "planned_actions": [],
        "hook_capabilities": [], "native_activation_status": "not-measured",
        "activation_commands": [], "host_activation": "not-measured", "owned_files": {},
        "registry_mode": "no-register",
        "module_execution_policy": {"caller_profiles_and_sessions": "not-inherited",
            "provider_credential_env": "not-inherited", "host_cli_path_entries": "removed",
            "global_git_config": "not-inherited"},
        "manual_gates": ["native-plugin-activation", "hooks", "statusLine"] if host == "claude-code" else ["hooks"],
        "runtime_python": python or sys.executable, "runtime_dependencies": ["PyYAML"],
        "rollback": "Only files listed in owned_files were created by setup. Preserve the receipt; review those paths before removing them. Existing files are never overwritten."}
    started = False
    before: dict[str, str] = {}
    try:
        source, target = Path(os.path.abspath(source.expanduser())), Path(os.path.abspath(target.expanduser()))
        _no_links(source)
        _no_links(target)
        if not source.is_dir() or not target.is_dir():
            raise SetupError("--source and --target must be existing directories")
        if source == target or source in target.parents or target in source.parents:
            raise SetupError("source and target directories must not overlap")
        manifest_path = source / "hpp.manifest.json"
        for path in (manifest_path, source / "marketplace.json", source / ".agents/plugins/marketplace.json"):
            _no_links(path)
        manifest, manifest_path = load_manifest(str(manifest_path))
        if manifest.get("product_version") != __version__:
            raise SetupError(f"source version {manifest.get('product_version')} differs from CLI {__version__}")
        by_id = {m["id"]: m for m in manifest["modules"]}
        for module in by_id.values():
            _safe_rel(module["id"])
            if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", module["id"]):
                raise SetupError(f"unsafe module id: {module['id']}")
            _no_links(source / _safe_rel(module["path"]))
        installer = source / _safe_rel(manifest["installer"]["path"])
        _no_links(installer)
        distribution = validate_distribution(manifest, source)
        if not distribution.get("checked") or distribution.get("status") != "ok":
            raise SetupError("--source must contain a full emitted distribution, not only the CLI")
        if host not in {"claude-code", "codex"} or host not in manifest["hosts"]:
            raise SetupError(f"unsupported host: {host}")
        if modules is not None and all_compatible:
            raise SetupError("choose --modules or --all-compatible")
        if modules is not None:
            selected = [m.strip() for m in modules.split(",")] if isinstance(modules, str) else list(modules)
            if not selected or any(not m for m in selected):
                raise SetupError("--modules requires non-empty module ids")
        elif all_compatible:
            selected = [m["id"] for m in by_id.values() if m["hosts"][host] != "unsupported"]
            report["skipped_modules"] = [{"id": m["id"], "reason": f"unsupported on {host}"}
                                        for m in by_id.values() if m["hosts"][host] == "unsupported"]
        else:
            if bundle not in manifest["bundles"]:
                raise SetupError(f"unknown bundle: {bundle}")
            selected = list(manifest["bundles"][bundle]["modules"])
        if len(set(selected)) != len(selected) or set(selected) - set(by_id):
            raise SetupError("duplicate or unknown module ids: " + ", ".join(selected))
        # Canonical order makes shared-profile precedence independent of argv.
        selected = [module_id for module_id in by_id if module_id in selected]
        custom = modules is not None or all_compatible
        planning = {**manifest, "bundles": {**manifest["bundles"], "custom": {"modules": selected}}}
        installation_plan(planning, "custom" if custom else bundle, host, target)
        # The installer and its helper scripts must be attested even when kit-forge
        # was not explicitly selected.
        installer_owners = [m for m in by_id.values() if (source / m["path"]) in installer.parents]
        if len(installer_owners) != 1:
            raise SetupError("installer must belong to exactly one checksummed module")
        verified = {}
        for module_id in dict.fromkeys([*selected, installer_owners[0]["id"]]):
            verified[module_id] = _verify_kit(source / by_id[module_id]["path"])
        owner = installer_owners[0]
        installer_rel = installer.relative_to(source / owner["path"]).as_posix()
        if installer_rel not in verified[owner["id"]]:
            raise SetupError("installer absent from checksum inventory")
        report.update(source=str(source), target=str(target), selected_modules=selected,
                      target_fingerprint=hashlib.sha256(str(target).encode("utf-8")).hexdigest(),
                      distribution=distribution, receipt_path=str(target / RECEIPT),
                      source_integrity={module_id: _sha(source / by_id[module_id]["path"] / "CHECKSUMS.txt")
                                        for module_id in verified},
                      hook_capabilities=hooks_for_modules(manifest, selected))
        receipt_path = target / RECEIPT
        for path in (receipt_path, receipt_path.with_suffix(".json.tmp"), target / ".hpp/profile.json"):
            _no_links(path)
        if receipt_path.with_suffix(".json.tmp").exists():
            raise SetupError("unfinished receipt temporary file exists; preserve and reconcile it before retry")
        previous = _read_object(receipt_path) if receipt_path.exists() else {}
        if previous:
            if (previous.get("schema") != SCHEMA or previous.get("source") != str(source)
                    or previous.get("target") != str(target)
                    or previous.get("target_fingerprint") != report["target_fingerprint"]
                    or previous.get("host") != host or previous.get("version") != __version__
                    or previous.get("selected_modules") != selected
                    or previous.get("source_integrity") != report["source_integrity"]):
                raise SetupError("existing setup receipt conflicts with requested source/host/selection/version")
            prior_modules = previous.get("modules")
            if (not isinstance(prior_modules, list) or len(prior_modules) != len(selected)
                    or any(not isinstance(item, dict) or item.get("id") != selected[index]
                           or not isinstance(item.get("status"), str)
                           or item.get("status") not in {"prepared", "pending", "running", "failed"}
                           for index, item in enumerate(prior_modules))):
                raise SetupError("malformed module ownership in setup receipt")
            _owned_ok(target, previous)
            report["owned_files"] = dict(previous["owned_files"])
        ctx = _Context(InitOptions(target=target, target_label=str(target), answers={"host": host,
            "bundle": bundle if not custom else "reliable-coding", "policy_mode": "audit",
            **({"modules": selected} if custom else {})}), manifest, manifest_path)
        profile_path = target / ".hpp/profile.json"
        ctx.existing_profile = _read_object(profile_path) if profile_path.exists() else None
        stage = stage_profile(ctx)
        if stage["status"] != "ok":
            raise SetupError("existing .hpp/profile.json conflicts with requested setup")
        report["profile"] = ctx.profile
        proposed: dict[str, str] = {}
        profile_sources: dict[str, str] = {}
        report["shared_profile_seeds"] = []
        report["customized_profiles"] = []
        done = {m["id"] for m in previous.get("modules", []) if m.get("status") == "prepared"}
        for module_id in selected:
            module = by_id[module_id]
            kit = source / module["path"]
            for seed, name in _profile_offers(kit):
                path = target / name
                _no_links(path)
                digest = _sha(seed)
                profile_sources.setdefault(name, str(seed))
                if name in proposed and proposed[name] != digest:
                    # The module engine deliberately keeps the first seed at a
                    # shared loader path. Make that composition visible; never
                    # silently describe the later template as configured.
                    report["shared_profile_seeds"].append({"module": module_id, "target": name,
                        "seed": str(seed), "status": "kept-first-selected-seed",
                        "manual_action": "Review this module's example for optional configuration; setup does not merge profiles."})
                else:
                    proposed[name] = digest
                if path.exists():
                    if not path.is_file():
                        raise SetupError(f"module profile destination is not a regular file: {name}")
                    if _sha(path) != proposed[name] and name not in report["customized_profiles"]:
                        report["customized_profiles"].append(name)
            if host == "codex":
                for path in [target / ".agents/hpp" / module_id,
                             *sorted((target / ".agents/skills").glob(f"hpp-{module_id}-*"))]:
                    files = _files(path)
                    for rel in files:
                        local = (path / rel).relative_to(target).as_posix()
                        if local not in previous.get("owned_files", {}):
                            raise SetupError(f"existing runtime/skill not owned by setup: {local}")
                _no_links(target / ".agents/skills")
            argv = [python or sys.executable, "-I", "-B", "-X", "utf8", str(installer), "install", "--kit", str(kit),
                    "--target", str(target), "--host", host, "--no-register"]
            report["modules"].append({"id": module_id, "integration": module["hosts"][host],
                "status": "prepared" if module_id in done else "pending", "argv": argv,
                "files_status": "previously-prepared" if module_id in done else "planned",
                "runtime_status": "copied" if module_id in done and host == "codex" else "not-copied",
                "configuration_status": "customized-not-verified" if any(name in report["customized_profiles"]
                    for _, name in _profile_offers(kit)) else "default-seeds",
                "activation_status": "manual" if host == "claude-code" and module["hosts"][host] == "native" else "explicit-command"})
        allowed_profiles = {".hpp/profile.json", *proposed}
        for rel in previous.get("owned_files", {}):
            allowed_runtime = host == "codex" and any(
                rel.startswith(f".agents/hpp/{module_id}/") or rel.startswith(f".agents/skills/hpp-{module_id}-")
                for module_id in selected)
            if rel not in allowed_profiles and not allowed_runtime:
                raise SetupError(f"receipt claims a file outside setup ownership: {rel}")
        if host == "claude-code":
            native = [m for m in report["modules"] if m["integration"] == "native"]
            if native:
                report["activation_commands"] = [["claude", "plugin", "marketplace", "add", str(source), "--scope", "project"],
                    *[["claude", "plugin", "install", f"{m['id']}@{manifest['name']}", "--scope", "project"] for m in native]]
        report["native_activation_status"] = "manual-required" if report["activation_commands"] else "not-applicable"
        report["planned_files"], report["planned_actions"] = _destination_plan(
            source, target, host, selected, by_id, verified, profile_sources)
        destinations = {item["destination"] for item in report["planned_files"]} - {RECEIPT.as_posix()}
        unexpected_owned = set(previous.get("owned_files", {})) - destinations
        if unexpected_owned:
            raise SetupError("receipt claims files outside the destination plan: " + ", ".join(sorted(unexpected_owned)))
        if previous and done:
            required = [item for item in report["planned_files"] if item["kind"] != "setup-receipt"
                        and (len(done) == len(selected) or item["module"] in done
                             or item["kind"] == "project-profile")]
            for item in required:
                rel = item["destination"]
                if not (target / rel).is_file():
                    raise SetupError(f"completed receipt is missing a required artifact: {rel}")
                if item["kind"] in {"runtime-copy", "codex-skill-transform"} and rel not in previous["owned_files"]:
                    raise SetupError(f"completed receipt omits artifact ownership: {rel}")
        if not apply:
            report.update(status="planned", exit_code=0)
            return report
        _probe_python(python or sys.executable, source)
        if len(done) == len(selected):
            # A fully verified rerun does not replace the successful receipt or
            # discard its stage evidence merely to say nothing changed.
            for item, recorded in zip(report["modules"], previous["modules"]):
                for key in ("preflight", "result"):
                    if key in recorded:
                        item[key] = recorded[key]
            report.update(status="prepared", exit_code=0, rerun_verified=True)
            return report
        for item in report["modules"]:
            if item["status"] != "prepared":
                try:
                    item["preflight"] = _execute(item["argv"], installer.parent)
                except SetupError as exc:
                    item["preflight"] = exc.result
                    item["status"] = "preflight-failed"
                    raise SetupError(f"{item['id']} preflight: {exc}") from exc
        # No target file has been written before every module plan passed.
        before = _snapshot(target, proposed, host, selected)
        started = True
        report.update(status="partial", exit_code=2)
        _save(target, report)
        ctx.options.apply = True
        stage_profile(ctx)
        _capture_owned(target, report, before, proposed)
        _save(target, report)
        for item in report["modules"]:
            if item["status"] == "prepared":
                continue
            item["status"] = "running"
            _save(target, report)
            try:
                item["result"] = _execute([*item["argv"], "--apply"], installer.parent)
            except (SetupError, OSError, subprocess.SubprocessError) as exc:
                item["status"] = "failed"
                if isinstance(exc, SetupError):
                    item["result"] = exc.result
                raise
            item.update(status="prepared", files_status="prepared",
                        runtime_status="copied" if host == "codex" else "source-checkout")
            _capture_owned(target, report, before, proposed)
            _save(target, report)
        report.update(status="prepared", exit_code=0)
        _save(target, report)
        return report
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        report.update(status="partial" if started else "error", exit_code=2, error=str(exc))
        if started:
            try:
                _capture_owned(target, report, before, proposed)
                _save(target, report)
            except (ValueError, OSError) as receipt_error:
                report["receipt_error"] = str(receipt_error)
        return report


def _snapshot(target: Path, profiles: dict[str, str], host: str, selected: list[str]) -> dict[str, str]:
    result = {}
    for name in [".hpp/profile.json", *profiles]:
        path = target / name
        if path.is_file():
            result[name] = _sha(path)
    if host == "codex":
        for module_id in selected:
            for root in [target / ".agents/hpp" / module_id,
                         *sorted((target / ".agents/skills").glob(f"hpp-{module_id}-*"))]:
                for rel, digest in _files(root).items():
                    result[(root / rel).relative_to(target).as_posix()] = digest
    return result


def _capture_owned(target: Path, report: dict[str, Any], before: dict[str, str], profiles: dict[str, str]) -> None:
    after = _snapshot(target, profiles, report["host"], report["selected_modules"])
    changed = [rel for rel in before if after.get(rel) != before[rel]]
    if changed:
        raise SetupError("installer changed pre-existing files: " + ", ".join(changed))
    report["owned_files"].update({rel: digest for rel, digest in after.items() if rel not in before})

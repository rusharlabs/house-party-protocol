"""`hpp init`: six fixed stages, plan-first, with a readiness score derived from real checks."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

from hpp import __version__
from hpp.brand import closing_line, logo_lines, pick_closing, PALETTE
from hpp.evals import EvalError, run_suite
from hpp.graph import build_graph
from hpp.install import InstallError, installation_plan
from hpp.manifest import ManifestError, hooks_for_modules, validate_distribution, PROTOCOL_VERSION
from hpp.policy import assess, exit_for as policy_exit_for
from hpp.state import StateError, event_path, project, read_events
from hpp.term import Console

STAGES = ("detect", "prereqs", "profile", "configure", "wire-suggest", "smoke")
BOOT_LINES = {
    "detect": "detecting host",
    "prereqs": "checking prerequisites",
    "profile": "mounting profile",
    "configure": "loading modules",
    "wire-suggest": "wiring suggestions",
    "smoke": "verifying evidence",
}
PROFILE_SCHEMA = "hpp.init/v1"
REPORT_SCHEMA = "hpp.init-report/v1"
PROFILE_RELPATH = Path(".hpp") / "profile.json"
# Why: the floor comes from what the CI matrix exercises, not from what the code would
# tolerate. The wizard refusing 3.9 is the same promise pyproject declares - two sources
# saying the same thing.
MIN_PYTHON = (3, 10)
POLICY_MODES = ("audit", "enforce")
# Why: the public marketplace is the channel the README documents; a flag overrides it for forks.
DEFAULT_MARKETPLACE = "rusharlabs/house-party-protocol"
BENCHMARK_SUITE = Path("examples") / "reliable-coding" / "benchmark-suite.json"
READINESS_CELLS = 20

# Why: the host seam mirrors the installer contract, so wire-suggest names the same paths the
# module installer will touch, without hpp ever writing to them.
HOSTS: dict[str, dict[str, Any]] = {
    "claude-code": {
        "settings_path": ".claude/settings.local.json",
        "plugin_manifest": ".claude-plugin/plugin.json",
        "manual_gates": ["hooks", "statusLine"],
    },
    "codex": {
        "settings_path": None,
        "agents_file": "AGENTS.md",
        "skills_path": ".agents/skills",
        "runtime_path": ".agents/hpp",
        "manual_gates": ["hooks"],
    },
}

_STATUS_RANK = {"ok": 0, "skipped": 0, "warn": 1, "fail": 2}


class InitUsageError(Exception):
    """The invocation itself is wrong (exit 3); the workspace was not judged."""


@dataclass
class InitOptions:
    target: Path
    target_label: str
    apply: bool = False
    answers: dict[str, Any] = field(default_factory=dict)
    sources: dict[str, str] = field(default_factory=dict)
    interactive: bool = False
    benchmark_k: int = 1
    marketplace: str = DEFAULT_MARKETPLACE


@dataclass
class _Context:
    options: InitOptions
    manifest: dict[str, Any]
    manifest_path: Path
    ask: Optional[Callable[[dict[str, Any]], tuple[str, str]]] = None
    classification: str = ""
    existing_profile: Optional[dict[str, Any]] = None
    distribution: dict[str, Any] = field(default_factory=dict)
    answers: dict[str, Any] = field(default_factory=dict)
    pending: list[str] = field(default_factory=list)
    profile: dict[str, Any] = field(default_factory=dict)
    profile_action: str = ""
    plan: dict[str, Any] = field(default_factory=dict)
    checksums: tuple[int, int, int] = (0, 0, 0)

    @property
    def root(self) -> Path:
        return self.manifest_path.parent


# ---------------------------------------------------------------------------
# Questions and option preparation
# ---------------------------------------------------------------------------


def questions(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    hosts = list(manifest["hosts"])
    bundles = sorted(manifest["bundles"])
    return [
        {"id": "host", "prompt": "Which host will run the harness?", "type": "choice",
         "options": hosts, "default": "claude-code" if "claude-code" in hosts else hosts[0]},
        {"id": "bundle", "prompt": "Which bundle should be planned?", "type": "choice",
         "options": bundles, "default": "reliable-coding" if "reliable-coding" in bundles else bundles[0]},
        {"id": "policy_mode", "prompt": "How should the command policy run?", "type": "choice",
         "options": list(POLICY_MODES), "default": "audit"},
    ]


def _load_answer_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise InitUsageError(f"profile file not found: {path}")
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InitUsageError(f"profile file is not valid JSON: {path}: {exc.msg}") from exc
    if not isinstance(loaded, dict):
        raise InitUsageError(f"profile file root must be a JSON object: {path}")
    allowed = {"host", "bundle", "policy_mode", "modules"}
    unknown = sorted(set(loaded) - allowed)
    if unknown:
        raise InitUsageError(f"profile file has unknown keys: {', '.join(unknown)} (allowed: {', '.join(sorted(allowed))})")
    for key in ("host", "bundle", "policy_mode"):
        if key in loaded and not isinstance(loaded[key], str):
            raise InitUsageError(f"profile key {key} must be a string")
    if "modules" in loaded:
        modules = loaded["modules"]
        if not isinstance(modules, list) or not modules or not all(isinstance(item, str) and item for item in modules):
            raise InitUsageError("profile key modules must be a non-empty list of module ids")
    return loaded


def _split_modules(raw: str) -> list[str]:
    modules = [item.strip() for item in raw.split(",")]
    modules = [item for item in modules if item]
    if not modules:
        raise InitUsageError("--modules needs at least one module id")
    return modules


def prepare_options(args: Any, manifest: dict[str, Any], env: Optional[Mapping[str, str]] = None,
                    stdin_tty: Optional[bool] = None, stdout_tty: Optional[bool] = None) -> InitOptions:
    """Validate flags before any stage runs: usage errors raise InitUsageError, choices InstallError."""
    import os

    env = os.environ if env is None else env
    target = Path(args.target).expanduser()
    if not target.is_dir():
        raise InitUsageError(f"target is not a directory: {target}")
    answers: dict[str, Any] = {}
    sources: dict[str, str] = {}
    if getattr(args, "profile", None):
        for key, value in _load_answer_file(Path(args.profile).expanduser()).items():
            answers[key] = value
            sources[key] = "file"
    for key in ("host", "bundle", "policy_mode"):
        value = getattr(args, key, None)
        if value:
            answers[key] = value
            sources[key] = "flag"
    if getattr(args, "modules", None):
        answers["modules"] = _split_modules(args.modules)
        sources["modules"] = "flag"
    known_modules = {module["id"] for module in manifest["modules"]}
    if "host" in answers and answers["host"] not in manifest["hosts"]:
        raise InstallError(f"unknown host: {answers['host']} (expected one of {', '.join(manifest['hosts'])})")
    if "bundle" in answers and answers["bundle"] not in manifest["bundles"]:
        raise InstallError(f"unknown bundle: {answers['bundle']} (expected one of {', '.join(sorted(manifest['bundles']))})")
    if "policy_mode" in answers and answers["policy_mode"] not in POLICY_MODES:
        raise InstallError(f"unknown policy mode: {answers['policy_mode']} (expected audit or enforce)")
    for module_id in answers.get("modules", []):
        if module_id not in known_modules:
            raise InstallError(f"unknown module: {module_id}")
    stdin_tty = _tty(sys.stdin) if stdin_tty is None else stdin_tty
    stdout_tty = _tty(sys.stdout) if stdout_tty is None else stdout_tty
    interactive = (
        stdin_tty and stdout_tty
        and not getattr(args, "non_interactive", False)
        and not getattr(args, "yes", False)
        and not getattr(args, "json", False)
        and not env.get("CI")
    )
    return InitOptions(
        target=target.resolve(), target_label=str(args.target), apply=bool(getattr(args, "apply", False)),
        answers=answers, sources=sources, interactive=interactive,
        benchmark_k=0 if getattr(args, "no_benchmark", False) else 1,
        marketplace=getattr(args, "marketplace", None) or DEFAULT_MARKETPLACE,
    )


def _tty(stream: Any) -> bool:
    probe = getattr(stream, "isatty", None)
    try:
        return bool(probe()) if probe else False
    except (OSError, ValueError):
        return False


# ---------------------------------------------------------------------------
# Stage helpers
# ---------------------------------------------------------------------------


def _stage(name: str, status: str, summary: str, detail: Optional[dict[str, Any]] = None,
           problems: Optional[list[dict[str, str]]] = None, exit_hint: int = 0) -> dict[str, Any]:
    return {"stage": name, "status": status, "summary": summary, "detail": detail or {},
            "problems": problems or [], "exit_hint": exit_hint}


def _problem(label: str, measured: str, expected: str, next_step: str) -> dict[str, str]:
    return {"label": label, "measured": measured, "expected": expected, "next_step": next_step}


def _git_commit_count(target: Path) -> Optional[int]:
    if shutil.which("git") is None:
        return None
    try:
        proc = subprocess.run(["git", "-C", str(target), "rev-list", "--count", "HEAD"],
                              capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return 0
    try:
        return int((proc.stdout or "").strip() or "0")
    except ValueError:
        return 0


def verify_checksums(module_dir: Path, checksums_file: Path) -> tuple[bool, int, list[str]]:
    """Compare every `sha256  path` line against the bytes on disk."""
    failures: list[str] = []
    checked = 0
    for line in checksums_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, separator, relative = line.partition("  ")
        if not separator:
            failures.append(f"malformed line: {line!r}")
            continue
        target = module_dir / relative
        if not target.is_file():
            failures.append(f"missing: {relative}")
            continue
        checked += 1
        if hashlib.sha256(target.read_bytes()).hexdigest() != expected:
            failures.append(f"mismatch: {relative}")
    return not failures, checked, failures


# ---------------------------------------------------------------------------
# The six stages
# ---------------------------------------------------------------------------


def stage_detect(ctx: _Context) -> dict[str, Any]:
    target = ctx.options.target
    signals: dict[str, Any] = {}
    existing: list[str] = []
    problems: list[dict[str, str]] = []
    claude_dir = target / ".claude"
    signals["claude_dir"] = claude_dir.is_dir()
    occupied = False
    for name in ("settings.json", "settings.local.json"):
        settings = claude_dir / name
        if settings.is_file():
            try:
                data = json.loads(settings.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                data = {}
            if isinstance(data, dict) and (data.get("hooks") or data.get("statusLine")):
                occupied = True
                existing.append(f".claude/{name}: hooks/statusLine already configured (kept)")
    signals["settings_occupied"] = occupied
    signals["agents_md"] = (target / "AGENTS.md").is_file()
    signals["agents_dir"] = (target / ".agents").is_dir()
    log = event_path(target)
    signals["event_log"] = log.is_file()
    signals["event_count"] = None
    if log.is_file():
        try:
            signals["event_count"] = len(read_events(log))
            existing.append(f".hpp/events.jsonl: {signals['event_count']} events (kept)")
        except StateError as exc:
            problems.append(_problem("event log", f"{log}: {exc}", "a JSON-lines log that projects onto the loop",
                                     f"inspect {log}, remove the corrupt line or move the file aside, then re-run"))
    profile_path = target / PROFILE_RELPATH
    signals["profile"] = "absent"
    if profile_path.is_file():
        try:
            loaded = json.loads(profile_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            loaded = None
            problems.append(_problem("profile", f"{profile_path}: {exc}", f"schema {PROFILE_SCHEMA}",
                                     "remove or repair .hpp/profile.json before --apply"))
        if isinstance(loaded, dict) and loaded.get("schema") == PROFILE_SCHEMA:
            ctx.existing_profile = loaded
            signals["profile"] = "present"
            existing.append(".hpp/profile.json: written by a previous hpp init (kept)")
        elif loaded is not None:
            signals["profile"] = "invalid"
            problems.append(_problem("profile", f"{profile_path}: schema is not {PROFILE_SCHEMA}", f"schema {PROFILE_SCHEMA}",
                                     "remove or repair .hpp/profile.json before --apply"))
    signals["git_commit_count"] = _git_commit_count(target)
    if ctx.existing_profile is not None:
        classification = "re-run"
    elif (signals["claude_dir"] or occupied or signals["agents_md"] or signals["event_log"]
          or (signals["git_commit_count"] or 0) > 3):
        classification = "in-progress"
    else:
        classification = "greenfield"
    ctx.classification = classification
    status = "warn" if problems else "ok"
    return _stage("detect", status, f"{classification} · {len(existing)} existing item(s) preserved",
                  {"classification": classification, "signals": signals, "existing_config": existing,
                   "target": str(target)}, problems)


def stage_prereqs(ctx: _Context) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    problems: list[dict[str, str]] = []
    status = "ok"
    exit_hint = 0
    version = sys.version_info
    python_ok = tuple(version[:2]) >= MIN_PYTHON
    measured_python = f"{version.major}.{version.minor}.{version.micro}"
    checks.append({"id": "python", "ok": python_ok, "measured": measured_python,
                   "expected": ">=%d.%d" % MIN_PYTHON, "command": f"{Path(sys.executable).name} --version"})
    if not python_ok:
        status, exit_hint = "fail", 2
        problems.append(_problem("python", measured_python, ">=%d.%d" % MIN_PYTHON,
                                 "install Python %d.%d or newer, then re-run with that interpreter" % MIN_PYTHON))
    manifest = ctx.manifest
    checks.append({"id": "manifest", "ok": True,
                   "measured": f"protocol {manifest['protocol_version']} · {len(manifest['modules'])} modules · {len(manifest['hosts'])} hosts",
                   "expected": f"protocol {PROTOCOL_VERSION}, validated", "command": "python -m hpp doctor"})
    try:
        distribution = validate_distribution(manifest, ctx.root)
    except ManifestError as exc:
        distribution = {"checked": True, "status": "error", "error": str(exc)}
        status, exit_hint = "fail", 2
        problems.append(_problem("distribution", str(exc), "manifest and marketplace.json agree",
                                 "python -m hpp doctor --json  (shows the divergence; re-emit the distribution)"))
    ctx.distribution = distribution
    if distribution.get("checked"):
        measured = (f"marketplace.json checked · {distribution.get('modules', 0)} modules"
                    if distribution.get("status") == "ok" else distribution.get("error", "diverges"))
    else:
        measured = "source tree (no marketplace.json beside the manifest)"
    checks.append({"id": "distribution", "ok": distribution.get("status") != "error", "verified": bool(distribution.get("checked")),
                   "measured": measured, "expected": "manifest and marketplace agree", "command": "python -m hpp doctor --json"})
    git = shutil.which("git")
    checks.append({"id": "git", "ok": git is not None, "measured": git or "not on PATH", "expected": "git on PATH (optional)",
                   "command": "git --version"})
    if git is None:
        if status == "ok":
            status = "warn"
        problems.append(_problem("git", "not on PATH", "git available so detect can read the commit count",
                                 _git_install_hint()))
    summary = f"python {measured_python} · protocol {manifest['protocol_version']}"
    if git is None:
        summary += " · git missing"
    return _stage("prereqs", status, summary, {"checks": checks}, problems, exit_hint)


def _git_install_hint() -> str:
    if sys.platform.startswith("win"):
        return "winget install --id Git.Git -e"
    if sys.platform == "darwin":
        return "xcode-select --install  (or: brew install git)"
    return "sudo apt-get install -y git  (or your distribution's package manager)"


def stage_profile(ctx: _Context) -> dict[str, Any]:
    options = ctx.options
    answers: dict[str, Any] = {}
    sources: dict[str, str] = {}
    pending: list[str] = []
    for question in questions(ctx.manifest):
        key = question["id"]
        if key in options.answers:
            answers[key] = options.answers[key]
            sources[key] = options.sources.get(key, "flag")
        elif options.interactive and ctx.ask is not None:
            value, source = ctx.ask(question)
            answers[key] = value
            sources[key] = source
        else:
            answers[key] = question["default"]
            sources[key] = "default"
            pending.append(key)
    modules = options.answers.get("modules")
    bundle = answers["bundle"]
    if modules:
        selected = list(modules)
        bundle_label = "custom"
    else:
        selected = list(ctx.manifest["bundles"][bundle]["modules"])
        bundle_label = bundle
    profile = {
        "schema": PROFILE_SCHEMA,
        "protocol_version": ctx.manifest["protocol_version"],
        "product_version": ctx.manifest.get("product_version", __version__),
        "host": answers["host"],
        "bundle": bundle_label,
        "modules": selected,
        "policy_mode": answers["policy_mode"],
    }
    ctx.answers = {**answers, "modules": selected, "bundle_label": bundle_label}
    ctx.pending = pending
    ctx.profile = profile
    path = options.target / PROFILE_RELPATH
    problems: list[dict[str, str]] = []
    status = "ok"
    existing = ctx.existing_profile
    if existing is None:
        action = "write" if options.apply else "would-write"
    elif existing == profile:
        action = "unchanged"
    else:
        action = "conflict"
        status = "warn"
        differing = sorted(key for key in set(existing) | set(profile) if existing.get(key) != profile.get(key))
        problems.append(_problem(
            "profile", f"existing .hpp/profile.json differs in: {', '.join(differing)}",
            "the same answers as the recorded profile",
            "re-run with the recorded answers, or remove .hpp/profile.json to initialise again (nothing was overwritten)",
        ))
    if action == "write":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(profile, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        action = "written"
    ctx.profile_action = action
    summary = f"{action} · host={profile['host']} · bundle={bundle_label} · policy={profile['policy_mode']}"
    if pending:
        summary += f" · {len(pending)} default(s)"
    return _stage("profile", status, summary,
                  {"path": str(PROFILE_RELPATH).replace("\\", "/"), "action": action, "answers": answers,
                   "sources": sources, "pending_defaults": pending, "profile": profile,
                   "writes": 1 if action == "written" else 0}, problems)


def stage_configure(ctx: _Context) -> dict[str, Any]:
    manifest = ctx.manifest
    host = ctx.answers["host"]
    bundle_label = ctx.answers["bundle_label"]
    plan_manifest = manifest
    bundle_name = ctx.answers["bundle"]
    if bundle_label == "custom":
        # Why: a synthetic bundle reuses installation_plan's host-coverage validation for an ad-hoc
        # module list instead of duplicating that rule here.
        plan_manifest = {**manifest, "bundles": {**manifest["bundles"], "custom": {"modules": ctx.answers["modules"],
                                                                                    "capabilities": ["custom"]}}}
        bundle_name = "custom"
    try:
        plan = installation_plan(plan_manifest, bundle_name, host, ctx.options.target)
    except InstallError as exc:
        other = [candidate for candidate in manifest["hosts"] if candidate != host]
        alternative = f"--host {other[0]}" if other else "another host"
        return _stage("configure", "fail", str(exc), {"host": host, "bundle": bundle_label},
                      [_problem("module coverage", str(exc), "every selected module native or explicit-command on the host",
                                f"pick {alternative}, or drop that module from --modules")], exit_hint=2)
    by_id = {module["id"]: module for module in manifest["modules"]}
    modules: list[dict[str, Any]] = []
    verified = mismatched = measurable = 0
    problems: list[dict[str, str]] = []
    for item in plan["modules"]:
        module = by_id[item["id"]]
        module_dir = ctx.root / module["path"]
        checksum: dict[str, Any] = {"status": "not-verified", "reason": "module directory not present in this tree"}
        if module_dir.is_dir():
            checksums_file = module_dir / "CHECKSUMS.txt"
            if checksums_file.is_file():
                measurable += 1
                ok, checked, failures = verify_checksums(module_dir, checksums_file)
                if ok:
                    verified += 1
                    checksum = {"status": "verified", "files": checked}
                else:
                    mismatched += 1
                    checksum = {"status": "mismatch", "failures": failures[:3]}
                    problems.append(_problem(f"checksum {module['id']}", "; ".join(failures[:3]),
                                             "every CHECKSUMS.txt line matches the bytes on disk",
                                             f"re-emit {module['path']} from source; do not install a module whose checksum diverges"))
            else:
                checksum = {"status": "not-verified", "reason": "no CHECKSUMS.txt in module directory"}
        modules.append({"id": module["id"], "version": module["version"], "integration": item["integration"],
                        "path": module["path"], "components": list(module.get("components", [])), "checksum": checksum})
    ctx.plan = {**plan, "bundle": bundle_label, "modules": modules}
    ctx.checksums = (verified, mismatched, len(modules))
    summary = f"{len(modules)} modules · {bundle_label} · {host}"
    if measurable:
        summary += f" · {verified}/{len(modules)} checksums verified"
    status = "fail" if mismatched else "ok"
    return _stage("configure", status, summary,
                  {"host": host, "bundle": bundle_label, "modules": modules,
                   "checksums": {"verified": verified, "mismatch": mismatched, "measurable": measurable, "total": len(modules)}},
                  problems, exit_hint=2 if mismatched else 0)


def stage_wire_suggest(ctx: _Context) -> dict[str, Any]:
    host = ctx.answers["host"]
    seam = HOSTS[host]
    manifest = ctx.manifest
    modules = ctx.plan["modules"]
    installer_rel = manifest["installer"]["path"]
    installer_present = (ctx.root / installer_rel).is_file()
    target = ctx.options.target_label
    lines: list[str] = []
    if host == "claude-code":
        native = [module for module in modules if module["integration"] == "native"]
        explicit = [module for module in modules if module["integration"] != "native"]
        lines.append("# Claude Code — native plugin channel")
        lines.append(f"/plugin marketplace add {ctx.options.marketplace}")
        lines.extend(f"/plugin install {module['id']}@{manifest['name']}" for module in native)
        if explicit:
            lines.append("")
            lines.append("# explicit-command modules on this host — run the module installer from the product checkout")
            lines.extend(f"python {installer_rel} install --kit {module['path']} --host claude-code --target {target} --apply"
                         for module in explicit)
        lines.append("")
        lines.append(f"# {seam['settings_path']}: {' and '.join(seam['manual_gates'])} stay a human gate — hpp wrote nothing there")
        hook_modules = [module["id"] for module in modules if "hooks" in module["components"]]
        if hook_modules:
            lines.append(f"# modules that declare hooks (review their hooks.json before enabling): {', '.join(hook_modules)}")
    else:
        lines.append("# Codex CLI — verified copy per module, run from the product checkout; hooks stay off")
        lines.extend(f"python {installer_rel} install --kit {module['path']} --host codex --target {target} --apply"
                     for module in modules)
        lines.append("")
        lines.append(f"# skills -> {seam['skills_path']} · runtime -> {seam['runtime_path']}/<module> · {seam['agents_file']} is read by Codex")
    if not installer_present:
        lines.append("")
        lines.append(f"# {installer_rel} is not in this source tree; it ships with the emitted distribution")
    lines.append("")
    lines.append(f"# command policy as configured: python -m hpp policy check --mode {ctx.answers['policy_mode']} --command \"<cmd>\"")
    # Why (A4, 2026-09-22): the block above says WHICH hooks to paste; the table below says what
    # each one is capable of. Consent to a list of filenames is consent to nothing.
    capabilities = [
        {"id": hook["id"], "module": hook["module"], "events": list(hook["events"]),
         "capabilities": list(hook["capabilities"]), "exit_policy": hook["exit_policy"]}
        for hook in hooks_for_modules(manifest, [module["id"] for module in modules])
    ]
    detail = {"host": host, "settings_path": seam.get("settings_path"), "manual_gates": list(seam["manual_gates"]),
              "installer": installer_rel, "installer_present": installer_present, "lines": lines, "writes": 0,
              "hook_capabilities": capabilities}
    summary = f"{len([line for line in lines if line and not line.startswith('#')])} commands to paste · 0 files written"
    if capabilities:
        summary += f" · {len(capabilities)} hooks declaring capabilities"
    return _stage("wire-suggest", "ok", summary, detail)


def stage_smoke(ctx: _Context) -> dict[str, Any]:
    controls: list[dict[str, Any]] = []
    safe = assess("python -m pytest -q")
    dangerous = assess("rm -rf src")
    policy_ok = safe["action"] == "ALLOW" and dangerous["action"] == "BLOCK" and policy_exit_for(dangerous, "enforce") == 2
    controls.append({"id": "policy", "ok": policy_ok, "measured": f"rm -rf -> {dangerous['action']} · pytest -> {safe['action']}",
                     "expected": "BLOCK · ALLOW", "command": 'python -m hpp policy check --mode enforce --command "rm -rf src"'})
    graph = build_graph(ctx.manifest, "capability")
    graph_ok = bool(graph["nodes"]) and bool(graph["edges"])
    controls.append({"id": "graph", "ok": graph_ok, "measured": f"{len(graph['nodes'])} nodes · {len(graph['edges'])} edges",
                     "expected": "non-empty capability graph", "command": "python -m hpp graph --view capability"})
    log = event_path(ctx.options.target)
    try:
        status = project(read_events(log), ctx.manifest)
        controls.append({"id": "events", "ok": True, "measured": f"state {status['state']} · {status['event_count']} events",
                         "expected": "event log projects onto the loop", "command": f"cd {ctx.options.target_label} && python -m hpp status"})
    except StateError as exc:
        controls.append({"id": "events", "ok": False, "measured": str(exc), "expected": "event log projects onto the loop",
                         "command": f"cd {ctx.options.target_label} && python -m hpp status"})
    suite = ctx.root / BENCHMARK_SUITE
    k = ctx.options.benchmark_k
    if k <= 0:
        controls.append({"id": "benchmark", "ok": None, "measured": "skipped (--no-benchmark)", "expected": "pass@k >= 0.90 and pass^k == 1.0",
                         "command": "python -m hpp benchmark -k 1"})
    elif not suite.is_file():
        controls.append({"id": "benchmark", "ok": None, "measured": "suite not shipped in this tree", "expected": "pass@k >= 0.90 and pass^k == 1.0",
                         "command": "python -m hpp benchmark -k 1"})
    else:
        try:
            report = run_suite(suite, k, "both")
            metrics = report["metrics"]
            controls.append({"id": "benchmark", "ok": bool(report["gate"]["passed"]),
                             "measured": f"pass@k={metrics['pass_at_k']:.2f} · pass^k={metrics['pass_caret_k']:.2f} · k={k}",
                             "expected": "pass@k >= 0.90 and pass^k == 1.0", "command": f"python -m hpp benchmark -k {k}"})
        except EvalError as exc:
            controls.append({"id": "benchmark", "ok": False, "measured": str(exc), "expected": "a valid benchmark suite",
                             "command": f"python -m hpp benchmark -k {k}"})
    failed = [control for control in controls if control["ok"] is False]
    problems = [_problem(control["id"], control["measured"], control["expected"], control["command"]) for control in failed]
    passed = [control["id"] for control in controls if control["ok"] is True]
    summary = " · ".join(passed) if not failed else f"{', '.join(control['id'] for control in failed)} FAILED"
    return _stage("smoke", "fail" if failed else "ok", summary, {"controls": controls}, problems, exit_hint=1 if failed else 0)


STAGE_FUNCTIONS: dict[str, Callable[[_Context], dict[str, Any]]] = {
    "detect": stage_detect,
    "prereqs": stage_prereqs,
    "profile": stage_profile,
    "configure": stage_configure,
    "wire-suggest": stage_wire_suggest,
    "smoke": stage_smoke,
}


# ---------------------------------------------------------------------------
# Readiness: every item is a check that ran, with the command that reproduces it
# ---------------------------------------------------------------------------


def build_readiness(stages: list[dict[str, Any]], ctx: _Context) -> dict[str, Any]:
    by_name = {stage["stage"]: stage for stage in stages}
    items: list[dict[str, str]] = []

    def add(item_id: str, label: str, status: str, evidence: str, command: str) -> None:
        items.append({"id": item_id, "label": label, "status": status, "evidence": evidence, "command": command})

    def ran(name: str) -> bool:
        return by_name.get(name, {}).get("status") not in {None, "skipped"}

    detect = by_name.get("detect", {})
    if ran("detect"):
        add("host", "host detected", "verified", f"{ctx.classification} · {ctx.answers.get('host', 'host not chosen yet')}",
            f"python -m hpp init --target {ctx.options.target_label}")
    else:
        add("host", "host detected", "not-verified", "stage not run", f"python -m hpp init --target {ctx.options.target_label}")
    checks = {check["id"]: check for check in by_name.get("prereqs", {}).get("detail", {}).get("checks", [])}
    for check_id, label in (("python", "python version"), ("manifest", "manifest contract"), ("distribution", "distribution integrity")):
        check = checks.get(check_id)
        if check is None:
            add(check_id, label, "not-verified", "stage not run", "python -m hpp doctor")
        elif check_id == "distribution" and not check.get("verified"):
            add(check_id, label, "not-verified", check["measured"], check["command"])
        else:
            add(check_id, label, "verified" if check["ok"] else "failed", check["measured"], check["command"])
    verified, mismatched, total = ctx.checksums
    if not ran("configure"):
        add("checksums", "module checksums", "not-verified", "stage not run", "python -m hpp doctor --json")
    elif mismatched:
        add("checksums", "module checksums", "failed", f"{mismatched}/{total} diverge", "python -m hpp doctor --json")
    elif total and verified == total:
        add("checksums", "module checksums", "verified", f"{verified}/{total} verified", "python -m hpp doctor --json")
    else:
        add("checksums", "module checksums", "not-verified", f"{verified}/{total} measurable here", "python -m hpp doctor --json")
    action = ctx.profile_action
    profile_command = f"python -m hpp init --target {ctx.options.target_label} --apply"
    if action in {"written", "unchanged"}:
        add("profile", "profile recorded", "verified", f".hpp/profile.json {action}", profile_command)
    elif action == "conflict":
        add("profile", "profile recorded", "failed", "existing .hpp/profile.json differs", profile_command)
    elif action == "would-write":
        add("profile", "profile recorded", "not-verified", "plan only — run with --apply", profile_command)
    else:
        add("profile", "profile recorded", "not-verified", "stage not run", profile_command)
    controls = {control["id"]: control for control in by_name.get("smoke", {}).get("detail", {}).get("controls", [])}
    for control_id, label in (("policy", "policy classifier"), ("graph", "capability graph"), ("events", "event log"), ("benchmark", "benchmark gate")):
        control = controls.get(control_id)
        if control is None:
            add(control_id, label, "not-verified", "stage not run", "python -m hpp benchmark -k 1")
        elif control["ok"] is None:
            add(control_id, label, "not-verified", control["measured"], control["command"])
        else:
            add(control_id, label, "verified" if control["ok"] else "failed", control["measured"], control["command"])
    add("wiring", "host wiring", "not-verified", "manual gate — paste the block, then run doctor", "python -m hpp doctor")
    counts = {"verified": 0, "failed": 0, "not-verified": 0}
    for item in items:
        counts[item["status"]] += 1
    total_items = len(items)
    cells = {"verified": 0, "failed": 0, "not-verified": 0}
    if total_items:
        cells["verified"] = round(counts["verified"] / total_items * READINESS_CELLS)
        cells["failed"] = round(counts["failed"] / total_items * READINESS_CELLS)
        cells["not-verified"] = READINESS_CELLS - cells["verified"] - cells["failed"]
    return {"items": items, "verified": counts["verified"], "failed": counts["failed"],
            "not_verified": counts["not-verified"], "total": total_items, "cells": cells}


# ---------------------------------------------------------------------------
# Running the wizard
# ---------------------------------------------------------------------------


def run_init(options: InitOptions, manifest: dict[str, Any], manifest_path: Path,
             ask: Optional[Callable[[dict[str, Any]], tuple[str, str]]] = None,
             on_begin: Optional[Callable[[str], None]] = None,
             on_end: Optional[Callable[[dict[str, Any]], None]] = None) -> dict[str, Any]:
    """Run the six stages in order; stop at the first blocking failure; return the full report."""
    ctx = _Context(options=options, manifest=manifest, manifest_path=manifest_path, ask=ask)
    stages: list[dict[str, Any]] = []
    halted: Optional[str] = None
    for name in STAGES:
        if halted is not None:
            stages.append(_stage(name, "skipped", f"not run — {halted} failed"))
            continue
        if on_begin is not None:
            on_begin(name)
        result = STAGE_FUNCTIONS[name](ctx)
        if on_end is not None:
            on_end(result)
        stages.append(result)
        if result["status"] == "fail" and result["exit_hint"] >= 2:
            halted = name
    exit_code = max((stage["exit_hint"] for stage in stages), default=0)
    if exit_code == 0 and any(stage["status"] in {"warn", "fail"} for stage in stages):
        exit_code = 1
    if halted is not None:
        status = "halted"
    elif any(stage["status"] == "fail" for stage in stages):
        status = "fail"
    elif any(stage["status"] == "warn" for stage in stages):
        status = "warn"
    elif ctx.profile_action == "unchanged":
        status = "no-op"
    else:
        status = "ok"
    mode = "apply" if options.apply else "plan"
    if status == "no-op":
        mode = "no-op"
    next_steps = _next_steps(status, options, ctx, stages)
    return {
        "schema": REPORT_SCHEMA,
        "version": __version__,
        "mode": mode,
        "status": status,
        "exit_code": exit_code,
        "target": str(options.target),
        "manifest": str(manifest_path),
        "interactive": options.interactive,
        "stages": stages,
        "readiness": build_readiness(stages, ctx),
        "writes": sum(stage["detail"].get("writes", 0) for stage in stages),
        "next": next_steps,
    }


def _next_steps(status: str, options: InitOptions, ctx: _Context, stages: list[dict[str, Any]]) -> list[str]:
    if status == "halted":
        blocked = next(stage for stage in stages if stage["status"] == "fail")
        return [problem["next_step"] for problem in blocked["problems"]] or ["fix the failing stage, then re-run the plan"]
    steps: list[str] = []
    flags = ""
    for key in ("host", "bundle", "policy_mode"):
        if key in ctx.answers and ctx.answers.get(key) is not None:
            flags += f" --{key.replace('_', '-')} {ctx.answers[key]}"
    if ctx.answers.get("bundle_label") == "custom":
        flags += " --modules " + ",".join(ctx.answers["modules"])
    if status == "no-op":
        steps.append("already initialised with these answers — nothing to do")
    elif not options.apply:
        steps.append(f"python -m hpp init --target {options.target_label}{flags} --apply")
    else:
        steps.append("paste the wire block above into your host (hpp never edits settings)")
        steps.append("python -m hpp doctor")
    for stage in stages:
        for problem in stage["problems"]:
            steps.append(problem["next_step"])
    return steps


# ---------------------------------------------------------------------------
# Interactive prompts (only ever called when the session is a TTY and no flag opted out)
# ---------------------------------------------------------------------------


def make_asker(console: Console, input_fn: Callable[[str], str] = input) -> Callable[[dict[str, Any]], tuple[str, str]]:
    def ask(question: dict[str, Any]) -> tuple[str, str]:
        options = question["options"]
        default = question["default"]
        console.write()
        console.write("  " + console.paint(question["prompt"], PALETTE["warm_white"], bold=True))
        for index, option in enumerate(options, 1):
            marker = console.glyph("bullet") if option == default else " "
            suffix = console.paint("  (default)", dim=True) if option == default else ""
            console.write(f"    {console.paint(marker, PALETTE['signal_orange'])} {index}) {option}{suffix}")
        for _ in range(3):
            try:
                raw = input_fn(f"  choice [1-{len(options)}] (Enter = {default}): ").strip()
            except EOFError:
                return default, "default"
            if raw == "":
                return default, "default-accepted"
            if raw.isdigit() and 1 <= int(raw) <= len(options):
                return options[int(raw) - 1], "human"
            if raw in options:
                return raw, "human"
            console.write(console.paint("    not a valid choice — pick a number from the list", red=True))
        return default, "default"

    return ask


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


class Boot:
    """Prints one boot line per stage, completed only when that stage has really finished."""

    def __init__(self, console: Console) -> None:
        self.console = console
        self._label = ""

    def begin(self, stage: str) -> None:
        self._label = f"> {BOOT_LINES[stage]}..."
        self.console.transient(self.console.paint(self._label, PALETTE["warm_white"]))

    def end(self, result: dict[str, Any]) -> None:
        console = self.console
        status = result["status"]
        label = self._label.ljust(30)
        if status == "ok":
            line = console.paint(label, PALETTE["warm_white"]) + console.paint(console.glyph("ok"), PALETTE["signal_orange"], bold=True) + " " + console.paint(result["summary"], PALETTE["warm_white"])
        elif status == "warn":
            line = console.paint(label, PALETTE["warm_white"]) + console.paint(console.glyph("warn"), PALETTE["signal_orange"], bold=True) + " " + console.paint(result["summary"], PALETTE["signal_orange"])
        else:
            line = console.paint(label + console.glyph("fail") + " " + result["summary"], red=True, bold=True)
        console.rewrite(line)
        console.pause(0.06)


def _section(console: Console, title: str, note: str = "") -> None:
    console.write()
    head = console.paint(title, PALETTE["signal_orange"], bold=True)
    if note:
        head += "  " + console.paint(note, dim=True)
    console.write("  " + head)


def render_report(report: dict[str, Any], console: Console) -> None:
    """Everything after the boot lines: readiness, plan, modules, wire block, problems, next, logo."""
    orange, white = PALETTE["signal_orange"], PALETTE["warm_white"]
    by_name = {stage["stage"]: stage for stage in report["stages"]}
    if report["status"] == "halted":
        console.write(console.paint("> protocol halted.", red=True, bold=True))
    else:
        tail = console.paint("  (with warnings)", dim=True) if report["status"] in {"warn", "fail"} else ""
        console.write(console.paint("> protocol online.", orange, bold=True) + tail)

    readiness = report["readiness"]
    bar = (console.paint(console.glyph("full") * readiness["cells"]["verified"], orange)
           + console.paint(console.glyph("half") * readiness["cells"]["failed"], red=True)
           + console.paint(console.glyph("light") * readiness["cells"]["not-verified"], dim=True))
    counts = f"{readiness['verified']}/{readiness['total']} verified · {readiness['not_verified']} not verified · {readiness['failed']} failed"
    _section(console, "READINESS", "every line is a check that ran; the command below it reproduces it")
    console.write(f"  {bar}  {console.paint(counts, white)}")
    for item in readiness["items"]:
        if item["status"] == "verified":
            glyph = console.paint(console.glyph("ok"), orange, bold=True)
        elif item["status"] == "failed":
            glyph = console.paint(console.glyph("fail"), red=True, bold=True)
        else:
            glyph = console.paint(console.glyph("skip"), dim=True)
        label = item["label"].ljust(24)
        evidence = item["evidence"] if item["status"] != "not-verified" else f"not verified — {item['evidence']}"
        console.write(f"    {glyph} {console.paint(label, white)}{evidence}")
        console.write(console.paint(f"        {console.glyph('corner')} {item['command']}", dim=True))

    profile = by_name.get("profile", {})
    detail = profile.get("detail", {})
    if report["mode"] == "no-op":
        _section(console, "NO-OP", "already initialised with these answers — nothing written")
    elif report["mode"] == "plan":
        _section(console, "PLAN", "nothing was written — re-run with --apply to record the profile")
    else:
        _section(console, "APPLIED", f"{report['writes']} file(s) written inside the target")
    if detail:
        answers = detail["profile"]
        console.write(f"    {detail['path'].ljust(20)} {detail['action'].ljust(12)} host={answers['host']} · bundle={answers['bundle']} · policy={answers['policy_mode']}")
        if detail.get("pending_defaults"):
            console.write(console.paint(f"    defaults taken for: {', '.join(detail['pending_defaults'])}  (pass --host/--bundle/--policy-mode to decide them)", dim=True))
    elif profile.get("status") == "skipped":
        console.write(console.paint(f"    {profile['summary']}", dim=True))

    configure = by_name.get("configure", {})
    modules = configure.get("detail", {}).get("modules", [])
    if modules:
        _section(console, "MODULES", configure["summary"])
        for index, module in enumerate(modules):
            branch = console.glyph("corner") if index == len(modules) - 1 else console.glyph("tee")
            checksum = module["checksum"]
            if checksum["status"] == "verified":
                mark = console.paint(f"checksum verified ({checksum['files']} files)", orange)
            elif checksum["status"] == "mismatch":
                mark = console.paint("checksum MISMATCH", red=True, bold=True)
            else:
                mark = console.paint(f"checksum not verified — {checksum['reason']}", dim=True)
            console.write(f"    {branch} {module['id'].ljust(24)}{module['version'].ljust(8)}{module['integration'].ljust(18)}{mark}")
    elif configure.get("status") in {"fail", "skipped"}:
        _section(console, "MODULES", configure["summary"])

    wire = by_name.get("wire-suggest", {})
    capabilities = wire.get("detail", {}).get("hook_capabilities") or []
    if capabilities:
        _section(console, "HOOK CAPABILITIES",
                 "what each hook you are about to paste is able to do — read it before the block below")
        for index, hook in enumerate(capabilities):
            branch = console.glyph("corner") if index == len(capabilities) - 1 else console.glyph("tee")
            events = ",".join(hook["events"])
            console.write(f"    {branch} {hook['id'].ljust(40)} {events.ljust(25)} "
                          f"{console.paint(hook['exit_policy'], orange)}")
            console.write(console.paint(f"        {', '.join(hook['capabilities'])}", dim=True))
    if wire.get("detail", {}).get("lines"):
        _section(console, "WIRE", "paste it yourself — hpp never edits settings or hooks")
        for line in wire["detail"]["lines"]:
            painted = console.paint(line, dim=True) if line.startswith("#") else console.paint(line, white)
            console.write(f"    {console.paint(console.glyph('bar'), orange)} {painted}")

    problems = [(stage["stage"], problem) for stage in report["stages"] for problem in stage["problems"]]
    if problems:
        _section(console, "PROBLEMS", "what was measured, what was expected, what to do")
        for stage_name, problem in problems:
            console.write(f"    {console.paint(console.glyph('fail'), red=True, bold=True)} {console.paint(problem['label'], white, bold=True)}  {console.paint('[' + stage_name + ']', dim=True)}")
            console.write(f"        measured: {problem['measured']}")
            console.write(f"        expected: {problem['expected']}")
            console.write(f"        {console.glyph('corner')} {console.paint(problem['next_step'], orange)}")

    _section(console, "NEXT")
    for step in report["next"]:
        console.write(f"    {console.paint(console.glyph('bullet'), orange)} {step}")

    if report["status"] != "halted":
        console.write()
        for line in logo_lines(console):
            console.write(line)
        console.write()
        console.blink_cursor(closing_line(console, pick_closing(report["status"])))
    else:
        console.write()
        console.write(console.paint(f"> exit {report['exit_code']} — fix the block above, then re-run the plan.", red=True))


def run_init_command(options: InitOptions, manifest: dict[str, Any], manifest_path: Path, *,
                     json_output: bool = False, no_animation: bool = False,
                     console: Optional[Console] = None, input_fn: Callable[[str], str] = input) -> int:
    """CLI entry: run the wizard and render it as JSON or as the animated human report."""
    if json_output:
        report = run_init(options, manifest, manifest_path)
        # Why: the machine report must survive an ASCII-only pipe, so non-ASCII is escaped in JSON.
        print(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True))
        return report["exit_code"]
    if console is None:
        console = Console(animate=not no_animation)
    elif no_animation:
        console.animate = False
    header = f"house-party init · v{__version__} · {'apply' if options.apply else 'plan'} · target {options.target_label}"
    console.write(console.paint(header, dim=True))
    console.write()
    boot = Boot(console)
    ask = make_asker(console, input_fn) if options.interactive else None
    report = run_init(options, manifest, manifest_path, ask=ask, on_begin=boot.begin, on_end=boot.end)
    render_report(report, console)
    return report["exit_code"]

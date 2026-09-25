"""Command-line surface for the House Party Protocol harness."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Optional

from hpp import __version__
from hpp.attest import AttestationError, create_attestation, verify_attestation
from hpp.citations import check_files as check_citations, context_ids, exit_for as citations_exit_for
from hpp.context import compile_context
from hpp.decision import effective as decision_effective, exit_for as decision_exit_for, run_decision_suite, validate as validate_decision
from hpp.deliberation import (
    PANEL_SCHEMA, SCHEMA as DELIBERATION_SCHEMA, SCHEMAS as DELIBERATION_SCHEMAS, TALLY_SCHEMA, TURN_SCHEMA,
    as_decision, build_record, decide_stop, exit_for_record, normalise_panel, normalise_turn, panel_verdict,
    tally as deliberation_tally, verify_record,
)
from hpp.evals import EvalError, exit_for as eval_exit_for, packaged_suite, run_suite
from hpp.evidence import (
    MUTANTS_SCHEMA, exit_for_mutation, exit_for_run as evidence_run_exit, exit_for_verify as evidence_verify_exit,
    generate_mutants, run_evidence, run_mutation, verify_evidence,
)
from hpp.findings import check as check_findings, exit_for as findings_exit_for
from hpp.graph import build_graph, to_mermaid
from hpp.install import InstallError, installation_plan
from hpp.manifest import ManifestError, hook_capability_census, load_manifest, validate_distribution
from hpp.maps import build_agent_map, build_context_map, build_lane_map, build_monitor_map
from hpp.policy import assess, exit_for as policy_exit_for
from hpp.retrieval import exit_for as retrieval_exit_for, run_retrieval_suite
from hpp.routing import route
from hpp.state import StateError, append_event, event_path, project, read_events
from hpp.term import Console
from hpp.wizard import DECISION_ADVISORS, InitUsageError, prepare_options, run_init_command
from hpp.workgraph import cited_tests, citation_coverage, compile_workgraph, read_junit, spec_execution


def _json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def _line(text: str) -> None:
    """Print a one-line human report through the same console the wizard uses."""
    # Why (cp1252 console, 2026-09-21): the one-liners carry `·`; written with print() to a
    # cp1252 stream (hpp.exe without -X utf8, output piped) the byte was not UTF-8 and read as
    # `�` downstream. Console picks ASCII glyphs from the stream's encoding and rewrites `·` and
    # `—` to `-`, exactly as `hpp init` already degrades.
    Console(animate=False).write(text)


def _manifest(args: argparse.Namespace) -> tuple[dict[str, Any], Path]:
    return load_manifest(getattr(args, "manifest", None))


def _read_json(path: str, expected: type) -> Any:
    source = Path(path)
    if not source.is_file():
        raise ValueError(f"JSON file not found: {source}")
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {source}: {exc.msg}") from exc
    if not isinstance(value, expected):
        label = "object" if expected is dict else "array"
        raise ValueError(f"JSON root in {source} must be an {label}")
    return value


def command_doctor(args: argparse.Namespace) -> int:
    manifest, path = _manifest(args)
    distribution = validate_distribution(manifest, path.parent)
    # Why (hook capability census, 2026-09-22): load_manifest already refuses a hook without a declaration, so
    # reaching this line IS the pass. The census is printed so the answer to "what can the
    # hooks I am about to paste do?" is a number, not a reading of nine Python files.
    hooks = hook_capability_census(manifest)
    result = {"status": "ok", "version": __version__, "manifest": str(path),
              "modules": len(manifest["modules"]), "bundles": sorted(manifest["bundles"]),
              "hosts": manifest["hosts"], "distribution": distribution, "hooks": hooks}
    if args.json:
        _json(result)
    else:
        gates = hooks["by_capability"].get("automatic-permission-gates", 0)
        egress = hooks["by_capability"].get("transcript-derived-llm-egress", 0)
        _line(f"HPP doctor: ok · modules={result['modules']} · hosts={', '.join(result['hosts'])} "
              f"· hooks={hooks['declared']} (permission gates={gates} · llm egress={egress})")
    return 0


def command_graph(args: argparse.Namespace) -> int:
    manifest, _ = _manifest(args)
    graph = build_graph(manifest, args.view)
    if args.format == "mermaid":
        print(to_mermaid(graph), end="")
    else:
        _json(graph)
    return 0


def command_install(args: argparse.Namespace) -> int:
    manifest, _ = _manifest(args)
    target = Path(args.target)
    plan = installation_plan(manifest, args.bundle, args.host, target)
    _json(plan)
    return 0


def command_init(args: argparse.Namespace) -> int:
    manifest, path = _manifest(args)
    try:
        options = prepare_options(args, manifest)
    except InitUsageError as exc:
        print(f"hpp init: {exc}", file=sys.stderr)
        return 3
    return run_init_command(options, manifest, path, json_output=args.json, no_animation=args.no_animation)


def command_policy(args: argparse.Namespace) -> int:
    verdict = assess(args.command)
    _json({"mode": args.mode, **verdict})
    return policy_exit_for(verdict, args.mode)


def command_event(args: argparse.Namespace) -> int:
    manifest, _ = _manifest(args)
    data: dict[str, Any] = {}
    if args.data:
        parsed = json.loads(args.data)
        if not isinstance(parsed, dict):
            raise ValueError("event data must be a JSON object")
        data = parsed
    status = append_event(event_path(), args.type, manifest, data)
    _json(status)
    return 0


def _status(manifest: dict[str, Any]) -> dict[str, Any]:
    path = event_path()
    events = read_events(path)
    return {"event_log": str(path), **project(events, manifest)}


def command_status(args: argparse.Namespace) -> int:
    manifest, _ = _manifest(args)
    status = _status(manifest)
    if args.json:
        _json(status)
    else:
        _line(f"HPP status: {status['state']} · events={status['event_count']} · next={status['next_step']}")
    return 0


def command_resume(args: argparse.Namespace) -> int:
    manifest, _ = _manifest(args)
    status = _status(manifest)
    _json({"state": status["state"], "next_step": status["next_step"], "event_count": status["event_count"]})
    return 0


def command_eval(args: argparse.Namespace) -> int:
    report = run_suite(Path(args.suite), args.k, args.gate)
    _json(report)
    return eval_exit_for(report)


def command_benchmark(args: argparse.Namespace) -> int:
    report = run_suite(packaged_suite(), args.k, "both")
    if args.json:
        _json(report)
    else:
        metrics = report["metrics"]
        _line(f"HPP benchmark: pass@k={metrics['pass_at_k']:.2f} · pass^k={metrics['pass_caret_k']:.2f} · gate={'PASS' if report['gate']['passed'] else 'FAIL'}")
    return eval_exit_for(report)


def command_attest(args: argparse.Namespace) -> int:
    if args.attest_command == "create":
        panel = None
        if args.deliberation:
            if not args.maker_family:
                raise ValueError("--deliberation needs --maker-family: a judge of the maker's family is refused")
            panel = panel_verdict(_read_json(args.deliberation, dict), session_type="release-gate",
                                  options={"approved", "revise", "blocked"}, forbid_family=args.maker_family,
                                  evidence_records_only=True)
        record = create_attestation(
            repo=Path(args.repo),
            spec=Path(args.spec),
            output=Path(args.output),
            maker=args.maker,
            checker=args.checker,
            session=args.session,
            verdict=args.verdict,
            panel=panel,
        )
        _json({"status": "recorded", **record})
        return 0 if record["verdict"] == "approved" else 2
    report = verify_attestation(Path(args.attestation), Path(args.repo))
    _json(report)
    return 0 if report["status"] == "valid" else 2


def _python_sources(paths: list[str]) -> dict[str, str]:
    """Every Python file named, or under a directory named; the universe of the coverage answer."""
    sources: dict[str, str] = {}
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            files = sorted(item for item in path.rglob("*.py") if "__pycache__" not in item.parts)
        elif path.is_file():
            if path.suffix != ".py":
                raise ValueError(f"only Python test sources are read: {path}")
            files = [path]
        else:
            raise ValueError(f"test source not found: {path}")
        for item in files:
            sources[item.as_posix()] = item.read_text(encoding="utf-8")
    if not sources:
        raise ValueError("no Python test source found: an empty universe covers nothing")
    return sources


def _work_coverage(args: argparse.Namespace, compiled: dict[str, Any]) -> int:
    sources = _python_sources(args.tests)
    citations = [entry for path, text in sources.items() for entry in cited_tests(text, path)]
    if not args.junit:
        report = citation_coverage(compiled, citations)
    else:
        cases, reports = [], []
        for name in args.junit:
            junit = Path(name)
            if not junit.is_file():
                raise ValueError(f"JUnit report not found: {junit}")
            data = junit.read_bytes()
            cases.extend(read_junit(data))
            reports.append({"file": name, "sha256": hashlib.sha256(data).hexdigest(), "mtime": junit.stat().st_mtime})
        # Why (review 2026-09-25): nothing tied a report to the tests it measured, so a report
        # older than an edit (a test later marked skip, or rewritten) kept its criterion
        # `executed`. A citing source modified after the oldest report makes the answer stale.
        oldest = min(item["mtime"] for item in reports)
        citing = sorted({entry["test"].split("::", 1)[0] for entry in citations})
        stale = [path for path in citing if Path(path).stat().st_mtime > oldest]
        report = spec_execution(compiled, citations, cases)
        report = {**report, "junit": list(args.junit), "reports": reports, "stale_sources": stale,
                  "complete": report["complete"] and not stale}
    _json({**report, "sources": len(sources)})
    return 0 if report["complete"] else 1


def command_work(args: argparse.Namespace) -> int:
    compiled = compile_workgraph(_read_json(args.spec, dict))
    if args.work_command == "coverage":
        return _work_coverage(args, compiled)
    if args.work_command == "waves":
        _json({
            "schema": "hpp.workgraph-waves/v1",
            "waves": compiled["waves"],
            "tier_counts": compiled["tier_counts"],
        })
    else:
        _json(compiled)
    return 0


def command_route(args: argparse.Namespace) -> int:
    request = _read_json(args.request, dict)
    providers = _read_json(args.providers, list)
    applied = None
    if args.deliberation:
        if not args.maker_family:
            raise ValueError("--deliberation needs --maker-family: a judge of the maker's family is refused")
        levels = ("low", "medium", "high")
        verdict = panel_verdict(_read_json(args.deliberation, dict), session_type="plan", options=set(levels),
                                forbid_family=args.maker_family)
        declared = request.get("risk")
        # A plan panel can only RAISE the risk: a gate that lowers it would let a panel talk a risky
        # change into a cheaper tier.
        raise_to = verdict["value"] if verdict["status"] == "recommendation" else None
        higher = raise_to in levels and declared in levels and levels.index(raise_to) > levels.index(declared)
        if higher:
            request = {**request, "risk": raise_to}
        applied = {"record_sha256": verdict["record_sha256"], "verdict": verdict["value"],
                   "status": verdict["status"], "applied": higher, "raised_from": declared if higher else None}
    result = route(request, args.policy, providers)
    if applied is not None:
        result["deliberation"] = applied
    _json(result)
    return 0


def command_decide(args: argparse.Namespace) -> int:
    if args.decide_command == "validate":
        record = validate_decision(_read_json(args.record, dict))
        _json({"status": "valid", "effective": decision_effective(record), "record": record})
        return 0
    command = None
    if args.decider_command:
        command = json.loads(args.decider_command)
        if not isinstance(command, list) or not command or not all(isinstance(item, str) and item for item in command):
            raise ValueError("--decider-command must be a JSON array of strings (argv, no shell)")
    report = run_decision_suite(Path(args.suite), decider_command=command, timeout=args.timeout,
                                min_selective_accuracy=args.min_selective_accuracy,
                                max_confident_errors=args.max_confident_errors, max_failures=args.max_failures)
    _json(report)
    return decision_exit_for(report)


def _verified(record: dict[str, Any]) -> int:
    report = verify_record(record)
    _json(report)
    return 0 if report["status"] == "intact" else 2


def _with_evidence(panel: dict[str, Any], context_path: Optional[str], records: list[str]) -> dict[str, Any]:
    """The panel with the ids its seats can cite: the context they were given, and every evidence
    record that verifies now. A record that does not verify resolves nothing and is refused."""
    # Why (review 2026-09-25): the panel is validated BEFORE evidence is added — its own hash
    # and any evidence it already declares — so an edited or malformed panel is refused, not repaired.
    declared = normalise_panel(panel).get("evidence") or {}
    ids = list(declared.get("ids", []))
    sources = list(declared.get("sources", []))
    if context_path:
        context = _read_json(context_path, list)
        ids += context_ids(context)
        canonical = json.dumps(context, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        sources.append({"kind": "context", "sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest()})
    for name in records:
        report = verify_evidence(Path(name), root=Path.cwd())
        if report["status"] != "valid":
            raise ValueError(f"evidence record {name} does not verify ({report['status']}): it resolves nothing")
        record = json.loads(Path(name).read_text(encoding="utf-8"))
        ids.append(record["id"])
        sources.append({"kind": "evidence-record", "id": record["id"], "sha256": record["record_sha256"]})
    updated = {key: value for key, value in panel.items() if key != "sha256"}
    updated["evidence"] = {"ids": sorted(set(ids)), "sources": sources}
    return updated


def command_deliberate(args: argparse.Namespace) -> int:
    action = args.deliberate_command
    if action == "verify":
        return _verified(_read_json(args.record, dict))
    if action in ("plan", "validate"):
        document = _read_json(args.file, dict)
        schema = document.get("schema")
        if action == "validate" and schema in DELIBERATION_SCHEMAS:
            return _verified(document)
        if action == "validate" and schema == TURN_SCHEMA:
            if not args.panel:
                raise ValueError("validating a turn needs --panel, the panel it belongs to")
            turn = normalise_turn(document, normalise_panel(_read_json(args.panel, dict)))
            _json({"status": "valid", "turn": turn})
            return 0
        if schema != PANEL_SCHEMA:
            raise ValueError(f"expected a {PANEL_SCHEMA}, {TURN_SCHEMA} or {DELIBERATION_SCHEMA} document, got {schema!r}")
        if action == "plan" and (args.context or args.evidence):
            document = _with_evidence(document, args.context, args.evidence)
        panel = normalise_panel(document)
        if action == "plan" and args.out:
            output = Path(args.out)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(panel, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        _json({"status": "valid", "panel": panel})
        return 0
    panel = _read_json(args.panel, dict)
    turns = _read_json(args.turns, list)
    if action == "tally":
        _json({"schema": TALLY_SCHEMA, "rounds": deliberation_tally(panel, turns)})
        return 0
    if action == "stop":
        _json(decide_stop(panel, turns))
        return 0
    judge = _read_json(args.judge, dict) if args.judge else None
    rationale = _read_json(args.rationale, dict) if args.rationale else None
    record = build_record(panel, turns, judge, rationale)
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _json({"status": "recorded", "record": str(output), "record_sha256": record["record_sha256"],
           "stop": record["stop"], "verdict": record["verdict"], "dissent": record["dissent"],
           "decision": as_decision(record)})
    return exit_for_record(record)


def command_findings(args: argparse.Namespace) -> int:
    subject = None
    if args.subject:
        source = Path(args.subject)
        if not source.is_file():
            raise ValueError(f"subject not found: {source}")
        subject = source.read_bytes()
    reports = [{"file": name, **check_findings(_read_json(name, dict), subject)} for name in args.files]
    _json({"reports": reports})
    return findings_exit_for(reports)


def command_retrieval(args: argparse.Namespace) -> int:
    command = None
    if args.retriever_command is not None:
        command = json.loads(args.retriever_command)
        if not isinstance(command, list) or not command or not all(isinstance(item, str) and item for item in command):
            raise ValueError("--retriever-command must be a JSON array of strings (argv, no shell)")
    report = run_retrieval_suite(Path(args.suite), retriever_command=command, k=args.k, timeout=args.timeout,
                                 min_recall=args.min_recall, max_failures=args.max_failures)
    _json(report)
    return retrieval_exit_for(report)


def command_cite(args: argparse.Namespace) -> int:
    options = {"max_per_sentence": args.max_per_sentence}
    if args.marker is not None:
        options["marker"] = args.marker
    report = check_citations(args.text, args.context, **options)
    _json(report)
    return citations_exit_for(report)


def command_evidence(args: argparse.Namespace) -> int:
    root = Path.cwd()
    if args.evidence_command == "verify":
        report = verify_evidence(Path(args.record), root=root)
        _json(report)
        return evidence_verify_exit(report)
    command = list(args.criterion)
    if command and command[0] == "--":
        command = command[1:]
    if args.evidence_command == "mutate":
        mutants: list[Any] = []
        if args.mutants:
            declared = _read_json(args.mutants, dict)
            if declared.get("schema") != MUTANTS_SCHEMA or not isinstance(declared.get("mutants"), list):
                raise ValueError(f"{args.mutants} must be an {MUTANTS_SCHEMA} object with a mutants list")
            mutants.extend(declared["mutants"])
        if args.generate:
            mutants.extend(generate_mutants(root, args.generate))
        if not args.mutants and not args.generate:
            raise ValueError("evidence mutate needs --mutants FILE or --generate FILE (or both)")
        record = run_mutation(args.id, command, mutants, root=root, timeout=args.timeout,
                              out_dir=Path(args.out) if args.out else None)
        _json(record)
        return exit_for_mutation(record)
    manifest = _manifest(args)[0] if args.record_event else None
    record = run_evidence(args.id, command, args.artifact or [], root=root, timeout=args.timeout,
                          out_dir=Path(args.out) if args.out else None, manifest=manifest)
    _json(record)
    return evidence_run_exit(record)


def command_context(args: argparse.Namespace) -> int:
    _json(compile_context(_read_json(args.inputs, list), args.budget))
    return 0


def command_map(args: argparse.Namespace) -> int:
    if args.map_view == "lane":
        projection = build_lane_map(
            _read_json(args.source, list),
            now=args.now,
            suspect_after=args.suspect_after,
            dead_after=args.dead_after,
        )
    elif args.map_view == "monitor":
        projection = build_monitor_map(_read_json(args.source, list), args.now, skew_tolerance=args.skew_tolerance)
    elif args.map_view == "context":
        projection = build_context_map(_read_json(args.source, list), args.budget)
    else:
        manifest, _ = _manifest(args)
        events = _read_json(args.events, list) if args.events else None
        projection = build_agent_map(manifest, events)
    _json(projection)
    return 0


def self_test() -> int:
    """Exercise deterministic local controls without changing a workspace."""
    manifest, _ = load_manifest()
    graph = build_graph(manifest, "capability")
    if not graph["nodes"] or not graph["edges"]:
        raise ValueError("self-test capability graph is empty")
    report = run_suite(packaged_suite(), 3, "both")
    if not report["gate"]["passed"]:
        raise ValueError("self-test benchmark gate failed")
    print("hpp self-test OK")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hpp", description="House Party Protocol local-first harness")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor")
    doctor.add_argument("--manifest")
    doctor.add_argument("--json", action="store_true")
    doctor.set_defaults(func=command_doctor)

    graph = sub.add_parser("graph")
    graph.add_argument("--manifest")
    graph.add_argument("--view", required=True, choices=["capability", "operational", "agent", "evidence", "code"])
    graph.add_argument("--format", default="json", choices=["json", "mermaid"])
    graph.set_defaults(func=command_graph)

    install = sub.add_parser("install")
    install.add_argument("--manifest")
    install.add_argument("--bundle", required=True)
    install.add_argument("--host", required=True)
    install.add_argument("--target", required=True)
    install.set_defaults(func=command_install)

    init = sub.add_parser(
        "init",
        description="Six fixed stages (detect, prereqs, profile, configure, wire-suggest, smoke). "
                    "Without --apply it only prints what it would do; wire-suggest never writes settings.",
    )
    init.add_argument("--manifest")
    init.add_argument("--target", default=".", help="project to initialise (default: current directory)")
    init.add_argument("--apply", action="store_true", help="write .hpp/profile.json inside the target (default: plan only)")
    init.add_argument("--host", help="host to plan for; defaults to the manifest's first supported host")
    init.add_argument("--bundle", help="bundle to plan; ignored when --modules is given")
    init.add_argument("--modules", help="comma-separated module ids instead of a bundle")
    init.add_argument("--policy-mode", dest="policy_mode", choices=["audit", "enforce"],
                      help="how the command policy should run in the suggested wiring")
    init.add_argument("--decision-advisor", dest="decision_advisor",
                      choices=list(DECISION_ADVISORS),
                      help="optional typed-decision advisor you will integrate yourself; hpp never calls it (default: off)")
    init.add_argument("--profile", help="JSON file with answers: host, bundle, policy_mode, modules, decision_advisor")
    init.add_argument("--yes", action="store_true", help="accept every default without prompting")
    init.add_argument("--non-interactive", dest="non_interactive", action="store_true",
                      help="never prompt; unanswered questions take their defaults")
    init.add_argument("--no-animation", dest="no_animation", action="store_true", help="plain output, no cursor tricks")
    init.add_argument("--no-benchmark", dest="no_benchmark", action="store_true",
                      help="skip the benchmark control in smoke (reported as not verified)")
    init.add_argument("--marketplace", help="marketplace slug used in the Claude Code wire block")
    init.add_argument("--json", action="store_true", help="machine-readable report, no animation, no colour")
    init.set_defaults(func=command_init)

    policy = sub.add_parser("policy")
    policy_sub = policy.add_subparsers(dest="policy_command", required=True)
    check = policy_sub.add_parser("check")
    check.add_argument("--mode", choices=["audit", "enforce"], required=True)
    check.add_argument("--command", required=True)
    check.set_defaults(func=command_policy)

    event = sub.add_parser("event")
    event_sub = event.add_subparsers(dest="event_command", required=True)
    append = event_sub.add_parser("append")
    append.add_argument("--manifest")
    append.add_argument("--type", required=True)
    append.add_argument("--data")
    append.set_defaults(func=command_event)

    status = sub.add_parser("status")
    status.add_argument("--manifest")
    status.add_argument("--json", action="store_true")
    status.set_defaults(func=command_status)

    resume = sub.add_parser("resume")
    resume.add_argument("--manifest")
    resume.set_defaults(func=command_resume)

    evaluate = sub.add_parser("eval")
    eval_sub = evaluate.add_subparsers(dest="eval_command", required=True)
    run = eval_sub.add_parser("run")
    run.add_argument("suite")
    run.add_argument("-k", type=int, default=3)
    run.add_argument("--gate", choices=["capability", "regression", "both"], default="capability")
    run.set_defaults(func=command_eval)

    benchmark = sub.add_parser("benchmark")
    benchmark.add_argument("-k", type=int, default=3)
    benchmark.add_argument("--json", action="store_true")
    benchmark.set_defaults(func=command_benchmark)

    attest = sub.add_parser("attest")
    attest_sub = attest.add_subparsers(dest="attest_command", required=True)
    attest_create = attest_sub.add_parser("create")
    attest_create.add_argument("--repo", default=".")
    attest_create.add_argument("--spec", required=True)
    attest_create.add_argument("--output", required=True)
    attest_create.add_argument("--maker", required=True)
    attest_create.add_argument("--checker", required=True)
    attest_create.add_argument("--session", required=True)
    attest_create.add_argument("--verdict", choices=["approved", "revise", "blocked"], required=True)
    attest_create.add_argument("--deliberation", help="a sealed release-gate session (hpp.deliberation/v2); "
                                                       "the stricter of the two verdicts is recorded")
    attest_create.add_argument("--maker-family", dest="maker_family",
                               help="the maker's model family; a judge of that family is refused")
    attest_create.set_defaults(func=command_attest)
    attest_verify = attest_sub.add_parser("verify")
    attest_verify.add_argument("attestation")
    attest_verify.add_argument("--repo", default=".")
    attest_verify.set_defaults(func=command_attest)

    work = sub.add_parser("work")
    work_sub = work.add_subparsers(dest="work_command", required=True)
    plan = work_sub.add_parser("plan")
    plan.add_argument("spec")
    plan.set_defaults(func=command_work)
    waves = work_sub.add_parser("waves")
    waves.add_argument("spec")
    waves.set_defaults(func=command_work)
    coverage = work_sub.add_parser(
        "coverage", help="which acceptance criteria a test cites and, with --junit, which a test actually ran")
    coverage.add_argument("spec")
    coverage.add_argument("--tests", nargs="+", required=True,
                          help="Python test files or directories; citations are read from docstrings")
    coverage.add_argument("--junit", nargs="+", default=[],
                          help="JUnit XML reports of the run; without them only citation is measured")
    coverage.set_defaults(func=command_work)

    route_parser = sub.add_parser("route")
    route_parser.add_argument("--request", required=True)
    route_parser.add_argument("--providers", required=True)
    route_parser.add_argument("--policy", choices=["economy", "balanced", "frontier"], default="balanced")
    route_parser.add_argument("--deliberation", help="a sealed plan session whose verdict can only raise the risk")
    route_parser.add_argument("--maker-family", dest="maker_family",
                              help="the maker's model family; a judge of that family is refused")
    route_parser.set_defaults(func=command_route)

    decide = sub.add_parser(
        "decide",
        description="Typed-decision records made OUTSIDE the harness: validate one, or measure a decider. "
                    "hpp never calls a model; a decider is a command you declare.",
    )
    decide_sub = decide.add_subparsers(dest="decide_command", required=True)
    decide_validate = decide_sub.add_parser("validate", help="check one hpp.decision/v1 record and print its effective value")
    decide_validate.add_argument("record")
    decide_validate.set_defaults(func=command_decide)
    decide_eval = decide_sub.add_parser("eval", help="measure a decider on a labelled suite; abstention is an outcome")
    decide_eval.add_argument("suite")
    decide_eval.add_argument("--decider-command", dest="decider_command",
                             help='JSON argv of the decider, e.g. ["python", "decide.py"]; omit to replay the records in the suite')
    decide_eval.add_argument("--timeout", type=float, default=10.0, help="seconds per case before it counts as an instrument failure")
    decide_eval.add_argument("--min-selective-accuracy", dest="min_selective_accuracy", type=float, default=0.9)
    decide_eval.add_argument("--max-confident-errors", dest="max_confident_errors", type=int, default=0)
    decide_eval.add_argument("--max-failures", dest="max_failures", type=int, default=0)
    decide_eval.set_defaults(func=command_decide)

    findings = sub.add_parser(
        "findings",
        description="Review lenses answer in one shape, hpp.findings/v1. hpp checks the shape and derives "
                    "the verdict; it never reads the change and never calls a model.",
    )
    findings_sub = findings.add_subparsers(dest="findings_command", required=True)
    findings_check = findings_sub.add_parser(
        "check", help="check hpp.findings/v1 documents; exit 0 all pass, 1 something found, 2 refused")
    findings_check.add_argument("files", nargs="+")
    findings_check.add_argument("--subject", help="the change reviewed; every document must name it by its sha256")
    findings_check.set_defaults(func=command_findings)

    deliberate = sub.add_parser(
        "deliberate",
        description="House Session: validate a panel of pinned deciders, count its turns, decide when it stops, "
                    "and seal the session as an hpp.deliberation/v1 record. hpp never calls a model; seats and "
                    "the judge answer outside it.",
    )
    deliberate_sub = deliberate.add_subparsers(dest="deliberate_command", required=True)
    deliberate_plan = deliberate_sub.add_parser("plan", help="check an hpp.panel/v1 and print it with its hash")
    deliberate_plan.add_argument("file")
    deliberate_plan.add_argument("--context", help="the context the seats were given (the file `cite check` reads); "
                                                   "its ids become the evidence a fact may cite")
    deliberate_plan.add_argument("--evidence", nargs="+", default=[],
                                 help="hpp.evidence/v1 records; each one that verifies adds its id to the evidence")
    deliberate_plan.add_argument("--out", help="write the checked panel (with its evidence) where the session will read it")
    deliberate_plan.set_defaults(func=command_deliberate)
    deliberate_validate = deliberate_sub.add_parser(
        "validate", help="check a panel, a turn (with --panel) or a deliberation record (verified)")
    deliberate_validate.add_argument("file")
    deliberate_validate.add_argument("--panel", help="the panel a turn belongs to")
    deliberate_validate.set_defaults(func=command_deliberate)
    for name, text in (("tally", "count every round: grounded and ungrounded votes, abstentions, seats not judged"),
                       ("stop", "continue with the next round, or stop with the rule that stopped the session"),
                       ("record", "seal a stopped session with the judge's decision into an hpp.deliberation/v1")):
        action = deliberate_sub.add_parser(name, help=text)
        action.add_argument("--panel", required=True, help="the hpp.panel/v1 file")
        action.add_argument("--turns", required=True, help="JSON list of hpp.turn/v1 turns")
        if name == "record":
            action.add_argument("--judge", help="the judge's hpp.decision/v1 record (not needed when a seat is not judged)")
            action.add_argument("--out", required=True, help="where to write the sealed record")
            action.add_argument("--rationale", help="the judge seat's hpp.rationale/v1: a steelman of each grounded "
                                                    "dissenting position and what would change the verdict")
        action.set_defaults(func=command_deliberate)
    deliberate_verify = deliberate_sub.add_parser("verify", help="check the seal and re-derive the record from its turns")
    deliberate_verify.add_argument("record")
    deliberate_verify.set_defaults(func=command_deliberate)

    retrieval = sub.add_parser(
        "retrieval",
        description="Measure a retriever on a labelled suite: hit@k, recall@k, precision@k, MRR and nDCG@k, "
                    "with instrument failures counted apart. hpp calls no model; a retriever is a command you declare.",
    )
    retrieval_sub = retrieval.add_subparsers(dest="retrieval_command", required=True)
    retrieval_eval = retrieval_sub.add_parser("eval", help="score a retriever against the relevant ids of each case")
    retrieval_eval.add_argument("suite")
    retrieval_eval.add_argument("--retriever-command", dest="retriever_command",
                                help='JSON argv of the retriever, e.g. ["python", "search.py"]; omit to replay the results in the suite')
    retrieval_eval.add_argument("-k", type=int, default=None, help="cut-off; defaults to the suite's k")
    retrieval_eval.add_argument("--timeout", type=float, default=10.0, help="seconds per case before it counts as an instrument failure")
    retrieval_eval.add_argument("--min-recall", dest="min_recall", type=float, default=0.8)
    retrieval_eval.add_argument("--max-failures", dest="max_failures", type=int, default=0)
    retrieval_eval.set_defaults(func=command_retrieval)

    cite = sub.add_parser(
        "cite",
        description="Check the citation markers in a text against the ids of the context it was written from: "
                    "unknown ids and ranges block, uncited numbers and overloaded sentences warn.",
    )
    cite_sub = cite.add_subparsers(dest="cite_command", required=True)
    cite_check = cite_sub.add_parser("check", help="read the two files given and report every finding")
    cite_check.add_argument("--text", required=True, help="the answer or report to check (UTF-8)")
    cite_check.add_argument("--context", required=True, help="JSON list of the context items and their ids")
    cite_check.add_argument("--max-per-sentence", dest="max_per_sentence", type=int, default=4)
    cite_check.add_argument("--marker", help=r"regex with one group for the id (default: \[ID:(...)\])")
    cite_check.set_defaults(func=command_cite)

    evidence = sub.add_parser(
        "evidence",
        description="Run a declared criterion command and hash the artifacts it produced (a trace, screenshots, "
                    "logs); verify re-hashes them later. hpp drives no browser and calls no model.",
    )
    evidence_sub = evidence.add_subparsers(dest="evidence_command", required=True)
    evidence_run = evidence_sub.add_parser("run", help="run the criterion and write .hpp/evidence/<id>-<utc>.json")
    evidence_run.add_argument("--id", required=True, help="a plain name for this evidence, e.g. e2e-login")
    evidence_run.add_argument("--artifact", action="append",
                              help="glob of a file the command must produce, relative to the workspace; repeatable")
    evidence_run.add_argument("--timeout", type=float, default=600.0, help="seconds before the run counts as a timeout")
    evidence_run.add_argument("--out", help="directory for the record, relative to the workspace (default .hpp/evidence)")
    evidence_run.add_argument("--record-event", dest="record_event", action="store_true",
                              help="append evidence_recorded to the event log when, and only when, the bundle passed")
    evidence_run.add_argument("--manifest")
    evidence_run.add_argument("criterion", nargs=argparse.REMAINDER, help="-- then the command to run")
    evidence_run.set_defaults(func=command_evidence)
    evidence_mutate = evidence_sub.add_parser(
        "mutate", help="run the criterion on a copy of the workspace: it must pass clean and fail on every mutant")
    evidence_mutate.add_argument("--id", required=True, help="a plain name for this measurement")
    evidence_mutate.add_argument("--mutants", help="an hpp.mutants/v1 file: {id, file, find, replace[, occurrence]}")
    evidence_mutate.add_argument("--generate", action="append",
                                 help="a Python file to mutate operator by operator "
                                      "(== != < <= > >= and or True False); repeatable")
    evidence_mutate.add_argument("--timeout", type=float, default=600.0, help="seconds per run of the criterion")
    evidence_mutate.add_argument("--out", help="directory for the record, relative to the workspace (default .hpp/evidence)")
    evidence_mutate.add_argument("criterion", nargs=argparse.REMAINDER, help="-- then the command to run, with relative paths")
    evidence_mutate.set_defaults(func=command_evidence)
    evidence_verify = evidence_sub.add_parser("verify", help="re-hash a record and its artifacts")
    evidence_verify.add_argument("record")
    evidence_verify.set_defaults(func=command_evidence)

    context = sub.add_parser("context")
    context_sub = context.add_subparsers(dest="context_command", required=True)
    compile_parser = context_sub.add_parser("compile")
    compile_parser.add_argument("inputs")
    compile_parser.add_argument("--budget", required=True, type=int)
    compile_parser.set_defaults(func=command_context)

    map_parser = sub.add_parser("map")
    map_sub = map_parser.add_subparsers(dest="map_view", required=True)
    lane = map_sub.add_parser("lane")
    lane.add_argument("source")
    lane.add_argument("--now", type=int,
                      help="explicit Unix timestamp used to derive liveness")
    lane.add_argument("--suspect-after", type=int, default=300)
    lane.add_argument("--dead-after", type=int, default=900)
    lane.set_defaults(func=command_map)
    agent = map_sub.add_parser("agent")
    agent.add_argument("--manifest")
    agent.add_argument("--events")
    agent.set_defaults(func=command_map)
    monitor = map_sub.add_parser("monitor")
    monitor.add_argument("source")
    monitor.add_argument("--now", required=True, type=int,
                         help="explicit Unix timestamp; avoids ambient-clock projections")
    monitor.add_argument("--skew-tolerance", type=int, default=5,
                         help="seconds a signal may sit after --now before it is reported as skew")
    monitor.set_defaults(func=command_map)
    context_map = map_sub.add_parser("context")
    context_map.add_argument("source")
    context_map.add_argument("--budget", required=True, type=int)
    context_map.set_defaults(func=command_map)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    arguments = list(sys.argv[1:] if argv is None else argv)
    try:
        if arguments == ["--self-test"]:
            return self_test()
        args = parser.parse_args(arguments)
        return args.func(args)
    except (AttestationError, ManifestError, InstallError, StateError, EvalError, ValueError, json.JSONDecodeError) as exc:
        print(f"hpp: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"hpp: internal error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())

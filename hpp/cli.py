"""Command-line surface for the House Party Protocol harness."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from hpp import __version__
from hpp.context import compile_context
from hpp.evals import EvalError, exit_for as eval_exit_for, run_suite
from hpp.graph import build_graph, to_mermaid
from hpp.install import InstallError, installation_plan
from hpp.manifest import ManifestError, load_manifest, validate_distribution
from hpp.maps import build_agent_map, build_context_map, build_lane_map, build_monitor_map
from hpp.policy import assess, exit_for as policy_exit_for
from hpp.routing import route
from hpp.state import StateError, append_event, event_path, project, read_events
from hpp.workgraph import compile_workgraph


def _json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


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
    result = {"status": "ok", "version": __version__, "manifest": str(path),
              "modules": len(manifest["modules"]), "bundles": sorted(manifest["bundles"]),
              "hosts": manifest["hosts"], "distribution": distribution}
    if args.json:
        _json(result)
    else:
        print(f"HPP doctor: ok · modules={result['modules']} · hosts={', '.join(result['hosts'])}")
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
        print(f"HPP status: {status['state']} · events={status['event_count']} · next={status['next_step']}")
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
    suite = Path(__file__).resolve().parent.parent / "examples" / "reliable-coding" / "benchmark-suite.json"
    report = run_suite(suite, args.k, "both")
    if args.json:
        _json(report)
    else:
        metrics = report["metrics"]
        print(f"HPP benchmark: pass@k={metrics['pass_at_k']:.2f} · pass^k={metrics['pass_caret_k']:.2f} · gate={'PASS' if report['gate']['passed'] else 'FAIL'}")
    return eval_exit_for(report)


def command_work(args: argparse.Namespace) -> int:
    compiled = compile_workgraph(_read_json(args.spec, dict))
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
    _json(route(request, args.policy, providers))
    return 0


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
        projection = build_monitor_map(_read_json(args.source, list), args.now)
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
    report = run_suite(
        Path(__file__).resolve().parent.parent / "examples" / "reliable-coding" / "benchmark-suite.json",
        3,
        "both",
    )
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

    work = sub.add_parser("work")
    work_sub = work.add_subparsers(dest="work_command", required=True)
    plan = work_sub.add_parser("plan")
    plan.add_argument("spec")
    plan.set_defaults(func=command_work)
    waves = work_sub.add_parser("waves")
    waves.add_argument("spec")
    waves.set_defaults(func=command_work)

    route_parser = sub.add_parser("route")
    route_parser.add_argument("--request", required=True)
    route_parser.add_argument("--providers", required=True)
    route_parser.add_argument("--policy", choices=["economy", "balanced", "frontier"], default="balanced")
    route_parser.set_defaults(func=command_route)

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
    except (ManifestError, InstallError, StateError, EvalError, ValueError, json.JSONDecodeError) as exc:
        print(f"hpp: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"hpp: internal error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())

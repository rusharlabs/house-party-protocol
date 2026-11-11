"""Conservative, commit-bound code relationships; inspection never imports project code."""
from __future__ import annotations

import ast
from collections import Counter
import json
from pathlib import Path, PurePosixPath
import re
import unicodedata
from typing import Any

from hpp import __version__
from hpp._process import run_bounded, valid_timeout
from hpp._repository import RepositoryError, artifact_status, read_text, snapshot
from hpp.context import _SECRET_PATTERN

SCHEMA = "hpp.codegraph/v1"
MAX_DOCUMENT_BYTES = 2 * 1024 * 1024
MAX_RECORDS = 50000
_LANGUAGES = {".py": "python", ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript",
              ".cjs": "javascript", ".ts": "typescript", ".tsx": "typescript"}
_JS_IMPORT = re.compile(r"\b(?:import|export)\s+(?:[^'\";\n]{0,512}?\bfrom\s*)?['\"]([^'\"\n]{1,512})['\"]")
_SAFE_REFERENCE = re.compile(r"[\w.$@/+-]+\Z", re.UNICODE)


class CodegraphError(ValueError):
    """A code graph cannot satisfy the input contract."""


def _label(value: Any) -> str:
    if (not isinstance(value, str) or not value or len(value) > 500
            or not re.fullmatch(r"[\w.:@/+-]+", value, re.UNICODE)
            or any(ord(c) < 32 for c in value) or _SECRET_PATTERN.search(value)
            or re.search(r"(?:^|:)[/\\]|[A-Za-z]:[/\\]|https?://", value)):
        raise CodegraphError("graph contains an unsafe label")
    return unicodedata.normalize("NFC", value)


def _path(value: Any) -> str:
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        raise CodegraphError("graph paths must be relative POSIX paths")
    value = unicodedata.normalize("NFC", value)
    if (PurePosixPath(value).is_absolute() or any(p in {"", ".", ".."} for p in value.split("/"))
            or any(ord(c) < 32 for c in value)):
        raise CodegraphError("graph paths must stay inside the repository")
    return value


def _reference(value: str) -> str:
    # Unresolved input is evidence of a limitation, not a channel for arbitrary source text.
    if len(value) > 300 or not _SAFE_REFERENCE.fullmatch(value) or value.startswith("/") or _SECRET_PATTERN.search(value):
        return "<withheld>"
    return unicodedata.normalize("NFC", value)


def _producer_argv(command: list[str]) -> list[str]:
    # Commands may carry credentials or source in positional arguments; never persist their values.
    executable = command[0].replace("\\", "/").rsplit("/", 1)[-1]
    try:
        executable = _label(executable)
    except CodegraphError:
        executable = "<withheld>"
    return [executable, *["<argument>" for _ in command[1:]]]


def _empty(snap, kind: str, status: str = "measured", reason: str | None = None) -> dict:
    result = {"schema": SCHEMA, "commit": snap.commit, "status": status, "producer": {"kind": kind},
              "coverage": {}, "nodes": [], "edges": [], "unresolved": [], "excluded": [],
              "instrument": {"status": status}}
    if reason:
        result["instrument"]["reason"] = reason
    return result


def _metrics(result: dict, snap) -> dict:
    result["universe_commit"] = snap.commit
    paths = {n["path"] for n in result["nodes"]}
    result["measured"] = {
        "universe_files": len(snap.files), "covered_files": len(paths),
        "coverage_ratio": len(paths) / len(snap.files) if snap.files else 0.0,
        "excluded_nodes": sum(x["count"] for x in result["excluded"] if x["reason"] != "unknown edge source")
                          if result["producer"]["kind"] == "declared" else 0,
        "excluded_files": sum(x["count"] for x in result["excluded"])
                          if result["producer"]["kind"] == "builtin-ast" else 0,
        "unresolved_edges": len(result["unresolved"]),
        "language_files": dict(sorted(Counter(_LANGUAGES.get(PurePosixPath(p).suffix, "other") for p in paths).items())),
    }
    result["freshness"] = artifact_status(snap.root, result)
    return result


def _normalise(snap, document: dict) -> dict:
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        raise CodegraphError("expected hpp.codegraph/v1 object")
    if document.get("status") in {"instrument-failure", "invalid", "not-measured"}:
        raise CodegraphError("declared graph is not a measured result")
    instrumentation = document.get("instrument")
    if instrumentation is not None and (not isinstance(instrumentation, dict)
                                        or instrumentation.get("status") != "measured"):
        raise CodegraphError("declared graph does not report measured instrumentation")
    try:
        encoded = json.dumps(document, ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, RecursionError):
        raise CodegraphError("graph must be bounded JSON data") from None
    if len(encoded) > MAX_DOCUMENT_BYTES:
        raise CodegraphError("graph exceeds the document byte limit")
    commit = document.get("commit")
    if not isinstance(commit, str) or not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", commit):
        raise CodegraphError("graph requires a full commit identity")
    if "universe_commit" in document:
        universe = document["universe_commit"]
        if (not isinstance(universe, str) or not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", universe)
                or universe != commit):
            raise CodegraphError("graph universe provenance must match its commit")
    nodes, edges, unresolved = (document.get(k, []) for k in ("nodes", "edges", "unresolved"))
    if any(not isinstance(items, list) or len(items) > MAX_RECORDS for items in (nodes, edges, unresolved)):
        raise CodegraphError("graph records must be bounded arrays")
    result = _empty(snap, "declared")
    result["commit"] = commit
    version = document.get("producer", {}).get("version") if isinstance(document.get("producer"), dict) else None
    if version is not None:
        result["producer"]["version"] = _label(version)
    seen, accepted, safe_paths = set(), set(), {}
    excluded = Counter()
    for node in nodes:
        if not isinstance(node, dict):
            raise CodegraphError("node must be an object")
        identity = _label(node.get("id"))
        if identity in seen:
            raise CodegraphError("duplicate graph node identity")
        seen.add(identity)
        try:
            path = _path(node.get("path"))
        except CodegraphError:
            excluded["outside universe"] += 1
            continue
        if path not in snap.files:
            excluded["outside universe"] += 1
            continue
        if path not in safe_paths:
            try:
                read_text(snap, path)
                safe_paths[path] = True
            except RepositoryError:
                safe_paths[path] = False
        if not safe_paths[path]:
            excluded["unreadable or excluded file"] += 1
            continue
        kind = node.get("kind")
        if kind not in {"module", "function", "class", "method", "symbol"}:
            raise CodegraphError("unsupported node kind")
        clean = {"id": identity, "kind": kind, "path": path}
        if "line" in node:
            line = node["line"]
            if isinstance(line, bool) or not isinstance(line, int) or not 1 <= line <= 100000000:
                raise CodegraphError("node line must be a positive integer")
            clean["line"] = line
        result["nodes"].append(clean)
        accepted.add(identity)
    for edge in edges:
        if not isinstance(edge, dict) or edge.get("relation") not in {"imports", "calls", "defines"}:
            raise CodegraphError("unsupported graph edge")
        source, target = _label(edge.get("from")), _label(edge.get("to"))
        relation = edge["relation"]
        if source not in accepted:
            excluded["unknown edge source"] += 1
            result["unresolved"].append({"from": source, "target": _reference(target),
                                         "relation": relation, "reason": "unknown source node"})
        elif target not in accepted:
            result["unresolved"].append({"from": source, "target": _reference(target),
                                         "relation": relation, "reason": "unknown node"})
        else:
            result["edges"].append({"from": source, "to": target, "relation": relation})
    for edge in unresolved:
        if not isinstance(edge, dict) or edge.get("relation") not in {"imports", "calls"}:
            raise CodegraphError("unsupported unresolved edge")
        source = _label(edge.get("from"))
        if source not in accepted:
            excluded["unknown edge source"] += 1
            continue
        result["unresolved"].append({"from": source, "target": _reference(str(edge.get("target", "<unknown>"))),
                                     "relation": edge["relation"], "reason": "declared unresolved"})
    # Never trust the producer's coverage, counters, freshness or instrumentation claims.
    for path in {node["path"] for node in result["nodes"]}:
        language = _LANGUAGES.get(PurePosixPath(path).suffix)
        if language:
            result["coverage"][language] = "declared; relationships not independently verified"
    result["nodes"].sort(key=lambda n: n["id"])
    result["edges"] = _unique(result["edges"])
    result["unresolved"] = _unique(result["unresolved"])
    result["excluded"] = [{"reason": reason, "count": count} for reason, count in sorted(excluded.items())]
    return _metrics(result, snap)


def _unique(items: list[dict]) -> list[dict]:
    return [json.loads(value) for value in sorted({json.dumps(x, sort_keys=True, ensure_ascii=False) for x in items})]


def import_codegraph(target: str | Path, document: dict) -> dict:
    """Validate and measure declared JSON against the regular files in HEAD; write nothing."""
    return _normalise(snapshot(target), document)


def _module(path: str) -> str:
    parts = list(PurePosixPath(path).with_suffix("").parts)
    if parts and parts[0] == "src":
        parts.pop(0)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts) or "__root__"


class _Python(ast.NodeVisitor):
    def __init__(self, module: str, identity: str, path: str):
        self.module, self.identity, self.path = module, identity, path
        self.scope: list[str] = []
        self.scope_kinds: list[str] = []
        self.sources = [identity]
        self.nodes: list[dict] = []
        self.parents: list[tuple[str, str]] = []
        self.definitions: dict[str, list[str]] = {}
        self.imports: list[tuple[str, ast.AST, bool]] = []
        self.conditional_depth = 0
        self.calls: list[tuple[str, str, list[list[str]], set[str]]] = []
        self.shadowed: list[set[str]] = [set()]

    def _definition(self, node, kind: str):
        name = ".".join([*self.scope, node.name])
        identity = f"symbol:{self.module}.{name}"
        if name in self.definitions:
            identity += f"@{node.lineno}"
        self.definitions.setdefault(name, []).append(identity)
        self.parents.append((self.sources[-1], identity))
        self.nodes.append({"id": identity, "kind": kind, "path": self.path, "line": node.lineno})
        self.scope.append(node.name)
        self.scope_kinds.append(kind)
        self.sources.append(identity)
        bound = {n.id for n in ast.walk(node) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            bound.update(arg.arg for arg in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs))
            bound.update(arg.arg for arg in (node.args.vararg, node.args.kwarg) if arg is not None)
        self.shadowed.append(bound)
        for child in node.body:
            self.visit(child)
        self.shadowed.pop()
        self.sources.pop()
        self.scope.pop()
        self.scope_kinds.pop()

    def visit_FunctionDef(self, node):
        self._definition(node, "function")

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        self._definition(node, "class")

    def visit_Import(self, node):
        self.imports.append((self.sources[-1], node, self.conditional_depth > 0))

    visit_ImportFrom = visit_Import

    def _conditional(self, node):
        self.conditional_depth += 1
        self.generic_visit(node)
        self.conditional_depth -= 1

    visit_If = _conditional
    visit_Try = _conditional
    visit_TryStar = _conditional
    visit_For = _conditional
    visit_AsyncFor = _conditional
    visit_While = _conditional
    visit_Match = _conditional

    def visit_Call(self, node):
        names, value = [], node.func
        while isinstance(value, ast.Attribute):
            names.insert(0, value.attr)
            value = value.value
        if isinstance(value, ast.Name):
            names.insert(0, value.id)
        else:
            names = ["<dynamic>"]
        lexical = [self.scope[:depth] for depth in range(len(self.scope), -1, -1)
                   if depth == len(self.scope) or depth == 0 or self.scope_kinds[depth - 1] != "class"]
        self.calls.append((self.sources[-1], ".".join(names), lexical, set.union(*self.shadowed)))
        self.generic_visit(node)


def _builtin(snap) -> dict:
    result = _empty(snap, "builtin-ast")
    result["producer"]["version"] = __version__
    result["limitations"] = ["Syntactic relationships, not execution or type analysis.",
                              "Dynamic imports, dynamic dispatch, wildcard imports and ambiguous names remain unresolved.",
                              "JavaScript and TypeScript use lexical imports only (512-character statement limit); comments may produce candidates."]
    excluded = Counter()
    parsers = {}
    if len(snap.modes) > len(snap.files):
        excluded["symlink or gitlink"] = len(snap.modes) - len(snap.files)
    modules: dict[str, list[str]] = {}
    module_nodes = {}
    for path in snap.files:
        language = _LANGUAGES.get(PurePosixPath(path).suffix)
        if language is None:
            excluded["unsupported language"] += 1
            continue
        try:
            text = read_text(snap, path)
        except RepositoryError:
            excluded["unreadable or excluded file"] += 1
            continue
        if language == "python":
            try:
                tree = ast.parse(text, filename="<snapshot>")
            except (SyntaxError, ValueError, RecursionError, MemoryError):
                excluded["Python parse failure"] += 1
                continue
            module = _module(path)
            # Path identities stay unique even where two source roots expose the same import name.
            identity = f"module:{path}"
            parser = _Python(module, identity, path)
            parser.shadowed[0].update(n.id for child in tree.body
                                      if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                                      for n in ast.walk(child) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store))
            try:
                parser.visit(tree)
            except RecursionError:
                excluded["Python parse depth limit"] += 1
                continue
            parsers[path] = parser
            modules.setdefault(module, []).append(identity)
        else:
            identity = f"module:{path}"
            parsers[path] = text
        module_nodes[path] = identity
        result["nodes"].append({"id": identity, "kind": "module", "path": path})
        result["coverage"][language] = "symbols+calls (conservative)" if language == "python" else "imports-only (lexical)"
    definitions = {}
    for parser in parsers.values():
        if isinstance(parser, _Python):
            # Symbol IDs include the module path, so colliding import roots cannot collide IDs.
            mapping = {n["id"]: n["id"].replace(f"symbol:{parser.module}.", f"symbol:{parser.path}:", 1) for n in parser.nodes}
            for node in parser.nodes:
                node["id"] = mapping[node["id"]]
                result["nodes"].append(node)
            parser.sources_map = mapping
            for source, target in parser.parents:
                result["edges"].append({"from": mapping.get(source, source), "to": mapping[target], "relation": "defines"})
            for name, ids in parser.definitions.items():
                definitions.setdefault(f"{parser.module}.{name}", []).extend(mapping[i] for i in ids)
    def edge(source, target, relation):
        if target:
            result["edges"].append({"from": source, "to": target, "relation": relation})
        else:
            raise AssertionError("edge requires a target")
    def unresolved(source, target, relation, reason):
        result["unresolved"].append({"from": source, "target": _reference(target), "relation": relation, "reason": reason})
    def resolve(name):
        ids = modules.get(name, []) + definitions.get(name, [])
        return ids[0] if len(ids) == 1 else None
    for path, parser in parsers.items():
        identity = module_nodes[path]
        if isinstance(parser, str):
            for match in _JS_IMPORT.finditer(parser):
                name = match.group(1)
                candidates = []
                if name.startswith("."):
                    parts = list(PurePosixPath(path).parent.parts)
                    for part in name.split("/"):
                        if part == ".." and parts:
                            parts.pop()
                        elif part not in {"", "."}:
                            parts.append(part)
                    stem = "/".join(parts)
                    candidates = [p for p in module_nodes if p in {stem, *(stem + ext for ext in (".js", ".jsx", ".ts", ".tsx", "/index.js", "/index.ts"))}]
                if len(candidates) == 1:
                    edge(identity, module_nodes[candidates[0]], "imports")
                else:
                    unresolved(identity, name, "imports", "outside universe or ambiguous lexical import")
            continue
        aliases_by_source = {}
        def bind(aliases, name, target):
            aliases[name] = target if name not in aliases or aliases[name] == target else None
        for source, node, conditional in parser.imports:
            source = parser.sources_map.get(source, source)
            aliases = aliases_by_source.setdefault(source, {})
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name
                    target = resolve(name)
                    if target:
                        edge(source, target, "imports")
                    else:
                        unresolved(source, name, "imports", "outside universe or ambiguous module")
                    bind(aliases, alias.asname or name.split(".")[0],
                         None if conditional else name if alias.asname else name.split(".")[0])
            else:
                package = parser.module.split(".") if PurePosixPath(path).stem == "__init__" else parser.module.split(".")[:-1]
                if node.level:
                    if node.level > len(package):
                        name = "<relative-outside>"
                    else:
                        base = package[:len(package) - node.level + 1]
                        name = ".".join([*base, *([node.module] if node.module else [])])
                else:
                    name = node.module or ""
                imported = resolve(name)
                if imported:
                    edge(source, imported, "imports")
                for alias in node.names:
                    qualified = f"{name}.{alias.name}".strip(".")
                    target = resolve(qualified)
                    if not imported:
                        child = resolve(qualified)
                        if child:
                            edge(source, child, "imports")
                        else:
                            unresolved(source, qualified, "imports", "outside universe or ambiguous import")
                    elif alias.name == "*":
                        unresolved(source, qualified, "imports", "wildcard import")
                    elif target is None:
                        unresolved(source, qualified, "imports", "unknown or dynamic imported member")
                    elif target.startswith("module:"):
                        edge(source, target, "imports")
                    bind(aliases, alias.asname or alias.name, None if conditional else qualified)
        for source, name, lexical, shadowed in parser.calls:
            source = parser.sources_map.get(source, source)
            aliases = dict(aliases_by_source.get(identity, {}))
            for scope in reversed(lexical):
                if not scope:
                    continue
                owners = parser.definitions.get(".".join(scope), [])
                for owner in owners:
                    inherited = aliases_by_source.get(parser.sources_map.get(owner, owner), {})
                    if len(owners) == 1:
                        aliases.update(inherited)
                    else:
                        aliases.update({key: None for key in inherited})
            parts = name.split(".")
            target = None
            if parts[0] not in shadowed:
                if parts[0] in aliases and aliases[parts[0]] is not None:
                    target = resolve(".".join([aliases[parts[0]], *parts[1:]]))
                elif parts[0] not in aliases:
                    for scope in lexical:
                        target = resolve(".".join([parser.module, *scope, name]))
                        if target:
                            break
            if target:
                edge(source, target, "calls")
            else:
                unresolved(source, name, "calls", "dynamic, external or ambiguous call")
    result["nodes"].sort(key=lambda n: n["id"])
    result["edges"] = _unique(result["edges"])
    result["unresolved"] = _unique(result["unresolved"])
    result["excluded"] = [{"reason": reason, "count": count} for reason, count in sorted(excluded.items())]
    return _metrics(result, snap)


def build_codegraph(target: str | Path, indexer_command: list[str] | str | None = None,
                    timeout: float = 30.0) -> dict:
    """Build from HEAD, or run an explicitly declared argv receiving commit/files JSON on stdin."""
    snap = snapshot(target)
    if indexer_command is None:
        return _builtin(snap)
    if isinstance(indexer_command, str):
        try:
            indexer_command = json.loads(indexer_command)
        except (ValueError, RecursionError):
            raise CodegraphError("indexer command must be an argv JSON array") from None
    if (not isinstance(indexer_command, list) or not indexer_command or len(indexer_command) > 256
            or any(not isinstance(arg, str) or not arg or "\x00" in arg or len(arg) > 16384 for arg in indexer_command)):
        raise CodegraphError("indexer command must be a nonempty bounded argv array")
    if not valid_timeout(timeout):
        raise CodegraphError("indexer timeout is invalid")
    request = json.dumps({"schema": "hpp.codegraph-request/v1", "commit": snap.commit,
                          "files": list(snap.files)}, ensure_ascii=False).encode("utf-8")
    state, code, stdout, _stderr = run_bounded(indexer_command, timeout=timeout, cwd=str(snap.root),
                                              stdin=request, max_output_bytes=MAX_DOCUMENT_BYTES)
    reason = state if state != "exited" else "nonzero exit" if code != 0 else None
    result = None
    if reason is None:
        try:
            document = json.loads(stdout)
            result = _normalise(snap, document)
        except (ValueError, UnicodeDecodeError, RecursionError):
            reason = "invalid indexer JSON or graph contract"
    if result is None:
        result = _metrics(_empty(snap, "declared", "instrument-failure", reason), snap)
    result["producer"]["argv"] = _producer_argv(indexer_command)
    result["instrument"].update(exit_code=code, stdout_bytes=len(stdout), stderr_tail="withheld")
    return result


def compare_codegraphs(target: str | Path, declared: dict) -> dict:
    """Compare file-level Python import edges, independently of producer-specific node IDs."""
    snap = snapshot(target)
    actual = _builtin(snap)
    other = _normalise(snap, declared)
    def imports(graph):
        paths = {n["id"]: n["path"] for n in graph["nodes"]}
        return {(paths[e["from"]], paths[e["to"]]) for e in graph["edges"]
                if e["relation"] == "imports" and paths[e["from"]].endswith(".py") and paths[e["to"]].endswith(".py")}
    base, found = imports(actual), imports(other)
    fresh = other["freshness"]["status"] == "fresh"
    def encode(items):
        return [{"from": a, "to": b} for a, b in sorted(items)]
    return {"schema": "hpp.codegraph-comparison/v1", "commit": snap.commit,
            "status": "measured" if fresh else "not-measured", "freshness": other["freshness"],
            "scope": "file-level Python imports; AST is a conservative reference, not runtime truth",
            "builtin_imports": len(base), "declared_imports": len(found),
            "shared": encode(base & found) if fresh else [],
            "missing_from_declared": encode(base - found) if fresh else [],
            "additional_declared": encode(found - base) if fresh else []}

"""lane-kit's Lane Dashboard: the server runs its own proof, answers only this page, and the page
is built from the project's design system.

Why this file exists: `lane_dashboard.py` serves an HTML page from an installed kit, where `docs/`
does not exist, so the page carries `docs/hpp.css` inlined. Nothing kept that copy honest, and a
page is where a fifth colour or a font from someone else's server arrives first. The same holds
for the two languages the page speaks: a key present in English and missing in Portuguese renders
the key's name to a Portuguese reader. The server side is proved by its `--self-test` and, here,
from outside, as a browser on another origin would try it.
"""
from __future__ import annotations

import base64
import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from types import ModuleType

import pytest

PRODUCT_ROOT = Path(__file__).resolve().parent.parent
MULTI_SESSION = PRODUCT_ROOT / "multi-session"
STYLESHEET = PRODUCT_ROOT / "docs" / "hpp.css"
BRAND = PRODUCT_ROOT / "docs" / "BRAND.md"

HEX = re.compile(r"#[0-9A-Fa-f]{6}\b|#[0-9A-Fa-f]{3}\b")
RGB = re.compile(r"rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})")
DATA_URI = re.compile(r"data:image/[a-z]+;base64,[A-Za-z0-9+/=]+")


def _kit() -> Path:
    if not MULTI_SESSION.is_dir():
        pytest.skip("multi-session/ exists only in the emitted tree; this is the source tree")
    boards = sorted(MULTI_SESSION.glob("lane-kit-*/scripts/lane_dashboard.py"))
    assert len(boards) == 1, f"expected exactly one emitted lane-kit dashboard, found {[b.as_posix() for b in boards]}"
    return boards[0].parents[1]


def _page() -> str:
    return DATA_URI.sub("data:", (_kit() / "scripts" / "lane_dashboard.html").read_text(encoding="utf-8"))


def _brand_hex() -> set[str]:
    return {value.upper() for value in HEX.findall(BRAND.read_text(encoding="utf-8")) if len(value) == 7}


def _outside_the_palette(text: str) -> set[str]:
    allowed_hex = _brand_hex()
    allowed_rgb = {tuple(int(value[i:i + 2], 16) for i in (1, 3, 5)) for value in allowed_hex}
    found = {value.upper() for value in HEX.findall(text)} - allowed_hex
    found |= {f"rgb{triple}" for triple in {tuple(map(int, match)) for match in RGB.findall(text)} - allowed_rgb}
    return found


# --- the server ---------------------------------------------------------------------------------

def test_the_dashboard_self_test_passes(tmp_path: Path) -> None:
    result = subprocess.run([sys.executable, "-X", "utf8", str(_kit() / "scripts" / "lane_dashboard.py"), "--self-test"],
                            cwd=tmp_path, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
    assert "self-test OK" in result.stdout


@pytest.fixture
def server(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(project)}
    process = subprocess.Popen([sys.executable, "-X", "utf8", str(_kit() / "scripts" / "lane_dashboard.py"),
                                "--project-dir", str(project), "--port", "0", "--no-orca"],
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8", env=env)
    try:
        first = process.stdout.readline()
        match = re.search(r"http://127\.0\.0\.1:(\d+)/", first)
        assert match, f"the dashboard did not print its URL: {first!r}"
        yield f"http://127.0.0.1:{match.group(1)}", project
    finally:
        process.terminate()
        process.wait(timeout=10)
        process.stdout.close()


def _call(url: str, body: dict | None = None, headers: dict | None = None) -> tuple[int, str]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers or {}, method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        body_text = error.read().decode("utf-8", "replace")
        error.close()
        return error.code, body_text


def test_an_empty_project_is_an_empty_board(server) -> None:
    base, _project = server
    status, body = _call(base + "/api/snapshot")
    projects = json.loads(body)["projects"]
    assert status == 200 and len(projects) == 1 and len(projects[0]["worktrees"]) == 1, projects
    snapshot = projects[0]["worktrees"][0]
    assert snapshot["id"] == "project" and snapshot["empty"] and not snapshot["backlog"]["exists"], snapshot
    assert snapshot["metrics"]["items"] == 0 and not snapshot["warnings"]


def test_a_page_on_another_origin_cannot_act(server) -> None:
    base, project = server
    port = base.rsplit(":", 1)[1]
    status, _body = _call(base + "/api/snapshot", headers={"Host": f"rebound.example:{port}"})
    assert status == 403, "a foreign Host header read the board (DNS rebinding)"
    spec = {"id": "SPEC-1", "title": "one", "acceptance": ["it works"], "create_plan": True}
    status, _body = _call(base + "/api/backlog/specs", spec, {"Content-Type": "application/json"})
    assert status == 403, "a POST without this run's token was accepted"
    status, _body = _call(base + "/api/backlog/specs", spec, {"Content-Type": "text/plain", "X-HPP-Token": "guess"})
    assert status == 403
    assert not (project / "docs" / "plans" / "execution" / "BACKLOG.json").exists()


def test_CONTROLE_the_page_s_own_token_is_accepted(server) -> None:
    """The refusals above are about the missing token: the page, with its token, can act."""
    base, project = server
    status, page = _call(base + "/")
    token = re.search(r'<meta name="hpp-session" content="([^"]+)">', page)
    assert status == 200 and token and not token.group(1).startswith("__"), "the page was not served with a token"
    status, body = _call(base + "/api/backlog/specs", {"id": "SPEC-1", "title": "one", "acceptance": ["it works"],
                                                         "create_plan": True},
                         {"Content-Type": "application/json", "X-HPP-Token": token.group(1)})
    assert status == 201, body
    assert (project / "docs" / "plans" / "execution" / "BACKLOG.json").is_file()


def test_the_relaunch_route_is_guarded_like_every_action(server) -> None:
    base, _project = server
    status, _body = _call(base + "/api/sessions/relaunch", {"lane_id": "claude-plan-x"}, {"Content-Type": "application/json"})
    assert status == 403, "a relaunch without this run's token was accepted"
    status, page = _call(base + "/")
    token = re.search(r'<meta name="hpp-session" content="([^"]+)">', page).group(1)
    status, body = _call(base + "/api/sessions/relaunch", {"lane_id": "claude-plan-x"},
                         {"Content-Type": "application/json", "X-HPP-Token": token})
    assert status == 404 and "no session was prepared" in json.loads(body)["error"], body


# --- the launchers: every one starts the session itself -----------------------------------------
# Why: the dashboard is an orchestration panel. A launcher that answers "paste this in a terminal"
# hands the operator the step the panel exists to take, so none does: Orca, tmux, a window of the
# system terminal or the background, detected from where the dashboard runs.

@pytest.fixture(scope="module")
def dashboard() -> ModuleType:
    spec = importlib.util.spec_from_file_location("lane_dashboard_under_test", _kit() / "scripts" / "lane_dashboard.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _which(*present: str):
    return lambda name: f"/usr/bin/{name}" if name in present else None


class _Process:
    pid = 4242

    def poll(self):
        return None


def _recorder(returncode: int = 0, stdout: str = "", stderr: str = "", fail: tuple[str, ...] = ()):
    """A fake `_run`: records every argv, answers `returncode` (or 1 for a tmux subcommand in `fail`)."""
    calls: list[list[str]] = []

    def run(argv, cwd, timeout, env=None):
        calls.append(list(argv))
        code = 1 if len(argv) > 1 and argv[1] in fail else returncode
        return subprocess.CompletedProcess(argv, code, stdout, stderr)
    run.calls = calls
    return run


def _profile(dashboard: ModuleType, project: Path, role: str = "planner"):
    return dashboard.agent_profile(project, "claude", role, _which("claude"))


def test_no_launcher_hands_the_operator_a_command_to_paste(dashboard: ModuleType) -> None:
    assert set(dashboard.LAUNCHERS) == {"orca", "tmux", "terminal", "headless"}
    page = _page()
    assert "data-copy" not in page and "manualRun" not in page, "the page still offers a command to copy"
    assert "o_terminal:" in page and "retry:" in page


@pytest.mark.parametrize(("env", "system", "tools", "expected"), [
    ({"TERM_PROGRAM": "Orca"}, "darwin", ("orca", "tmux", "open"), "orca"),
    ({"TERM_PROGRAM": "tmux", "TMUX": "/tmp/tmux-1/default,1,0", "TMUX_PANE": "%1"}, "darwin", ("orca", "tmux", "open"), "tmux"),
    ({"TERM_PROGRAM": "Apple_Terminal"}, "darwin", ("orca", "tmux", "open"), "terminal"),
    ({"TERM_PROGRAM": "vscode", "ORCA_TERMINAL_HANDLE": "term_x"}, "darwin", ("orca", "open"), "terminal"),
    ({"DISPLAY": ":0"}, "linux", ("tmux", "gnome-terminal"), "terminal"),
    ({}, "linux", ("tmux", "gnome-terminal"), "tmux"),
    ({}, "linux", ("gnome-terminal",), "headless"),
    ({}, "win32", ("powershell",), "terminal"),
])
def test_the_launcher_is_detected_from_where_the_dashboard_runs(dashboard: ModuleType, tmp_path: Path,
                                                                env, system, tools, expected) -> None:
    rows = dashboard.launchers_snapshot(tmp_path, which=_which(*tools), env=env, system=system)
    assert {row["id"] for row in rows} == set(dashboard.LAUNCHERS)
    preferred = [row for row in rows if row["preferred"]]
    assert [row["id"] for row in preferred] == [expected] and preferred[0]["available"], rows


def test_a_terminal_session_on_macos_is_a_script_terminal_runs(dashboard: ModuleType, tmp_path: Path) -> None:
    run = _recorder()
    info = dashboard.start_session(tmp_path, "terminal", _profile(dashboard, tmp_path), "planner", "claude-plan-w1",
                                   "Wave w1 · planner", "Read the request.", which=_which("claude", "open"),
                                   run=run, env={}, system="darwin")
    script = tmp_path / ".claude" / "lanes" / "sessions" / "claude-plan-w1.command"
    assert run.calls == [["open", "-a", "Terminal", str(script)]]
    assert info["session"] == "terminal:Terminal" and "commands" not in info, info
    text = script.read_text(encoding="utf-8")
    assert os.access(script, os.X_OK), "Terminal runs a .command only when it is executable"
    assert f"cd {shlex.quote(str(tmp_path))}" in text
    assert "CLAUDE_LANE_ID=claude-plan-w1" in text and "CLAUDE_LANE_ROLE=planner" in text
    assert "/usr/bin/claude" in text, "the window must run the agent the dashboard found, not whatever its PATH finds"
    assert "Read the request." not in text, "the prompt is read from its file, never inlined in a shell script"


@pytest.mark.skipif(os.name == "nt" or not shutil.which("sh"), reason="runs the POSIX script for real")
def test_the_terminal_script_hands_the_prompt_to_the_agent_verbatim(dashboard: ModuleType, tmp_path: Path) -> None:
    """What the window runs, run here with a stand-in agent: a prompt full of shell syntax arrives as one
    argument, unexpanded, in the project directory, with the lane identity the hooks read."""
    project = tmp_path / "it's a project"
    project.mkdir()
    agent = tmp_path / "bin" / "claude"
    agent.parent.mkdir()
    out = tmp_path / "received.txt"
    agent.write_text(f'#!/bin/sh\n{{ pwd; echo "$CLAUDE_LANE_ID"; echo "$#"; printf %s "$1"; }} > {shlex.quote(str(out))}\n',
                     encoding="utf-8")
    agent.chmod(0o755)
    prompt = "Read `the request` and $HOME; don't \"quote\" me.\nSecond line."
    dashboard.start_session(project, "terminal", _profile(dashboard, project), "planner", "claude-plan-w9", "t", prompt,
                            which=lambda name: str(agent) if name == "claude" else f"/usr/bin/{name}",
                            run=_recorder(), env={}, system="darwin")
    subprocess.run(["sh", str(project / ".claude" / "lanes" / "sessions" / "claude-plan-w9.command")],
                   check=True, timeout=30, env={"PATH": "/usr/bin:/bin"})
    cwd, lane, argc, received = out.read_text(encoding="utf-8").split("\n", 3)
    assert Path(cwd).resolve() == project.resolve() and lane == "claude-plan-w9" and argc == "1"
    assert received == prompt


def test_a_terminal_session_on_linux_opens_the_desktop_terminal(dashboard: ModuleType, tmp_path: Path) -> None:
    launched: list[tuple[list[str], dict]] = []

    def popen(argv, **options):
        launched.append((argv, options))
        return _Process()
    info = dashboard.start_session(tmp_path, "terminal", _profile(dashboard, tmp_path), "planner", "claude-plan-w2", "t",
                                   "go", which=_which("claude", "gnome-terminal", "xterm"), popen=popen,
                                   env={"DISPLAY": ":0"}, system="linux")
    script = tmp_path / ".claude" / "lanes" / "sessions" / "claude-plan-w2.command"
    assert launched[0][0] == ["/usr/bin/gnome-terminal", "--", str(script)], launched
    assert launched[0][1].get("start_new_session") is True
    assert info["session"].startswith("terminal:gnome-terminal")
    with pytest.raises(dashboard.LaunchError, match="no screen"):
        dashboard.start_session(tmp_path, "terminal", _profile(dashboard, tmp_path), "planner", "claude-plan-w3", "t",
                                "go", which=_which("claude", "gnome-terminal"), popen=popen, env={}, system="linux")


def test_a_terminal_session_on_windows_is_a_powershell_console(dashboard: ModuleType, tmp_path: Path) -> None:
    project = tmp_path / "it's here"
    project.mkdir()
    launched: list[tuple[list[str], dict]] = []

    def popen(argv, **options):
        launched.append((argv, options))
        return _Process()
    dashboard.start_session(project, "terminal", _profile(dashboard, project, "executor"), "executor", "claude-fix-it-1",
                            "Fix IT-1", "go", which=_which("claude", "powershell"), popen=popen, env={}, system="win32")
    argv, options = launched[0]
    assert argv[:3] == ["/usr/bin/powershell", "-NoExit", "-EncodedCommand"], argv
    assert options.get("creationflags") == 0x00000010, "CREATE_NEW_CONSOLE: the session gets its own window"
    command = base64.b64decode(argv[3]).decode("utf-16-le")
    quoted = str(project).replace("'", "''")
    assert f"Set-Location -LiteralPath '{quoted}'" in command, command
    assert "$env:CLAUDE_LANE_ID='claude-fix-it-1'" in command and "$env:CLAUDE_LANE_ROLE='executor'" in command
    assert "Get-Content -Raw -LiteralPath" in command and "& '/usr/bin/claude'" in command


def test_tmux_opens_the_window_in_the_session_the_dashboard_runs_in(dashboard: ModuleType, tmp_path: Path) -> None:
    run = _recorder(stdout="work\n")
    info = dashboard.start_session(tmp_path, "tmux", _profile(dashboard, tmp_path), "planner", "claude-plan-w4", "t", "go",
                                   which=_which("claude", "tmux"), run=run,
                                   env={"TMUX": "/tmp/tmux-1/default,1,0", "TMUX_PANE": "%3"}, system="linux")
    assert run.calls[-1][:5] == ["tmux", "new-window", "-d", "-t", "work:"], run.calls
    assert info["session"].startswith("tmux:work:") and "attach" not in info, "inside tmux there is nothing to attach"
    run = _recorder(fail=("has-session",))
    info = dashboard.start_session(tmp_path, "tmux", _profile(dashboard, tmp_path), "planner", "claude-plan-w5", "t", "go",
                                   which=_which("claude", "tmux"), run=run, env={}, system="linux")
    assert ["tmux", "new-session", "-d", "-s", "hpp-lanes", "-c", str(tmp_path)] in run.calls
    assert run.calls[-1][:5] == ["tmux", "new-window", "-d", "-t", "hpp-lanes:"]
    assert info["attach"] == "tmux attach -t hpp-lanes"


def test_a_launcher_that_is_not_available_is_refused_before_anything_is_written(dashboard: ModuleType,
                                                                                  tmp_path: Path) -> None:
    status, refused = dashboard.launch_lane(tmp_path, launcher="terminal", agent_id="claude", role="planner",
                                            lane_id="claude-plan-w6", title="t", prompt_for=lambda _event: "go",
                                            which=_which("claude", "gnome-terminal"), env={}, system="linux")
    assert status == 503 and "terminal" in refused["error"], refused
    assert not (tmp_path / ".claude" / "lanes" / "registry.json").exists(), "a refused launch registered a lane"


def test_a_session_that_did_not_start_is_retried_not_pasted(dashboard: ModuleType, tmp_path: Path) -> None:
    status, value = dashboard.launch_lane(tmp_path, launcher="terminal", agent_id="claude", role="planner",
                                          lane_id="claude-plan-w7", title="t", prompt_for=lambda _event: "go",
                                          which=_which("claude", "open"), run=_recorder(1, stderr="no Terminal here"),
                                          env={}, system="darwin")
    assert status == 202 and value.get("retry") is True and "no Terminal here" in value["warning"], value
    assert "commands" not in value.get("launch", {}), "a failed start fell back to a command to paste"
    registry = json.loads((tmp_path / ".claude" / "lanes" / "registry.json").read_text(encoding="utf-8"))
    assert "claude-plan-w7" in registry["lanes"], "the lane of a recorded hand-off must stay for the retry"

    started: list[list[str]] = []

    def popen(argv, **options):
        started.append(argv)
        return _Process()
    status, again = dashboard.relaunch_session(tmp_path, {"lane_id": "claude-plan-w7", "launcher": "headless"},
                                               which=_which("claude"), popen=popen, env={}, system="darwin")
    assert status == 200 and again["launch"]["session"] == "pid:4242", again
    assert started and started[0][-1] == "go", "the retry must start the same prompt"
    status, refused = dashboard.relaunch_session(tmp_path, {"lane_id": "claude-plan-w7", "launcher": "headless"},
                                                 which=_which("claude"), popen=popen, env={}, system="darwin")
    assert status == 409 and len(started) == 1, "a lane whose session started was started twice"
    status, refused = dashboard.relaunch_session(tmp_path, {"lane_id": "../../etc"}, which=_which("claude"))
    assert status == 400, refused


# --- the page and the design system -------------------------------------------------------------

def test_the_page_inlines_the_repository_stylesheet_verbatim() -> None:
    page = _page()
    style = page.split("<style>", 1)[1].split("</style>", 1)[0]
    lines = [line for line in STYLESHEET.read_text(encoding="utf-8").splitlines() if line.strip()]
    position = 0
    for line in lines:
        found = style.find(line, position)
        assert found >= 0, f"docs/hpp.css line missing or out of order in the page: {line[:90]}"
        position = found + len(line)


def test_the_page_uses_only_the_brand_palette() -> None:
    assert _brand_hex(), "BRAND.md stopped declaring hex values — nothing to compare against"
    assert not _outside_the_palette(_page()), f"colours outside BRAND.md: {_outside_the_palette(_page())}"


def test_CONTROLE_the_palette_check_sees_a_fifth_colour() -> None:
    assert _outside_the_palette("a{color:#AABBCC}") == {"#AABBCC"}
    assert _outside_the_palette("a{color:rgba(1,2,3,.5)}") == {"rgb(1, 2, 3)"}
    assert not _outside_the_palette("a{color:rgba(244,241,235,.5);background:#0F1113}")


def test_the_page_makes_no_external_request() -> None:
    page = _page()
    assert not re.search(r"""(?:src|href)\s*=\s*["']https?://""", page), "the page loads something from the network"
    assert not re.search(r"url\(\s*['\"]?https?://", page)
    assert "@import" not in page and "@font-face" not in page


def test_the_page_speaks_both_languages_with_the_same_keys() -> None:
    page = _page()
    english = page.split("  en: {", 1)[1].split('  "pt-BR": {', 1)[0]
    portuguese = page.split('  "pt-BR": {', 1)[1].split("\n  }\n};", 1)[0]
    # A key opens a line or follows a comma; a word before a colon INSIDE a string ("the project root:")
    # follows a space, and is text, not a key.
    keys = lambda block: set(re.findall(r"(?:^[ \t]*|,[ \t]*)([A-Za-z_]\w*):\"", block, re.MULTILINE))  # noqa: E731
    assert keys(english), "no English strings found — the parser no longer matches the page"
    assert keys(english) == keys(portuguese), (
        f"only in English: {sorted(keys(english) - keys(portuguese))}; "
        f"only in Portuguese: {sorted(keys(portuguese) - keys(english))}")
    assert '<html lang="en">' in page and "document.documentElement.lang = lang" in page
    assert ":focus-visible{outline" in page, "the focus ring was removed"


# --- many projects, and the worktrees of each ---------------------------------------------------
# Why: an operator with several projects open (in Orca, say) orchestrates them from one page. A project
# is a repository, and each of its worktrees keeps its own board in its own .claude/lanes/. The panel
# groups the worktrees under their project -- a worktree shown as a project of its own is how an
# operator took one for the other -- and every action names its worktree by an id from the server's
# own list, never by a path.

def _token(base: str) -> str:
    _status, page = _call(base + "/")
    return re.search(r'<meta name="hpp-session" content="([^"]+)">', page).group(1)


def _git_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    for args in (["init", "-q", "-b", "main"],
                 ["-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "--allow-empty", "-m", "one"]):
        subprocess.run(["git", *args], cwd=path, check=True, capture_output=True)
    return path


@pytest.fixture
def two_projects(tmp_path: Path):
    first, second = tmp_path / "shop" / "app", tmp_path / "blog" / "app"
    for project in (first, second):
        project.mkdir(parents=True)
    process = subprocess.Popen([sys.executable, "-X", "utf8", str(_kit() / "scripts" / "lane_dashboard.py"),
                                "--project-dir", str(first), "--project-dir", str(second), "--port", "0", "--no-orca"],
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8")
    try:
        match = re.search(r"http://127\.0\.0\.1:(\d+)/", process.stdout.readline())
        assert match, "the dashboard did not print its URL"
        yield f"http://127.0.0.1:{match.group(1)}", first, second
    finally:
        process.terminate()
        process.wait(timeout=10)
        process.stdout.close()


def test_every_project_is_served_with_its_worktrees(two_projects) -> None:
    base, _first, second = two_projects
    _status, body = _call(base + "/api/snapshot")
    projects = json.loads(body)["projects"]
    assert [(p["id"], p["name"], [w["id"] for w in p["worktrees"]]) for p in projects] == [
        ("app", "app", ["app"]), ("app-2", "app", ["app-2"])], projects
    board = projects[1]["worktrees"][0]
    assert board["path"] == str(second) and board["main"] is True and board["project"] == "app"
    assert all("columns" in w and "backlog" in w and "launchers" in w for p in projects for w in p["worktrees"])


def test_an_action_goes_to_the_worktree_it_names_and_only_there(two_projects) -> None:
    base, first, second = two_projects
    headers = {"Content-Type": "application/json", "X-HPP-Token": _token(base)}
    spec = {"id": "SPEC-1", "title": "one", "acceptance": ["it works"], "create_plan": True}
    status, body = _call(base + "/api/backlog/specs", spec, headers)
    assert status == 400 and "worktree" in json.loads(body)["error"], "with two worktrees, an action must name one"
    for wrong in ("nope", str(first), "../app"):
        status, body = _call(base + "/api/backlog/specs", {**spec, "worktree": wrong}, headers)
        assert status == 404, f"worktree={wrong!r} was accepted: {body}"
    status, body = _call(base + "/api/backlog/specs", {**spec, "worktree": "app-2"}, headers)
    assert status == 201, body
    assert (second / "docs" / "plans" / "execution" / "BACKLOG.json").is_file()
    assert not (first / "docs" / "plans" / "execution" / "BACKLOG.json").exists()


@pytest.mark.skipif(not shutil.which("git"), reason="groups worktrees by their git repository")
def test_the_worktrees_of_one_repository_are_one_project(dashboard: ModuleType, tmp_path: Path) -> None:
    repo = _git_repo(tmp_path / "shop")
    feature, plain = tmp_path / "shop-feature", tmp_path / "shop-plain"
    for branch, tree in (("feature-x", feature), ("plain", plain)):
        subprocess.run(["git", "worktree", "add", "-q", "-b", branch, str(tree)], cwd=repo, check=True, capture_output=True)
    for tree in (repo, feature):
        (tree / ".claude" / "lanes").mkdir(parents=True)
    for given in ([repo], [feature]):
        projects = dashboard.Projects(given, orca=False)
        boards = projects.list()
        assert [(b["id"], b["project_id"], b["project"], b["worktree"], b["main"]) for b in boards] == [
            ("shop", "shop", "shop", "main", True), ("shop-feature-x", "shop", "shop", "feature-x", False)], (given, boards)
        assert projects.resolve("shop-feature-x").resolve() == feature.resolve()
    assert not any(b["path"].resolve() == plain.resolve() for b in boards), "a worktree without lane-kit is not served"


def _orca(repos: list[dict], worktrees: list[dict]):
    """A fake `_run` answering `orca repo list --json` and `orca worktree list --json`."""
    calls: list[list[str]] = []

    def run(argv, cwd, timeout, env=None):
        calls.append(list(argv))
        result = {"repos": repos} if argv[1] == "repo" else {"worktrees": worktrees}
        return subprocess.CompletedProcess(argv, 0, json.dumps({"ok": True, "result": result}), "")
    run.calls = calls
    return run


def test_the_orca_worktrees_that_use_lane_kit_are_grouped_under_their_repo(dashboard: ModuleType, tmp_path: Path) -> None:
    shop, shop_wt, blog, gone, archived = (tmp_path / name for name in ("shop", "shop-feature", "blog", "gone", "old"))
    for project in (shop, shop_wt, archived):
        (project / ".claude" / "lanes").mkdir(parents=True)
    blog.mkdir()
    repos = [{"id": "r1", "displayName": "shop", "path": str(shop)}, {"id": "r2", "displayName": "blog", "path": str(blog)}]
    worktrees = [
        {"repoId": "r1", "path": str(shop), "displayName": "main", "isMainWorktree": True},
        {"repoId": "r1", "path": str(shop_wt), "displayName": "feature-x", "isMainWorktree": False},
        {"repoId": "r2", "path": str(blog), "displayName": "main", "isMainWorktree": True},
        {"repoId": "r1", "path": str(gone), "displayName": "gone", "isMainWorktree": False},
        {"repoId": "r1", "path": str(archived), "displayName": "old", "isMainWorktree": False, "isArchived": True},
    ]
    projects = dashboard.Projects([], orca=True, run=_orca(repos, worktrees), which=_which("orca"))
    assert [(b["id"], b["project_id"], b["project"], b["worktree"], b["main"], b["path"], b["source"])
            for b in projects.list()] == [("shop", "shop", "shop", "main", True, shop, "orca"),
                                          ("shop-feature-x", "shop", "shop", "feature-x", False, shop_wt, "orca")]
    assert projects.without_lanes() == ["blog"], "a project without lane-kit is named, so the operator knows why"
    assert projects.resolve("shop-feature-x") == shop_wt and projects.resolve(str(shop)) is None


def test_CONTROLE_without_orca_only_the_named_projects_are_served(dashboard: ModuleType, tmp_path: Path) -> None:
    run = _orca([], [])
    projects = dashboard.Projects([tmp_path], orca=True, run=run, which=_which())
    assert [p["path"] for p in projects.list()] == [tmp_path] and not run.calls, "orca is not on PATH: nothing to ask"
    projects = dashboard.Projects([tmp_path], orca=False, run=run, which=_which("orca"))
    assert not run.calls, "--no-orca asks Orca nothing"


def test_orca_opens_the_session_in_the_project_s_own_worktree(dashboard: ModuleType, tmp_path: Path) -> None:
    answer = json.dumps({"ok": True, "result": {"terminal": {"handle": "term_1"}}})
    run = _recorder(stdout=answer)
    info = dashboard.start_session(tmp_path, "orca", _profile(dashboard, tmp_path), "planner", "claude-plan-o1", "t", "go",
                                   which=_which("claude", "orca"), run=run, env={}, system="darwin")
    assert run.calls[0][3:5] == ["--worktree", f"path:{tmp_path}"] and info["session"] == "term_1", run.calls
    calls: list[list[str]] = []

    def not_a_worktree(argv, cwd, timeout, env=None):
        calls.append(list(argv))
        code = 1 if argv[4].startswith("path:") else 0
        return subprocess.CompletedProcess(argv, code, "" if code else answer, "no worktree at that path" if code else "")
    info = dashboard.start_session(tmp_path, "orca", _profile(dashboard, tmp_path), "planner", "claude-plan-o2", "t", "go",
                                   which=_which("claude", "orca"), run=not_a_worktree, env={}, system="darwin")
    assert [call[4] for call in calls] == [f"path:{tmp_path}", "active"] and info["session"] == "term_1", calls


def test_every_action_on_the_page_names_its_worktree() -> None:
    page = _page()
    posts = re.findall(r'post\("api/[^"]+",\s*\{[^}]*', page)
    assert posts, "no POST found in the page -- the check no longer matches it"
    assert all("worktree" in call for call in posts), [call for call in posts if "worktree" not in call]
    # The buttons drawn for an item; the masthead's "Start a wave" picks its worktree in the dialog.
    buttons = [b for b in re.findall(r'<button[^>]*data-action="(?:wave|review|fix|approve|brief|report)"[^>]*>', page)
               if "${" in b]
    assert buttons and all("data-worktree" in button for button in buttons), buttons
    assert 'id="spec-worktree"' in page and 'id="wave-worktree"' in page, "a new spec or a wave must name its worktree"
    assert 'id="worktrees"' in page and "data-worktree-filter" in page, "the worktrees of a project have their own view"


def test_a_board_in_the_old_format_is_one_warning_not_one_per_line(dashboard: ModuleType, tmp_path: Path) -> None:
    """One project with a board from an older lane-kit (Portuguese keys) must not bury the all-projects
    view under a warning per line: each kind of skipped line is one warning, with a count."""
    board = tmp_path / "board.jsonl"
    legacy = {"ts": "2026-08-12T07:17:35", "item_id": "MVP-0", "estado": "CLAIMED", "lane_id": "exec-a"}
    lines = [json.dumps(legacy)] * 300 + ["{not json", "{still not"] + [json.dumps({"item_id": "A", "state": "CLAIMED"})]
    board.write_text("\n".join(lines) + "\n", encoding="utf-8")
    events, warnings = dashboard.read_events(board)
    assert [event["item_id"] for event in events] == ["A"]
    assert len(warnings) == 2, warnings
    old, broken = warnings
    assert "300 lines" in old and "estado" in old and "older lane-kit" in old, old
    assert "2 lines" in broken and "not JSON" in broken and "301" in broken, broken


def test_CONTROLE_a_single_bad_line_still_says_which(dashboard: ModuleType, tmp_path: Path) -> None:
    board = tmp_path / "board.jsonl"
    board.write_text(json.dumps({"item_id": "A", "state": "CLAIMED"}) + "\n[1, 2]\n", encoding="utf-8")
    _events, warnings = dashboard.read_events(board)
    assert warnings == ["line 2 of board.jsonl is not a board event and was skipped"], warnings

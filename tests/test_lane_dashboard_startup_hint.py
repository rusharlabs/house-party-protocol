"""The real server prints usable command help while preserving legacy serve help."""
from __future__ import annotations

import os
from pathlib import Path
import queue
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.request

import pytest

from hpp._process import _kill_tree


def _script() -> Path:
    product = Path(__file__).resolve().parents[1]
    modules = product / "multi-session"
    if modules.is_dir():
        scripts = sorted(modules.glob("lane-kit-*/scripts/lane_dashboard.py"))
        assert len(scripts) == 1, "the emitted product must contain exactly one dashboard"
        return scripts[0]
    source = product.parents[2] / "staging/lane-kit/scripts/lane_dashboard.py"
    if source.is_file():
        return source
    pytest.skip("Lane Dashboard is available in the emitted modules or a source checkout")


def _env(project: Path) -> dict[str, str]:
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(project), "PYTHONDONTWRITEBYTECODE": "1"}
    for key in ("CLAUDE_LANE_ID", "CLAUDE_LANE_ROLE", "CLAUDE_LANE_MODEL", "LANE_KIT_CONFIG"):
        env.pop(key, None)
    return env


def test_real_server_startup_explains_subcommand_help_and_is_reaped(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    process = subprocess.Popen(
        [sys.executable, "-B", "-X", "utf8", str(_script()), "serve", "--project-dir", str(project),
         "--port", "0", "--no-orca"],
        cwd=project, env=_env(project), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", start_new_session=os.name != "nt",
    )
    lines = queue.Queue()

    def read_startup():
        try:
            for line in process.stdout:
                lines.put(line)
        finally:
            lines.put(None)

    reader = threading.Thread(target=read_startup, daemon=True)
    reader.start()
    output = []
    port = None
    try:
        deadline = time.monotonic() + 30
        while not any("Every action here" in line for line in output):
            try:
                line = lines.get(timeout=max(0.01, deadline - time.monotonic()))
            except queue.Empty:
                pytest.fail("dashboard startup timed out: " + "".join(output)[-1500:])
            assert line is not None, "dashboard stopped before printing its startup help: " + "".join(output)[-1500:]
            output.append(line)
            match = re.search(r"Lane Dashboard: http://127\.0\.0\.1:(\d+)/", line)
            if match:
                port = int(match.group(1))
        assert port is not None and port > 0
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f"http://127.0.0.1:{port}/", timeout=10) as response:
            assert response.status == 200
            assert response.read().startswith(b"<!doctype html>")
        startup = "".join(output)
        assert "lane_dashboard.py <command> --help" in startup
        assert "lane_dashboard.py --help" not in startup
    finally:
        # The same tree cleanup used by bounded commands covers server descendants too.
        _kill_tree(process)
        process.wait(timeout=10)
        reader.join(timeout=5)
        process.stdout.close()
        assert process.poll() is not None and not reader.is_alive(), "dashboard process or output reader leaked"
        if port is not None:
            with socket.socket() as client:
                client.settimeout(2)
                assert client.connect_ex(("127.0.0.1", port)) != 0, "dashboard listener leaked"


def test_legacy_bare_help_still_describes_serve(tmp_path):
    outputs = []
    for args in (["--help"], ["serve", "--help"]):
        result = subprocess.run([sys.executable, "-B", "-X", "utf8", str(_script()), *args],
                                cwd=tmp_path, env=_env(tmp_path), capture_output=True, text=True,
                                encoding="utf-8", timeout=30)
        assert result.returncode == 0, result.stderr
        outputs.append(result.stdout)
    assert outputs[0] == outputs[1]
    assert "usage: lane_dashboard.py serve" in outputs[0]

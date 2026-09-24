"""No file in the distribution may carry a machine path or a user account name.

A README that quotes a drive-letter user profile or a macOS home directory leaks the
maintainer's account and breaks every command it shows for everyone else. Measured before
this file existed: the tree was clean (0 hits) and nothing kept it that way. The scan below
is the same one the maintainers run by hand, made permanent; it walks the checkout it lives
in, so it protects the emitted repository and the source tree alike.

What counts as a personal path, in any text file: a drive letter followed by the Users folder
and an account name; a macOS home directory; a Linux home directory; a bare Windows profile
path with the drive already stripped. The four patterns are spelled out once, in
PERSONAL_PATH below, and nowhere else in this file on purpose: the gate scans this file too,
so a literal example here would be the gate's first finding.

Exceptions are structural, never by name: the `.git` directory, bytecode caches, packaging
leftovers, the harness's own `.hpp/` state, and binary files (zips, images).
"""
from __future__ import annotations

import re
from pathlib import Path

PRODUCT_ROOT = Path(__file__).resolve().parent.parent

PERSONAL_PATH = re.compile(
    r"[A-Za-z]:[\\/]Users[\\/][A-Za-z0-9_.-]+"      # drive letter, Users folder, account
    r"|(?<![A-Za-z0-9_])/Users/[A-Za-z0-9_.-]+"    # macOS home
    r"|(?<![A-Za-z0-9_])/home/[A-Za-z0-9_.-]+"     # Linux home
    r"|\\Users\\[A-Za-z0-9_.-]+"                   # Windows profile, drive already stripped
)                                                  # (one backslash; the doubled JSON form contains it)
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", "dist", "build", ".hpp", "node_modules"}
SKIP_SUFFIXES = {".zip", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pyc", ".whl", ".gz"}


def _text_files(root: Path) -> list[Path]:
    files = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        parts = set(path.relative_to(root).parts[:-1])
        if parts & SKIP_DIRS or any(part.endswith(".egg-info") for part in parts):
            continue
        if path.suffix.lower() in SKIP_SUFFIXES:
            continue
        files.append(path)
    return files


def scan(root: Path) -> list[str]:
    """Every `<relative path>:<line>: <match>` found under `root`. Empty list means clean."""
    hits = []
    for path in _text_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue  # binary that the suffix list did not name; a path in it cannot be read anyway
        for number, line in enumerate(text.splitlines(), 1):
            for match in PERSONAL_PATH.finditer(line):
                hits.append(f"{path.relative_to(root).as_posix()}:{number}: {match.group(0)}")
    return hits


# --------------------------------------------------------------------------- the gate itself

def test_distribution_has_no_personal_path():
    files = _text_files(PRODUCT_ROOT)
    assert len(files) > 50, f"the scan saw only {len(files)} files — the gate would be vacuous"
    hits = scan(PRODUCT_ROOT)
    assert hits == [], "personal paths in the distribution:\n" + "\n".join(hits)


# --------------------------------------------------------------------------- GATE 1e: it discriminates

def _planted(tmp_path: Path, name: str, line: str) -> Path:
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"first line\n{line}\nlast line\n", encoding="utf-8")
    return path


def test_scanner_reports_each_personal_path_form(tmp_path: Path):
    # Why: the strings are assembled at runtime so this file never contains a literal
    # personal path of its own — the real gate above scans this file too.
    forms = {
        "windows.md": "see " + "C:" + "\\Users\\" + "alice" + "\\repo\\notes.txt",
        "windows-forward.md": "see " + "D:" + "/Users/" + "bob" + "/repo",
        "macos.md": "cd " + "/Users/" + "carol" + "/code",
        "linux.md": "cd " + "/home/" + "dave" + "/code",
        "bare.md": "path " + "\\Users\\" + "erin" + "\\x",
    }
    for name, line in forms.items():
        _planted(tmp_path, name, line)
    hits = scan(tmp_path)
    reported = {hit.split(":", 1)[0] for hit in hits}
    assert reported == set(forms), f"missed: {set(forms) - reported}; hits={hits}"
    assert all(":2: " in hit for hit in hits), hits


def test_CONTROLE_scanner_is_silent_on_a_clean_tree(tmp_path: Path):
    # Control: prose that mentions users, homes and drive letters without a personal path.
    _planted(tmp_path, "clean.md", "Users of the CLI run `hpp init --target ../your-repo` from C:\\ or /opt.")
    _planted(tmp_path, "clean.py", 'HOME = "/home"  # the directory, not an account')
    assert scan(tmp_path) == []


def test_scanner_ignores_binary_and_cache_content(tmp_path: Path):
    planted = "C:" + "\\Users\\" + "frank"
    _planted(tmp_path, "__pycache__/x.md", planted)
    _planted(tmp_path, ".git/config", planted)
    (tmp_path / "blob.zip").write_bytes(planted.encode("utf-8") + b"\x00\xff")
    (tmp_path / "raw.bin").write_bytes(b"\xff\xfe" + planted.encode("utf-8"))  # not UTF-8: skipped
    assert scan(tmp_path) == []

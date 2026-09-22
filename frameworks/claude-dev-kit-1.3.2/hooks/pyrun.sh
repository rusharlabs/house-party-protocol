#!/usr/bin/env bash
# pyrun.sh - resolve the PROJECT's Python interpreter and run the hook with it.
#
# Why: hooks.json used to call a bare `python`. macOS and most Linux ship only `python3`;
# Windows ships only `python` (plus a `python3` that may be the Microsoft Store stub, which
# opens the Store and exits with an error). A hook that cannot find the interpreter fails in
# EVERY tool, silently - and the whole kit becomes decoration.
#
# Order: the project .venv (CLAUDE_PROJECT_DIR, else the cwd - Claude Code runs hooks at the
# project root) -> the right binary for this OS -> the other one. Never `py`.
#
# Two caveats:
#   . the project .venv runs with the trust you already give the project you opened - the
#     same thing any venv-aware tool does. To turn it off: HPP_PYRUN_NO_VENV=1.
#   . on Windows without Python, `command -v python` FINDS the WindowsApps alias (the Store
#     stub, which points at Microsoft.DesktopAppInstaller); it is skipped by the symlink
#     TARGET - Python installed from the Store/PythonManager also lives in WindowsApps and
#     is kept.
root="${CLAUDE_PROJECT_DIR:-$PWD}"
if [ -z "${HPP_PYRUN_NO_VENV:-}" ]; then
  for c in "$root/.venv/bin/python" "$root/.venv/Scripts/python.exe"; do
    [ -x "$c" ] && exec "$c" "$@"
  done
fi
case "$(uname -s 2>/dev/null)" in
  MINGW*|MSYS*|CYGWIN*) order="python python3" ;;
  *)                    order="python3 python" ;;
esac
for c in $order; do
  bin="$(command -v "$c" 2>/dev/null || true)"
  [ -n "$bin" ] || continue
  # the WindowsApps alias is a symlink: the real Python points at PythonSoftwareFoundation.*;
  # the Store stub points at Microsoft.DesktopAppInstaller_* (measured 2026-09-20). The target decides.
  case "$(readlink -f "$bin" 2>/dev/null || echo "$bin")" in *DesktopAppInstaller*) continue ;; esac
  exec "$bin" "$@"
done
echo "pyrun.sh: no Python interpreter found (python3/python) - hook did not run" >&2
exit 0   # WARN-only: a hook without Python must never take the tool down (RULE #29)

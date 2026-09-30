#!/usr/bin/env python3
"""
ralph_gate - DEPRECATED alias of hooks/loop_gate.py. Removed in 3.0.

The loop gate now carries a neutral name: `hooks/loop_gate.py`, `/loop-gate`,
`/cancel-loop-gate`, `LOOP-GATE.md`, `evals/loop-gate-T1-T4.sh` and the state file
`.claude/loop-gate.local.json`. This entry point stays so that a hooks.json, a settings block
or a command written against the old path keeps working: it runs `hooks/loop_gate.py` in this
same process, with the same argv and the same stdin, and answers with the same stdout and the
same exit code. It prints nothing of its own to stdout (a hook speaks JSON there); the
deprecation notice goes to stderr.

Point your wiring at `hooks/loop_gate.py` before 3.0.
"""
import runpy
import sys
from pathlib import Path

TARGET = Path(__file__).resolve().with_name("loop_gate.py")

if __name__ == "__main__":
    print("ralph_gate.py is a deprecated alias of hooks/loop_gate.py (removed in 3.0): "
          "point your wiring at hooks/loop_gate.py", file=sys.stderr)
    runpy.run_path(str(TARGET), run_name="__main__")

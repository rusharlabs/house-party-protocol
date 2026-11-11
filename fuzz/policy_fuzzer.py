"""Coverage-guided Atheris entry point for the policy contract."""
from __future__ import annotations

import sys
from pathlib import Path

import atheris

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

with atheris.instrument_imports():
    from policy_properties import check_input


if __name__ == "__main__":
    atheris.Setup(sys.argv, check_input)
    atheris.Fuzz()


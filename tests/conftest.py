"""Shared configuration for the HPP test suite.

Makes sure `import hpp` resolves to the package in this product root, whatever
directory `pytest` / `python -m pytest` was invoked from. `python -m pytest`
already puts the cwd on sys.path[0] because of the `-m` itself, but a `pytest`
invoked without `-m` (or from another cwd) has no such guarantee -- this file makes
the suite robust in both cases, without requiring `pip install -e .` first.
"""
from __future__ import annotations

import sys
from pathlib import Path

PRODUCT_ROOT = Path(__file__).resolve().parent.parent
if str(PRODUCT_ROOT) not in sys.path:
    sys.path.insert(0, str(PRODUCT_ROOT))

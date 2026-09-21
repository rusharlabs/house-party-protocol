"""Configuracao compartilhada da suite de testes do HPP.

Garante que `import hpp` resolva para o pacote deste product-root, seja qual for
o diretorio de onde `pytest`/`python -m pytest` foi invocado. `python -m pytest`
ja poe o cwd em sys.path[0] por conta do proprio `-m`, mas um `pytest` invocado
sem `-m` (ou de outro cwd) nao tem essa garantia -- este arquivo torna a suite
robusta aos dois casos, sem exigir `pip install -e .` antes de rodar.
"""
from __future__ import annotations

import sys
from pathlib import Path

PRODUCT_ROOT = Path(__file__).resolve().parent.parent
if str(PRODUCT_ROOT) not in sys.path:
    sys.path.insert(0, str(PRODUCT_ROOT))

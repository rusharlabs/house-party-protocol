#!/bin/bash
set -euo pipefail

export PYTHONPATH="$SRC/hpp"
compile_python_fuzzer "$SRC/hpp/fuzz/policy_fuzzer.py"

# Pure Python uses Atheris' bundled libFuzzer, without preloading a native
# sanitizer library into the PyInstaller executable.
cat > "$OUT/policy_fuzzer" <<'WRAPPER'
#!/bin/sh
# LLVMFuzzerTestOneInput
set -eu
directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
chmod +x "$directory/policy_fuzzer.pkg"
exec "$directory/policy_fuzzer.pkg" "$@"
WRAPPER
chmod +x "$OUT/policy_fuzzer"

cp "$SRC/hpp/fuzz/policy_fuzzer.dict" "$OUT/policy_fuzzer.dict"
cp "$SRC/hpp/fuzz/policy_fuzzer.options" "$OUT/policy_fuzzer.options"
python3 - <<'PYTHON'
import os
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

corpus = Path(os.environ["SRC"]) / "hpp" / "fuzz" / "corpus" / "policy"
with ZipFile(Path(os.environ["OUT"]) / "policy_fuzzer_seed_corpus.zip", "w", ZIP_DEFLATED) as archive:
    for path in sorted(corpus.iterdir()):
        if path.is_file():
            archive.write(path, path.name)
PYTHON


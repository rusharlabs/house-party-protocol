"""Replay policy seeds and deterministic byte mutations without the fuzzing engine."""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from policy_properties import check_input  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mutations", type=int, default=2000)
    args = parser.parse_args()
    if not 0 <= args.mutations <= 10000:
        parser.error("--mutations must be between 0 and 10000")
    seeds = [path.read_bytes() for path in sorted((Path(__file__).parent / "corpus" / "policy").iterdir()) if path.is_file()]
    if not seeds:
        raise ValueError("the policy corpus must contain at least one seed")
    for seed in seeds:
        check_input(seed)
    rng = random.Random(0)
    for number in range(args.mutations):
        data = bytearray(seeds[number % len(seeds)])
        position = rng.randrange(len(data) + 1)
        if number % 3 == 0 and position < len(data):
            data[position] ^= 1 << rng.randrange(8)
        elif number % 3 == 1:
            data[position:position] = bytes([rng.randrange(256)])
        else:
            data = data[:position]
        check_input(bytes(data))
    print(f"policy corpus: {len(seeds)} seeds, {args.mutations} deterministic mutations passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())


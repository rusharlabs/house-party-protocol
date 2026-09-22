[English](PROOF.md) · [Português](PROOF.pt-BR.md)

# Proof matrix

A public claim only enters here with a reproduction.

| Claim | Command | Criterion |
|---|---|---|
| consistent manifest | `python -m hpp doctor` | exit 0, ten modules, zero errors |
| policy blocks | `python -m hpp policy check --mode enforce --command "rm -rf src"` | exit 2 and `BLOCK` |
| deterministic graphs | `python -m hpp graph --view operational --format json` twice | identical hashes |
| standalone eval | `python -m hpp eval run examples/reliable-coding/benchmark-suite.json -k 3 --gate both` | ten executable controls, no pre-approved replay |
| stable benchmark | `python -m hpp benchmark -k 3 --json` | pass^k 1.00 on the critical cases |
| intact artifacts | `python installers/kit-forge-1.4.1/kit_doctor.py marketplace .` | status ok |

Dated results belong to the release log, not to this living document.

## Attestation provenance

The binding between approval, spec hash and snapshot was researched in the repository
`chaseai-yt/claudex-loop`, MIT licence, commit
`8cf5e2c1771c5151d90c12642391d0ba8fa71b0e`. HPP did not incorporate the runner, prompts,
names or structure of that project. `hpp.attest` is a clean-room implementation,
provider-neutral and integrated with HPP's local contract.

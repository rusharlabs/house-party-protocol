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
| decision ruler | `python -m hpp decide eval examples/typed-decisions/gotcha-family-suite.json --decider-command '["python", "examples/typed-decisions/baseline_decider.py"]'` | zero instrument failures; coverage and selective accuracy reported separately (the shipped suite proves the ruler, not a decider) |
| evidence bundle | `python -m hpp evidence run --id smoke-page --artifact out/report.html --artifact out/smoke.log -- python examples/evidence/smoke_page.py`, then `python -m hpp evidence verify <record>` | exit 0 `passed`, then exit 0 `valid` |
| evidence bundle, control | the same run with `--break` after the script; then a passed record whose `out/report.html` was changed afterwards | exit 1 `failed`, and `verify` exit 1 `not-evidence`; the changed artifact makes `verify` exit 2 `blocked` |
| retrieval ruler | `python -m hpp retrieval eval examples/retrieval/suite.json --retriever-command '["python", "examples/retrieval/keyword_retriever.py"]'` | seven cases measured, zero instrument failures, the same metrics as the replay without `--retriever-command`; exit 1 on the default gate (the shipped suite proves the ruler, not a retriever) |
| retrieval ruler, control | `python -m hpp retrieval eval examples/retrieval/suite.json --retriever-command '["python", "-c", "import sys; sys.exit(3)"]'` | exit 1, seven instrument failures, null metrics, never 0% |
| citation check | `python -m hpp cite check --text examples/citations/answer.md --context examples/citations/context.json` | exit 0, verdict `ok` |
| citation check, control | the same on a copy of `answer.md` with `[ID:glossary]` changed to `[ID:glossary-v2]` | exit 2, `UNKNOWN_ID` |
| criterion sensitivity | `python -m hpp evidence mutate --id weak --generate examples/criterion-sensitivity/discount.py -- python examples/criterion-sensitivity/check_weak.py` | exit 1, `blind-spots`, three survivors named by file and line |
| criterion sensitivity, control | the same with `check_strong.py` | exit 0, `sensitive`, score 1.0 |
| House Session | `python -m hpp decide eval examples/typed-decisions/gotcha-family-suite.json --decider-command '["python", "examples/house-session/panel_decider.py"]'` | 15 recorded sessions sealed and verified, 12 decided, 3 abstained, 0 instrument failures, exit 0 (synthetic sessions: they prove the contract, not that a panel is better) |
| House Session, control | `python -m hpp deliberate verify` on a copy of a sealed record with the verdict edited | exit 2, `record_sha256 does not match` |
| best-of-N selection | `python multi-session/lane-kit-1.4.1/scripts/lane_board.py --self-test` | exit 0; the competitions block passes every check |
| best-of-N selection, control | `lane_board.py select` on a declared competition, by a reviewer of the same model family as one builder | exit 1, `SAME model family`; no winner recorded |
| intact artifacts | `python installers/kit-forge-1.4.2/kit_doctor.py marketplace .` | status ok |

Dated results belong to the release log, not to this living document.

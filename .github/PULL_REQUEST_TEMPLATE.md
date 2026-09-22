## What and why

<!-- One paragraph: the change, and the failure or request it answers. Link the issue if there is one. -->

## Proof

<!-- Paste the command and its real output. For a bug fix, show the test that FAILS before the
     fix and PASSES after it (CONTRIBUTING.md, "the test that fails before and passes after"). -->

```text
$ python -m pytest tests -q
```

## Checklist

- [ ] `python -m pytest tests -q`, `python -m hpp doctor` and `python -m hpp benchmark -k 3` pass locally.
- [ ] Bug fix: the new test fails on the previous code and passes on this branch; the output is pasted above.
- [ ] `CHANGELOG.md` **and** `CHANGELOG.pt-BR.md` have a bullet under `## [Unreleased]`, same meaning on both sides.
- [ ] Human-facing docs changed in both languages (`X.md` and `X.pt-BR.md`), same headings, identical code blocks.
- [ ] No hand edits to `CHECKSUMS.txt`, `*.zip`, `marketplace.json` or module directories; module changes come through the forge (CONTRIBUTING.md).
- [ ] No version bump in `pyproject.toml`, `hpp/__init__.py`, `hpp.manifest.json` or `CITATION.cff` unless this PR is the release.
- [ ] No credential, token, machine path or personal data in the diff (`python -m pytest tests/test_no_personal_paths.py -q`).
- [ ] Still stdlib-only: no new third-party import in `hpp/` (`python -m pytest tests/test_stdlib_only.py -q`).

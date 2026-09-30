[English](GOVERNANCE.md) · [Português](GOVERNANCE.pt-BR.md)

# Governance

House Party Protocol has one maintainer. This page says who decides, where each decision is
recorded, how a disagreement ends, how a release is made, and what happens if the maintainer is
gone. It describes how the project works today; where a part of the plan is not in place yet, it
says so.

## Who decides

The project follows a single-maintainer model. The maintainer is Max Parisi, who acts on GitHub
through the maintainer account that `.github/CODEOWNERS` names for every path of the repository.

The maintainer decides what is merged, what is released and when, what the roadmap says and what
the project refuses. Anyone can propose any of it. A decision is taken in public, in the thread
where it was asked, with its reason next to it.

## Roles

| responsibility | role | held by |
|---|---|---|
| triage of issues and discussions | maintainer | Max Parisi |
| review and merge of pull requests | maintainer | Max Parisi |
| releases | maintainer | Max Parisi |
| security response ([SECURITY.md](SECURITY.md)) | maintainer | Max Parisi |
| code of conduct enforcement ([CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)) | maintainer | Max Parisi |
| issues, discussions, pull requests and reviews under [CONTRIBUTING.md](CONTRIBUTING.md) | contributor | anyone |

There is no second maintainer today. See [Continuity](#continuity).

## Where decisions are recorded

- **`CHANGELOG.md` and `CHANGELOG.pt-BR.md`** record every change that ships, per version. The
  release workflow refuses a tag whose version has no non-empty section in both files.
- **The release notes.** The body of each GitHub Release is that version's CHANGELOG section,
  English first and Portuguese below it; the workflow writes it, nobody retypes it.
- **Discussions, category Announcements.** Each release opens its own discussion there, and the
  roadmap is discussed there. The maintainer posts; anyone comments.
- **The issue or pull request itself** carries the reasoning for a single change.
- **[MANIFESTO.md](MANIFESTO.md), "What the project refuses to do"**, holds the standing refusals.
  Changing one of them is a change to that file, recorded in the CHANGELOG like any other.

## How a disagreement is resolved

1. Say it where the question lives: the issue, the pull request, or the Ideas category of
   Discussions when it is not tied to a change. Name the failure, the change you propose and the
   evidence — the command you ran and its output.
2. The maintainer answers in the same thread with a decision and its reason. Evidence outweighs
   preference: a reproduction counts for more than an argument, on either side.
3. New evidence reopens a decision; repeating the argument does not. A poll in the Polls category
   informs a decision; it does not make it.
4. The code is MIT-licensed. Whoever still disagrees may fork it; the fork is a different
   project, and a copy that keeps the name is not this one ([SECURITY.md](SECURITY.md), "Official
   surfaces").

A conduct matter follows the enforcement section of [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md), and
a vulnerability goes through the private channels of [SECURITY.md](SECURITY.md) — neither is
argued in a public thread.

## How a release is made

A release is a tag `vX.Y.Z`. Pushing it runs `.github/workflows/release.yml`, which:

1. refuses to go on unless the four version sources (`pyproject.toml`, `hpp/__init__.py`,
   `hpp.manifest.json`, `CITATION.cff`) equal the tag and both CHANGELOG files carry a non-empty
   section for it;
2. builds the wheel and the sdist once, and writes `SHA256SUMS`;
3. installs that wheel, with no checkout, on Ubuntu, macOS and Windows, and runs `hpp --version`,
   `hpp doctor`, `hpp benchmark -k 3` and `hpp init` from an empty directory;
4. signs build provenance for the wheel and the sdist in a job of its own;
5. creates the GitHub Release with the wheel, the sdist, `SHA256SUMS` and the provenance bundle,
   the CHANGELOG section as notes, and opens the release's discussion in Announcements;
6. publishes to PyPI through trusted publishing, with no stored token, when the repository
   variable `PYPI_PUBLISH` is `true`.

A manual run exists only to recover a tag whose push did not start the workflow; it demands an
existing tag, and that tag passes the same steps. Anyone can check where a file came from:

```bash
gh attestation verify <file> --repo rusharlabs/house-party-protocol
```

Which versions receive fixes is stated in [SECURITY.md](SECURITY.md), "Supported versions".

## Continuity

This section is a plan, not a report. It says what the project needs so that someone other than
the maintainer can keep it running, and which parts are not in place yet.

What a successor needs:

- the **owner** role on the GitHub organization `rusharlabs` — repository settings, branch
  protection, Discussions, the `pypi` environment, the `PYPI_PUBLISH` variable and private
  vulnerability reporting live there;
- the **owner** role on the PyPI project `house-party-protocol`, whose only publisher is this
  repository's release workflow;
- control of the domain of the site that [SECURITY.md](SECURITY.md) and
  [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) give as the contact channel for security and conduct
  reports.

The recovery codes of the accounts that hold these three are to be kept in a safe the second
person can open.

| part of the plan | state |
|---|---|
| what a successor needs, listed above | written here |
| recovery codes kept in a safe | plan — this page does not attest it |
| a second person named, with the access above | **pending — nobody is named yet** |
| triage, accept changes and release within one week of the maintainer becoming unavailable | the commitment once the second person is named; not in force before that |

Until a second person is named, the project depends on one person. The licence already guarantees
the rest: anyone may fork the code and continue it under another name.

## Changing this document

This page changes through a pull request like any other file, and the change is recorded in the
CHANGELOG.

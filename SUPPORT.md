[English](SUPPORT.md) · [Português](SUPPORT.pt-BR.md)

# Support

## Questions and design conversations

For usage questions or design discussions, use [GitHub Discussions](https://github.com/rusharlabs/house-party-protocol/discussions). Questions go to the [Q&A](https://github.com/rusharlabs/house-party-protocol/discussions/categories/q-a) category, in English or Portuguese; an early idea or a design question that is not ready for the idea form below goes to [Ideas](https://github.com/rusharlabs/house-party-protocol/discussions/categories/ideas). Paste the command you ran and its output, without tokens or personal paths.

## Report a documentation mismatch

If a command behaves differently from the documentation, open a [problem report](https://github.com/rusharlabs/house-party-protocol/issues/new?template=problem.yml). Include the exact command and its output. Remove tokens and other secrets before posting.

## Give feedback

If something was confusing, slower than it should be, or made you stop using a piece of the harness, open the [feedback form](https://github.com/rusharlabs/house-party-protocol/issues/new?template=feedback.yml). It needs no reproduction: a sentence is enough, and leaving a module out or turning a hook off counts. Run the command below and paste the report it prints into the form:

```bash
hpp doctor --report
```

It prints the link to the form with the title filled in and, below it, the report: versions, Python, platform and the doctor's counts, with no path from your machine. The command makes no network call; nothing is sent until you open the link yourself. From a clone without the package installed, run `python -m hpp doctor --report`.

## Propose an idea

For a capability, module or contract the harness should have, open the [idea form](https://github.com/rusharlabs/house-party-protocol/issues/new?template=idea.yml). It asks for the failure the idea removes, what the harness would do differently, and the command or test that would prove it, with the negative case that would show it refusing. An idea also has to fit the [honest limits](README.md#honest-limits), or say which one it would change and why.

## Report a vulnerability

Do not open a public issue for a vulnerability. Use [GitHub private vulnerability reporting](https://github.com/rusharlabs/house-party-protocol/security/advisories/new) or the contact channel on the [project site](https://rusharlabs.com), as described in [SECURITY.md](SECURITY.md).

## Manual and catalogue

Find the [manual](https://rusharlabs.github.io/house-party-protocol/MANUAL.html) and [catalogue](https://rusharlabs.github.io/house-party-protocol/CATALOG.html) on the project site.

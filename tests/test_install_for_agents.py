"""The agent-facing install guide cannot drift from the README, the CLI or the version.

Why this file exists: `INSTALL_FOR_AGENTS.md` is the fourth place in this repository that tells
someone how to install the harness -- after the README, `hpp init` and `hpp.manifest.json`. A
fourth copy with nothing tying it down is the copy that rots, and a rotted install guide is
worse than none: an agent follows it, installs a version that is not the one shipped, and
reports success. The suggestion to add the guide came with this condition attached.

The install command is compared as an exact string, not parsed. The point is not that both
files mention `pip`; it is that a person who fixes the README and forgets this file gets a red
test in the same run.
"""
from __future__ import annotations

import re
from pathlib import Path

from hpp import __version__

PRODUCT_ROOT = Path(__file__).resolve().parent.parent
GUIDE_EN = PRODUCT_ROOT / "INSTALL_FOR_AGENTS.md"
GUIDE_PT = PRODUCT_ROOT / "INSTALL_FOR_AGENTS.pt-BR.md"
README_EN = PRODUCT_ROOT / "README.md"
README_PT = PRODUCT_ROOT / "README.pt-BR.md"
AGENTS = PRODUCT_ROOT / "AGENTS.md"

# Why a full-line anchor: the bump script rewrites the pinned tag as a whole line. A pattern
# that matched mid-line would also match prose about an older release and pass on a stale file.
INSTALL_LINE = re.compile(
    r"^pip install git\+https://github\.com/rusharlabs/house-party-protocol@v(?P<version>[0-9]+\.[0-9]+\.[0-9]+)$",
    re.M,
)
EXIT_CODES = "`0` ok · `1` warn/manual · `2` block · `3` error."


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _install_commands(text: str) -> list[str]:
    return INSTALL_LINE.findall(text)


def test_the_four_files_exist() -> None:
    for p in (GUIDE_EN, GUIDE_PT, README_EN, README_PT):
        assert p.is_file(), f"{p.name} does not exist"


def test_the_version_pinned_in_the_guide_is_the_one_that_ships() -> None:
    for guide in (GUIDE_EN, GUIDE_PT):
        found = _install_commands(_read(guide))
        assert found, f"{guide.name}: no install command in the expected format"
        assert set(found) == {__version__}, (
            f"{guide.name} pins {sorted(set(found))}, the package is {__version__}"
        )


def test_the_guide_and_the_readme_pin_the_SAME_version() -> None:
    from_readme = set(_install_commands(_read(README_EN))) | set(
        _install_commands(_read(README_PT))
    )
    from_guide = set(_install_commands(_read(GUIDE_EN))) | set(
        _install_commands(_read(GUIDE_PT))
    )
    assert from_readme, "the README no longer carries the install command"
    assert from_readme == from_guide, f"README pins {sorted(from_readme)}, guide pins {sorted(from_guide)}"


def test_the_exit_codes_match_AGENTS_md() -> None:
    # Why: an agent decides whether to stop or carry on by the exit code. Two diverging tables in
    # the same tree make it stop in the wrong case, and neither of them looks wrong on its own.
    assert EXIT_CODES in _read(AGENTS), "AGENTS.md changed the exit code table"
    for guide in (GUIDE_EN, GUIDE_PT):
        assert EXIT_CODES in _read(guide), f"{guide.name} diverged from the AGENTS.md table"


def test_the_guide_requires_the_plan_before_apply() -> None:
    # Why: this is the only step of the guide that protects the person. If it drops out in a
    # rewrite, the guide starts teaching an installer that writes before anyone reads -- the
    # failure the product itself exists to prevent.
    assert "DO NOT SKIP" in _read(GUIDE_EN)
    assert "NÃO PULE" in _read(GUIDE_PT)
    for guide in (GUIDE_EN, GUIDE_PT):
        text = _read(guide)
        without_apply = text.index("hpp init --target")
        with_apply = text.index("--apply", without_apply)
        assert without_apply < with_apply, f"{guide.name}: --apply appears before the plan"


def test_the_README_points_to_the_guide() -> None:
    # Why: no agent reads this file by convention -- the name is not a standard anywhere. It is
    # only found if the README announces it, so the pointer IS the feature.
    for readme in (README_EN, README_PT):
        assert "INSTALL_FOR_AGENTS" in _read(readme), f"{readme.name} does not point to the guide"


def test_CONTROLE_the_detector_rejects_a_divergent_version() -> None:
    # Why: without this control, the tests above would pass with a broken regex -- a pattern that
    # matches nothing returns an empty list, and "empty == empty" is true.
    fake = "pip install git+https://github.com/rusharlabs/house-party-protocol@v0.0.1"
    assert _install_commands(fake) == ["0.0.1"], "the detector does not read the version"
    assert _install_commands("pip install house-party-protocol") == [], (
        "the detector matches a line that is not the pinned form"
    )

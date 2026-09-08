"""CI guard: assert the adcp SDK pin targets the expected AdCP spec version."""

import re
import tomllib
from pathlib import Path

import adcp

from scripts.audit.storyboard_spec import pinned_version

EXPECTED_SPEC_VERSION = "3.1.1"

_REPO = Path(__file__).resolve().parents[2]

# CLAUDE.md's "AdCP Spec Version" section states both the spec version and the SDK
# pin in one sentence. Capture both so a bump that misses this file is caught.
_CLAUDE_MD_TARGETS = re.compile(
    r"This project targets AdCP spec \*\*(?P<spec>[^*]+)\*\* "
    r"via the `adcp==(?P<sdk>[^`]+)` Python SDK\."
)


def test_adcp_spec_version_matches_pin() -> None:
    """Verify SDK pin targets the spec version this codebase expects.

    Failure here means the adcp Python SDK pin in pyproject.toml has shifted
    to a version that targets a different AdCP spec version. Either revert
    the pin or follow docs/adcp-spec-version.md to update
    EXPECTED_SPEC_VERSION and the related references it lists.
    """
    actual = adcp.get_adcp_spec_version()
    assert actual == EXPECTED_SPEC_VERSION, (
        f"adcp SDK targets spec {actual}, but this codebase expects "
        f"{EXPECTED_SPEC_VERSION}. See docs/adcp-spec-version.md for "
        f"reconciliation steps."
    )


def _pyproject_adcp_pin() -> str:
    """Return the exact `adcp==` version pinned in pyproject.toml."""
    with (_REPO / "pyproject.toml").open("rb") as fh:
        deps = tomllib.load(fh)["project"]["dependencies"]
    pins = [d.split("==", 1)[1].strip() for d in deps if d.replace(" ", "").startswith("adcp==")]
    assert len(pins) == 1, f"expected exactly one exact adcp pin in pyproject.toml, found {pins}"
    return pins[0]


# Prose calling a version the CURRENT/pinned one, in the shapes no primitive
# reads. The headline claim ("targets **AdCP spec version X**") is deliberately
# NOT here: storyboard_spec.pinned_version() already owns that read out of this
# same doc, and a local copy of its regex is a second implementation of one
# fact. Deliberately narrow otherwise: the version-history table row and
# past-tense prose about an older version ("Then (3.1.0-beta.3): ...") stay
# legal, because naming history IS that prose's job.
_PIN_CLAIM = re.compile(r"(\*\*pin\*\*\s*\([^)]+\))|(\*\*Now \(pinned [^)]+\):?\*\*)")


def test_claude_md_states_the_pinned_versions() -> None:
    """Verify CLAUDE.md's stated spec version and SDK pin match reality.

    CLAUDE.md is what every session reads first, so a stale version line there
    silently misdirects work for the whole epic that follows it. This pins the
    prose to the two authorities it paraphrases: EXPECTED_SPEC_VERSION above
    (itself tied to the installed SDK by the test above) and the `adcp==` pin
    in pyproject.toml. Bumping the SDK means updating CLAUDE.md in the same
    change -- see docs/adcp-spec-version.md.
    """
    claude_md = (_REPO / "CLAUDE.md").read_text(encoding="utf-8")
    match = _CLAUDE_MD_TARGETS.search(claude_md)
    assert match is not None, (
        "CLAUDE.md no longer contains the 'This project targets AdCP spec "
        "**<spec>** via the `adcp==<sdk>` Python SDK.' sentence this guard "
        "pins. Restore the sentence or update _CLAUDE_MD_TARGETS."
    )

    assert match.group("spec") == EXPECTED_SPEC_VERSION, (
        f"CLAUDE.md states AdCP spec {match.group('spec')}, but this codebase "
        f"targets {EXPECTED_SPEC_VERSION}. Update CLAUDE.md."
    )

    expected_sdk = _pyproject_adcp_pin()
    assert match.group("sdk") == expected_sdk, (
        f"CLAUDE.md states adcp=={match.group('sdk')}, but pyproject.toml pins adcp=={expected_sdk}. Update CLAUDE.md."
    )


def test_spec_version_doc_presents_only_the_pinned_version_as_current() -> None:
    """docs/adcp-spec-version.md must not present a stale version as the CURRENT pin.

    Sibling of the CLAUDE.md guard above, and for the same failure mode: this is
    the document CLAUDE.md's own pointer sends a reader to, so a stale pin
    number here misdirects exactly the work that went looking for the authority.
    It shipped wrong once — the "Behavior target vs SDK pin" section called the
    pin 3.1.0-beta.3 long after the 3.1.1 bump, and justified a behavior
    divergence with two SDK claims that had stopped being true.

    Only CURRENT-pin claims are graded. The version-history table names older
    versions as history, which is its job, and prose that says a past version
    did something ("Then (3.1.0-beta.3): ...") is likewise legitimate. What is
    banned is bolding another version as **the** pin.
    """
    # The headline claim ("targets **AdCP spec version X**") is graded by the
    # primitive that owns that read: pinned_version() parses this same doc and
    # raises when the sentence disagrees with the installed SDK.
    documented = pinned_version(_REPO)
    assert documented == EXPECTED_SPEC_VERSION, (
        f"docs/adcp-spec-version.md's headline claim tracks AdCP {documented}, but "
        f"this codebase targets {EXPECTED_SPEC_VERSION}. Update the prose in the "
        f"same change as the pin bump."
    )

    doc = (_REPO / "docs" / "adcp-spec-version.md").read_text(encoding="utf-8")

    # Check the CLAIM, not the whole line: a line may legitimately mention the
    # pinned version elsewhere (a compliance path like dist/compliance/3.1.1/...)
    # while its claim names a stale one, and a line-wide search calls that clean.
    stale_pin_claims = [
        match.group(0) for match in _PIN_CLAIM.finditer(doc) if EXPECTED_SPEC_VERSION not in match.group(0)
    ]
    assert not stale_pin_claims, (
        "docs/adcp-spec-version.md presents a version other than the pinned "
        f"{EXPECTED_SPEC_VERSION} as the current SDK pin:\n  "
        + "\n  ".join(stale_pin_claims)
        + "\nUpdate the prose in the same change as the pin bump."
    )

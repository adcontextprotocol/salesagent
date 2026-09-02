"""Structural guard: `@storyboard-v3.1` scenarios must cite a binding that resolves.

A scenario tagged `@storyboard-v3.1` is claiming that an AdCP conformance storyboard
grades the behaviour it tests. That claim rotted silently: an audit at the 3.1.1 pin
found all 40 tagged scenarios carried a broken binding — 29 pinned to commit
`04f59d2d5` (an ancestor of beta.3, older than the repo's own pin), 11 with no
`@source` footer at all, 16 citing the *next* scenario's storyboard, and 21 claiming a
storyboard gated behind a protocol, specialism, or capability we do not declare.

None of that was detectable at `make quality` time, which is why it drifted for
months. This guard makes each failure mode fail loudly:

1. a tagged scenario has an `@source` footer
2. the footer's `ref` names the pinned spec version, not some older commit
3. the cited storyboard path exists at the pin
4. a phase named in prose lives in the cited file
5. the cited storyboard is not gated by a protocol/specialism/capability we lack

Offline: reads `tests/fixtures/adcp_storyboards_pinned/index.json`, refreshed by the
`_refresh.py` next to it when the pin advances. This guard runs in CI, where no
`~/projects/adcp` clone exists — it must never resolve a live pinned tree.

Feature-file parsing (tagged-scenario extraction, `@source` footer parsing, path
normalization) comes from scripts/audit/storyboard_spec.py, the shared L0 module
also used by storyboard_coverage_map.py and storyboard_binding_sweep.py, so this
guard's notion of a tagged scenario's block/footer agrees with the audit scripts by
construction — importing it is safe here because none of its
functions this file calls (`tagged_scenarios`, `parse_source_footer`,
`normalize_cited_path`) touch the pinned compliance tree; only the vendored
`index.json` and this repo's own `.feature` files are read.

Allowlist policy is the repo standard — it may only shrink. Entries are seeded from
the audit baseline; each is removed as its scenario is re-pinned or retagged.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FEATURES = REPO_ROOT / "tests" / "bdd" / "features"
INDEX = REPO_ROOT / "tests" / "fixtures" / "adcp_storyboards_pinned" / "index.json"

sys.path.insert(0, str(REPO_ROOT))

from scripts.audit import storyboard_spec  # noqa: E402

# Scenarios whose binding is known-broken at the audit baseline. MAY ONLY SHRINK.
# Every entry is a scenario the 3.1.1 audit found mis-bound; removing one means its
# @source now resolves (or it was retagged @schema-v3.1 and left this guard's scope).
#
# Empty: every @storyboard-v3.1 scenario's footer was re-verified against the pinned
# v3.1.1 tree and corrected to its true source (wrong path/phase/step fixed, missing
# footers added) rather than ledgered here. Stays the (empty)
# seed of this shrink-only guard.
KNOWN_BROKEN_BINDINGS: frozenset[str] = frozenset()


def _index() -> dict:
    return json.loads(INDEX.read_text(encoding="utf-8"))


def _violations() -> dict[str, str]:
    """Map identifier -> first binding defect found. Empty when every binding resolves."""
    index = _index()
    # Resolve against the REPO'S pin (docs/adcp-spec-version.md), not the fixture's own
    # recorded `adcp_spec_version` — a pin bump with no fixture refresh must fail loudly
    # here rather than keep validating footers against a version the fixture no longer
    # represents. `test_fixture_index_version_matches_the_pin` below is what catches that
    # drift directly; this guard just must not silently agree with a stale fixture.
    version = storyboard_spec.pinned_version(REPO_ROOT)
    storyboards: dict[str, dict] = index["storyboards"]
    declared = storyboard_spec.declared_capabilities(REPO_ROOT)
    bad: dict[str, str] = {}

    for scenario in storyboard_spec.tagged_scenarios(FEATURES):
        try:
            footer = storyboard_spec.parse_source_footer(scenario.block)
        except storyboard_spec.SourceFooterError as exc:
            bad[scenario.identifier] = f"{scenario.feature}: malformed @source footer: {exc}"
            continue
        if footer is None:
            bad[scenario.identifier] = f"{scenario.feature}: no @source footer"
            continue

        ref, raw_path = footer.ref, footer.path
        if version not in ref:
            bad[scenario.identifier] = (
                f"{scenario.feature}: @source ref {ref!r} does not name the pinned version {version}"
            )
            continue

        rel = storyboard_spec.normalize_cited_path(raw_path)
        if "schemas" in rel:
            continue  # schema-only citation; nothing storyboard-shaped to resolve
        entry = storyboards.get(rel)
        if entry is None:
            bad[scenario.identifier] = f"{scenario.feature}: cited storyboard {rel!r} does not exist at {version}"
            continue

        # Reachability before tier: a scenario's directory does not determine its
        # gate. `governance_conditions` sits under `protocols/media-buy/scenarios/`
        # but is pulled in only by specialisms we do not declare, so a path-prefix
        # check reports it ungated.
        owners: list[str] = entry.get("required_by", [])
        if owners and not any(storyboard_spec.index_reachable(o, declared) for o in owners):
            bad[scenario.identifier] = (
                f"{scenario.feature}: only required by {owners} — all behind gates we do not declare"
            )
            continue

        if (specialism := entry.get("specialism")) and specialism not in declared["specialisms"]:
            bad[scenario.identifier] = f"{scenario.feature}: gated by undeclared specialism {specialism!r}"
            continue
        if (protocol := entry.get("protocol")) and protocol not in declared["protocols"]:
            bad[scenario.identifier] = f"{scenario.feature}: gated by undeclared protocol {protocol!r}"
            continue
        if capability := entry.get("requires_capability"):
            bad[scenario.identifier] = f"{scenario.feature}: gated by requires_capability {capability['path']}"
            continue

        known = set(entry.get("phases", []))

        # The footer's own `phase=`/`step=` resolve against the cited file's ids
        # directly -- `step` is the addressable unit the conformance ledger keys
        # on (protocol, track, storyboard_id, step_id); a `step=` naming nothing
        # real must fail here, not carry unchecked.
        if footer.phase and footer.phase not in known:
            bad[scenario.identifier] = f"{scenario.feature}: cites phase {footer.phase!r}, absent from cited {rel!r}"
            continue
        if footer.step and footer.step not in known:
            bad[scenario.identifier] = f"{scenario.feature}: cites step {footer.step!r}, absent from cited {rel!r}"
            continue

        for named in {m.group(1) for m in re.finditer(r"\b([a-z][a-z0-9_]{3,})\s+phase\b", scenario.block)}:
            if any(named in sb.get("phases", []) for sb in storyboards.values()) and named not in known:
                bad[scenario.identifier] = f"{scenario.feature}: names phase {named!r}, absent from cited {rel!r}"
                break

    return bad


def test_storyboard_bindings_resolve_at_the_pin() -> None:
    """Every @storyboard-v3.1 scenario cites a binding that resolves at the pinned version."""
    new = {k: v for k, v in _violations().items() if k not in KNOWN_BROKEN_BINDINGS}
    assert new == {}, (
        "New broken @storyboard-v3.1 bindings. A scenario carrying this tag claims an AdCP "
        "storyboard grades it — the claim must resolve at the pinned version:\n"
        + "\n".join(f"  {k}: {v}" for k, v in sorted(new.items()))
    )


def test_fixture_index_version_matches_the_pin() -> None:
    """The vendored index and docs/adcp-spec-version.md must move together.

    Two artifacts are pin-coupled and neither updates itself when the pin does:
    this vendored index (``tests/fixtures/adcp_storyboards_pinned/index.json``)
    and the TS conformance runner's ``@adcp/sdk`` dependency
    (``tests/storyboard/runner/package.json``, guarded separately by
    ``tests/storyboard/test_runner_sdk_pin.py`` once installed). Bumping the pin
    without refreshing the fixture leaves every binding above silently graded
    against a version the fixture has no data for — the exact way this whole
    guard drifted for months (see module docstring). Catch it at the fixture,
    not by trusting `_violations()` to notice.
    """
    pinned = storyboard_spec.pinned_version(REPO_ROOT)
    fixture_version = _index()["adcp_spec_version"]
    assert fixture_version == pinned, (
        f"tests/fixtures/adcp_storyboards_pinned/index.json is pinned to {fixture_version!r} but "
        f"docs/adcp-spec-version.md now pins {pinned!r}. Refresh BOTH pin-coupled storyboard "
        "artifacts named in that document's bump checklist: "
        "tests/fixtures/adcp_storyboards_pinned/index.json (run its _refresh.py against a fresh "
        "~/projects/adcp clone) and tests/storyboard/runner/package.json's @adcp/sdk dependency."
    )


def test_allowlist_has_no_stale_entries() -> None:
    """Allowlisted scenarios that now resolve must be removed — the ratchet only shrinks."""
    broken = set(_violations())
    identifiers = {s.identifier for s in storyboard_spec.tagged_scenarios(FEATURES)}
    stale = {e for e in KNOWN_BROKEN_BINDINGS if e in identifiers and e not in broken}
    assert stale == set(), "These bindings now resolve; remove them from KNOWN_BROKEN_BINDINGS:\n" + "\n".join(
        f"  {e}" for e in sorted(stale)
    )


@pytest.mark.parametrize(
    "block,expected",
    [
        ("  @T-X-storyboard-a @storyboard-v3.1\n  Scenario: x\n", "no @source footer"),
        (
            "  @T-X-storyboard-b @storyboard-v3.1\n  Scenario: x\n"
            "    # @source repo=adcp ref=v3.1-04f59d2d5 path=protocols/media-buy/index.yaml\n",
            "does not name the pinned version",
        ),
        (
            "  @T-X-storyboard-c @storyboard-v3.1\n  Scenario: x\n"
            "    # @source repo=adcp ref=v3.1.1 path=protocols/media-buy/scenarios/nope.yaml\n",
            "does not exist",
        ),
        (
            "  @T-X-storyboard-d @storyboard-v3.1\n  Scenario: x\n"
            "    # @source repo=adcp ref=v3.1.1 path=protocols/media-buy/index.yaml"
            " phases=create_buy,create_media_buy\n",
            "malformed @source footer",
        ),
        (
            "  @T-X-storyboard-e @storyboard-v3.1\n  Scenario: x\n"
            "    # @source repo=adcp ref=v3.1.1 path=protocols/media-buy/index.yaml"
            " phase=create_buy step=not_a_real_step\n",
            "cites step",
        ),
    ],
)
def test_guard_catches_each_failure_mode(tmp_path: Path, monkeypatch, block: str, expected: str) -> None:
    """Meta-test: a guard that cannot fail is not a guard."""
    feature = tmp_path / "BR-UC-999-meta.feature"
    feature.write_text("Feature: meta\n\n" + block, encoding="utf-8")
    monkeypatch.setattr(f"{__name__}.FEATURES", tmp_path)
    found = _violations()
    assert found, f"guard did not flag the {expected!r} case"
    assert expected in next(iter(found.values()))

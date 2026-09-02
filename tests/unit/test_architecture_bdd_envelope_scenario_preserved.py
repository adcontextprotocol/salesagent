"""Guard: UC-019's envelope-status scenario must survive regeneration on its own.

``BR-UC-019-query-media-buys.feature`` :45 (``@T-UC-019-envelope-status``) is the
oracle for the spec-required ``status`` on a get_media_buys response envelope —
the requirement reaches that response through a top-level ``allOf`` composition,
which is exactly how it went missing in a real implementation with no transport
noticing.

Today the scenario is safe, and NOT for a reason anyone chose: it survives only
because an identical twin exists upstream in adcp-req. ``classify_scenario_pair``
reaches ``_has_hand_edited_marker`` only when ``target is None``, so while the twin
is there the pair classifies NO-OP and is kept. Remove the twin upstream — a change
made in a different repository, by someone not looking at this file — and the
scenario classifies LEGACY-DELETE and ``merge_feature`` drops it. Measured against
the real adcp-req checkout with the twin stripped from the target: the tag is
absent from the merged output and the LEGACY-DELETE bucket goes 2 -> 3. The oracle
would not fail; it would cease to exist.

So this guard pins BOTH halves, because the obvious fix breaks the other one:

  * with the twin GONE the scenario must be PRESERVED — the marker must exist;
  * with the twin PRESENT the pair must still classify NO-OP — the marker must not
    participate in matching.

The ``@hand-edited`` TAG form satisfies the first and BREAKS the second:
``_tags_match_ignoring_id`` compares tag sets modulo ``@T-``, so a locally-added
tag makes the sets differ and converts a clean NO-OP into NEEDS-SEMANTIC-MERGE on
every regeneration (UC-019 is in WIRED_UCS). The ``# HAND-EDITED`` COMMENT form is
accepted by ``_has_hand_edited_marker`` and participates in neither tag nor step
matching. Test 3 below is what holds the fix to the comment form.

The TARGET side is synthesized from this repo's own copy of the feature rather
than read out of ``../adcp-req``: the twin was verified at source
(``adcp-req/tests/features/BR-UC-019-query-media-buys.feature`` :41-42) to carry
identical tags and identical steps, and a guard that depends on a sibling checkout
does not run for anyone who lacks it.

GH: PR #1941 round-5 review.
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

from compile_bdd import (  # noqa: E402  (path is set immediately above)
    HAND_EDITED_RE,
    Scenario,
    classify_scenario_pair,
    merge_feature,
    parse_feature_file,
)

_FEATURE = _REPO_ROOT / "tests" / "bdd" / "features" / "BR-UC-019-query-media-buys.feature"
_SCENARIO_TAG = "@T-UC-019-envelope-status"
_SCENARIO_ID = "T-UC-019-envelope-status"


def _scenario_by_tag(feature_text: str, tag: str) -> Scenario:
    for scenario in parse_feature_file(feature_text).scenarios:
        if tag in scenario.tags:
            return scenario
    raise AssertionError(f"{tag} is not in the feature file at all; every assertion here would be vacuous")


def _synthesized_upstream_twin(legacy: Scenario) -> Scenario:
    """The verified upstream twin, modelled from this repo's own scenario.

    Upstream carries identical tags and identical steps (verified at
    ``adcp-req/tests/features/BR-UC-019-query-media-buys.feature`` :41-42), and it
    will never carry a marker added HERE — so every hand-edit marker is stripped
    from the TARGET side. That asymmetry is the entire point: a marker exists only
    on LEGACY, which is exactly why the ``@hand-edited`` TAG form desynchronises
    the two tag sets while the ``# HAND-EDITED`` comment form does not.

    Modelling the twin rather than reading ``../adcp-req`` keeps the guard runnable
    without a sibling checkout. Cross-checked: against the real upstream file this
    pair returns NO-OP with no marker, NO-OP with the comment form, and
    NEEDS-SEMANTIC-MERGE with the tag form — the same three answers this model gives.
    """
    return dataclasses.replace(
        legacy,
        tags=[t for t in legacy.tags if not HAND_EDITED_RE.search(t)],
        comment_lines=[c for c in legacy.comment_lines if not HAND_EDITED_RE.search(c)],
    )


def _feature_without(feature_text: str, tag: str) -> str:
    """The feature text with the tagged scenario block removed.

    Stands in for the upstream TARGET after the twin is deleted there. Blocks are
    delimited the way the file is written: a scenario starts at its tag line and
    runs to the next tag line at the same indent.
    """
    out: list[str] = []
    dropping = False
    for line in feature_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("@"):
            dropping = tag in stripped
        if not dropping:
            out.append(line)
    result = "\n".join(out) + "\n"
    assert tag not in result, f"{tag} survived the strip; the fixture does not produce the state under test"
    return result


@pytest.fixture
def feature_text() -> str:
    assert _FEATURE.exists(), f"{_FEATURE} is missing"
    return _FEATURE.read_text(encoding="utf-8")


class TestTheScenarioSurvivesLosingItsUpstreamTwin:
    """The half that needs the marker."""

    def test_classification_is_legacy_preserve_when_the_twin_is_gone(self, feature_text):
        """The decision point, named exactly.

        ``LEGACY-DELETE`` here is not a warning and not a manifest entry — it is a
        silent drop on a regeneration nobody is watching.
        """
        legacy = _scenario_by_tag(feature_text, _SCENARIO_TAG)

        bucket = classify_scenario_pair(legacy, None)

        assert bucket == "LEGACY-PRESERVE", (
            f"{_SCENARIO_ID} classifies {bucket} with no upstream twin. It is the PR's principal "
            f"envelope oracle and it carries no hand-edit marker, so merge_feature() deletes it the "
            f"first time the twin disappears upstream. Add a `# HAND-EDITED` comment inside the "
            f"scenario body — NOT an @hand-edited tag (see the NO-OP test below)."
        )

    def test_merge_keeps_the_scenario_when_the_target_no_longer_has_it(self, feature_text, tmp_path):
        """The effect, end to end through merge_feature().

        Classification is the decision, but the thing that matters to a buyer is
        whether the oracle is still in the file afterwards.
        """
        target = tmp_path / _FEATURE.name
        target.write_text(_feature_without(feature_text, _SCENARIO_TAG), encoding="utf-8")

        _uc_key, output_text, _manifest, _ids, _mappings, buckets = merge_feature(target, _FEATURE, {}, "0" * 40)

        assert _SCENARIO_TAG in output_text, (
            f"{_SCENARIO_ID} is absent from the merged feature once the upstream twin is gone "
            f"(buckets: {buckets}). The envelope-status oracle was deleted, not failed."
        )


class TestTheMarkerDoesNotPerturbTodaysClassification:
    """The half the obvious fix breaks."""

    def test_the_pair_still_classifies_no_op_while_the_twin_exists(self, feature_text):
        """Adding the marker must change NOTHING about the present state.

        The TARGET here is this repo's own scenario, which is tag- and
        step-identical to the verified upstream twin. If the marker is added as an
        ``@hand-edited`` TAG, ``_tags_match_ignoring_id`` sees two different tag
        sets and this pair becomes NEEDS-SEMANTIC-MERGE — a manifest entry demanding
        a human decision, regenerated every single time, forever. That is strictly
        worse than the risk the marker is insurance against.
        """
        legacy = _scenario_by_tag(feature_text, _SCENARIO_TAG)
        target = _synthesized_upstream_twin(legacy)

        bucket = classify_scenario_pair(legacy, target)

        assert bucket == "NO-OP", (
            f"{_SCENARIO_ID} classifies {bucket} against an upstream twin carrying the same tags and "
            f"steps. The hand-edit marker must be a `# HAND-EDITED` COMMENT, which participates in "
            f"neither _tags_match_ignoring_id nor _steps_match; the @hand-edited TAG form "
            f"desynchronises the tag sets and re-raises this scenario for semantic merge on every "
            f"regeneration."
        )

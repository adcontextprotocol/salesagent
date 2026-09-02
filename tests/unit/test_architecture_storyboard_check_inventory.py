"""Regression tests for the storyboard check-type inventory.

The storyboard roadmap (``scripts/audit/storyboard_roadmap.py``) publishes a per-storyboard
inventory of graded check types ("Checks" column, plus the per-storyboard
totals in both summary tables). That inventory was built by iterating
``storyboard_spec.phases()`` and summing ``checks_for_phase()`` over each id --
which double-counts every nested check:

* ``phases()`` returns every ``- id:`` at ANY depth. Phases sit at two-space
  indent, their steps at six.
* ``checks_for_phase()`` windows from its anchor to the next SIBLING id (indent
  ``<=`` the anchor's) -- deliberately, so ``phase_is_graded()`` still sees a
  phase whose grading lives in a later step. A phase window therefore already
  encloses its own steps and their ``validations:`` blocks.

So each check was counted once at the step and again at its parent phase.
Measured at the 3.1.1 pin: 119 of 121 storyboards published inflated counts.

The fix is a dedicated aggregate primitive, ``storyboard_spec.check_inventory()``,
which counts each ``check:`` line exactly once by keying on its absolute offset
across the (overlapping) phase windows. ``checks_for_phase()`` and
``phase_is_graded()`` are deliberately left alone -- the wide window is correct
for THEIR question ("is this phase graded at all?"), only wrong for summing.

Why offsets and not a whole-text ``findall``: the assertions below grade the
primitive against an independently-written literal count of the file's
``check:`` lines. Were the primitive itself a whole-text count, those
assertions would be a tautology -- two spellings of one regex agreeing with
each other, surviving any mutation of the behavior they claim to pin.

The inline test below carries the regression in CI, where no ``~/projects/adcp``
clone exists; the live-tree tests pin the real pinned-file numbers from the
ticket and are skipped without the clone (same contract as
``test_architecture_storyboard_spec.py``).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

sys.path.insert(0, str(REPO_ROOT))

from scripts.audit import storyboard_spec  # noqa: E402
from tests.unit._storyboard_guard_env import (  # noqa: E402
    ADCP_HOME,
    DIST,
    requires_pinned_bundle,
)

# The literal ground truth this whole module is graded against: one entry per
# `check:` line physically present in the file. Intentionally a second,
# independent expression of the check-line shape -- if the production regex
# drifts, this disagrees rather than drifting with it.
_LITERAL_CHECK_RE = re.compile(r"^\s*(?:-\s*)?check:\s*(\S+)\s*$", re.M)


def _literal_inventory(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for check_type in _LITERAL_CHECK_RE.findall(text):
        counts[check_type] = counts.get(check_type, 0) + 1
    return dict(sorted(counts.items()))


# A phase (two-space indent) whose steps (six-space indent) each carry their own
# `validations:` block -- the exact nesting that produced the double-count.
NESTED_STORYBOARD = """\
id: nested_example
track: example
phases:
  - id: outer_phase
    description: |
      A narrative that mentions the create/update parity check:
      and must never contribute a count.
    steps:
      - id: inner_step_one
        validations:
          - id: v1
            check: response_schema
          - check: field_present
      - id: inner_step_two
        validations:
          - id: v2
            check: field_value
  - id: second_phase
    steps:
      - id: inner_step_three
        validations:
          - check: field_value
"""


def test_check_inventory_counts_each_nested_check_exactly_once():
    """The double-count regression, pinned without a spec clone.

    Four `check:` lines exist in NESTED_STORYBOARD. The pre-fix aggregate
    reported eight -- each counted once at its step and once at the enclosing
    phase.
    """
    assert _literal_inventory(NESTED_STORYBOARD) == {
        "field_present": 1,
        "field_value": 2,
        "response_schema": 1,
    }

    assert storyboard_spec.check_inventory(NESTED_STORYBOARD) == {
        "field_present": 1,
        "field_value": 2,
        "response_schema": 1,
    }


def test_check_inventory_ignores_prose_ending_in_check_colon():
    """The narrative line ending in "check:" must contribute nothing.

    Guards the fix against the obvious over-correction: a relaxed regex that
    counts every line containing `check:` would report a phantom fifth entry.
    """
    assert "parity check:" in NESTED_STORYBOARD
    assert sum(storyboard_spec.check_inventory(NESTED_STORYBOARD).values()) == 4


def test_phase_is_graded_still_sees_grading_in_a_later_step():
    """The wide window in checks_for_phase() must survive the fix.

    `outer_phase` carries no check of its own -- its grading lives in its
    steps. A "fix" that narrowed the window to the next id at ANY depth would
    report this graded phase as prose.
    """
    assert storyboard_spec.phase_is_graded(NESTED_STORYBOARD, "outer_phase") == "graded"
    assert storyboard_spec.phase_is_graded(NESTED_STORYBOARD, "inner_step_one") == "graded"
    assert storyboard_spec.phase_is_graded(NESTED_STORYBOARD, "nope") == "absent"


@requires_pinned_bundle
@pytest.mark.parametrize(
    ("rel", "expected"),
    [
        # The two files named in the original finding, at their file-literal counts.
        ("universal/signed-requests.yaml", {"field_present": 1, "field_value": 1}),
        (
            "protocols/media-buy/scenarios/billing_finality_delivery.yaml",
            {"field_absent": 2, "field_present": 4, "field_value": 10, "response_schema": 5},
        ),
        # The five storyboards whose pre-fix inflation was NOT a clean 2x -- they
        # mix nesting depths, so a fix that merely halved the old totals would
        # get these wrong.
        (
            "protocols/media-buy/scenarios/measurement_accountability.yaml",
            {"field_present": 5, "field_value": 1, "field_value_or_absent": 1, "response_schema": 4},
        ),
        (
            "protocols/media-buy/scenarios/vendor_metric_accountability.yaml",
            {"field_present": 12, "field_value": 1, "response_schema": 4},
        ),
        (
            "protocols/media-buy/scenarios/performance_buy_flow_roas.yaml",
            {
                "error_code": 1,
                "field_present": 9,
                "field_value": 2,
                "response_schema": 6,
                "upstream_traffic": 2,
            },
        ),
        (
            "protocols/media-buy/scenarios/dependency_impairment.yaml",
            {
                "field_contains": 3,
                "field_present": 9,
                "field_value": 9,
                "field_value_or_absent": 2,
                "response_schema": 13,
            },
        ),
        (
            "protocols/media-buy/scenarios/dependency_impairment_cardinality.yaml",
            {
                "field_contains": 4,
                "field_present": 16,
                "field_value": 18,
                "field_value_or_absent": 3,
                "response_schema": 21,
            },
        ),
    ],
)
def test_check_inventory_matches_pinned_file_counts(rel: str, expected: dict[str, int]):
    """Pinned per-file numbers from the ticket, read off the live 3.1.1 tree."""
    text = (DIST / rel).read_text(encoding="utf-8")

    # The file really does contain what the ticket claims.
    assert _literal_inventory(text) == expected

    assert storyboard_spec.check_inventory(text) == expected


@requires_pinned_bundle
def test_check_inventory_matches_file_truth_for_every_pinned_storyboard():
    """Sweep: no storyboard at the pin may publish an inflated inventory."""
    mismatches = {
        sb.rel: (storyboard_spec.check_inventory(sb.text), _literal_inventory(sb.text))
        for sb in storyboard_spec.storyboards(DIST)
        if storyboard_spec.check_inventory(sb.text) != _literal_inventory(sb.text)
    }
    assert mismatches == {}


@requires_pinned_bundle
def test_roadmap_rows_publish_file_truth_check_counts():
    """The deliverable itself: every roadmap row's Checks cell equals file truth.

    Tests the artifact, not just the primitive -- the bug shipped because the
    roadmap did its own summing rather than calling a shared aggregate.
    """
    from scripts.audit import storyboard_roadmap

    result = storyboard_roadmap.build(REPO_ROOT, ADCP_HOME)
    assert result["rows"], "roadmap resolved no on-path rows — the fixture, not the fix, is broken"

    mismatches = {
        row["storyboard"]: (row["checks"], _literal_inventory((DIST / row["storyboard"]).read_text(encoding="utf-8")))
        for row in result["rows"]
        if row["checks"] != _literal_inventory((DIST / row["storyboard"]).read_text(encoding="utf-8"))
    }
    assert mismatches == {}

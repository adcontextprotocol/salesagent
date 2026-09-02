"""Controller-ungradable status derives from required_tools.

The storyboard roadmap's (``scripts/audit/storyboard_roadmap.py``) Status column answers one
question objectively: what did the in-network job actually measure. It has
three answers, and the distinction between the last two is the whole point of
the column --

* ``FAILING`` — measured, ledgered.
* ``no ledger entries`` — the job ran it and nothing failed. Debt at worst.
* ``ungradable (comply_test_controller)`` — the job could not reach the
  assertions at all, and never will: the storyboard needs a tool this agent
  has decided not to implement (it is a production test-control backdoor, see). A documented divergence, not debt.

That last state was read off ``_COMPLY_TEST_CONTROLLER_DIVERGENCE``, a
hand-maintained dict of 20 stems. Measured against the 3.1.1 pin: 29
storyboards declare ``comply_test_controller`` in top-level ``required_tools``,
and the dict is a strict subset of them -- it adds nothing the tree does not
already state, and silently misses the 9 nobody typed in. Four of those 9 are
ON-PATH, so they render today as ``no ledger entries``: a permanent,
by-design divergence displayed as not-yet-measured.

The fix derives ungradability from ``required_tools`` and keeps the dict for
the one thing it genuinely carries: the DETERMINISTIC INJECTION vs PRIOR STATE
ONLY editorial call, which no amount of structure can derive.

The offline tests below run in CI off the vendored
``tests/fixtures/adcp_storyboards_pinned/index.json``; the live-tree test pins
the four named on-path storyboards and is skipped without an ``~/projects/adcp``
clone.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
INDEX = REPO_ROOT / "tests" / "fixtures" / "adcp_storyboards_pinned" / "index.json"

sys.path.insert(0, str(REPO_ROOT))

from scripts.audit import storyboard_roadmap, storyboard_spec  # noqa: E402
from tests.unit._storyboard_guard_env import (  # noqa: E402
    ADCP_HOME,
    requires_pinned_bundle,
)

CONTROLLER = "comply_test_controller"

# The four ON-PATH storyboards the dict misses. Named rather than derived: this
# is the ticket's evidence, and a test that re-derived it would pass no matter
# what production did.
ON_PATH_UNMARKED = {
    "create_media_buy_async",
    "delivery_reporting",
    "measurement_accountability",
    "vendor_metric_accountability",
}


def _index_stems_requiring_controller() -> set[str]:
    index = json.loads(INDEX.read_text(encoding="utf-8"))
    return {
        storyboard_spec.storyboard_key(rel)
        for rel, entry in index["storyboards"].items()
        if CONTROLLER in (entry.get("required_tools") or [])
    }


def _storyboard_text(required_tools: list[str]) -> str:
    """Minimal storyboard text declaring the given top-level required_tools."""
    tools = "\n".join(f"  - {tool}" for tool in required_tools)
    return f"id: synthetic_example\ntrack: example\nrequired_tools:\n{tools}\n\nphases:\n  - id: only_phase\n"


def test_ungradable_derives_from_required_tools_not_dict_membership():
    """The regression, stated directly and offline.

    A storyboard that needs the controller is ungradable whether or not anyone
    typed its stem into the divergence dict. Under the old logic this row read
    "no ledger entries" — permanently-unreachable displayed as
    not-yet-measured.
    """
    unlisted = "a_stem_nobody_typed_into_the_dict"
    assert unlisted not in storyboard_roadmap._COMPLY_TEST_CONTROLLER_DIVERGENCE

    row = storyboard_roadmap.build_row_status_fields(
        stem=unlisted,
        text=_storyboard_text([CONTROLLER, "create_media_buy"]),
    )

    assert row["requires_controller"] is True
    assert storyboard_roadmap._status_cell({**row, "ledgered_failures": []}) == "ungradable (comply_test_controller)"


def test_storyboard_without_the_controller_is_not_ungradable():
    """Negative: the derivation must not paint every row ungradable."""
    row = storyboard_roadmap.build_row_status_fields(
        stem="ordinary_storyboard",
        text=_storyboard_text(["create_media_buy", "get_products"]),
    )

    assert row["requires_controller"] is False
    assert storyboard_roadmap._status_cell({**row, "ledgered_failures": []}) == "no ledger entries"


def test_measured_failure_outranks_ungradable():
    """A ledgered failure is measured evidence and keeps precedence.

    If the job DID reach the assertions and they failed, saying "ungradable"
    would discard a real measurement.
    """
    row = storyboard_roadmap.build_row_status_fields(
        stem="marked_and_failing",
        text=_storyboard_text([CONTROLLER]),
    )

    cell = storyboard_roadmap._status_cell({**row, "ledgered_failures": ["step_a", "step_b"]})
    assert cell == "**FAILING** — 2 ledgered"


def test_editorial_label_survives_for_triaged_storyboards():
    """The dict keeps the one judgement that cannot be derived."""
    row = storyboard_roadmap.build_row_status_fields(
        stem="audience_buy_flow",
        text=_storyboard_text([CONTROLLER]),
    )

    assert row["divergence"] == "DETERMINISTIC INJECTION"


def test_untriaged_controller_storyboard_is_labelled_untriaged():
    """An ungradable row with no editorial call says so, rather than rendering blank."""
    row = storyboard_roadmap.build_row_status_fields(
        stem="a_stem_nobody_typed_into_the_dict",
        text=_storyboard_text([CONTROLLER]),
    )

    assert row["divergence"] == "UNTRIAGED"


def test_divergence_dict_names_only_storyboards_that_require_the_controller():
    """Structural guard on the surviving hand-maintained input.

    The dict may only carry the editorial label for a storyboard the tree says
    needs the tool. A stem that does not — a typo, or a storyboard the spec
    stopped gating — would attach a divergence label to a row that has no
    divergence, and nothing else would catch it.
    """
    strays = sorted(set(storyboard_roadmap._COMPLY_TEST_CONTROLLER_DIVERGENCE) - _index_stems_requiring_controller())
    assert strays == [], (
        "these stems carry a comply_test_controller divergence label but the pinned tree "
        "does not list that tool in their required_tools"
    )


def test_every_controller_storyboard_in_the_pinned_index_is_covered():
    """Derivation covers the whole set, including what the dict never named.

    Grades the REAL per-storyboard ``required_tools`` recorded in the vendored
    index, not a hardcoded ``[CONTROLLER]`` list fed to every stem — that
    older shape made ``requires_controller`` true by construction for every
    stem under test, so ``return True`` in production would have passed here
    too. Building each stem's synthetic text from its own indexed tools means
    the ~90 storyboards that do NOT require the controller must derive
    ``False``, which a blanket ``return True`` fails.
    """
    index = json.loads(INDEX.read_text(encoding="utf-8"))
    requiring = _index_stems_requiring_controller()

    assert ON_PATH_UNMARKED <= requiring, "the ticket's four on-path storyboards must require the controller"
    # The dict was, and may remain, a strict subset — that is exactly why it
    # cannot be the source of the status.
    assert set(storyboard_roadmap._COMPLY_TEST_CONTROLLER_DIVERGENCE) < requiring

    mismatched = []
    for rel, entry in index["storyboards"].items():
        stem = storyboard_spec.storyboard_key(rel)
        real_tools = entry.get("required_tools") or []
        row = storyboard_roadmap.build_row_status_fields(stem=stem, text=_storyboard_text(real_tools))
        expected = CONTROLLER in real_tools
        if row["requires_controller"] != expected:
            mismatched.append((rel, stem, row["requires_controller"], expected))
    assert mismatched == []


@requires_pinned_bundle
def test_roadmap_renders_every_controller_storyboard_as_ungradable():
    """The deliverable: no on-path controller row may read 'no ledger entries'."""
    result = storyboard_roadmap.build(REPO_ROOT, ADCP_HOME)
    rows = {row["stem"]: row for row in result["rows"]}

    rendered = {
        stem: storyboard_roadmap._status_cell(row) for stem, row in rows.items() if CONTROLLER in row["required_tools"]
    }
    assert rendered, "no on-path row requires comply_test_controller — the fixture, not the fix, is broken"

    # The four the hand-maintained dict missed.
    assert ON_PATH_UNMARKED <= set(rendered), "the ticket's four on-path storyboards must be on-path in this build"
    for stem in ON_PATH_UNMARKED:
        assert rendered[stem] == "ungradable (comply_test_controller)", stem

    misreported = {stem: cell for stem, cell in rendered.items() if cell == "no ledger entries"}
    assert misreported == {}

"""Regression tests for scripts/audit/storyboard_spec.py (the reconciliation pass).

``storyboard_spec.py`` is the new shared L0 parsing module that
``scripts/audit/storyboard_coverage_map.py``, ``scripts/audit/storyboard_binding_sweep.py``,
``tests/fixtures/adcp_storyboards_pinned/_refresh.py`` and
``tests/unit/test_architecture_storyboard_binding.py`` are migrated onto (Implementation
Plan v2, step 1-2). Per step 4, this file pins ONE regression case per fixed parsing bug
found by the codebase disease scan (NOTES, "Codebase Disease Scan")
and confirmed by the architect review -- these are the ticket's own
acceptance criteria.

This file is written BEFORE ``scripts/audit/storyboard_spec.py`` exists (TDD red): every
test here must currently fail with ``ModuleNotFoundError`` on
``from scripts.audit import storyboard_spec``.

Bugs pinned here:

1. ``checks_for_phase()`` must extract real check types when a validation item orders
   ``id:`` before ``check:`` (id-first ordering), not only the leading-``- check:`` form
   ``storyboard_binding_sweep.py:156`` assumed
   (``re.search(r"^\\s*-\\s*check:", window, re.M)``). Pinned against
   ``protocols/media-buy/scenarios/refine_finalize_exclusivity.yaml`` at the AdCP 3.1.1
   pin, which uses id-first ordering exclusively -- the old regex misses all 18 real
   checks in this file (verified: zero ``^\\s*-\\s*check:`` matches, 18
   ``^\\s*check:`` matches).
2. The fix for (1) must not start matching prose. The pinned tree contains real prose
   sentences that end in the word "check:" inside a phase's narrative text (not inside a
   ``validations:`` block) -- pinned against
   ``protocols/media-buy/scenarios/inventory_list_targeting.yaml``'s
   ``update_swap_lists`` phase, whose narrative literally contains "This is the
   create/update parity check:" alongside 6 REAL validation checks in the same
   sibling-indent window. ``checks_for_phase()`` must extract exactly the 6 real checks,
   not 7.

Reads the live pinned AdCP compliance tree the way every existing sibling script does
(``scripts/audit/storyboard_coverage_map.py::pinned_version`` +
``storyboard_spec.adcp_home()``, see ``docs/adcp-spec-version.md``) -- skipped when
NO tree resolves at all: not $ADCP_HOME, not the in-repo release bundle, and not a
personal clone. These tests pin behavior against real spec content
rather than a vendored offline index (that offline contract belongs to
``test_architecture_storyboard_binding.py``, which stays on the vendored index.json).
"""

from __future__ import annotations

import re
from pathlib import Path

from scripts.audit import storyboard_spec
from tests.unit._storyboard_guard_env import (  # noqa: E402
    DIST,
    requires_pinned_bundle,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


pytestmark = requires_pinned_bundle


def _read_pinned(rel_path: str) -> str:
    path = DIST / rel_path
    assert path.is_file(), f"expected pinned storyboard file missing at pin: {path}"
    return path.read_text(encoding="utf-8")


def test_checks_for_phase_extracts_id_first_ordered_checks():
    """checks_for_phase() must extract check types when `check:` follows `- id:`
    on the validation item's own line (id-first ordering), not only the
    leading-`- check:` form the old regex required.
    """

    text = _read_pinned("protocols/media-buy/scenarios/refine_finalize_exclusivity.yaml")

    # Ground truth for this pin: zero validations at this file use the leading
    # `- check:` form the old regex (storyboard_binding_sweep.py:156) required.
    assert re.search(r"^\s*-\s*check:", text, re.M) is None
    # ... yet 18 real `check:` keys exist, all id-first ordered.
    assert len(re.findall(r"^\s*check:\s*\S+", text, re.M)) == 18

    setup_checks = storyboard_spec.checks_for_phase(text, "setup")
    assert setup_checks == [
        "response_schema",
        "field_present",
        "response_schema",
        "field_present",
    ]

    all_phase_ids = [
        "setup",
        "setup_second_proposal",
        "mixed_finalize_rejected",
        "non_proposal_finalize_rejected",
        "multi_finalize_atomic_path",
        "multi_finalize_unsupported_path",
        "multi_finalize_gate",
    ]
    all_checks = [check for phase_id in all_phase_ids for check in storyboard_spec.checks_for_phase(text, phase_id)]
    assert len(all_checks) == 18


def test_checks_for_phase_does_not_match_prose_ending_in_check_colon():
    """A prose sentence inside a phase's narrative that happens to end in the word
    "check:" must not be counted as a validation check -- only real `check:` keys
    inside a `validations:` item may contribute.
    """

    text = _read_pinned("protocols/media-buy/scenarios/inventory_list_targeting.yaml")

    # Ground truth for this pin: the prose collision is real.
    assert "This is the create/update parity check:" in text

    checks = storyboard_spec.checks_for_phase(text, "update_swap_lists")

    # 6 real checks live in this phase's window (2 steps: 3 validations each).
    # A regex relaxed to match bare `check:` without validation-item context would
    # report a 7th, phantom entry sourced from the prose line above.
    assert checks == [
        "response_schema",
        "field_present",
        "field_contains",
        "response_schema",
        "field_value",
        "field_value",
    ]


def test_tagged_scenarios_block_terminates_at_next_tagline():
    """A tagged scenario's comment block must stop at the NEXT scenario's tag
    line, not run to a fixed line count -- a fixed-window extractor with no
    terminator bleeds the following scenario's @source citations into this
    one's block (verified pre-fix: 16 of 21 tagged scenarios in
    tests/bdd/features/ were affected).
    """

    feature_dir = REPO_ROOT / "tests" / "bdd" / "features"
    scenarios = storyboard_spec.tagged_scenarios(feature_dir)
    assert scenarios, "expected at least one @storyboard-v3.1 tagged scenario"

    by_ident = {s.identifier: s for s in scenarios}
    target = by_ident.get("T-UC-003-storyboard-media-buy-not-found")
    assert target is not None, "expected T-UC-003-storyboard-media-buy-not-found to be tagged"

    footer = storyboard_spec.parse_source_footer(target.block)
    assert footer is not None
    cited_path = storyboard_spec.normalize_cited_path(footer.path)
    assert "invalid_transitions" in cited_path

    # The bug this guards: a fixed-window extractor with no tag-line terminator
    # bleeds sibling scenarios' own citations into this scenario's block. Confirm
    # this scenario's block does not contain another tagged scenario's tag line.
    other_taglines = [f"@{s.identifier}" for s in scenarios if s.identifier != target.identifier]
    leaked = [tag for tag in other_taglines if tag != "@(unnamed)" and tag in target.block]
    assert not leaked, f"scenario block leaked sibling tag(s): {leaked}"


def test_tagged_scenarios_keys_on_an_arbitrary_tag():
    """``tagged_scenarios(tag=...)`` must key on any tag, not only ``TAG``.

    A caller may look up ONE scenario by its own ``@T-UC-…`` identifier rather
    than the shared ``@storyboard-v3.1``, so the ``tag`` parameter has to really
    select on the caller's tag. Pinned as the same block reached two ways.
    """

    feature_dir = REPO_ROOT / "tests" / "bdd" / "features"
    identifier = "T-UC-003-storyboard-media-buy-not-found"

    by_identifier = storyboard_spec.tagged_scenarios(feature_dir, tag=f"@{identifier}")
    assert len(by_identifier) == 1, f"expected exactly one scenario tagged @{identifier}"

    from_default = next(s for s in storyboard_spec.tagged_scenarios(feature_dir) if s.identifier == identifier)
    assert by_identifier[0].feature == from_default.feature == "BR-UC-003-update-media-buy.feature"
    assert by_identifier[0].block == from_default.block
    assert by_identifier[0].line == from_default.line

    # And it is genuinely selective: the identifier tag pulls one scenario, the
    # shared tag pulls the whole tagged population.
    assert len(storyboard_spec.tagged_scenarios(feature_dir)) > 1


def test_storyboard_key_does_not_collapse_index_files_onto_index():
    """storyboard_key() must key an index.yaml by its parent directory, not the
    literal stem "index" -- Path.stem collapses every */index.yaml onto the
    same key, making one citation of protocols/creative/index.yaml look like a
    claim on every specialism's index.
    """

    key_a = storyboard_spec.storyboard_key("protocols/media-buy/index.yaml")
    key_b = storyboard_spec.storyboard_key("specialisms/sales-non-guaranteed/index.yaml")
    assert key_a != key_b
    assert key_a == "media-buy"
    assert key_b == "sales-non-guaranteed"

    # Non-index files still key by their own stem.
    assert storyboard_spec.storyboard_key("universal/capability_discovery.yaml") == "capability_discovery"


def test_storyboards_excludes_non_gradable_universal_files():
    """storyboards() must exclude universal/ files lacking a top-level track:
    (fictional-entities.yaml, runner-output-contract.yaml, storyboard-schema.yaml)
    -- confirmed against a real-runner baseline, neither ever appears in
    storyboards_executed or storyboards_missing_tools.
    """

    rels = {sb.rel for sb in storyboard_spec.storyboards(DIST)}
    assert "universal/fictional-entities.yaml" not in rels
    assert "universal/runner-output-contract.yaml" not in rels
    assert not any(storyboard_spec.storyboard_key(rel) == "storyboard-schema" for rel in rels)
    assert not any(rel.startswith(("domains/", "test-kits/", "test-vectors/")) for rel in rels)
    # A real, gradable universal/ storyboard must still be included.
    assert "universal/capability-discovery.yaml" in rels

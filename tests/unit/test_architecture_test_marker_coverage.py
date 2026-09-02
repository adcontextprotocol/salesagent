"""The entity auto-marking rule: one definition, asserted directly.

Entity markers (delivery, creative, product, media_buy, tenant, auth, adapter,
inventory, schema, admin, architecture, targeting, transport, workflow, policy,
agent, infra) let a human run a slice of the suite by domain:

    make test-entity ENTITY=delivery
    pytest -m "creative and unit"

That Makefile target is the only consumer in the repo — there is no CI entity
sharding — so this module grades the RULE, not the population.

Why there is no longer a coverage ratchet here
----------------------------------------------
This module used to answer "does every unit test carry a marker?" by running
`pytest tests/unit/ --collect-only -m "not (...)"` in a subprocess and scanning
stdout for lines containing `::`. It could not fail: `pytest.ini`'s addopts
carries `-v`, which `-q` reduces to NORMAL verbosity, where `--collect-only`
prints a module TREE and no node ids. Measured on `origin/main`: 869 stdout
lines, 0 containing `::`, so the guard matched nothing for its entire life
while pytest's own answer to the same query was `685/5740 tests collected`.
It was also the single largest contributor to the unit suite's floor (21s), and
its 60s timeout did not survive the suite going parallel.

The subprocess is gone. What replaced it was a count ratchet over 613 unmarked
tests, and that was dropped too: nothing breaks when a test is unmarked. An
unmarked test is one `make test-entity` skips for whoever typed it, locally.
That is a convenience, not an invariant, and a ratchet is only worth its
maintenance when breaking it is bad. The real gap — 613 unit tests in ~60 files
earn no marker, so entity-scoped runs are quietly partial — is filed separately;
the decision it needs is whether entity markers should become load-bearing (CI
sharding) or be dropped as a concept, and neither belongs in a test-runner fix.

What survives is the part that had a defect: the rule now lives in exactly one
place, `tests.conftest.entity_markers_for_path`, which collection itself calls.
Two copies would drift, and anything grading the rule would then grade something
production does not follow.
"""

import pytest

from tests.conftest import _ENTITY_MARKERS, entity_markers_for_path


@pytest.mark.arch_guard
def test_filename_pattern_earns_its_entity():
    """Markers come from a SUBSTRING of the filename stem, not an exact match."""
    markers = entity_markers_for_path("/repo/tests/unit/test_delivery_webhook_behavioral.py")
    assert "delivery" in markers, f"expected 'delivery' from the filename stem, got {sorted(markers)}"


@pytest.mark.arch_guard
def test_directory_earns_its_entity_independently_of_the_filename():
    """`tests/admin/` earns `admin` even when the stem matches no pattern."""
    markers = entity_markers_for_path("/repo/tests/admin/test_zzz_no_pattern_matches_this.py")
    assert "admin" in markers, f"expected 'admin' from the directory, got {sorted(markers)}"


@pytest.mark.arch_guard
def test_a_stem_that_matches_nothing_earns_nothing():
    """Negative control: the rule is capable of returning the empty set.

    Without this, every assertion above would still pass if the function
    returned every marker for every path — the exact shape that would make an
    entity-scoped run silently select the whole suite.
    """
    assert entity_markers_for_path("/repo/tests/unit/test_zzz_no_pattern_matches_this.py") == frozenset()


@pytest.mark.arch_guard
def test_the_rule_reads_the_whole_path_not_just_the_stem():
    """Two files sharing a stem in different directories earn different markers.

    The cache behind this function was keyed on the STEM. Ten stems are
    duplicated across `tests/`, and one diverges: `tests/admin/` adds `admin`.
    Under a stem key, whichever file collection reached first decided for both,
    so `pytest tests/ -m admin` ran 333 items where 320 are admin tests — 13
    non-admin tests selected as admin, or 13 admin tests dropped, depending on
    collection order. `make test-entity` is exactly that invocation.
    """
    admin_side = entity_markers_for_path("/repo/tests/admin/test_authorized_properties.py")
    unit_side = entity_markers_for_path("/repo/tests/unit/test_authorized_properties.py")

    assert "admin" in admin_side, f"tests/admin/ must earn 'admin', got {sorted(admin_side)}"
    assert "admin" not in unit_side, (
        f"tests/unit/ must NOT earn 'admin' from a stem it shares with tests/admin/, got {sorted(unit_side)}"
    )
    assert admin_side != unit_side, "the two paths collapsed to one answer -- the rule is keyed on the stem again"


@pytest.mark.arch_guard
def test_every_marker_the_rule_can_emit_is_a_declared_entity():
    """A pattern naming an entity that `-m` does not know selects nothing.

    Also a positive control on the pattern table: an empty union would mean the
    rule cannot mark anything, which no assertion above would catch on its own.
    """
    emitted = set()
    for path in (
        "/repo/tests/unit/test_delivery_webhook_behavioral.py",
        "/repo/tests/admin/test_zzz_no_pattern_matches_this.py",
    ):
        emitted |= entity_markers_for_path(path)

    assert emitted, "the rule emitted no markers at all -- the pattern table is not being read"
    assert emitted <= set(_ENTITY_MARKERS), (
        f"rule emits markers pytest does not know: {sorted(emitted - set(_ENTITY_MARKERS))}"
    )

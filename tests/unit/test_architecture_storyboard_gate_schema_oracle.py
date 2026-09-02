"""Oracle: the published gate column, graded against the PINNED SCHEMA.

Plan Decision 4 (#1858) commissions this by name: "Give each derived value an
oracle that does not call its producer. An assertion that re-runs the
implementation is not an oracle."

The guard this replaces did exactly that. It graded the gate column by calling
``statuses_from_vendored_index`` -> ``classify_gates`` — the function that
PRODUCED the column — so it could detect a hand-edited artifact and never a
defect in the classifier. It passed while 336 checks were published as
``gate=ON-PATH`` with an empty ``gate_reason`` whose storyboards declared a
capability gate that was never consulted.

WHY THIS DOES NOT SHARE THE IMPLEMENTATION, deliberately.
``storyboard_coverage_map.classify_gates``'s own docstring (:133-138) argues the
opposite for production code, and is right to: "the gate logic has been wrong
four separate times during this sweep ... so it exists exactly once and every
caller routes through it." An ORACLE inverts that. Its entire value is being a
SECOND derivation — from the spec — so that a classifier which is
self-consistent but wrong about the spec has something to disagree with. Do not
"fix" this duplication; it is the instrument.

INDEPENDENCE IS REQUIRED ON TWO AXES, not one:

* not ``classify_gates`` — the obvious one, and the deleted guard's mistake;
* not ``storyboard_spec.requires_capability()`` — the subtle one. Of the 336
  misgraded checks, **272 came from the extraction seam alone**: ``classify_gates``
  consulted the gate correctly for those and got ``None`` back, because the
  extractor understood one matcher of three. An oracle that asked the production
  extractor "does this storyboard declare a gate?" would have inherited that
  defect and reported 64 violations instead of 336 — missing four of every five.

So this module reads the pinned YAML itself, with its own anchored pattern.

ANCHORED to column 0, for two measured reasons. The schema also permits
``requires_capability`` on a PHASE, where it "skips only that phase"
(universal/storyboard-schema.yaml:259-279), and ``universal/deterministic-testing.yaml``
declares six phase-level gates and no storyboard-level one. And an unanchored
scan additionally matches ``universal/storyboard-schema.yaml`` — the schema file
that merely DOCUMENTS the key.

Precisely: both would inflate the DECLARING SET. At this pin neither would flip
either assertion — deterministic-testing and the schema file contribute 0 index
records between them — so the exclusions are belt-and-braces rather than
load-bearing today. They are kept because a future pin can give either file
graded checks, and then the inflated expectation would demand gating the spec
does not require.

BLIND SPOT, now covered elsewhere. Both assertions read the PUBLISHED records,
and only ON-PATH and GATED storyboards are published (``INDEXED_STATUSES``). So a
declaring storyboard misrouted to OFF-PATH leaves the index entirely and both
tests go quiet — absence is invisible to a comparison over what is present. The
floor that catches it lives in ``test_architecture_measurement_floors.py``
(``test_the_published_check_index_does_not_silently_shrink``): it pins the GATED
storyboard SET, so a storyboard leaving the index reddens there even though it
goes silent here.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.audit import storyboard_check_index  # noqa: E402
from tests.unit._storyboard_guard_env import (  # noqa: E402
    ADCP_HOME,
    DIST,
    requires_pinned_bundle,
)

# The oracle's OWN reading of the spec. Deliberately not imported from
# storyboard_spec — see the module docstring's second independence axis.
_DECLARES_GATE = re.compile(r"^requires_capability:", re.M)

# The schema file documents the key rather than declaring a gate; it is not a
# storyboard and carries no graded checks.
_SCHEMA_FILE = "universal/storyboard-schema.yaml"


pytestmark = requires_pinned_bundle


def _storyboards_declaring_a_gate() -> set[str]:
    """Storyboard paths whose OWN YAML declares a storyboard-level capability gate."""
    return {
        str(path.relative_to(DIST))
        for path in DIST.rglob("*.yaml")
        if str(path.relative_to(DIST)) != _SCHEMA_FILE and _DECLARES_GATE.search(path.read_text(encoding="utf-8"))
    }


def _published_records() -> list[dict]:
    return storyboard_check_index.jsonl(storyboard_check_index.build(REPO_ROOT, ADCP_HOME))


def _record_key(record: dict) -> tuple[str, str, str, int]:
    """A key that is unique PER RECORD, not per step.

    `(storyboard, step_id)` alone is not: a step can be graded by several check
    types, and a check type can repeat within a step (hence `ordinal`). Measured
    at the pin, the shorter key collapses 1351 records into 389 — so a set built
    from it silently deduplicates, and a set comparison over it is far weaker
    than it looks. The gated subset collapses 544 -> 179.
    """
    return (record["storyboard"], record["step_id"], record["check_type"], record["ordinal"])


def test_no_declaring_storyboard_is_published_as_ungated() -> None:
    """A storyboard that declares a capability gate must not read as fully graded.

    This is the assertion that would have failed on the 336. The pinned schema
    makes ``requires_capability`` a storyboard-level applicability gate for ANY
    tier, so a record from a declaring storyboard carrying ``ON-PATH`` with an
    empty ``gate_reason`` is a published claim that the spec contradicts.
    """
    declaring = _storyboards_declaring_a_gate()
    violations = sorted(
        f"{record['storyboard']}::{record['step_id']}"
        for record in _published_records()
        if record["storyboard"] in declaring and record["gate"] == "ON-PATH" and not record.get("gate_reason")
    )
    assert violations == [], (
        f"{len(violations)} check(s) are published as fully graded, but their storyboard declares a "
        "requires_capability gate that the classifier never applied. The spec makes the gate "
        "storyboard-level for every tier:\n  " + "\n  ".join(violations[:20])
    )


def test_gated_records_and_declaring_storyboards_are_the_same_set() -> None:
    """Every GATED record traces to a declared gate, and every declared gate gates its records.

    Strictly stronger than the violation check above, and it fails in the other
    direction too: that one catches UNDER-gating, this also catches OVER-gating —
    a record marked GATED whose storyboard declares nothing, which is what
    attributing a PHASE-level gate to its whole storyboard would produce.
    """
    declaring = _storyboards_declaring_a_gate()
    records = _published_records()
    from_declaring = {_record_key(r) for r in records if r["storyboard"] in declaring}
    gated = {_record_key(r) for r in records if r["gate"] == "GATED"}

    assert from_declaring == gated, (
        f"the GATED set ({len(gated)}) and the declaring-storyboard set ({len(from_declaring)}) disagree — "
        f"declared-but-not-gated: {sorted(from_declaring - gated)[:6]}; "
        f"gated-but-undeclared: {sorted(gated - from_declaring)[:6]}"
    )

"""The ONE marker-set derivation both routing call sites use.

The accessor's home is genuine
latitude, so the implement atom picks it and records it. It cannot live in
``tests/bdd/conftest.py`` — the liveness plugin importing conftest is a
partial-import cycle — and it cannot live in ``scripts/audit/storyboard_spec.py``,
which is stdlib-only and imports no pytest. ``tests/helpers`` is the existing
leaf both sides already import (``tests/helpers/ledger.py`` plays the same role),
so it goes here.

WHY THIS EXISTS AT ALL: a shared resolver fed by two DIFFERENT derivations
reproduces this lane's disease one layer out, and an agreement test that calls
the resolver directly cannot see it — the test supplies the argument itself. The
two sides genuinely differed:

* ``tests/bdd/conftest.py`` derived ``{m.name for m in request.node.iter_markers()}``
  — which includes auto-applied entity markers plus xfail/parametrize/slow.
* ``tests/bdd/scenario_liveness.py`` derived ``scenario.tags | feature.tags`` —
  a STRICT SUBSET.

``iter_markers`` is pinned as the contract because it is the superset, and it is
persistable: the plugin has ``request.node`` in ``pytest_bdd_before_scenario``,
so it can record exactly what the conftest routes on.
"""

from __future__ import annotations

from typing import Any


def derive_marker_names(node: Any) -> frozenset[str]:
    """Every marker name applied to *node*, as the routing contract defines it.

    Takes a pytest node (``request.node`` on both sides) rather than a tag set,
    so neither caller can quietly narrow the derivation to the tags it happens
    to have on hand.
    """
    return frozenset(marker.name for marker in node.iter_markers())

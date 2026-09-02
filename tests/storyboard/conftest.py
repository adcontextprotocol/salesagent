"""Storyboard-conformance test configuration (the storyboard-conformance job).

Grades a MEASURED run of the real ``@adcp/sdk`` storyboard runner through pytest
as ordinary parametrized tests — one per ``(protocol, track, storyboard_id,
step_id)``, the runner being executed once per protocol (mcp, a2a) against the
same agent — reusing the exact ledger/xfail/lock-test discipline established by
``tests/bdd/e2e_rest_known_failures.txt`` (Core Invariant)
rather than inventing a second comparator system.

Runner-reported skips (missing_test_controller, missing_tool, prerequisite_failed)
are native ``pytest.skip()`` in the test module, never ledgered here — only
genuine check FAILURES are known-failures-ledger entries.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.helpers.ledger import load_ledger_nodeids

_LEDGER_PATH = Path(__file__).parent / "known_failures.txt"

# Known-failing storyboard-conformance test ids — genuine production/runner gaps
# only. xfail(strict=False)'d by exact test id below. Locked by
# tests/unit/test_storyboard_ledger_state.py — keep that test in sync.
_STORYBOARD_KNOWN_FAILURES: frozenset[str] = load_ledger_nodeids(_LEDGER_PATH)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Xfail exactly the ledgered known-failing storyboard checks, non-strict.

    Non-strict: an environment-dependent xpass (e.g. a check that starts
    passing because the live stack happened to be seeded differently) must
    not fail CI — graduation is handled by updating the ledger + its lock
    test together, the same discipline as the e2e_rest ledger.
    """
    for item in items:
        if item.nodeid in _STORYBOARD_KNOWN_FAILURES:
            item.add_marker(
                pytest.mark.xfail(
                    reason="storyboard-conformance: known genuine gap (tests/storyboard/known_failures.txt)",
                    strict=False,
                )
            )

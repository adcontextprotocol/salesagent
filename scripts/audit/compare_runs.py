#!/usr/bin/env python3
"""Compare two test runs test-by-test, and refuse to summarise.

Aggregate counts cannot establish that a change was safe. A suite can hold its
passed count exactly while silently swapping which tests pass, and a change that
adds tests moves every total at once so nothing can be read from the movement.
The only claim worth making is per-test: THIS nodeid had THIS outcome before and
THIS outcome now, and here is why.

The comparison is deliberately split, because the two halves support different
claims:

PRE-EXISTING nodeids (present in both runs)
    The safety claim. A change that adds test files must not perturb a single
    test that already existed. Any outcome change here is a regression until
    individually explained -- including a change to a MORE tolerant outcome, since
    pass -> xfail and pass -> skip both remove grading while looking green.

NEW nodeids (present only in the new run)
    The accounting claim. Every one must be explained by a reason the change
    intends, grouped so the reasons can be read and judged. A new test with no
    stated reason for its outcome is unaccounted for, not "fine because it is new".

KNOWN NOISE, measured before trusting this tool. Two runs of the SAME code
disagree on about 19 of 8324 bdd_inprocess nodeids, and the disagreement is
always the transport parameter: the identical scenario appears as
``[rest-<example>]`` in one run and ``[mcp-<example>]`` in the other. It shows up
here as ~19 added and ~19 removed with no outcome change behind it. Treat a
removed/added pair at that scale as selection instability in the suite, not as a
consequence of whatever change is being graded — and treat a materially LARGER
number as real, because that is what a genuinely disappearing test looks like.

Exit status is 1 when any pre-existing test changed outcome, so this can gate.

    python3 scripts/audit/compare_runs.py <baseline-dir> <new-dir> [suite.json ...]
"""

from __future__ import annotations

import collections
import json
import pathlib
import sys


def outcomes(report: pathlib.Path) -> dict[str, tuple[str, str]]:
    """``nodeid -> (outcome, reason)`` for one suite's JSON report."""
    data = json.loads(report.read_text())
    result: dict[str, tuple[str, str]] = {}
    for test in data.get("tests", []):
        outcome = test.get("outcome", "?")
        reason = ""
        for phase in ("setup", "call", "teardown"):
            info = test.get(phase) or {}
            if info.get("longrepr"):
                reason = str(info["longrepr"])
                break
        result[test["nodeid"]] = (outcome, reason)
    return result


def compare(baseline: pathlib.Path, new: pathlib.Path, suite: str) -> int:
    old_report, new_report = baseline / suite, new / suite
    if not old_report.exists() or not new_report.exists():
        print(f"  {suite}: MISSING ({'baseline' if not old_report.exists() else 'new'}) — cannot compare")
        return 0

    old, now = outcomes(old_report), outcomes(new_report)
    shared = old.keys() & now.keys()
    added = now.keys() - old.keys()
    removed = old.keys() - now.keys()

    changed = sorted(n for n in shared if old[n][0] != now[n][0])

    print(f"\n=== {suite} ===")
    print(
        f"  baseline {len(old):6}   new {len(now):6}   shared {len(shared):6}   added {len(added):6}   removed {len(removed):6}"
    )

    if changed:
        print(f"\n  PRE-EXISTING TESTS THAT CHANGED OUTCOME: {len(changed)}  <-- each needs an explanation")
        transitions = collections.Counter((old[n][0], now[n][0]) for n in changed)
        for (before, after), count in transitions.most_common():
            print(f"    {count:6}  {before} -> {after}")
            for nodeid in [n for n in changed if (old[n][0], now[n][0]) == (before, after)][:3]:
                print(f"            e.g. {nodeid[:100]}")
                if now[nodeid][1]:
                    print(f"                 now: {now[nodeid][1].strip().splitlines()[-1][:90]}")
    else:
        print("\n  PRE-EXISTING TESTS: zero outcome changes")

    if removed:
        print(f"\n  DISAPPEARED (collected before, not now): {len(removed)}  <-- always a defect")
        for nodeid in sorted(removed)[:5]:
            print(f"    {nodeid[:104]}")

    if added:
        print(f"\n  NEW TESTS: {len(added)}, by outcome and reason")
        by_reason = collections.Counter()
        for nodeid in added:
            outcome, reason = now[nodeid]
            head = reason.strip().splitlines()[-1][:76] if reason.strip() else "(no reason recorded)"
            by_reason[(outcome, head)] += 1
        for (outcome, head), count in by_reason.most_common(14):
            print(f"    {count:6}  {outcome:9} {head}")
        if len(by_reason) > 14:
            print(f"    ... {len(by_reason) - 14} more distinct reasons")

    return 1 if (changed or removed) else 0


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    baseline, new = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
    suites = sys.argv[3:] or sorted(p.name for p in new.glob("*.json"))
    status = 0
    for suite in suites:
        status |= compare(baseline, new, suite)
    print(
        "\n"
        + (
            "REGRESSION: pre-existing tests changed outcome"
            if status
            else "CLEAN: no pre-existing test changed outcome"
        )
    )
    return status


if __name__ == "__main__":
    raise SystemExit(main())

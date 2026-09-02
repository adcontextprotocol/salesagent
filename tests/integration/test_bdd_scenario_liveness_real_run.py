"""Real-run proof for tests/bdd/scenario_liveness.py.

The pure-logic tests live in ``tests/unit/test_architecture_bdd_scenario_liveness.py``.
This file is the grounding the parent finding demands: the liveness artifact must be
emitted from an ACTUAL BDD run, and a scenario with genuinely unbound steps must be
recorded as such — not asserted against hand-constructed dataclasses.

Shells out to two narrow, fast, real ``pytest tests/bdd`` slices (selected by the
``@storyboard-v3.1`` marker so the count of scenarios discovered matches what
``scripts/audit/storyboard_coverage_map.covered_storyboards`` claims as covered):

* UC-006's ``uc006-storyboard-routing`` scenarios landed real
  step definitions for all six (none are dormant/steps-unbound any more). Five
  genuinely xfail with a ``ledgered`` reason citing a real production gap
  (provenance validation, multi-format sync status); the sixth,
  format-id-roundtrip-on-sync, genuinely passes. Proves the artifact distinguishes
  ledgered-xfail from live-pass for scenarios that both have their steps bound —
  not just the steps-bound/unbound axis.
* UC-005's format-id-roundtrip scenarios, which pass for real on all three
  in-process transports. Proves ``steps_bound=True`` and ``harness_wired=True`` for a
  scenario that isn't dormant — a guard that only ever proves the negative case isn't
  a guard.

Needs a real Postgres reachable via ``DATABASE_URL`` (the harness these scenarios
exercise creates tenants/principals/products for real) — skipped otherwise, same as
every other ``requires_db`` test in this suite.

Two further obligations are graded here (steps 1-2),
because neither is observable from the pure-logic unit tests:

* **The artifact must survive xdist.** ``tox.ini`` runs the bdd env under
  ``-n auto``; ``_RECORDS`` is a per-PROCESS global, so a sharded run's
  controller writes the artifact from an empty dict while every measurement
  sits in the workers. ``test_liveness_artifact_is_identical_under_xdist_and_
  serial`` compares a sharded run against a serial one by SET EQUALITY of
  scenario ids plus per-scenario observation counts — never by non-emptiness,
  which a "let the last worker write" non-fix would satisfy with one shard.
* **Membership is keyed on the scenario's own ``@T-*`` IDENTITY tag**, with the
  ``@storyboard-v3.1``/``@schema-v3.1`` provenance tags RECORDED as a field
  rather than used as a collection filter. A provenance retag currently
  removes a scenario from the measurement silently; an identity tag cannot
  move under a retag. Every expected id here is DERIVED in-test from the
  feature file's own tags (via the single owner, ``storyboard_spec.
  tagged_scenarios``) — a re-frozen literal id list would be exactly the
  frozen-literal artifact this lane's Core Invariant forbids.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

import pytest

from scripts.audit import storyboard_spec

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]

REPO_ROOT = Path(__file__).resolve().parents[2]
FEATURES_DIR = REPO_ROOT / "tests" / "bdd" / "features"

# The two in-process slices this module shells out to.
UC006_FILE = "tests/bdd/test_uc006_sync_creatives.py"
UC006_MARKER = "uc006-storyboard-routing"
UC005_FILE = "tests/bdd/test_uc005_discover_creative_formats.py"

# Every in-process transport the bdd suite parametrizes over with
# ``BDD_E2E_ENABLED`` popped (see _run_bdd_slice's docstring).
IN_PROCESS_TRANSPORTS = {"mcp", "a2a", "rest"}


def _slice_scenarios(feature: str, marker: str) -> list[storyboard_spec.TaggedScenario]:
    """The scenarios a ``-m <marker>`` slice of ``feature`` runs, from the feature's own tags.

    Read through ``storyboard_spec.tagged_scenarios`` — the single owner of the
    tag-line/identity-tag grammar (``_IDENT_TAG_RE``) — so this grader never
    grows a second copy of the regex, and so the expected set is regenerated
    from the tree on every run instead of frozen into this file.
    """
    return [s for s in storyboard_spec.tagged_scenarios(FEATURES_DIR, tag=f"@{marker}") if s.feature == feature]


def _identity_tags(scenarios: Sequence[storyboard_spec.TaggedScenario]) -> set[str]:
    return {s.identifier for s in scenarios}


def _run_bdd_slice(tmp_path: Path, test_file: str, marker_expr: str, *, extra_args: Sequence[str] = ()) -> dict:
    """Shell out to a real, narrow pytest slice with a deliberately isolated env.

    This test's assertions pin an exact 3-way in-process transport set
    (mcp/a2a/rest). The nested subprocess must not silently inherit
    ``BDD_E2E_ENABLED`` from whatever ambient environment this test itself
    runs under (e.g. run_all_tests.sh, which sets it once the Docker e2e
    stack is up for the outer suite) — that would make the nested slice
    additionally parametrize over e2e_rest, and this test's fixed-3-transport
    assertions would fail for reasons unrelated to what they're testing.
    """
    artifact = tmp_path / "liveness.json"
    tmp_path.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.pop("BDD_E2E_ENABLED", None)
    env["BDD_LIVENESS_ARTIFACT"] = str(artifact)
    env.setdefault("ADCP_TESTING", "true")
    # Measure EVERY transport. The BDD conftest's single-transport optimization
    # deselects mcp/rest for any scenario carrying a strict xfail, which is
    # exactly what a ledgered scenario carries — so without this the artifact
    # would record one observation for every ledgered scenario and the
    # "not silently zero, not silently one" assertion below would be measuring
    # the optimization rather than the scenario. A later split moved these gaps from
    # inline pytest.xfail() (invisible to that optimization) to ledger tags,
    # which is what surfaced it.
    env["BDD_ALL_TRANSPORTS"] = "1"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            test_file,
            "-m",
            marker_expr,
            "-p",
            "no:cacheprovider",
            "-q",
            *extra_args,
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert artifact.is_file(), (
        f"pytest subprocess did not write the liveness artifact to {artifact}.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    return json.loads(artifact.read_text(encoding="utf-8"))


# Measured 65.17s on an idle 40-core box against CI's --timeout=60 (ci.yml
# "Integration (other)"). Same class as test_liveness_artifact_is_identical_
# under_xdist_and_serial below: a real nested-pytest-subprocess cost, not a
# hang. Scoped rather than raising the job's CLI timeout, same reasoning.
@pytest.mark.timeout(300)
def test_real_run_records_uc006_storyboard_scenarios_as_ledgered_or_live(tmp_path: Path) -> None:
    """The UC-006 storyboard-routing slice is measured in full, and its
    ``@storyboard-v3.1``-tagged members have real, bound step definitions
    — none are dormant/steps-unbound. Five genuinely xfail
    with a real, ledgered production-gap reason (not StepDefinitionNotFoundError);
    the sixth, format-id-roundtrip-on-sync, genuinely passes. Proves the artifact
    tracks real state, not a frozen count, and distinguishes ledgered-xfail from
    live-pass even though both have steps_bound=True."""
    data = _run_bdd_slice(tmp_path, UC006_FILE, UC006_MARKER)
    scenarios = {s["scenario_id"]: s for s in data["scenarios"]}

    # DERIVED, not frozen: every scenario the slice runs carries a `@T-*` identity
    # tag, and identity — not provenance — is what the artifact keys membership on.
    # The two `@schema-v3.1`-retagged members (provenance-claim-contradicted,
    # creative-reception-stateful-render) are part of this slice and must be
    # measured; a provenance retag must not be able to delete a scenario from the
    # measurement.
    slice_scenarios = _slice_scenarios("BR-UC-006-sync-creatives.feature", UC006_MARKER)
    assert set(scenarios) == _identity_tags(slice_scenarios)

    # The scenarios whose detailed ledgered/live behaviour this test pins — again
    # derived from the feature's own tags, not listed here.
    storyboard_tagged = {s.identifier for s in slice_scenarios if storyboard_spec.TAG in s.tags}
    # An EXACT partition, not a relaxed "either live or ledgered" predicate: the
    # latter would satisfy the letter of the assertion while destroying its
    # regression-detecting power.
    #
    # TWO live members since the split of @T-UC-006-storyboard-multi-format-sync.
    # Its ACTION obligations were dead code — the status gap's xfail aborted the
    # scenario before they ran — so the split left them live here and moved the
    # status obligations to their own ledgered scenario. A single live id was
    # correct only while that scenario was wholly ledgered.
    live_scenario_ids = {
        "T-UC-006-storyboard-format-id-roundtrip-on-sync",
        "T-UC-006-storyboard-multi-format-sync",
    }
    assert live_scenario_ids <= storyboard_tagged, (
        f"expected live members missing from the slice: {sorted(live_scenario_ids - storyboard_tagged)}"
    )

    for scenario_id in sorted(storyboard_tagged):
        record = scenarios[scenario_id]
        # Every scenario has real steps bound now — the dormant/unbound axis is
        # fully retired for this feature.
        assert record["steps_bound"] is True, f"{scenario_id} unexpectedly reports steps_bound=False"
        assert record["unbound_steps"] == [], f"{scenario_id} unexpectedly reports unbound step text"
        if scenario_id in live_scenario_ids:
            assert record["ledgered"] is False
            assert all(o["outcome"] == "passed" for o in record["observations"])
            assert all(o["reason_category"] == "live" for o in record["observations"])
        else:
            assert record["ledgered"] is True, f"{scenario_id} unexpectedly reports ledgered=False"
            assert all(o["outcome"] == "xfailed" for o in record["observations"])
            assert all(o["reason_category"] == "ledgered" for o in record["observations"])
            assert all("SPEC-PRODUCTION GAP" in o["reason"] for o in record["observations"]), (
                f"{scenario_id}'s xfail reason doesn't cite a real production gap"
            )
        # Real transports actually ran (not silently zero, not silently one).
        assert {o["transport"] for o in record["observations"]} == {"mcp", "a2a", "rest"}


def test_real_run_records_uc005_format_id_roundtrip_scenarios_as_live(tmp_path: Path) -> None:
    """A scenario that is NOT dormant reports steps_bound=True/harness_wired=True — the
    guard proves both directions, not only the failure case."""
    data = _run_bdd_slice(tmp_path, UC005_FILE, "storyboard-v3.1")
    scenarios = {s["scenario_id"]: s for s in data["scenarios"]}

    assert set(scenarios) == _identity_tags(
        _slice_scenarios("BR-UC-005-discover-creative-formats.feature", "storyboard-v3.1")
    )
    for scenario_id, record in scenarios.items():
        assert record["steps_bound"] is True, f"{scenario_id} unexpectedly reports steps_bound=False"
        assert record["unbound_steps"] == []
        assert record["harness_wired"] is True
        assert record["ledgered"] is False
        assert {o["transport"] for o in record["observations"]} == IN_PROCESS_TRANSPORTS
        assert all(o["outcome"] == "passed" for o in record["observations"])


# Measured 62.52s on an idle 40-core box against CI's --timeout=60. Same class
# as the two siblings above/below: a real nested-pytest-subprocess cost.
@pytest.mark.timeout(300)
def test_provenance_tag_is_a_recorded_field_not_a_collection_filter(tmp_path: Path) -> None:
    """A ``@schema-v3.1`` retag must not delete a scenario from the measurement.

    ``scenario_liveness._TAG`` is used at ``pytest_bdd_before_scenario`` as an
    early-``return`` COLLECTION FILTER, so the two UC-006 scenarios retagged
    ``@schema-v3.1`` are invisible to the artifact — the instrument reports on a
    population that a tag edit can silently shrink. A later change converts that filter
    into a recorded field: membership is the scenario's ``@T-*`` identity tag
    (which a provenance retag cannot move), and the provenance tags are carried
    on the record as data.

    Graded on the two retagged members specifically, and on what the artifact
    then says about them: both are genuinely DORMANT today (pytest-bdd raises
    ``StepDefinitionNotFoundError`` on their first Given), so honest measurement
    must report them ``steps_bound=False`` with the unbound step named — the
    exact fact the current filter hides.
    """
    data = _run_bdd_slice(tmp_path, UC006_FILE, UC006_MARKER)
    scenarios = {s["scenario_id"]: s for s in data["scenarios"]}

    slice_scenarios = _slice_scenarios("BR-UC-006-sync-creatives.feature", UC006_MARKER)
    retagged = [s for s in slice_scenarios if storyboard_spec.TAG not in s.tags]
    # The premise of this test: the slice really does contain members whose
    # provenance tag is not @storyboard-v3.1. If a retag ever removes them, this
    # fails loudly rather than passing vacuously over an empty list.
    assert {s.identifier for s in retagged} == {
        "T-UC-006-storyboard-provenance-claim-contradicted",
        "T-UC-006-storyboard-creative-reception-stateful-render",
    }

    unbound_given = {
        "T-UC-006-storyboard-provenance-claim-contradicted": (
            'the Buyer Agent submits a creative claiming digital_source_type "digital_capture"'
        ),
        "T-UC-006-storyboard-creative-reception-stateful-render": (
            "the Buyer Agent pushes creative assets to a stateful sales agent"
        ),
    }

    for scenario in retagged:
        record = scenarios[scenario.identifier]
        # The provenance tag is DATA on the record, not the membership predicate.
        assert set(record["tags"]) == {t.lstrip("@") for t in scenario.tags}
        # Dormancy, measured — this is what the collection filter currently hides.
        assert record["steps_bound"] is False
        assert unbound_given[scenario.identifier] in record["unbound_steps"]
        assert record["harness_wired"] is None
        assert {o["transport"] for o in record["observations"]} == IN_PROCESS_TRANSPORTS
        assert all(o["outcome"] == "xfailed" for o in record["observations"])
        assert all(o["reason_category"] == "no_steps_bound" for o in record["observations"])


# Scoped budget, NOT a global relaxation. Every other test here shells out to ONE
# nested pytest session; this one shells out to TWO (serial, then ``-n 2``) plus
# xdist's worker bootstrap, and that is irreducible — the comparison IS the
# grader. Measured: 37.2s (M-series laptop) / 49.1s (x86 Linux CI box) here,
# against 20.7s/19.3s/10.0s and 25.0s/24.0s/14.3s for its single-run siblings. It
# is the only test in this module that crosses the 60s budget CI's integration job
# passes (``.github/workflows/ci.yml`` ``--timeout=60``) once a GitHub-hosted
# runner's slower cores are applied — exactly what fork run 32152198573 measured
# ("Failed: Timeout (>60.0s)") while the siblings passed.
#
# The alternative the design considered — shrinking the measured slice — was
# rejected: the slice's 8 scenarios x 3 in-process transports = 24 items under
# ``--dist load`` are what force a genuine shard-and-merge, and set equality of
# scenario ids PLUS per-scenario observation counts is the whole assertion.
# Trading that for speed would buy a green mark with a weaker grader.
#
# 300s is ~8x the measured cost, leaves the job's 25-minute budget untouched, and
# the marker overrides the CLI ``--timeout`` for this item only (pytest-timeout
# precedence: marker > CLI > ini), so no other test's budget moves.
@pytest.mark.timeout(300)
def test_liveness_artifact_is_identical_under_xdist_and_serial(tmp_path: Path) -> None:
    """A sharded run must publish the same measurement a serial run does.

    ``tox.ini:138`` runs the bdd env under ``-n {env:BDD_XDIST_N:auto}``, but
    ``scenario_liveness._RECORDS`` is a per-PROCESS module global: every worker
    accumulates its own records and the controller — which has none — writes the
    artifact last. The published file is therefore EMPTY in exactly the
    configuration CI uses.

    ``--dist load`` is PINNED here deliberately. ``tox.ini`` pairs ``-n`` with
    ``--dist loadfile``, and mirroring that "for fidelity" would put this
    single-file slice entirely on ONE worker — a last-writer-wins non-fix would
    then pass this grader vacuously. Under ``--dist load`` the slice's 8
    scenarios x 3 in-process transports = 24 items genuinely split across the
    two workers, so only a real shard-and-merge satisfies the comparison.

    The comparison itself is SET EQUALITY of scenario ids plus per-scenario
    observation counts, never non-emptiness: an artifact carrying one worker's
    shard is non-empty and still wrong.
    """
    serial = _run_bdd_slice(tmp_path / "serial", UC006_FILE, UC006_MARKER, extra_args=("-p", "no:randomly"))
    sharded = _run_bdd_slice(
        tmp_path / "sharded", UC006_FILE, UC006_MARKER, extra_args=("-p", "no:randomly", "-n", "2", "--dist", "load")
    )

    serial_records = {s["scenario_id"]: s for s in serial["scenarios"]}
    sharded_records = {s["scenario_id"]: s for s in sharded["scenarios"]}

    assert set(sharded_records) == set(serial_records), (
        f"-n 2 --dist load published {len(sharded_records)} scenario(s); serial published "
        f"{len(serial_records)}. The sharded run's measurements never reached the process "
        "that wrote the artifact."
    )

    # Anti-vacuity: the serial baseline must itself be the full slice, otherwise
    # "sharded == serial" could be satisfied by two equally-broken runs.
    assert set(serial_records) == _identity_tags(_slice_scenarios("BR-UC-006-sync-creatives.feature", UC006_MARKER))

    assert {sid: len(r["observations"]) for sid, r in sharded_records.items()} == {
        sid: len(r["observations"]) for sid, r in serial_records.items()
    }

    for scenario_id, serial_record in serial_records.items():
        sharded_record = sharded_records[scenario_id]
        assert {o["transport"] for o in sharded_record["observations"]} == {
            o["transport"] for o in serial_record["observations"]
        }
        # The merge must not lose or invert the joined verdicts either.
        assert sharded_record["steps_bound"] == serial_record["steps_bound"]
        assert sharded_record["unbound_steps"] == serial_record["unbound_steps"]
        assert sharded_record["ledgered"] == serial_record["ledgered"]
        assert sharded_record["harness_wired"] == serial_record["harness_wired"]

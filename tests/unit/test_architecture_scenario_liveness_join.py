"""Regression tests for scripts/audit/scenario_liveness_join.py.

Pure-logic, offline tests for the join primitives: the ``ENV_ROUTES`` registry data
lookup (never reason-text matching), the artifact loader's conservative
missing-file/missing-scenario behavior, and ``ScenarioLiveness.graded_by_live_scenario``'s
three-way AND. The real end-to-end proof — that this join actually changes
``storyboard_check_index.build()``'s published totals and per-record fields — lives in
``tests/unit/test_architecture_storyboard_check_index_liveness.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.audit import scenario_liveness_join as slj


def _route(xfail_reason: str | None = None, *, uc: str | None = None, when=None) -> object:
    """A minimal stand-in for tests.bdd.conftest.EnvRoute.

    The join resolves through ``storyboard_spec.resolve_env_route``,
    which reads ``when`` and ``uc`` off a row (and the caller reads
    ``xfail_reason``), so a stand-in carries all three.
    """

    class _Route:
        pass

    r = _Route()
    r.xfail_reason = xfail_reason
    r.uc = uc
    r.when = when
    return r


# --- registry_wired: data lookup, no prose parsing ---


def test_registry_wired_exact_scenario_tag_match() -> None:
    tag = "T-UC-003-storyboard-media-buy-not-found"
    routes = [_route(when=lambda m, t=tag: t in m)]
    assert slj.registry_wired(frozenset({tag}), routes) is True


def test_registry_wired_uc_bucket_match() -> None:
    routes = [_route(uc="UC-005")]
    assert slj.registry_wired(frozenset({"T-UC-005-storyboard-baseline-format-id-object-shape"}), routes) is True


def test_registry_wired_placeholder_row_is_not_wired() -> None:
    """An EnvRoute with xfail_reason set is a registered placeholder, not a real wire."""
    routes = [_route(xfail_reason="not built yet", uc="UC-999")]
    assert slj.registry_wired(frozenset({"T-UC-999-storyboard-something"}), routes) is False


def test_registry_wired_no_match_at_all() -> None:
    routes = [_route(uc="UC-005")]
    assert slj.registry_wired(frozenset({"T-UC-006-storyboard-multi-format-sync"}), routes) is False


def test_registry_wired_non_uc_tag_with_no_row_is_not_wired() -> None:
    assert slj.registry_wired(frozenset({"T-ADMIN-something"}), []) is False


# --- load_artifact: conservative on absence ---


def test_load_artifact_missing_file_returns_empty() -> None:
    assert slj.load_artifact(Path("/nonexistent/does-not-exist.json")) == {}


def test_load_artifact_reads_scenarios_keyed_by_id(tmp_path: Path) -> None:
    path = tmp_path / "liveness.json"
    path.write_text(
        json.dumps({"scenarios": [{"scenario_id": "T-UC-005-x", "steps_bound": True, "ledgered": False}]}),
        encoding="utf-8",
    )
    loaded = slj.load_artifact(path)
    assert set(loaded) == {"T-UC-005-x"}
    assert loaded["T-UC-005-x"]["steps_bound"] is True


def test_default_artifact_path_honors_env_override(monkeypatch) -> None:
    monkeypatch.setenv("BDD_LIVENESS_ARTIFACT", "/tmp/somewhere/liveness.json")
    assert slj.default_artifact_path() == Path("/tmp/somewhere/liveness.json")


def test_default_artifact_path_falls_back_to_test_results(monkeypatch) -> None:
    monkeypatch.delenv("BDD_LIVENESS_ARTIFACT", raising=False)
    assert slj.default_artifact_path() == Path("test-results") / "bdd_scenario_liveness.json"


# --- ScenarioLiveness.graded_by_live_scenario: the strict three-way AND ---


def test_graded_requires_measured_this_run() -> None:
    fact = slj.ScenarioLiveness(
        scenario_id="s", steps_bound=True, registry_wired=True, ledgered=False, measured_this_run=False
    )
    assert fact.graded_by_live_scenario is False


def test_graded_requires_steps_bound() -> None:
    fact = slj.ScenarioLiveness(
        scenario_id="s", steps_bound=False, registry_wired=True, ledgered=False, measured_this_run=True
    )
    assert fact.graded_by_live_scenario is False


def test_graded_requires_registry_wired() -> None:
    """steps_bound alone (the parent finding's original 4-of-21 measurement) is not enough."""
    fact = slj.ScenarioLiveness(
        scenario_id="s", steps_bound=True, registry_wired=False, ledgered=False, measured_this_run=True
    )
    assert fact.graded_by_live_scenario is False


def test_graded_true_when_all_three_hold() -> None:
    fact = slj.ScenarioLiveness(
        scenario_id="s", steps_bound=True, registry_wired=True, ledgered=False, measured_this_run=True
    )
    assert fact.graded_by_live_scenario is True


# --- build_index: the whole join, offline (env_routes/artifact_path injected) ---


def test_build_index_scenario_absent_from_artifact_is_conservative() -> None:
    """A scenario the artifact never observed is unmeasured, not silently live."""
    index = slj.build_index({"T-UC-005-x"}, artifact_path=Path("/nonexistent.json"), env_routes=[_route(uc="UC-005")])
    fact = index["T-UC-005-x"]
    assert fact.measured_this_run is False
    assert fact.steps_bound is False
    # NOT wired. Routing keys are on the MARKER SET, and an unmeasured
    # scenario has no record to carry one — so there is nothing to route on and
    # reporting it wired would be a guess. Consistent either way, because
    # graded_by_live_scenario already ANDs measured_this_run.
    assert fact.registry_wired is False
    assert fact.graded_by_live_scenario is False


def test_build_index_joins_artifact_and_registry(tmp_path: Path) -> None:
    path = tmp_path / "liveness.json"
    path.write_text(
        json.dumps(
            {
                "scenarios": [
                    {
                        "scenario_id": "T-UC-005-x",
                        "steps_bound": True,
                        "ledgered": False,
                        # The record carries the marker set: since the shared-contract change the join
                        # routes on markers (the conftest's predicates key on them),
                        # and the artifact is its only marker source.
                        "marker_names": ["T-UC-005-x"],
                    },
                    {
                        "scenario_id": "T-UC-006-y",
                        "steps_bound": True,
                        "ledgered": True,
                        "marker_names": ["T-UC-006-y"],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    index = slj.build_index(
        {"T-UC-005-x", "T-UC-006-y"},
        artifact_path=path,
        env_routes=[_route(uc="UC-005")],  # UC-006 deliberately absent from the registry
    )
    assert index["T-UC-005-x"].graded_by_live_scenario is True
    # UC-006 has steps bound and is even ledgered, but its UC bucket isn't a
    # registry row -- registry_wired stays False and it must NOT count as graded.
    assert index["T-UC-006-y"].registry_wired is False
    assert index["T-UC-006-y"].graded_by_live_scenario is False
    assert index["T-UC-006-y"].ledgered is True

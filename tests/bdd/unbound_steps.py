"""Skip a scenario that has any step with no definition behind it.

Executing such a scenario is pointless. pytest-bdd raises
``StepDefinitionNotFoundError`` at the first unbound step, so nothing after it
runs: no tool is dispatched, no response is produced, and every assertion the
scenario carries is unreachable. The failure reports one missing sentence, which
is a fact about the HARNESS, not about production — and it is indistinguishable
in a summary from a scenario that ran and found a real defect.

SKIP, not xfail, for the same reason the undispatchable-tool rule skips. An xfail
asserts "this ran and failed as expected". A scenario that stops at step one did
not run in any useful sense, and calling its non-execution an expected failure
overstates what was measured.

MEASURED, NEVER INFERRED, and reusing pytest-bdd's own lookup rather than a
second opinion. ``get_step_function`` is the exact call ``_execute_scenario``
makes to decide whether to raise, so a step this module calls unbound is
precisely a step the runner would have failed on. A private reimplementation
would be free to disagree with the runner, and the disagreement would show up as
scenarios that skip but would have run, or run but instantly die.

Checks EVERY step, not just the first the runner would hit, so the skip reason
names the full set of sentences that need writing. That list is the work
inventory for wiring a use case, and truncating it at the first miss would hide
most of the job.

Runs in ``pytest_bdd_before_scenario`` — after fixtures resolve (so the lookup
can see the step definitions) and before any step body executes (so nothing has
happened yet that a skip would abandon halfway).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from pytest_bdd.scenario import get_step_function

if TYPE_CHECKING:
    from _pytest.fixtures import FixtureRequest
    from pytest_bdd.parser import Feature, Scenario


def unbound_step_names(request: FixtureRequest, scenario: Scenario) -> list[str]:
    """Every step of *scenario* with no step definition bound, in scenario order."""
    return [step.name for step in scenario.steps if get_step_function(request, step) is None]


def pytest_bdd_before_scenario(request: FixtureRequest, feature: Feature, scenario: Scenario) -> None:
    """Skip before the first step runs when any step of this scenario is unbound.

    Deliberately ordered AFTER ``tests/bdd/scenario_liveness.py``'s hook of the
    same name in plugin registration, so the liveness instrument still records
    ``steps_bound=False`` and the unbound sentences for this scenario. Skipping
    it must not delete it from the measurement — the count of unwired scenarios
    is the thing being tracked, and an instrument that stops seeing them the
    moment they are skipped would report the problem shrinking as it is hidden.
    """
    unbound = unbound_step_names(request, scenario)
    if not unbound:
        return

    shown = ", ".join(repr(name) for name in unbound[:3])
    more = f" (+{len(unbound) - 3} more)" if len(unbound) > 3 else ""
    pytest.skip(f"{len(unbound)} step(s) have no definition, so this scenario cannot execute: {shown}{more}")

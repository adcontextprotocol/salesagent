"""Regression: a Then step must not PASS when the dispatch it grades errored.

Two steps in ``tests/bdd/steps/domain/uc011_accounts.py`` wrapped every assertion
in ``if resp is not None:`` with no ``else``. On an errored dispatch
``payload_or_none`` returns ``None``, the body is skipped, and the step returns
normally having asserted nothing — a green scenario that graded nothing.

That shape is invisible in a test report: the scenario is not skipped, not
xfailed, and not failed. It reads exactly like a scenario that verified its
claim. The only way to see it is to call the step with an errored context and
observe that it returns.

The contract these tests pin is deliberately weaker than "the step raises
AssertionError", because the two correct answers differ:

* ``then_no_dry_run_include`` must REQUIRE a payload — its error-variant twin
  ``then_no_dry_run_field`` grades the error path under its own step text, so
  there is nothing for this step to say about an error.
* ``then_context_identical`` must grade the error path the way its sibling
  ``then_response_includes_context`` already does: read the echoed context off
  the error object, and ``pytest.xfail`` explicitly when production cannot yet
  supply one (GH #1417).

``pytest.xfail`` raises, so both correct answers agree on the one property that
matters and that the bug violates: **the step must not return normally when the
dispatch errored**. Asserting the exception TYPE would forbid the xfail answer
and force the wrong fix.
"""

from __future__ import annotations

import pytest

from tests.bdd.steps.domain import uc011_accounts

# The AdCP error a real errored dispatch records. Any object works — the steps
# never inspect it today, which is the defect — so use something that would make
# an accidental attribute read obvious rather than silently truthy.
_RECORDED_ERROR = RuntimeError("dispatch failed: VALIDATION_ERROR")


def _errored_ctx(**extra: object) -> dict:
    """A context shaped exactly like a dispatch that errored.

    No ``result`` and no ``self_dispatched_response``, so ``payload_or_none``
    returns ``None``; ``error`` set, so a step that looks has something to find.
    """
    return {"error": _RECORDED_ERROR, **extra}


@pytest.mark.parametrize(
    ("step", "ctx"),
    [
        pytest.param(
            uc011_accounts.then_no_dry_run_include,
            _errored_ctx(),
            id="then_no_dry_run_include",
        ),
        pytest.param(
            uc011_accounts.then_context_identical,
            # sent_context is present so the step gets PAST its own guard and
            # reaches the vacuous branch; without it the step would fail for an
            # unrelated reason and this test would pass for the wrong one.
            _errored_ctx(sent_context={"tenant": "t1"}),
            id="then_context_identical",
        ),
    ],
)
def test_step_does_not_return_normally_on_an_errored_dispatch(step, ctx: dict) -> None:
    """The step must react to an errored dispatch — raise, or xfail. Not return."""
    with pytest.raises(BaseException) as caught:  # noqa: PT011 - see the module docstring
        step(ctx)

    # A step that reached its own `assert sent is not None`-style guard and died
    # there would satisfy `pytest.raises` without grading anything. Pin that the
    # failure is ABOUT the missing payload or the error, not about the fixture.
    assert not isinstance(caught.value, KeyError), (
        f"{step.__name__} raised KeyError — it died on context plumbing, not on the errored dispatch"
    )

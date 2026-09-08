"""Oracle: the webhook circuit breaker's three env knobs actually configure it.

``_configured_breaker`` and its three knobs
(``ADCP_WEBHOOK_BREAKER_FAILURE_THRESHOLD``, ``_SUCCESS_THRESHOLD``,
``_TIMEOUT_SECONDS``) shipped with no test at all — ``grep -rn
"ADCP_WEBHOOK_BREAKER" tests/`` returned zero before this file.

The unset arm is the one that matters most, and it is the reason this is not
ceremony. ``docker-compose.e2e.yml`` supplies a shorter recovery timeout so the
e2e stack can reach HALF_OPEN without spending 60 real seconds per scenario. If
a knob stopped being read — renamed, typo'd, or moved to an import-time read
that freezes the first value — the stack would go on looking configured while
running the shipped 60-second default, and every breaker scenario would either
slow down or silently stop reaching the state it grades. Nothing would fail.

The rejection arms are graded too, because ``env_float``'s contract is to fall
back LOUDLY rather than honour a non-positive or non-numeric value: a knob set
to ``0`` must yield the default, not zero. Silently honouring it would give a
breaker that never opens or never recovers.
"""

from __future__ import annotations

import pytest

from src.services.webhook_delivery_service import (
    _BREAKER_FAILURE_THRESHOLD_ENV,
    _BREAKER_SUCCESS_THRESHOLD_ENV,
    _BREAKER_TIMEOUT_ENV,
    _DEFAULT_BREAKER_FAILURE_THRESHOLD,
    _DEFAULT_BREAKER_SUCCESS_THRESHOLD,
    _DEFAULT_BREAKER_TIMEOUT_SECONDS,
    _configured_breaker,
)

pytestmark = pytest.mark.unit

# (env var, breaker attribute, shipped default, a distinct value to set).
# The set values are deliberately unequal to each other AND to every default, so
# a breaker that wired two knobs to the same field cannot pass.
_KNOBS = [
    (_BREAKER_FAILURE_THRESHOLD_ENV, "failure_threshold", _DEFAULT_BREAKER_FAILURE_THRESHOLD, 11),
    (_BREAKER_SUCCESS_THRESHOLD_ENV, "success_threshold", _DEFAULT_BREAKER_SUCCESS_THRESHOLD, 7),
    (_BREAKER_TIMEOUT_ENV, "timeout_seconds", _DEFAULT_BREAKER_TIMEOUT_SECONDS, 13),
]


@pytest.mark.parametrize(("env_var", "attribute", "default", "configured"), _KNOBS)
def test_a_set_knob_reaches_the_breaker(env_var, attribute, default, configured, monkeypatch) -> None:
    """Setting the variable changes the field it names, and only that field."""
    monkeypatch.setenv(env_var, str(configured))

    breaker = _configured_breaker()

    assert getattr(breaker, attribute) == configured, (
        f"{env_var}={configured} did not reach breaker.{attribute} "
        f"(got {getattr(breaker, attribute)!r}) — the knob is not wired"
    )
    # Every OTHER field keeps its default: a knob wired to the wrong attribute
    # would satisfy the assertion above on some other run and never be caught.
    for other_var, other_attr, other_default, _ in _KNOBS:
        if other_var == env_var:
            continue
        assert getattr(breaker, other_attr) == other_default, (
            f"setting {env_var} also changed breaker.{other_attr} — the knobs are crossed"
        )


@pytest.mark.parametrize(("env_var", "attribute", "default", "_configured"), _KNOBS)
def test_an_unset_knob_falls_back_to_the_shipped_default(env_var, attribute, default, _configured, monkeypatch) -> None:
    """With nothing set, the breaker carries the shipped policy."""
    monkeypatch.delenv(env_var, raising=False)

    assert getattr(_configured_breaker(), attribute) == default


@pytest.mark.parametrize(("env_var", "attribute", "default", "_configured"), _KNOBS)
@pytest.mark.parametrize("rejected", ["0", "-1", "not-a-number", ""])
def test_a_rejected_value_falls_back_rather_than_being_honoured(
    env_var, attribute, default, _configured, rejected, monkeypatch
) -> None:
    """``env_float`` refuses non-positive and non-numeric values, loudly.

    Honouring ``0`` would give a breaker with a zero failure threshold (opens on
    nothing) or a zero recovery timeout (never stays open) — both worse than the
    default, and both invisible without this arm.
    """
    monkeypatch.setenv(env_var, rejected)

    assert getattr(_configured_breaker(), attribute) == default, (
        f"{env_var}={rejected!r} was honoured instead of rejected"
    )

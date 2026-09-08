"""The mock adapter's injected-failure knob selects an exception CLASS, not a recovery.

``_raise_injected_failure`` used to build ``AdCPAdapterError(..., recovery=<the
injected string>)``. That was the last place a free string became a wire recovery:
whatever a BDD Given step wrote into ``test_behavior`` reached the buyer verbatim,
including spellings that are not classifications at all — ``"retryable"`` shipped
that way from two steps.

``recovery`` is now a read-only property derived from the pinned enumMetadata, so
the knob cannot set it. It selects the class whose PINNED recovery is the value
asked for, which is the same invariant every production raise site now lives
under: possession of the class is the proof.

These grade that mapping directly. It is otherwise ungraded — the in-process BDD
suites inject through the mocked adapter and never reach this code, and the e2e
scenarios that do reach it assert non-persistence and the presence of a
suggestion, never the emitted class. A wrong mapping here would reach a buyer
through the Docker-hosted adapter with no test disagreeing.
"""

from __future__ import annotations

import pytest

from src.adapters.mock_ad_server import MockAdServer
from src.core.exceptions import (
    AdCPAdapterError,
    AdCPConfigurationError,
    AdCPError,
    AdCPValidationError,
)


def _adapter_with_behavior(monkeypatch: pytest.MonkeyPatch, behavior: dict) -> MockAdServer:
    """A MockAdServer whose DB-backed test_behavior is *behavior*.

    Patches only the DB read: the mapping under test is pure, and standing up an
    AdapterConfig row would grade the repository rather than the classification.
    """
    adapter = MockAdServer.__new__(MockAdServer)
    monkeypatch.setattr(MockAdServer, "_read_test_behavior", lambda self: behavior)
    return adapter


@pytest.mark.parametrize(
    ("injected", "expected_cls", "expected_code", "expected_recovery"),
    [
        ("transient", AdCPAdapterError, "SERVICE_UNAVAILABLE", "transient"),
        ("terminal", AdCPConfigurationError, "CONFIGURATION_ERROR", "terminal"),
        ("correctable", AdCPValidationError, "VALIDATION_ERROR", "correctable"),
    ],
)
def test_knob_selects_the_class_whose_pinned_recovery_it_names(
    monkeypatch: pytest.MonkeyPatch,
    injected: str,
    expected_cls: type[AdCPError],
    expected_code: str,
    expected_recovery: str,
) -> None:
    """Each pinned classification maps to the class that DERIVES it."""
    adapter = _adapter_with_behavior(monkeypatch, {"fail_on_create": True, "recovery": injected})

    with pytest.raises(expected_cls) as excinfo:
        adapter._raise_injected_failure("fail_on_create")

    exc = excinfo.value
    assert exc.error_code == expected_code
    assert exc.recovery == expected_recovery, (
        f"injecting {injected!r} produced {exc.error_code}/{exc.recovery} — the knob must select "
        f"the class the pin classifies {injected!r}, not merely a class that looks related"
    )


def test_the_default_knob_is_the_transient_adapter_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """An injection with no recovery key keeps the historical behaviour."""
    adapter = _adapter_with_behavior(monkeypatch, {"fail_on_create": True})

    with pytest.raises(AdCPAdapterError) as excinfo:
        adapter._raise_injected_failure("fail_on_create")

    assert excinfo.value.recovery == "transient"


def test_a_non_classification_knob_fails_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    """A value outside the pinned vocabulary raises instead of shipping.

    ``"retryable"`` is the live example — two BDD steps injected it, and before the
    mapping it reached the wire as a recovery no spec defines. No Quiet Failures:
    an unmappable knob is a broken test fixture and must say so, not silently pick
    a class.
    """
    adapter = _adapter_with_behavior(monkeypatch, {"fail_on_create": True, "recovery": "retryable"})

    with pytest.raises(AdCPConfigurationError, match="not a recovery classification"):
        adapter._raise_injected_failure("fail_on_create")


def test_the_flag_gates_the_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    """No flag, no failure — the injection is opt-in per operation."""
    adapter = _adapter_with_behavior(monkeypatch, {"recovery": "terminal"})

    adapter._raise_injected_failure("fail_on_create")  # must not raise


def test_suggestion_stays_first_class(monkeypatch: pytest.MonkeyPatch) -> None:
    """The suggestion is lifted out of details onto the error's own field.

    Graded alongside the class because the two travel through the same rewrite: a
    suggestion buried in ``details`` yields a non-conformant wire error with an
    empty top-level ``suggestion``.
    """
    adapter = _adapter_with_behavior(
        monkeypatch,
        {"fail_on_upload": True, "recovery": "terminal", "error_details": {"suggestion": "Fix the thing"}},
    )

    with pytest.raises(AdCPConfigurationError) as excinfo:
        adapter._raise_injected_failure("fail_on_upload")

    assert excinfo.value.suggestion == "Fix the thing"

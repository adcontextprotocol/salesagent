"""Egress backoff/flag helpers shared by the outbound-HTTP integration tests.

Extracted from ``tests/integration/test_outbound_http.py`` (GH #1802 merge). That module
has 67 real tests of its own, so it was simultaneously a test suite and a helper library
for fifteen other modules — the shape ``test_architecture_no_cross_test_module_imports``
forbids, because importing it drags its whole suite (and its fixtures) into an unrelated
module's collection. The symbols are unchanged; only their home is.
"""

from __future__ import annotations

BACKOFF_BASE_ENV = "ADCP_OUTBOUND_BACKOFF_BASE_SECONDS"


def set_flags(monkeypatch, *, private: bool = False) -> None:
    """Set the private-range escape hatch explicitly.

    Always writing it — including the off case, as the literal ``"false"`` the
    repo's ``== "true"`` convention treats as off — pins the test against
    ambient environment rather than assuming the variable is unset. The name
    and literal come from :func:`tests.helpers.egress_hatches.egress_hatch_env`,
    which is the only place in the test tree that spells it.

    There is no ``insecure`` parameter anymore (GH #1757): the scheme
    gate is unconditional in production, so there is nothing left to relax —
    a caller that used to pass ``insecure=True`` needed a real https origin
    (see the ``local_origin_tls`` fixture) instead.
    """
    for name, value in egress_hatch_env(private=private).items():
        monkeypatch.setenv(name, value)


def pin_jitter(monkeypatch, value: float) -> list[tuple]:
    """Freeze the seam's jitter draw and record how it was called.

    BR-RULE-029's jitter is a real ``random.uniform(0, 1)`` draw, so any test
    that asserts a delay's magnitude has to pin it — otherwise the assertion is
    graded against a number the test does not know.

    The patch target is the module attribute ``egress.attempts.random``, which
    is also the string target the UC-004 circuit-breaker harness patches
    (``tests/harness/delivery_circuit_breaker.py``) — the schedule moved there
    with ``_backoff_seconds`` (GH #1802). Pinning it here for the same
    obligation keeps the seam suite and the BDD suite grading one implementation:
    a ``from random import uniform`` in ``egress.attempts`` would break both at
    once, which is the point.

    Returns the list of ``(args)`` tuples the seam passed to ``uniform``, so a
    caller can grade the draw itself — one draw per sleep, with the literal
    ``(0, 1)`` bounds the rule names.
    """
    calls: list[tuple] = []

    def _pinned(*args):
        calls.append(args)
        return value

    monkeypatch.setattr(_attempts_module().random, "uniform", _pinned)
    return calls


def fast_backoff(monkeypatch) -> None:
    """Make a retry test's real sleeps negligible without weakening what it grades.

    For the retry tests that grade attempt COUNTS: they have to sleep between
    attempts, but what they sleep is not their obligation — BR-RULE-029's
    magnitudes are graded once, by the schedule section below.

    BOTH halves are required. The base override alone does not make these tests
    fast, because the jitter is an additive ``uniform(0, 1)`` draw independent of
    the base: at a 1ms base each sleep would still average half a second.

    The base is written EXPLICITLY, exactly as ``set_flags`` writes the literal
    ``"false"``, so an ambient value in the shell cannot change what these tests
    wait — the variable is deliberately absent from ``tox.ini``'s ``pass_env``,
    but a bare host ``pytest`` inherits the whole environ.
    """
    monkeypatch.setenv(BACKOFF_BASE_ENV, "0.001")
    pin_jitter(monkeypatch, 0.0)


def rate_limited(local_origin, retry_after: str | None = None) -> None:
    """Program the origin to answer 429, optionally with a ``Retry-After`` header.

    The header is sent by a server that really wrote it, not injected into a
    mocked response object: "the seam honoured Retry-After" is a claim about
    what it does with bytes off the wire, and a stubbed ``response.headers``
    could only restate the number the test already chose.
    """
    headers = {"Retry-After": retry_after} if retry_after is not None else None
    local_origin.respond_with(429, body=_RATE_LIMITED_BODY, headers=headers)

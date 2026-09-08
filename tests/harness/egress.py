"""The egress-hatch posture, settable on any env that grades a seam refusal.

``set_egress_hatches`` began life on ``RealResolverProductEnv`` for the
get_products property-list refusal. The ingest-time webhook refusal
(``create_media_buy`` with a ``push_notification_config.url`` the seam would
never dial) grades the same seam from ``MediaBuyCreateEnv``, and the BDD
guards forbid per-env ``hasattr`` branching in steps — so the method lives
here once and both envs mix it in, instead of each growing a copy that can
drift into setting only one hatch.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import TYPE_CHECKING
from unittest.mock import patch

from src.core.security.egress.attempts import _BACKOFF_BASE_ENV
from tests.harness._realize import realize_e2e
from tests.helpers.egress_hatches import egress_hatch_env


def _egress_hatches_on_the_live_stack(self: EgressHatchMixin, *, private: bool) -> None:
    """Realize a hatch posture on the live e2e stack — whose posture is fixed, and open.

    ``docker-compose.e2e.yml`` exports ``ADCP_OUTBOUND_ALLOW_PRIVATE=true`` on
    both the adcp-server and the runner, and the process making the outbound
    request is not the process this test controls — so over e2e_rest the
    posture cannot be set from here. ``private=True`` is ALREADY realized, and
    asking for it is a true no-op rather than an assumption.

    No Gherkin phrase asks for the CLOSED posture any more. GH #1802
    deleted both the ``... egress hatch is closed`` step and its one binding, so
    there is no reachable caller with ``private=False`` over e2e_rest, and this
    function returns unconditionally. That deletion is the mitigation, not the
    escape-hatch pin: the pin only sees declaration sites, so it would say
    nothing about a future scenario that asks for the closed posture with no
    declaration and gets silently graded against the stack's open one. Restoring
    that ability means restoring a Gherkin phrase AND a pinned declaration
    together.

    This function and its ``@realize_e2e`` decorator stay even though nothing
    raises: without them the e2e branch would run the in-process ``patch.dict``
    and claim to have set a posture in a process that is not the server's, which
    is the silent lie the decorator exists to prevent.

    ``ADCP_OUTBOUND_ALLOW_INSECURE`` no longer exists anywhere in this stack
    (GH #1757 deleted it — the outbound origins the server dials are all
    https now). That asymmetry (private always open, scheme never relaxable) is
    what makes the refusal causes the egress scenarios grade — a cloud-metadata
    address, an unresolvable host, and a plaintext http scheme — meaningful over
    e2e_rest: all three are refused with the private hatch WIDE OPEN, so their
    green mark over e2e_rest means what it means in-process.
    """


class EgressHatchMixin:
    """Mixes ``set_egress_hatches`` into an env whose scenarios grade the seam.

    Host env must be an ``IntegrationEnv`` (relies on ``_guard`` for
    posture cleanup on exit).
    """

    if TYPE_CHECKING:
        # Declared, not implemented. This mixin is only ever composed with
        # BaseTestEnv, which owns the cleanup registry; the requirement used to
        # be spelled as a bare ``_patchers: list`` annotation and this is the
        # same statement for the method that replaced it.
        def _guard(self, label: str, cleanup: Callable[[], None]) -> None: ...

    @realize_e2e(_egress_hatches_on_the_live_stack)
    def set_egress_hatches(self, *, private: bool) -> None:
        """Pin the private-range outbound escape hatch for the lifetime of this env.

        A refusal scenario that does not say which posture it runs under is
        graded by a different gate in each environment. Saying it out loud
        makes the scenario name the gate it grades.

        The patcher is registered with ``_guard``, so both release paths stop it
        with everything else and no scenario leaks a posture into the next one —
        including a scenario whose ``__enter__`` failed after this call.
        """
        patcher = patch.dict(os.environ, egress_hatch_env(private=private))
        patcher.start()
        self._guard("egress_hatches", patcher.stop)


class FastOutboundBackoffMixin:
    """Shorten the egress seam's retry backoff BASE for this env's lifetime.

    The seam's real base is 1s (BR-RULE-029: 1s/2s/4s + jitter), which a retry
    case would otherwise pay in wall time on every run. The SHAPE (x2 per
    attempt) and the jitter are NOT overridden — only the base — and the
    schedule itself is graded once, in ``tests/integration/test_outbound_http.py``
    via ``tests/helpers/backoff_assertions.py``.

    The knob is read by the seam at call time, so it takes effect only for a
    call site that has actually been migrated onto the seam; a call site still
    running its own sleep loop ignores it and its retry cases stay slow.

    The env-var name is IMPORTED from the seam
    (``src.core.security.egress.attempts._BACKOFF_BASE_ENV``), never re-spelled.
    A mixin cannot misspell a name it never spells, and a rename at the seam
    reaches here for free.

    COMPOSITION RULE — only envs whose tests do NOT observe the seam's sleep may
    compose this. The two webhook envs qualify. The delivery envs do NOT: they
    mock ``outbound_http.time.sleep`` and grade sleep MAGNITUDES against
    ``BR_RULE_029_BASE_DELAYS = (1.0, 2.0, 4.0)``, so shortening the base would
    silently invalidate ~15 assertions rather than fail them.
    """

    FAST_BACKOFF_BASE_SECONDS = "0.01"

    if TYPE_CHECKING:
        # Same declaration as EgressHatchMixin above: composed only with
        # BaseTestEnv, which owns the registry.
        def _guard(self, label: str, cleanup: Callable[[], None]) -> None: ...

    def _enter_pre(self) -> None:
        # The super() here resolves at COMPOSITION time to whatever sits next in
        # the host env's MRO (LocalOriginMixin, then BaseTestEnv). A bare mixin
        # has no such superclass, which is all mypy is objecting to.
        super()._enter_pre()  # type: ignore[misc]
        backoff = patch.dict(os.environ, {_BACKOFF_BASE_ENV: self.FAST_BACKOFF_BASE_SECONDS})
        backoff.start()
        self._guard("fast_backoff", backoff.stop)

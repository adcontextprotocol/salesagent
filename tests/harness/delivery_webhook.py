"""WebhookEnv — integration test environment for deliver_webhook_with_retry.

Real: a local HTTP origin that actually serves the delivery attempts, and
      ``get_db_session`` for delivery record tracking.
Mocked: the SEAM's ``time.sleep`` (so backoff is observable without waiting for
      it). Nothing else — the loopback allowance is the seam's own escape hatch,
      opened by ``LocalOriginMixin``.

Nothing about the outbound transport is patched. That is the point: the tests
grade the bytes ``src.core.security.outbound_http.send`` puts on the socket, not
which client library puts them there.

Requires: integration_db fixture (creates test PostgreSQL DB).

Usage::

    @pytest.mark.requires_db
    def test_something(self, integration_db):
        with WebhookEnv() as env:
            env.set_http_status(200)
            success, result = env.call_deliver(payload={"event": "delivery.update"})
            assert success is True
            assert env.delivery_attempts == 1

Available mocks via env.mock:
    "sleep"       -- the seam's time.sleep (the retry schedule, not a transport)
"""

from __future__ import annotations

from tests.harness._base import IntegrationEnv
from tests.harness._mixins import WebhookMixin


class WebhookEnv(WebhookMixin, IntegrationEnv):
    """Integration test environment for deliver_webhook_with_retry.

    Delivery goes over real HTTP to a real local origin; DB operations for
    delivery tracking go through the real database.

    Fluent API (from WebhookMixin / LocalOriginMixin):
        webhook_url                       -- the running origin's URL
        set_http_status(code, text)       -- answer every attempt with one status
        set_http_sequence(responses)      -- answer attempts in order, last repeats
        set_http_error()                  -- drop the connection without answering
        call_deliver(...)                 -- call deliver_webhook_with_retry
        delivery_attempts / last_delivery -- what the endpoint actually received
    """

    MODULE = "src.core.webhook_delivery"

    # Delivery is on the egress seam, so the schedule is observed where it is now
    # decided. The url_policy patch is GONE: LocalOriginMixin already opens
    # ADCP_OUTBOUND_ALLOW_PRIVATE / _INSECURE for the loopback origin, which is the
    # seam's own supported way to say "this one address is fine" — the in-repo twin
    # the old docstring promised would be deleted at exactly this point.
    EXTERNAL_PATCHES = {
        "sleep": "src.core.security.outbound_http.time.sleep",
    }

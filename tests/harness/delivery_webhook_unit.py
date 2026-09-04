"""WebhookEnv — unit test environment for deliver_webhook_with_retry.

Identical to the integration variant except that ``get_db_session`` is mocked
out, so no database is needed. Delivery itself still goes over real HTTP to a
real local origin — a stdlib server on an ephemeral loopback port is cheap
enough for a unit test, and it is what keeps these tests indifferent to whether
delivery is implemented with ``requests`` or with the egress seam.

Usage::

    with WebhookEnv() as env:
        env.set_http_status(200)
        success, result = env.call_deliver(payload={"event": "delivery.update"})
        assert success is True
        assert result["status"] == "delivered"

Available mocks via env.mock:
    "sleep"       -- the seam's time.sleep (the retry schedule, not a transport)
    "db"          -- get_db_session mock
"""

from __future__ import annotations

from unittest.mock import MagicMock

from tests.harness._base import BaseTestEnv
from tests.harness._mixins import WebhookMixin


class WebhookEnv(WebhookMixin, BaseTestEnv):
    """Unit test environment for deliver_webhook_with_retry.

    Fluent API (from WebhookMixin / LocalOriginMixin):
        webhook_url                       -- the running origin's URL
        set_http_status(code, text)       -- answer every attempt with one status
        set_http_sequence(responses)      -- answer attempts in order, last repeats
        set_http_error()                  -- drop the connection without answering
        call_deliver(...)                 -- call deliver_webhook_with_retry
        delivery_attempts / last_delivery -- what the endpoint actually received
    """

    MODULE = "src.core.webhook_delivery"
    EXTERNAL_PATCHES = {
        # The seam's clock, not this module's — delivery no longer sleeps here.
        "sleep": "src.core.security.outbound_http.time.sleep",
        "db": f"{MODULE}.get_db_session",
    }

    def _configure_mocks(self) -> None:
        # DB session: no-op context manager
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=MagicMock())
        mock_ctx.__exit__ = MagicMock(return_value=False)
        self.mock["db"].return_value = mock_ctx

"""OrderApprovalWebhookEnv — integration test environment for _send_approval_webhook.

Real: a local HTTP origin that actually serves the POST, and the real database
      for the ``PushNotificationConfig`` lookup that builds the auth header.
Mocked: nothing. There is no ``EXTERNAL_PATCHES`` entry on purpose — the whole
      point of this env is that the transport is not substituted: the assertions
      grade ``src.core.security.outbound_http.send`` putting real bytes on a real
      socket, indifferent to how the seam is implemented.

Why an env rather than the bare ``local_origin`` fixture plus a factory call:
``_send_approval_webhook`` reads its auth config out of the database
(``select(PushNotificationConfig)``), and ``PushNotificationConfigFactory``
(tests/factories/webhook.py) ships with ``sqlalchemy_session = None``.
``IntegrationEnv.__enter__`` is what binds that session, so outside an env the
factory has no session and cannot create the row at all.

``LocalOriginMixin`` already means "start the origin, publish ``webhook_url``,
open both outbound escape hatches" — the origin necessarily listens on loopback
over plain HTTP, which the egress seam refuses by default. Composing it is how
that decision stays spelled once.

Requires: integration_db fixture (creates test PostgreSQL DB).

Usage::

    @pytest.mark.requires_db
    def test_something(self, integration_db):
        with OrderApprovalWebhookEnv() as env:
            tenant, principal = env.setup_default_data()
            env.set_http_status(200)

            env.call_send_approval_webhook(status="approved")

            assert env.delivery_attempts == 1
            assert env.last_delivery.json()["status"] == "approved"
"""

from __future__ import annotations

from typing import Any

from src.services.order_approval_service import _send_approval_webhook
from tests.harness._base import IntegrationEnv
from tests.harness._mixins import LocalOriginMixin
from tests.harness.egress import FastOutboundBackoffMixin


class OrderApprovalWebhookEnv(FastOutboundBackoffMixin, LocalOriginMixin, IntegrationEnv):
    """Integration test environment for ``_send_approval_webhook``.

    The webhook POST goes over real HTTP to a real local origin; the
    ``PushNotificationConfig`` lookup that builds the ``Authorization`` header
    runs against the real database.

    Fluent API (from LocalOriginMixin):
        webhook_url                       -- the running origin's URL
        set_http_status(code, text)       -- answer every attempt with one status
        set_http_sequence(responses)      -- answer attempts in order, last repeats
        set_http_error()                  -- drop the connection without answering
        delivery_attempts / last_delivery -- what the endpoint actually received
        delivered_requests                -- every request, oldest first
    """

    MODULE = "src.services.order_approval_service"

    def call_send_approval_webhook(
        self,
        *,
        webhook_url: str | None = None,
        media_buy_id: str = "mb_123",
        status: str = "approved",
        message: str = "Order approved successfully",
        order_id: str | None = None,
        attempts: int | None = None,
        **overrides: Any,
    ) -> None:
        """Call the real ``_send_approval_webhook`` against the running origin.

        ``webhook_url`` defaults to the origin that is really listening. Passing
        an explicit URL is how a test targets somewhere the origin is NOT.

        ``tenant_id`` / ``principal_id`` default to the env's own, which is what
        makes the ``PushNotificationConfig`` row created through the env's
        factories the one production looks up.

        Returns ``None`` — the production function returns nothing and both of
        its callers ignore it, so there is no result to hand back. What it did
        is read off the origin.
        """
        kwargs: dict[str, Any] = {
            "webhook_url": webhook_url if webhook_url is not None else self.webhook_url,
            "tenant_id": self._tenant_id,
            "principal_id": self._principal_id,
            "media_buy_id": media_buy_id,
            "status": status,
            "message": message,
            "order_id": order_id,
            "attempts": attempts,
        }
        kwargs.update(overrides)
        _send_approval_webhook(**kwargs)

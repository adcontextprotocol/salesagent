"""CircuitBreakerEnv — integration test environment for WebhookDeliveryService.

Patches: the SEAM's time.sleep and random.uniform — timing and randomness only.
Delivery retries are the seam's since GH #1589, so the schedule is
observed where it is now decided; patching this module's names would silently
observe nothing.
Real: a local HTTP origin that actually serves the delivery attempts, and
      get_db_session for PushNotificationConfig queries (real DB).

Egress policy is NOT mocked here. It used to be — a ``ssrf`` patch pointed at a
send-side validator production had already stopped calling, so the control
intercepted nothing and the Given that used it asserted nothing (gh-#1589). The
gate now lives on the seam and is driven by naming a destination it genuinely
refuses; the loopback origin these scenarios need is admitted because
``LocalOriginMixin`` opens both egress hatches for the env's lifetime.

The outbound transport is NOT patched — see ``LocalOriginMixin``. Webhook
endpoints must therefore be configured with ``env.webhook_url``, which is the
origin that is really listening.

Requires: integration_db fixture (creates test PostgreSQL DB).

Usage::

    @pytest.mark.requires_db
    def test_something(self, integration_db):
        with CircuitBreakerEnv() as env:
            tenant = TenantFactory(tenant_id="t1")
            principal = PrincipalFactory(tenant=tenant)
            PushNotificationConfigFactory(tenant=tenant, principal=principal, url=env.webhook_url)

            env.set_http_response(200)
            service = env.get_service()
            result = service.send_delivery_webhook(...)
            assert env.delivery_attempts == 1

Available mocks via env.mock:
    "sleep"     -- time.sleep mock
    "random"    -- random.uniform mock
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select

from src.core.database.models import PushNotificationConfig
from src.services.webhook_delivery_service import WebhookDeliveryService
from tests.harness._base import IntegrationEnv
from tests.harness._mixins import CircuitBreakerMixin, WebhookOutcomeRowsMixin


class _LogCaptureHandler(logging.Handler):
    """Captures formatted log records into a list for assertion in tests."""

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.records: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(self.format(record))


class CircuitBreakerEnv(WebhookOutcomeRowsMixin, CircuitBreakerMixin, IntegrationEnv):
    """Integration test environment for WebhookDeliveryService and CircuitBreaker.

    Only mocks timing and randomness. Delivery goes over real HTTP to a real
    local origin; DB queries for PushNotificationConfig run against real database.

    Fluent API (from CircuitBreakerMixin / LocalOriginMixin):
        webhook_url                      -- the running origin's URL
        endpoint_key(tenant_id)          -- production's per-endpoint breaker key
        get_service()                    -- return a WebhookDeliveryService instance
        get_breaker(**kwargs)            -- return a fresh CircuitBreaker instance
        set_http_response(status_code)   -- answer every attempt with one status
        call_send(...)                   -- call service.send_delivery_webhook
        make_webhook_config(...)         -- create a PushNotificationConfig in DB
        set_db_webhooks(configs)         -- replace webhook configs in DB
        delivery_attempts / last_delivery -- what the endpoint actually received
    """

    MODULE = "src.services.webhook_delivery_service"

    EXTERNAL_PATCHES = {
        "sleep": "src.core.security.outbound_http.time.sleep",
        "random": "src.core.security.egress.attempts.random.uniform",
    }

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._service: WebhookDeliveryService | None = None
        self._log_handler: _LogCaptureHandler | None = None
        self.captured_logs: list[str] = []

    def _enter_post(self) -> None:
        """Attach log capture once the env is otherwise live.

        Post, not pre: nothing in the base's setup logs to this logger, and the
        handler is a resource — registering its removal with ``_guard`` is what
        stops a failed enter from leaving a dead handler attached to a
        process-global logger for every later test.
        """
        super()._enter_post()
        self._log_handler = _LogCaptureHandler()
        webhook_logger = logging.getLogger("src.services.webhook_delivery_service")
        webhook_logger.addHandler(self._log_handler)
        self.captured_logs = self._log_handler.records
        self._guard("log_capture", self._remove_log_handler)

    def _remove_log_handler(self) -> None:
        if self._log_handler is not None:
            logging.getLogger("src.services.webhook_delivery_service").removeHandler(self._log_handler)
            self._log_handler = None

    def _configure_mocks(self) -> None:
        # random.uniform: return 0.0 for deterministic tests
        self.mock["random"].return_value = 0.0

        # The origin answers 200 OK unless a test programs otherwise.
        self.set_http_response(200)

    def make_webhook_config(
        self,
        url: str | None = None,
        auth_type: str | None = None,
        auth_token: str | None = None,
    ) -> PushNotificationConfig:
        """Create a PushNotificationConfig via factory and return the ORM instance.

        ``url`` defaults to the running origin, so the configured endpoint is one
        that really answers.

        There is no ``secret=`` parameter (GH #1894). It wrote
        ``webhook_secret``, a column with zero writers in ``src/``, so every test
        that used it configured a row no buyer can create -- and graded a signing
        branch production has now abandoned. An HMAC row is
        ``auth_type="HMAC-SHA256", auth_token=<secret>``, which is what
        ``media_buy_create`` and the A2A push-config handler actually persist.
        """
        from tests.factories import PushNotificationConfigFactory

        url = url if url is not None else self.webhook_url

        # Reuse existing tenant/principal from setup_default_data
        session = self._session
        from src.core.database.models import Principal, Tenant

        tenant = session.scalars(select(Tenant).filter_by(tenant_id=self._tenant_id)).first()
        principal = session.scalars(
            select(Principal).filter_by(tenant_id=self._tenant_id, principal_id=self._principal_id)
        ).first()

        return PushNotificationConfigFactory(
            tenant=tenant,
            principal=principal,
            url=url,
            authentication_type=auth_type,
            authentication_token=auth_token,
            is_active=True,
        )

    def set_db_webhooks(self, webhook_list: list[PushNotificationConfig]) -> None:
        """Replace active webhook configs in DB with the given list.

        Deactivates all existing configs for this tenant/principal, then
        persists the new ones (already created by make_webhook_config).
        """
        session = self._session
        existing = session.scalars(
            select(PushNotificationConfig).filter_by(
                tenant_id=self._tenant_id,
                principal_id=self._principal_id,
                is_active=True,
            )
        ).all()
        for cfg in existing:
            if cfg not in webhook_list:
                cfg.is_active = False
        session.commit()

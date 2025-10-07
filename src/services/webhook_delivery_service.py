"""Thread-safe webhook delivery service for AdCP delivery reporting.

This service provides a shared infrastructure for sending AdCP V2.3 compliant
delivery webhooks from any adapter (mock, GAM, etc.). It handles:
- Thread-safe sequence number tracking
- Webhook failure tracking with retry logic
- AdCP V2.3 GetMediaBuyDeliveryResponse format
- Graceful shutdown handling

This is a CORE feature used by all adapters. Time acceleration is adapter-specific
(e.g., mock adapter for testing).
"""

import atexit
import logging
import threading
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class WebhookDeliveryService:
    """Thread-safe service for sending AdCP delivery webhooks."""

    def __init__(self):
        """Initialize the webhook delivery service."""
        self._sequence_numbers: dict[str, int] = {}  # Track sequence per media buy
        self._lock = threading.Lock()  # Protect shared state
        self._failure_counts: dict[str, int] = {}  # Track failures per media buy
        self._last_webhook_times: dict[str, datetime] = {}  # Track last successful send

        # Register graceful shutdown
        atexit.register(self._shutdown)

        logger.info("✅ WebhookDeliveryService initialized")

    def send_delivery_webhook(
        self,
        media_buy_id: str,
        tenant_id: str,
        principal_id: str,
        reporting_period_start: datetime,
        reporting_period_end: datetime,
        impressions: int,
        spend: float,
        currency: str = "USD",
        status: str = "active",
        clicks: int | None = None,
        ctr: float | None = None,
        by_package: list[dict[str, Any]] | None = None,
        is_final: bool = False,
        next_expected_interval_seconds: float | None = None,
    ) -> bool:
        """Send AdCP V2.3 compliant delivery webhook.

        Thread-safe method that can be called from any thread/adapter.

        Args:
            media_buy_id: Media buy identifier
            tenant_id: Tenant identifier
            principal_id: Principal identifier
            reporting_period_start: Start of reporting period
            reporting_period_end: End of reporting period
            impressions: Impressions delivered
            spend: Spend amount
            currency: Currency code (default: USD)
            status: Media buy status (active, completed, paused, etc.)
            clicks: Optional click count
            ctr: Optional CTR
            by_package: Optional package-level breakdown
            is_final: Whether this is the final webhook (notification_type=final)
            next_expected_interval_seconds: Seconds until next webhook (for calculating next_expected_at)

        Returns:
            True if webhook sent successfully, False otherwise
        """
        try:
            # Thread-safe sequence number increment
            with self._lock:
                self._sequence_numbers[media_buy_id] = self._sequence_numbers.get(media_buy_id, 0) + 1
                sequence_number = self._sequence_numbers[media_buy_id]

            # Determine notification type
            notification_type = "final" if is_final else "scheduled"

            # Calculate next_expected_at if not final
            next_expected_at = None
            if not is_final and next_expected_interval_seconds:
                next_expected_at = (datetime.now(UTC) + timedelta(seconds=next_expected_interval_seconds)).isoformat()

            # Build AdCP V2.3 compliant payload
            delivery_payload = {
                "adcp_version": "2.3.0",
                "notification_type": notification_type,
                "sequence_number": sequence_number,
                "reporting_period": {
                    "start": reporting_period_start.isoformat(),
                    "end": reporting_period_end.isoformat(),
                },
                "currency": currency,
                "media_buy_deliveries": [
                    {
                        "media_buy_id": media_buy_id,
                        "status": status,
                        "totals": {
                            "impressions": impressions,
                            "spend": round(spend, 2),
                        },
                        "by_package": by_package or [],
                    }
                ],
            }

            # Add optional fields
            if next_expected_at:
                delivery_payload["next_expected_at"] = next_expected_at

            totals = delivery_payload["media_buy_deliveries"][0]["totals"]
            if clicks is not None:
                totals["clicks"] = clicks
            if ctr is not None:
                totals["ctr"] = ctr

            logger.info(
                f"📤 Delivery webhook #{sequence_number} for {media_buy_id}: "
                f"{impressions:,} imps, ${spend:,.2f} [{notification_type}]"
            )

            # Log to audit log
            self._log_to_audit(
                tenant_id=tenant_id,
                principal_id=principal_id,
                media_buy_id=media_buy_id,
                sequence_number=sequence_number,
                notification_type=notification_type,
                impressions=impressions,
                spend=spend,
            )

            # Send webhook synchronously (no asyncio.run() in threads!)
            success = self._send_webhook_sync(
                tenant_id=tenant_id,
                principal_id=principal_id,
                media_buy_id=media_buy_id,
                task_status="completed" if is_final else "working",
                delivery_payload=delivery_payload,
            )

            # Track success/failure
            with self._lock:
                if success:
                    self._failure_counts[media_buy_id] = 0
                    self._last_webhook_times[media_buy_id] = datetime.now(UTC)
                else:
                    self._failure_counts[media_buy_id] = self._failure_counts.get(media_buy_id, 0) + 1

            return success

        except Exception as e:
            logger.error(f"❌ Failed to send delivery webhook for {media_buy_id}: {e}", exc_info=True)
            return False

    def _send_webhook_sync(
        self,
        tenant_id: str,
        principal_id: str,
        media_buy_id: str,
        task_status: str,
        delivery_payload: dict[str, Any],
    ) -> bool:
        """Send webhook synchronously (no asyncio).

        This avoids the asyncio.run() anti-pattern when called from threads.

        Args:
            tenant_id: Tenant identifier
            principal_id: Principal identifier
            media_buy_id: Media buy identifier
            task_status: A2A task status (working, completed)
            delivery_payload: AdCP delivery payload

        Returns:
            True if sent successfully, False otherwise
        """
        try:
            # Get webhook configurations for this principal
            from src.core.database.database_session import get_db_session
            from src.core.database.models import PushNotificationConfig

            with get_db_session() as db:
                configs = (
                    db.query(PushNotificationConfig)
                    .filter_by(tenant_id=tenant_id, principal_id=principal_id, is_active=True)
                    .all()
                )

                if not configs:
                    logger.debug(f"⚠️ No webhooks configured for {tenant_id}/{principal_id}")
                    return False

                # Build A2A envelope
                a2a_payload = {
                    "task_id": media_buy_id,
                    "status": task_status,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "tenant_id": tenant_id,
                    "principal_id": principal_id,
                    "data": delivery_payload,
                }

                # Send to all configured webhooks
                sent_count = 0
                for config in configs:
                    if self._deliver_to_endpoint(config, a2a_payload):
                        sent_count += 1

                if sent_count > 0:
                    logger.debug(f"✅ Delivery webhook sent to {sent_count} endpoint(s)")
                    return True
                else:
                    logger.warning("⚠️ Failed to deliver webhook to any endpoint")
                    return False

        except Exception as e:
            logger.error(f"❌ Error in webhook delivery: {e}", exc_info=True)
            return False

    def _deliver_to_endpoint(self, config: Any, payload: dict[str, Any]) -> bool:
        """Deliver webhook to a single endpoint with retries.

        Args:
            config: PushNotificationConfig database object
            payload: Webhook payload

        Returns:
            True if delivered successfully, False otherwise
        """
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "AdCP-Sales-Agent/1.0 (Delivery Webhooks)",
        }

        # Add authentication
        if config.authentication_type == "bearer" and config.authentication_token:
            headers["Authorization"] = f"Bearer {config.authentication_token}"
        elif config.authentication_type == "basic" and config.authentication_token:
            headers["Authorization"] = f"Basic {config.authentication_token}"

        if config.validation_token:
            headers["X-Webhook-Token"] = config.validation_token

        # Synchronous HTTP request with retries
        max_retries = 3
        timeout_seconds = 10

        for attempt in range(max_retries):
            try:
                # Use synchronous httpx client
                with httpx.Client(timeout=timeout_seconds) as client:
                    response = client.post(
                        config.url,
                        json=payload,
                        headers=headers,
                    )

                    if 200 <= response.status_code < 300:
                        logger.debug(
                            f"Webhook delivered to {config.url} "
                            f"(status: {response.status_code}, attempt: {attempt + 1})"
                        )
                        return True

                    logger.warning(
                        f"Webhook delivery to {config.url} returned status {response.status_code} "
                        f"(attempt: {attempt + 1}/{max_retries})"
                    )

            except httpx.TimeoutException:
                logger.warning(f"Webhook delivery to {config.url} timed out " f"(attempt: {attempt + 1}/{max_retries})")
            except httpx.RequestError as e:
                logger.warning(
                    f"Webhook delivery to {config.url} failed with error: {e} "
                    f"(attempt: {attempt + 1}/{max_retries})"
                )
            except Exception as e:
                logger.error(f"Unexpected error delivering to {config.url}: {e}", exc_info=True)
                break  # Don't retry on unexpected errors

        return False

    def reset_sequence(self, media_buy_id: str):
        """Reset sequence number for a media buy.

        Thread-safe operation.

        Args:
            media_buy_id: Media buy identifier
        """
        with self._lock:
            if media_buy_id in self._sequence_numbers:
                del self._sequence_numbers[media_buy_id]
            if media_buy_id in self._failure_counts:
                del self._failure_counts[media_buy_id]
            if media_buy_id in self._last_webhook_times:
                del self._last_webhook_times[media_buy_id]

    def get_failure_count(self, media_buy_id: str) -> int:
        """Get webhook failure count for a media buy.

        Thread-safe operation.

        Args:
            media_buy_id: Media buy identifier

        Returns:
            Number of consecutive failures
        """
        with self._lock:
            return self._failure_counts.get(media_buy_id, 0)

    def get_last_webhook_time(self, media_buy_id: str) -> datetime | None:
        """Get last successful webhook time for a media buy.

        Thread-safe operation.

        Args:
            media_buy_id: Media buy identifier

        Returns:
            Last successful webhook time, or None if never sent
        """
        with self._lock:
            return self._last_webhook_times.get(media_buy_id)

    def _log_to_audit(
        self,
        tenant_id: str,
        principal_id: str,
        media_buy_id: str,
        sequence_number: int,
        notification_type: str,
        impressions: int,
        spend: float,
    ):
        """Log webhook delivery to audit log.

        Args:
            tenant_id: Tenant identifier
            principal_id: Principal identifier
            media_buy_id: Media buy identifier
            sequence_number: Webhook sequence number
            notification_type: scheduled or final
            impressions: Impressions delivered
            spend: Spend amount
        """
        try:
            from src.core.database.database_session import get_db_session
            from src.core.database.models import AuditLog

            with get_db_session() as db:
                audit_log = AuditLog(
                    tenant_id=tenant_id,
                    timestamp=datetime.now(UTC),
                    operation="send_delivery_webhook",
                    principal_id=principal_id,
                    success=True,
                    details={
                        "media_buy_id": media_buy_id,
                        "sequence_number": sequence_number,
                        "notification_type": notification_type,
                        "impressions": impressions,
                        "spend": round(spend, 2),
                    },
                )
                db.add(audit_log)
                db.commit()

        except Exception as e:
            logger.warning(f"Failed to write webhook delivery to audit log: {e}")

    def _shutdown(self):
        """Graceful shutdown handler."""
        logger.info("🛑 WebhookDeliveryService shutting down")
        with self._lock:
            active_buys = list(self._sequence_numbers.keys())
            if active_buys:
                logger.info(f"📊 Active media buys at shutdown: {active_buys}")


# Global singleton instance
webhook_delivery_service = WebhookDeliveryService()

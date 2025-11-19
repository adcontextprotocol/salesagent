"""Integration-style tests for delivery webhook scheduler end-to-end behavior.

These tests:
- Use a real PostgreSQL database via the integration_db fixture
- Exercise DeliveryWebhookScheduler end-to-end for a single media buy
- Mock only the GAM reporting layer (get_media_buy_delivery + freshness) and outbound HTTP
"""

import pytz
from datetime import UTC, datetime, timedelta, time
from unittest.mock import AsyncMock, patch

import pytest

from src.core.database.database_session import get_db_session
from src.core.database.models import MediaBuy, Principal, Tenant, PushNotificationConfig, PricingOption, Product
from src.services.delivery_webhook_scheduler import DeliveryWebhookScheduler


def _create_basic_media_buy_with_webhook() -> tuple[str, str, str]:
    """Create a minimal tenant/principal/media_buy with a daily reporting_webhook.

    Returns:
        (tenant_id, principal_id, media_buy_id)
    """
    tenant_id = "tenant_integration"
    principal_id = "principal_integration"
    product_id = "sample_product_id"
    media_buy_id = "mb_integration"

    today = datetime.now(UTC).date()

    with get_db_session() as session:
        tenant = Tenant(
            tenant_id=tenant_id,
            name="Integration Tenant",
            subdomain="integration-tenant",
        )
        principal = Principal(
            tenant_id=tenant_id,
            principal_id=principal_id,
            name="Integration Principal",
            platform_mappings={"mock": {"advertiser_id": "adv_123"}},
            access_token="test-token",
        )

        product = Product(
            tenant_id=tenant_id,
            product_id=product_id,
            name="My demo product",
            description="This is demo product for testing",
            format_ids=[],
            targeting_template={},
            delivery_type=""
        )

        pricing_option = PricingOption(
            tenant_id=tenant_id,
            pricing_model="cpm",
            rate=15.0,
            currency="EUR",
            is_fixed=False,
            price_guidance=None,
            parameters=None,
            min_spend_per_package=None,
            product_id=product.product_id
        )

        media_buy = MediaBuy(
            media_buy_id=media_buy_id,
            tenant_id=tenant_id,
            principal_id=principal_id,
            buyer_ref="buyer_ref_123",
            order_name="Test Order",
            advertiser_name="Test Advertiser",
            start_date=today - timedelta(days=7),
            end_date=today + timedelta(days=7),
            status="active",
            raw_request={
                "packages": [{
                    "buyer_ref": "nike_web",
                    "product_id": product.product_id,
                    "pricing_option_id": pricing_option.id
                }],
                "reporting_webhook": {
                    "url": "https://example.com/webhook",  # outbound HTTP will be mocked
                    "frequency": "daily",
                }
            },
        )

        session.add(tenant)
        session.add(principal)
        session.add(media_buy)
        session.commit()

    return tenant_id, principal_id, media_buy_id


@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_delivery_webhook_sends_for_fresh_data(integration_db):
    """Scheduler should call get_media_buy_delivery for the correct period and send webhook when data is fresh."""

    tenant_id, principal_id, media_buy_id = _create_basic_media_buy_with_webhook()

    scheduler = DeliveryWebhookScheduler()

    print("scheduler.webhook_service")

    async def fake_send_notification(*args, **kwargs):
        # Simulate successful webhook send without doing network I/O
        return True

    # Patch GAM/reporting + freshness + outbound HTTP, keep scheduler logic + DB real
    with (
        patch.object(
            scheduler.webhook_service,
            "send_notification",
            new_callable=AsyncMock,
            side_effect=fake_send_notification,
        ) as mock_send_notification
    ):
        # Run a single batch (no need to run the full hourly loop)
        await scheduler._send_reports()
        
        args, kwargs = mock_send_notification.await_args

        task_type = kwargs.get("task_type")
        task_id = kwargs.get("task_id")
        status = kwargs.get("status")
        push_notification_config = kwargs.get("push_notification_config")
        result = kwargs.get("result")
        error = kwargs.get("error")
        tenant_id = kwargs.get("tenant_id")
        principal_id = kwargs.get("principal_id")
        
        print("result")
        print(result)

        # Webhook should have been sent exactly once
        assert mock_send_notification.await_count == 1
        assert task_type == "media_buy_delivery"
        assert error is None
        assert tenant_id == tenant_id
        assert principal_id == principal_id
        assert media_buy_id == media_buy_id
        assert result is not None
        assert result.get("notification_type") == "scheduled"
        assert result.get("sequence_number") == 1
        assert result.get("next_expected_at") is not None
        assert result.get("frequency") == "daily"
        assert result.get("partial_data") is False
        assert result.get("unavailable_count") == 0
        assert result.get("reporting_period") is not None
        assert result.get("errors") is None

        yesterday = datetime.now(UTC).date() - timedelta(days=1)

        expected_start_date=(datetime.combine(yesterday, time.min)).isoformat()
        expected_end_date=(datetime.combine(yesterday, time.max)).isoformat()

        assert len(result.get('media_buy_deliveries')) == 1

        assert result.get("reporting_period").get("start") == expected_start_date
        assert result.get("reporting_period").get("end") == expected_end_date


@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_delivery_webhook_skips_when_data_not_fresh(integration_db):
    """Scheduler should skip sending webhook when GAM data freshness check fails."""

    _create_basic_media_buy_with_webhook()

    scheduler = DeliveryWebhookScheduler()

    class DummyDeliveryResponse:
        def __init__(self):
            self.reporting_data = object()

        def model_dump(self):
            return {"dummy": "payload"}

    def fake_get_media_buy_delivery_impl(req, context):
        return DummyDeliveryResponse()

    with (
        patch(
            "src.services.delivery_webhook_scheduler._get_media_buy_delivery_impl",
            side_effect=fake_get_media_buy_delivery_impl,
        ),
        patch(
            "src.adapters.gam_data_freshness.validate_and_log_freshness",
            return_value=False,
        ),
        patch.object(
            scheduler.webhook_service,
            "send_notification",
            new_callable=AsyncMock,
        ) as mock_send_notification,
    ):
        await scheduler._send_reports()

    # Data not fresh -> no webhook should be sent
    mock_send_notification.assert_not_awaited()



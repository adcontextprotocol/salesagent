"""Test AI product service with adapter configuration."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_product_service import AIProductConfigurationService, ProductDescription
from database_session import get_db_session
from models import AdapterConfig, Tenant


@pytest.fixture
def ai_tenant_with_adapter(integration_db):
    """Create a tenant with adapter configuration."""
    from datetime import UTC, datetime

    with get_db_session() as session:
        # Create tenant
        now = datetime.now(UTC)
        tenant = Tenant(
            tenant_id="test_ai_tenant",
            name="Test AI Tenant",
            subdomain="test-ai",
            ad_server="mock",
            authorized_emails=["test@example.com"],
            created_at=now,
            updated_at=now,
            is_active=True,
        )
        session.add(tenant)

        # Create adapter config
        adapter_config = AdapterConfig(tenant_id="test_ai_tenant", adapter_type="mock", mock_dry_run=False)
        session.add(adapter_config)

        session.commit()

        return {
            "tenant_id": tenant.tenant_id,
            "name": tenant.name,
            "ad_server": tenant.ad_server,
        }


@pytest.mark.asyncio
async def test_ai_product_with_adapter_config(ai_tenant_with_adapter):
    """Test that AI product service correctly handles AdapterConfig without config column."""
    # Mock the Gemini API before initializing the service
    with (
        patch("ai_product_service.genai.configure"),
        patch("ai_product_service.genai.GenerativeModel") as mock_model_class,
    ):

        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = json.dumps(
            {
                "products": [
                    {
                        "name": "Test Product",
                        "description": "AI generated product",
                        "formats": ["display_300x250"],
                        "delivery_type": "guaranteed",
                        "is_fixed_price": True,
                        "cpm": 10.0,
                        "min_spend": 1000.0,
                        "countries": ["US"],
                        "targeting_template": {"geo_country_any_of": ["US"]},
                        "implementation_config": {},
                    }
                ]
            }
        )
        mock_model.generate_content = MagicMock(return_value=mock_response)
        mock_model_class.return_value = mock_model

        # Now initialize the service with mocked Gemini
        service = AIProductConfigurationService()

        # Mock adapter's get_available_inventory
        with patch("adapters.get_adapter_class") as mock_get_adapter:
            mock_adapter_class = MagicMock()
            mock_adapter_instance = MagicMock()
            mock_adapter_instance.get_available_inventory = AsyncMock(
                return_value={"ad_units": [], "targeting_keys": [], "formats": []}
            )
            mock_adapter_class.return_value = mock_adapter_instance
            mock_get_adapter.return_value = mock_adapter_class

            # Test product generation - should not raise AttributeError about 'config'
            result = await service.create_product_from_description(
                tenant_id="test_ai_tenant",
                description=ProductDescription(
                    name="Test Product", external_description="News website", internal_details="Mock adapter testing"
                ),
                adapter_type="mock",
            )

            # The method returns a Product object or error dict
            assert result is not None
            if isinstance(result, dict) and "error" in result:
                pytest.fail(f"Product creation failed: {result['error']}")

            # Verify adapter was instantiated with correct config structure
            mock_adapter_class.assert_called_once()
            call_kwargs = mock_adapter_class.call_args.kwargs
            assert "config" in call_kwargs
            assert call_kwargs["config"]["adapter_type"] == "mock"
            assert "enabled" in call_kwargs["config"]
            # Should NOT have a nested 'config' key
            assert "config" not in call_kwargs["config"]


@pytest.mark.asyncio
async def test_ai_product_with_gam_adapter(integration_db):
    """Test AI product service with Google Ad Manager adapter config."""
    from datetime import UTC, datetime

    with get_db_session() as session:
        # Create tenant with GAM adapter
        now = datetime.now(UTC)
        tenant = Tenant(
            tenant_id="gam_tenant",
            name="GAM Tenant",
            subdomain="gam-test",
            ad_server="google_ad_manager",
            authorized_emails=["test@example.com"],
            created_at=now,
            updated_at=now,
            is_active=True,
        )
        session.add(tenant)

        # Create GAM adapter config
        adapter_config = AdapterConfig(
            tenant_id="gam_tenant",
            adapter_type="google_ad_manager",
            gam_network_code="123456",
            gam_refresh_token="test_token",
            gam_company_id="789",
            gam_trafficker_id="456",
            gam_manual_approval_required=True,
        )
        session.add(adapter_config)
        session.commit()

    # Mock the Gemini API before initializing the service
    with (
        patch("ai_product_service.genai.configure"),
        patch("ai_product_service.genai.GenerativeModel") as mock_model_class,
    ):
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = json.dumps({"products": []})
        mock_model.generate_content = MagicMock(return_value=mock_response)
        mock_model_class.return_value = mock_model

        # Now initialize the service with mocked Gemini
        service = AIProductConfigurationService()

        with patch("adapters.get_adapter_class") as mock_get_adapter:
            mock_adapter_class = MagicMock()
            mock_adapter_instance = MagicMock()
            mock_adapter_instance.get_available_inventory = AsyncMock(
                return_value={"ad_units": [], "targeting_keys": [], "formats": []}
            )
            mock_adapter_class.return_value = mock_adapter_instance
            mock_get_adapter.return_value = mock_adapter_class

            # Generate products - should correctly build GAM config
            await service.create_product_from_description(
                tenant_id="gam_tenant",
                description=ProductDescription(
                    name="Sports Product", external_description="Sports site", internal_details="GAM adapter testing"
                ),
                adapter_type="google_ad_manager",
            )

            # Verify GAM config was built correctly
            call_kwargs = mock_adapter_class.call_args.kwargs
            assert call_kwargs["config"]["adapter_type"] == "google_ad_manager"
            assert call_kwargs["config"]["network_code"] == "123456"
            assert call_kwargs["config"]["refresh_token"] == "test_token"
            assert call_kwargs["config"]["company_id"] == "789"
            assert call_kwargs["config"]["trafficker_id"] == "456"
            assert call_kwargs["config"]["manual_approval_required"] is True


def test_adapter_config_has_no_config_column(integration_db):
    """Verify AdapterConfig model doesn't have a config column."""
    from models import AdapterConfig

    # This test documents the schema change that caused the bug
    assert not hasattr(AdapterConfig, "config"), "AdapterConfig should not have a 'config' column"

    # Verify expected columns exist
    assert hasattr(AdapterConfig, "adapter_type")
    assert hasattr(AdapterConfig, "mock_dry_run")
    assert hasattr(AdapterConfig, "gam_network_code")
    assert hasattr(AdapterConfig, "kevel_network_id")
    assert hasattr(AdapterConfig, "triton_station_id")

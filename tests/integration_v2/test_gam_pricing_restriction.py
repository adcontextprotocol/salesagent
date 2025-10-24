"""Integration test for GAM pricing model restrictions (AdCP PR #88).

Tests that GAM adapter properly enforces CPM-only restriction.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import delete

from src.core.database.database_session import get_db_session
from src.core.database.models import AdapterConfig, CurrencyLimit, PricingOption, Principal, Product, Tenant
from src.core.main import _create_media_buy_impl
from src.core.tool_context import ToolContext
from tests.integration_v2.conftest import add_required_setup_data, create_test_product_with_pricing
from tests.utils.database_helpers import create_tenant_with_timestamps

pytestmark = [pytest.mark.integration, pytest.mark.requires_db, pytest.mark.asyncio]


@pytest.fixture
def setup_gam_tenant_with_non_cpm_product(integration_db):
    """Create a GAM tenant with a product offering non-CPM pricing."""
    with get_db_session() as session:
        # Create GAM tenant
        tenant = create_tenant_with_timestamps(
            tenant_id="test_gam_tenant",
            name="GAM Test Publisher",
            subdomain="gam-test",
            ad_server="google_ad_manager",
        )
        session.add(tenant)
        session.flush()

        # Add GAM adapter config with mock refresh token to bypass auth check
        adapter_config = AdapterConfig(
            tenant_id="test_gam_tenant",
            adapter_type="google_ad_manager",
            gam_network_code="test_network_123",
            gam_refresh_token="mock_refresh_token_for_testing",
        )
        session.add(adapter_config)
        session.flush()

        # Add required setup data (access control, authorized properties, currency limits, etc.)
        add_required_setup_data(session, "test_gam_tenant")

        # Create principal
        principal = Principal(
            tenant_id="test_gam_tenant",
            principal_id="test_advertiser",
            name="Test Advertiser",
            access_token="test_gam_token",
            platform_mappings={"google_ad_manager": {"advertiser_id": "123456"}},
        )
        session.add(principal)

        # Create product with CPCV pricing (not supported by GAM)
        product_cpcv = create_test_product_with_pricing(
            session=session,
            tenant_id="test_gam_tenant",
            product_id="prod_gam_cpcv",
            name="Video Ads - CPCV",
            description="Video inventory with CPCV pricing",
            formats=[{"agent_url": "https://test.com", "id": "video_instream"}],
            delivery_type="non_guaranteed",
            pricing_model="cpcv",
            rate=Decimal("0.40"),
            is_fixed=True,
            targeting_template={},
            implementation_config={},
        )
        session.add(product_cpcv)
        session.flush()

        # Create product with CPM pricing (supported by GAM)
        product_cpm = create_test_product_with_pricing(
            session=session,
            tenant_id="test_gam_tenant",
            product_id="prod_gam_cpm",
            name="Display Ads - CPM",
            description="Display inventory with CPM pricing",
            formats=[{"agent_url": "https://test.com", "id": "display_300x250"}],
            delivery_type="guaranteed",
            pricing_model="cpm",
            rate=Decimal("12.50"),
            is_fixed=True,
            targeting_template={},
            implementation_config={},
        )
        session.add(product_cpm)
        session.flush()

        # Create product with multiple pricing models including non-CPM
        # Start with CPM pricing (supported)
        product_multi = create_test_product_with_pricing(
            session=session,
            tenant_id="test_gam_tenant",
            product_id="prod_gam_multi",
            name="Premium Package",
            description="Multiple pricing models (some unsupported)",
            formats=[
                {"agent_url": "https://test.com", "id": "display_300x250"},
                {"agent_url": "https://test.com", "id": "video_instream"},
            ],
            delivery_type="non_guaranteed",
            pricing_model="cpm",
            rate=Decimal("15.00"),
            is_fixed=True,
            targeting_template={},
            implementation_config={},
        )
        session.add(product_multi)
        session.flush()

        # Add second pricing option: CPP (not supported by GAM)
        pricing_multi_cpp = PricingOption(
            tenant_id="test_gam_tenant",
            product_id="prod_gam_multi",
            pricing_model="cpp",
            rate=Decimal("250.00"),
            currency="USD",
            is_fixed=True,
            price_guidance=None,
            parameters={"demographic": "A18-49"},
            min_spend_per_package=None,
        )
        session.add(pricing_multi_cpp)

        session.commit()

    yield

    # Cleanup (SQLAlchemy 2.0 pattern)
    with get_db_session() as session:
        session.execute(delete(PricingOption).where(PricingOption.tenant_id == "test_gam_tenant"))
        session.execute(delete(Product).where(Product.tenant_id == "test_gam_tenant"))
        session.execute(delete(Principal).where(Principal.tenant_id == "test_gam_tenant"))
        session.execute(delete(CurrencyLimit).where(CurrencyLimit.tenant_id == "test_gam_tenant"))
        session.execute(delete(AdapterConfig).where(AdapterConfig.tenant_id == "test_gam_tenant"))
        session.commit()


@pytest.mark.skip_ci  # TODO: Fix FormatId hashable bug before enabling
@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_gam_rejects_cpcv_pricing_model(setup_gam_tenant_with_non_cpm_product):
    """Test that GAM adapter rejects CPCV pricing model with clear error."""
    from unittest.mock import MagicMock, patch

    from src.adapters.google_ad_manager import GoogleAdManager
    from src.core.config_loader import set_current_tenant

    start_time = datetime.now(UTC) + timedelta(days=1)
    end_time = start_time + timedelta(days=30)

    with get_db_session() as session:
        tenant_obj = session.query(Tenant).filter_by(tenant_id="test_gam_tenant").first()
        principal_obj = session.query(Principal).filter_by(tenant_id="test_gam_tenant").first()

        set_current_tenant(
            {
                "tenant_id": tenant_obj.tenant_id,
                "name": tenant_obj.name,
                "ad_server": tenant_obj.ad_server,
            }
        )

    context = ToolContext(
        context_id="test_gam_cpcv",
        tenant_id="test_gam_tenant",
        principal_id="test_advertiser",
        tool_name="create_media_buy",
        request_timestamp=datetime.now(UTC),
    )

    # Mock get_adapter to return a mock GAM adapter that skips auth
    # This allows us to test pricing validation without real GAM credentials
    mock_adapter = MagicMock(spec=GoogleAdManager)
    mock_adapter.get_supported_pricing_models.return_value = ["cpm"]

    with patch("src.core.main.get_adapter", return_value=mock_adapter):
        # This should fail with a clear error about GAM not supporting CPCV
        with pytest.raises(Exception) as exc_info:
            await _create_media_buy_impl(
                buyer_ref="test-buyer-cpcv",
                brand_manifest={"name": "https://example.com/product"},
                packages=[
                    {
                        "buyer_ref": "pkg_1",
                        "products": ["prod_gam_cpcv"],
                        "budget": {"total": 10000.0, "currency": "USD"},
                    }
                ],
                budget={"total": 10000.0, "currency": "USD"},
                start_time=start_time,
                end_time=end_time,
                context=context,
            )

        error_msg = str(exc_info.value)
        # Should mention GAM limitation and CPCV
        assert "gam" in error_msg.lower() or "google" in error_msg.lower()
        assert "cpcv" in error_msg.lower() or "pricing" in error_msg.lower()


@pytest.mark.skip_ci  # TODO: Fix FormatId hashable bug before enabling
@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_gam_accepts_cpm_pricing_model(setup_gam_tenant_with_non_cpm_product):
    """Test that GAM adapter accepts CPM pricing model."""
    from unittest.mock import MagicMock, patch

    from src.adapters.google_ad_manager import GoogleAdManager
    from src.core.config_loader import set_current_tenant

    start_time = datetime.now(UTC) + timedelta(days=1)
    end_time = start_time + timedelta(days=30)

    with get_db_session() as session:
        tenant_obj = session.query(Tenant).filter_by(tenant_id="test_gam_tenant").first()
        principal_obj = session.query(Principal).filter_by(tenant_id="test_gam_tenant").first()

        set_current_tenant(
            {
                "tenant_id": tenant_obj.tenant_id,
                "name": tenant_obj.name,
                "ad_server": tenant_obj.ad_server,
            }
        )

    context = ToolContext(
        context_id="test_gam_cpm",
        tenant_id="test_gam_tenant",
        principal_id="test_advertiser",
        tool_name="create_media_buy",
        request_timestamp=datetime.now(UTC),
    )

    # Mock get_adapter to return a mock GAM adapter that accepts CPM
    mock_adapter = MagicMock(spec=GoogleAdManager)
    mock_adapter.get_supported_pricing_models.return_value = ["cpm"]
    mock_adapter.create_media_buy = MagicMock(return_value={"order_id": "123", "line_items": []})

    with patch("src.core.main.get_adapter", return_value=mock_adapter):
        # This should succeed
        response = await _create_media_buy_impl(
            buyer_ref="test-buyer-cpm",
            brand_manifest={"name": "https://example.com/product"},
            packages=[
                {
                    "buyer_ref": "pkg_1",
                    "products": ["prod_gam_cpm"],
                    "budget": {"total": 10000.0, "currency": "USD"},
                }
            ],
            budget={"total": 10000.0, "currency": "USD"},
            start_time=start_time,
            end_time=end_time,
            context=context,
        )

        assert response.media_buy_id is not None


@pytest.mark.skip_ci  # TODO: Fix FormatId hashable bug before enabling
@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_gam_rejects_cpp_from_multi_pricing_product(setup_gam_tenant_with_non_cpm_product):
    """Test that GAM adapter rejects CPP when buyer chooses it from multi-pricing product."""
    from unittest.mock import MagicMock, patch

    from src.adapters.google_ad_manager import GoogleAdManager
    from src.core.config_loader import set_current_tenant

    start_time = datetime.now(UTC) + timedelta(days=1)
    end_time = start_time + timedelta(days=30)

    with get_db_session() as session:
        tenant_obj = session.query(Tenant).filter_by(tenant_id="test_gam_tenant").first()
        principal_obj = session.query(Principal).filter_by(tenant_id="test_gam_tenant").first()

        set_current_tenant(
            {
                "tenant_id": tenant_obj.tenant_id,
                "name": tenant_obj.name,
                "ad_server": tenant_obj.ad_server,
            }
        )

    context = ToolContext(
        context_id="test_gam_cpp",
        tenant_id="test_gam_tenant",
        principal_id="test_advertiser",
        tool_name="create_media_buy",
        request_timestamp=datetime.now(UTC),
    )

    # Mock get_adapter to return a mock GAM adapter that rejects CPP
    mock_adapter = MagicMock(spec=GoogleAdManager)
    mock_adapter.get_supported_pricing_models.return_value = ["cpm"]

    with patch("src.core.main.get_adapter", return_value=mock_adapter):
        # This should fail with clear error about GAM not supporting CPP
        with pytest.raises(Exception) as exc_info:
            await _create_media_buy_impl(
                buyer_ref="test-buyer-cpp",
                brand_manifest={"name": "https://example.com/product"},
                packages=[
                    {
                        "buyer_ref": "pkg_1",
                        "products": ["prod_gam_multi"],
                        "budget": {"total": 15000.0, "currency": "USD"},
                    }
                ],
                budget={"total": 15000.0, "currency": "USD"},
                start_time=start_time,
                end_time=end_time,
                context=context,
            )

        error_msg = str(exc_info.value)
        assert "cpp" in error_msg.lower() or "pricing" in error_msg.lower()


@pytest.mark.skip_ci  # TODO: Fix FormatId hashable bug before enabling
@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_gam_accepts_cpm_from_multi_pricing_product(setup_gam_tenant_with_non_cpm_product):
    """Test that GAM adapter accepts CPM when buyer chooses it from multi-pricing product."""
    from unittest.mock import MagicMock, patch

    from src.adapters.google_ad_manager import GoogleAdManager
    from src.core.config_loader import set_current_tenant

    start_time = datetime.now(UTC) + timedelta(days=1)
    end_time = start_time + timedelta(days=30)

    with get_db_session() as session:
        tenant_obj = session.query(Tenant).filter_by(tenant_id="test_gam_tenant").first()
        principal_obj = session.query(Principal).filter_by(tenant_id="test_gam_tenant").first()

        set_current_tenant(
            {
                "tenant_id": tenant_obj.tenant_id,
                "name": tenant_obj.name,
                "ad_server": tenant_obj.ad_server,
            }
        )

    context = ToolContext(
        context_id="test_gam_multi_cpm",
        tenant_id="test_gam_tenant",
        principal_id="test_advertiser",
        tool_name="create_media_buy",
        request_timestamp=datetime.now(UTC),
    )

    # Mock get_adapter to return a mock GAM adapter that accepts CPM
    mock_adapter = MagicMock(spec=GoogleAdManager)
    mock_adapter.get_supported_pricing_models.return_value = ["cpm"]
    mock_adapter.create_media_buy = MagicMock(return_value={"order_id": "123", "line_items": []})

    with patch("src.core.main.get_adapter", return_value=mock_adapter):
        # This should succeed - buyer chose CPM from multi-option product
        response = await _create_media_buy_impl(
            buyer_ref="test-buyer-multi-cpm",
            brand_manifest={"name": "https://example.com/product"},
            packages=[
                {
                    "buyer_ref": "pkg_1",
                    "products": ["prod_gam_multi"],
                    "budget": {"total": 10000.0, "currency": "USD"},
                }
            ],
            budget={"total": 10000.0, "currency": "USD"},
            start_time=start_time,
            end_time=end_time,
            context=context,
        )

        assert response.media_buy_id is not None

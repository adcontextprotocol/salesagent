"""Integration test for GAM pricing model restrictions (AdCP PR #88).

Tests that GAM adapter properly enforces CPM-only restriction.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from src.core.database.database_session import get_db_session
from src.core.database.models import CurrencyLimit, PricingOption, Principal, Product, Tenant
from src.core.main import _create_media_buy_impl
from src.core.schemas import CreateMediaBuyRequest, Package, PricingModel
from tests.utils.database_helpers import create_tenant_with_timestamps

pytestmark = pytest.mark.requires_db


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

        # Add currency limit
        currency_limit = CurrencyLimit(
            tenant_id="test_gam_tenant",
            currency_code="USD",
            max_daily_package_spend=Decimal("50000.00"),
        )
        session.add(currency_limit)

        # Create principal
        principal = Principal(
            tenant_id="test_gam_tenant",
            principal_id="test_advertiser",
            name="Test Advertiser",
            access_token="test_gam_token",
            platform_mappings={"google_ad_manager": {"advertiser_id": "gam_adv_123"}},
        )
        session.add(principal)

        # Create product with CPCV pricing (not supported by GAM)
        product = Product(
            tenant_id="test_gam_tenant",
            product_id="prod_gam_cpcv",
            name="Video Ads - CPCV",
            description="Video inventory with CPCV pricing",
            formats=["video_instream"],
            delivery_type="non-guaranteed",
            targeting_template={},
            implementation_config={},
            property_tags=["all_inventory"],  # Required field
        )
        session.add(product)
        session.flush()

        # Add CPCV pricing option
        pricing_cpcv = PricingOption(
            tenant_id="test_gam_tenant",
            product_id="prod_gam_cpcv",
            pricing_model="cpcv",
            rate=Decimal("0.40"),
            currency="USD",
            is_fixed=True,
            price_guidance=None,
            parameters=None,
            min_spend_per_package=None,
        )
        session.add(pricing_cpcv)

        # Create product with CPM pricing (supported by GAM)
        product_cpm = Product(
            tenant_id="test_gam_tenant",
            product_id="prod_gam_cpm",
            name="Display Ads - CPM",
            description="Display inventory with CPM pricing",
            formats=["display_300x250"],
            delivery_type="guaranteed",
            targeting_template={},
            implementation_config={},
            property_tags=["all_inventory"],  # Required field
        )
        session.add(product_cpm)
        session.flush()

        # Add CPM pricing option
        pricing_cpm = PricingOption(
            tenant_id="test_gam_tenant",
            product_id="prod_gam_cpm",
            pricing_model="cpm",
            rate=Decimal("12.50"),
            currency="USD",
            is_fixed=True,
            price_guidance=None,
            parameters=None,
            min_spend_per_package=None,
        )
        session.add(pricing_cpm)

        # Create product with multiple pricing models including non-CPM
        product_multi = Product(
            tenant_id="test_gam_tenant",
            product_id="prod_gam_multi",
            name="Premium Package",
            description="Multiple pricing models (some unsupported)",
            formats=["display_300x250", "video_instream"],
            delivery_type="non-guaranteed",
            targeting_template={},
            implementation_config={},
            property_tags=["all_inventory"],  # Required field
        )
        session.add(product_multi)
        session.flush()

        # Add CPM (supported)
        pricing_multi_cpm = PricingOption(
            tenant_id="test_gam_tenant",
            product_id="prod_gam_multi",
            pricing_model="cpm",
            rate=Decimal("15.00"),
            currency="USD",
            is_fixed=True,
            price_guidance=None,
            parameters=None,
            min_spend_per_package=None,
        )
        session.add(pricing_multi_cpm)

        # Add CPP (not supported by GAM)
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

    # Cleanup
    with get_db_session() as session:
        session.query(PricingOption).filter_by(tenant_id="test_gam_tenant").delete()
        session.query(Product).filter_by(tenant_id="test_gam_tenant").delete()
        session.query(Principal).filter_by(tenant_id="test_gam_tenant").delete()
        session.query(Tenant).filter_by(tenant_id="test_gam_tenant").delete()
        session.commit()


@pytest.mark.requires_db
async def test_gam_rejects_cpcv_pricing_model(setup_gam_tenant_with_non_cpm_product):
    """Test that GAM adapter rejects CPCV pricing model with clear error."""
    request = CreateMediaBuyRequest(
        buyer_ref="test_buyer_ref_cpcv",
        brand_manifest="https://example.com/product",
        packages=[
            Package(
                package_id="pkg_1",
                products=["prod_gam_cpcv"],
                pricing_model=PricingModel.CPCV,  # Not supported by GAM
                budget=10000.0,
            )
        ],
        start_time="2025-02-01T00:00:00Z",
        end_time="2025-02-28T23:59:59Z",
        budget=10000.0,
        currency="USD",
    )

    from src.core.config_loader import set_current_tenant
    from src.core.tool_context import ToolContext
    from src.core.utils.tenant_utils import serialize_tenant_to_dict

    with get_db_session() as session:
        tenant_obj = session.query(Tenant).filter_by(tenant_id="test_gam_tenant").first()
        # Use proper tenant serialization instead of manually building dict
        tenant_dict = serialize_tenant_to_dict(tenant_obj)
        set_current_tenant(tenant_dict)

    context = ToolContext(
        context_id="test_ctx_gam_cpcv",
        tenant_id="test_gam_tenant",
        principal_id="test_advertiser",
        tool_name="create_media_buy",
        request_timestamp=datetime.now(UTC),
    )

    # This should fail with a clear error about GAM not supporting CPCV
    with pytest.raises(Exception) as exc_info:
        await _create_media_buy_impl(
            buyer_ref=request.buyer_ref,
            brand_manifest=request.brand_manifest,
            packages=[p.model_dump_internal() for p in request.packages] if request.packages else None,
            start_time=request.start_time,
            end_time=request.end_time,
            budget=request.budget,
            currency=request.currency,
            context=context,
        )

    error_msg = str(exc_info.value)
    # Should mention GAM limitation and CPCV
    assert "gam" in error_msg.lower() or "google" in error_msg.lower()
    assert "cpcv" in error_msg.lower() or "pricing" in error_msg.lower()


@pytest.mark.requires_db
async def test_gam_accepts_cpm_pricing_model(setup_gam_tenant_with_non_cpm_product):
    """Test that GAM adapter accepts CPM pricing model."""
    from src.core.config_loader import set_current_tenant
    from src.core.tool_context import ToolContext
    from src.core.utils.tenant_utils import serialize_tenant_to_dict

    request = CreateMediaBuyRequest(
        buyer_ref="test_buyer_ref_cpm",
        brand_manifest="https://example.com/product",
        packages=[
            Package(
                package_id="pkg_1",
                products=["prod_gam_cpm"],
                pricing_model=PricingModel.CPM,  # Supported by GAM
                budget=10000.0,
            )
        ],
        start_time="2025-02-01T00:00:00Z",
        end_time="2025-02-28T23:59:59Z",
        budget=10000.0,
        currency="USD",
    )

    with get_db_session() as session:
        tenant_obj = session.query(Tenant).filter_by(tenant_id="test_gam_tenant").first()
        # Use proper tenant serialization
        tenant_dict = serialize_tenant_to_dict(tenant_obj)
        set_current_tenant(tenant_dict)

    context = ToolContext(
        context_id="test_ctx_gam_cpm",
        tenant_id="test_gam_tenant",
        principal_id="test_advertiser",
        tool_name="create_media_buy",
        request_timestamp=datetime.now(UTC),
    )

    # This should succeed
    response = await _create_media_buy_impl(
        buyer_ref=request.buyer_ref,
        brand_manifest=request.brand_manifest,
        packages=[p.model_dump_internal() for p in request.packages] if request.packages else None,
        start_time=request.start_time,
        end_time=request.end_time,
        budget=request.budget,
        currency=request.currency,
        context=context,
    )

    assert response.media_buy_id is not None
    assert response.status in ["active", "pending"]


@pytest.mark.requires_db
async def test_gam_rejects_cpp_from_multi_pricing_product(setup_gam_tenant_with_non_cpm_product):
    """Test that GAM adapter rejects CPP when buyer chooses it from multi-pricing product."""
    from src.core.config_loader import set_current_tenant
    from src.core.tool_context import ToolContext
    from src.core.utils.tenant_utils import serialize_tenant_to_dict

    request = CreateMediaBuyRequest(
        buyer_ref="test_buyer_ref_cpp",
        brand_manifest="https://example.com/product",
        packages=[
            Package(
                package_id="pkg_1",
                products=["prod_gam_multi"],
                pricing_model=PricingModel.CPP,  # Not supported by GAM
                budget=15000.0,
            )
        ],
        start_time="2025-02-01T00:00:00Z",
        end_time="2025-02-28T23:59:59Z",
        budget=15000.0,
        currency="USD",
    )

    with get_db_session() as session:
        tenant_obj = session.query(Tenant).filter_by(tenant_id="test_gam_tenant").first()
        # Use proper tenant serialization
        tenant_dict = serialize_tenant_to_dict(tenant_obj)
        set_current_tenant(tenant_dict)

    context = ToolContext(
        context_id="test_ctx_gam_cpp",
        tenant_id="test_gam_tenant",
        principal_id="test_advertiser",
        tool_name="create_media_buy",
        request_timestamp=datetime.now(UTC),
    )

    # This should fail with clear error about GAM not supporting CPP
    with pytest.raises(Exception) as exc_info:
        await _create_media_buy_impl(
            buyer_ref=request.buyer_ref,
            brand_manifest=request.brand_manifest,
            packages=[p.model_dump_internal() for p in request.packages] if request.packages else None,
            start_time=request.start_time,
            end_time=request.end_time,
            budget=request.budget,
            currency=request.currency,
            context=context,
        )

    error_msg = str(exc_info.value)
    assert "cpp" in error_msg.lower() or "pricing" in error_msg.lower()


@pytest.mark.requires_db
async def test_gam_accepts_cpm_from_multi_pricing_product(setup_gam_tenant_with_non_cpm_product):
    """Test that GAM adapter accepts CPM when buyer chooses it from multi-pricing product."""
    from src.core.config_loader import set_current_tenant
    from src.core.tool_context import ToolContext
    from src.core.utils.tenant_utils import serialize_tenant_to_dict

    request = CreateMediaBuyRequest(
        buyer_ref="test_buyer_ref_cpm_multi",
        brand_manifest="https://example.com/product",
        packages=[
            Package(
                package_id="pkg_1",
                products=["prod_gam_multi"],
                pricing_model=PricingModel.CPM,  # Supported by GAM
                budget=10000.0,
            )
        ],
        start_time="2025-02-01T00:00:00Z",
        end_time="2025-02-28T23:59:59Z",
        budget=10000.0,
        currency="USD",
    )

    with get_db_session() as session:
        tenant_obj = session.query(Tenant).filter_by(tenant_id="test_gam_tenant").first()
        # Use proper tenant serialization
        tenant_dict = serialize_tenant_to_dict(tenant_obj)
        set_current_tenant(tenant_dict)

    context = ToolContext(
        context_id="test_ctx_gam_cpm_multi",
        tenant_id="test_gam_tenant",
        principal_id="test_advertiser",
        tool_name="create_media_buy",
        request_timestamp=datetime.now(UTC),
    )

    # This should succeed - buyer chose CPM from multi-option product
    response = await _create_media_buy_impl(
        buyer_ref=request.buyer_ref,
        brand_manifest=request.brand_manifest,
        packages=[p.model_dump_internal() for p in request.packages] if request.packages else None,
        start_time=request.start_time,
        end_time=request.end_time,
        budget=request.budget,
        currency=request.currency,
        context=context,
    )

    assert response.media_buy_id is not None
    assert response.status in ["active", "pending"]

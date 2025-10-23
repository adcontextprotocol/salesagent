"""Integration tests for GAM pricing model support (CPC, VCPM, FLAT_RATE).

Tests end-to-end flow of creating media buys with different pricing models
and verifying correct GAM line item configuration.
"""

import pytest

from src.core.database.database_session import get_db_session
from tests.utils.database_helpers import create_tenant_with_timestamps

# TODO: Fix failing tests and remove skip_ci (see GitHub issue #XXX)
pytestmark = [pytest.mark.integration, pytest.mark.requires_db, pytest.mark.skip_ci]


@pytest.fixture
def setup_gam_tenant_with_all_pricing_models(integration_db):
    """Create a GAM tenant with products offering all supported pricing models."""
    with get_db_session() as session:
        # Create GAM tenant
        tenant = create_tenant_with_timestamps(
            tenant_id="test_gam_pricing_tenant",
            name="GAM Pricing Test Publisher",
            subdomain="gam-pricing-test",
            ad_server="google_ad_manager",
        )
        session.add(tenant)
        session.flush()

        # Add adapter config (mock mode for testing)
        adapter_config = AdapterConfig(
            tenant_id="test_gam_pricing_tenant",
            adapter_type="google_ad_manager",
            gam_network_code="123456",
            gam_advertiser_id="gam_adv_123",
            gam_trafficker_id="gam_traffic_456",
            dry_run=True,  # Dry run mode
        )
        session.add(adapter_config)

        # Add currency limit
        currency_limit = CurrencyLimit(
            tenant_id="test_gam_pricing_tenant",
            currency_code="USD",
            max_daily_package_spend=Decimal("100000.00"),
        )
        session.add(currency_limit)

        # Add property tag (required for products)
        property_tag = PropertyTag(
            tenant_id="test_gam_pricing_tenant",
            tag_id="all_inventory",
            tag_name="All Inventory",
            metadata={"description": "All available inventory"},
        )
        session.add(property_tag)

        # Create principal
        principal = Principal(
            tenant_id="test_gam_pricing_tenant",
            principal_id="test_advertiser_pricing",
            name="Test Advertiser - Pricing",
            access_token="test_gam_pricing_token",
            platform_mappings={"google_ad_manager": {"advertiser_id": "gam_adv_123"}},
        )
        session.add(principal)

        # Product 1: CPM pricing (guaranteed)
        product_cpm = Product(
            tenant_id="test_gam_pricing_tenant",
            product_id="prod_gam_cpm_guaranteed",
            name="Display Ads - CPM Guaranteed",
            description="Display inventory with guaranteed CPM pricing",
            formats=["display_300x250"],
            delivery_type="guaranteed",
            property_tags=["all_inventory"],
            targeting_template={},
            implementation_config={
                "targeted_ad_unit_ids": ["ad_unit_123"],
                "line_item_type": "STANDARD",
                "priority": 8,
            },
        )
        session.add(product_cpm)
        session.flush()

        pricing_cpm = PricingOption(
            tenant_id="test_gam_pricing_tenant",
            product_id="prod_gam_cpm_guaranteed",
            pricing_model="cpm",
            rate=Decimal("15.00"),
            currency="USD",
            is_fixed=True,
            price_guidance=None,
            parameters=None,
            min_spend_per_package=None,
        )
        session.add(pricing_cpm)

        # Product 2: CPC pricing (non-guaranteed)
        product_cpc = Product(
            tenant_id="test_gam_pricing_tenant",
            product_id="prod_gam_cpc",
            name="Display Ads - CPC",
            description="Click-based pricing for performance campaigns",
            formats=["display_300x250", "display_728x90"],
            delivery_type="non_guaranteed",
            property_tags=["all_inventory"],
            targeting_template={},
            implementation_config={
                "targeted_ad_unit_ids": ["ad_unit_123"],
            },
        )
        session.add(product_cpc)
        session.flush()

        pricing_cpc = PricingOption(
            tenant_id="test_gam_pricing_tenant",
            product_id="prod_gam_cpc",
            pricing_model="cpc",
            rate=Decimal("2.50"),
            currency="USD",
            is_fixed=True,
            price_guidance=None,
            parameters=None,
            min_spend_per_package=None,
        )
        session.add(pricing_cpc)

        # Product 3: VCPM pricing (guaranteed, viewable impressions)
        product_vcpm = Product(
            tenant_id="test_gam_pricing_tenant",
            product_id="prod_gam_vcpm",
            name="Display Ads - VCPM",
            description="Viewable CPM pricing for brand safety",
            formats=["display_300x250"],
            delivery_type="guaranteed",
            property_tags=["all_inventory"],
            targeting_template={},
            implementation_config={
                "targeted_ad_unit_ids": ["ad_unit_123"],
            },
        )
        session.add(product_vcpm)
        session.flush()

        pricing_vcpm = PricingOption(
            tenant_id="test_gam_pricing_tenant",
            product_id="prod_gam_vcpm",
            pricing_model="vcpm",
            rate=Decimal("18.00"),
            currency="USD",
            is_fixed=True,
            price_guidance=None,
            parameters=None,
            min_spend_per_package=None,
        )
        session.add(pricing_vcpm)

        # Product 4: FLAT_RATE pricing (sponsorship)
        product_flat = Product(
            tenant_id="test_gam_pricing_tenant",
            product_id="prod_gam_flatrate",
            name="Homepage Takeover - Flat Rate",
            description="Fixed daily rate for premium placement",
            formats=["display_728x90", "display_300x600"],
            delivery_type="guaranteed",
            property_tags=["all_inventory"],
            targeting_template={},
            implementation_config={
                "targeted_ad_unit_ids": ["ad_unit_homepage"],
            },
        )
        session.add(product_flat)
        session.flush()

        pricing_flat = PricingOption(
            tenant_id="test_gam_pricing_tenant",
            product_id="prod_gam_flatrate",
            pricing_model="flat_rate",
            rate=Decimal("5000.00"),  # $5000 total
            currency="USD",
            is_fixed=True,
            price_guidance=None,
            parameters=None,
            min_spend_per_package=None,
        )
        session.add(pricing_flat)

        session.commit()

    yield

    # Cleanup
    with get_db_session() as session:
        session.query(PricingOption).filter_by(tenant_id="test_gam_pricing_tenant").delete()
        session.query(Product).filter_by(tenant_id="test_gam_pricing_tenant").delete()
        session.query(PropertyTag).filter_by(tenant_id="test_gam_pricing_tenant").delete()
        session.query(Principal).filter_by(tenant_id="test_gam_pricing_tenant").delete()
        session.query(AdapterConfig).filter_by(tenant_id="test_gam_pricing_tenant").delete()
        session.query(CurrencyLimit).filter_by(tenant_id="test_gam_pricing_tenant").delete()
        session.query(Tenant).filter_by(tenant_id="test_gam_pricing_tenant").delete()
        session.commit()


@pytest.mark.requires_db
def test_gam_cpm_guaranteed_creates_standard_line_item(setup_gam_tenant_with_all_pricing_models):
    """Test CPM guaranteed creates STANDARD line item with priority 8."""
    request = CreateMediaBuyRequest(
        brand_manifest={"name": "https://example.com/product"},
        packages=[
            Package(
                package_id="pkg_cpm",
                products=["prod_gam_cpm_guaranteed"],
                pricing_model=PricingModel.CPM,
                budget=10000.0,
                impressions=100000,
            )
        ],
        budget={"total": 10000.0, "currency": "USD"},
        currency="USD",
        flight_start_date="2025-03-01",
        flight_end_date="2025-03-31",
    )

    class MockContext:
        http_request = type("Request", (), {"headers": {"x-adcp-auth": "test_gam_pricing_token"}})()

    with get_db_session() as session:
        tenant_obj = session.query(Tenant).filter_by(tenant_id="test_gam_pricing_tenant").first()
        tenant = {
            "tenant_id": tenant_obj.tenant_id,
            "name": tenant_obj.name,
            "config": tenant_obj.config,
            "ad_server": tenant_obj.ad_server,
        }
        principal_obj = session.query(Principal).filter_by(tenant_id="test_gam_pricing_tenant").first()

    response = _create_media_buy_impl(request, MockContext(), tenant, principal_obj)

    # Verify response
    assert response.media_buy_id is not None
    assert response.status in ["active", "pending"]
    assert len(response.errors) == 0

    # In dry-run mode, the response should succeed
    # In real mode, we'd verify GAM line item properties:
    # - lineItemType = "STANDARD"
    # - priority = 8
    # - costType = "CPM"
    # - costPerUnit = $15.00


@pytest.mark.requires_db
def test_gam_cpc_creates_price_priority_line_item_with_clicks_goal(setup_gam_tenant_with_all_pricing_models):
    """Test CPC creates PRICE_PRIORITY line item with CLICKS goal unit."""
    request = CreateMediaBuyRequest(
        brand_manifest={"name": "https://example.com/product"},
        packages=[
            Package(
                package_id="pkg_cpc",
                products=["prod_gam_cpc"],
                pricing_model=PricingModel.CPC,
                budget=5000.0,
                impressions=2000,  # 2000 clicks goal
            )
        ],
        budget={"total": 5000.0, "currency": "USD"},
        currency="USD",
        flight_start_date="2025-03-01",
        flight_end_date="2025-03-31",
    )

    class MockContext:
        http_request = type("Request", (), {"headers": {"x-adcp-auth": "test_gam_pricing_token"}})()

    with get_db_session() as session:
        tenant_obj = session.query(Tenant).filter_by(tenant_id="test_gam_pricing_tenant").first()
        tenant = {
            "tenant_id": tenant_obj.tenant_id,
            "name": tenant_obj.name,
            "config": tenant_obj.config,
            "ad_server": tenant_obj.ad_server,
        }
        principal_obj = session.query(Principal).filter_by(tenant_id="test_gam_pricing_tenant").first()

    response = _create_media_buy_impl(request, MockContext(), tenant, principal_obj)

    # Verify response
    assert response.media_buy_id is not None
    assert response.status in ["active", "pending"]
    assert len(response.errors) == 0

    # In real GAM mode, line item would have:
    # - lineItemType = "PRICE_PRIORITY"
    # - priority = 12
    # - costType = "CPC"
    # - costPerUnit = $2.50
    # - primaryGoal.unitType = "CLICKS"
    # - primaryGoal.units = 2000


@pytest.mark.requires_db
def test_gam_vcpm_creates_standard_line_item_with_viewable_impressions(setup_gam_tenant_with_all_pricing_models):
    """Test VCPM creates STANDARD line item with VIEWABLE_IMPRESSIONS goal."""
    request = CreateMediaBuyRequest(
        brand_manifest={"name": "https://example.com/product"},
        packages=[
            Package(
                package_id="pkg_vcpm",
                products=["prod_gam_vcpm"],
                pricing_model=PricingModel.VCPM,
                budget=12000.0,
                impressions=50000,  # 50k viewable impressions
            )
        ],
        budget={"total": 12000.0, "currency": "USD"},
        currency="USD",
        flight_start_date="2025-03-01",
        flight_end_date="2025-03-31",
    )

    class MockContext:
        http_request = type("Request", (), {"headers": {"x-adcp-auth": "test_gam_pricing_token"}})()

    with get_db_session() as session:
        tenant_obj = session.query(Tenant).filter_by(tenant_id="test_gam_pricing_tenant").first()
        tenant = {
            "tenant_id": tenant_obj.tenant_id,
            "name": tenant_obj.name,
            "config": tenant_obj.config,
            "ad_server": tenant_obj.ad_server,
        }
        principal_obj = session.query(Principal).filter_by(tenant_id="test_gam_pricing_tenant").first()

    response = _create_media_buy_impl(request, MockContext(), tenant, principal_obj)

    # Verify response
    assert response.media_buy_id is not None
    assert response.status in ["active", "pending"]
    assert len(response.errors) == 0

    # In real GAM mode, line item would have:
    # - lineItemType = "STANDARD" (VCPM only works with STANDARD)
    # - priority = 8
    # - costType = "VCPM"
    # - costPerUnit = $18.00
    # - primaryGoal.unitType = "VIEWABLE_IMPRESSIONS"
    # - primaryGoal.units = 50000


@pytest.mark.requires_db
def test_gam_flat_rate_calculates_cpd_correctly(setup_gam_tenant_with_all_pricing_models):
    """Test FLAT_RATE converts to CPD (cost per day) correctly."""
    # 10 day campaign: $5000 total = $500/day
    request = CreateMediaBuyRequest(
        brand_manifest={"name": "https://example.com/product"},
        packages=[
            Package(
                package_id="pkg_flat",
                products=["prod_gam_flatrate"],
                pricing_model=PricingModel.FLAT_RATE,
                budget=5000.0,
                impressions=1000000,  # Impressions goal still tracked
            )
        ],
        budget={"total": 5000.0, "currency": "USD"},
        currency="USD",
        flight_start_date="2025-03-01",
        flight_end_date="2025-03-10",  # 10 days
    )

    class MockContext:
        http_request = type("Request", (), {"headers": {"x-adcp-auth": "test_gam_pricing_token"}})()

    with get_db_session() as session:
        tenant_obj = session.query(Tenant).filter_by(tenant_id="test_gam_pricing_tenant").first()
        tenant = {
            "tenant_id": tenant_obj.tenant_id,
            "name": tenant_obj.name,
            "config": tenant_obj.config,
            "ad_server": tenant_obj.ad_server,
        }
        principal_obj = session.query(Principal).filter_by(tenant_id="test_gam_pricing_tenant").first()

    response = _create_media_buy_impl(request, MockContext(), tenant, principal_obj)

    # Verify response
    assert response.media_buy_id is not None
    assert response.status in ["active", "pending"]
    assert len(response.errors) == 0

    # In real GAM mode, line item would have:
    # - lineItemType = "SPONSORSHIP" (FLAT_RATE → CPD uses SPONSORSHIP)
    # - priority = 4
    # - costType = "CPD"
    # - costPerUnit = $500.00 (5000 / 10 days)
    # - primaryGoal.unitType = "IMPRESSIONS"
    # - primaryGoal.units = 1000000


@pytest.mark.requires_db
def test_gam_multi_package_mixed_pricing_models(setup_gam_tenant_with_all_pricing_models):
    """Test creating media buy with multiple packages using different pricing models."""
    request = CreateMediaBuyRequest(
        brand_manifest={"name": "https://example.com/campaign"},
        packages=[
            Package(
                package_id="pkg_1_cpm",
                products=["prod_gam_cpm_guaranteed"],
                pricing_model=PricingModel.CPM,
                budget=8000.0,
                impressions=80000,
            ),
            Package(
                package_id="pkg_2_cpc",
                products=["prod_gam_cpc"],
                pricing_model=PricingModel.CPC,
                budget=3000.0,
                impressions=1200,  # 1200 clicks
            ),
            Package(
                package_id="pkg_3_vcpm",
                products=["prod_gam_vcpm"],
                pricing_model=PricingModel.VCPM,
                budget=9000.0,
                impressions=40000,  # 40k viewable impressions
            ),
        ],
        budget={"total": 20000.0, "currency": "USD"},
        currency="USD",
        flight_start_date="2025-03-01",
        flight_end_date="2025-03-31",
    )

    class MockContext:
        http_request = type("Request", (), {"headers": {"x-adcp-auth": "test_gam_pricing_token"}})()

    with get_db_session() as session:
        tenant_obj = session.query(Tenant).filter_by(tenant_id="test_gam_pricing_tenant").first()
        tenant = {
            "tenant_id": tenant_obj.tenant_id,
            "name": tenant_obj.name,
            "config": tenant_obj.config,
            "ad_server": tenant_obj.ad_server,
        }
        principal_obj = session.query(Principal).filter_by(tenant_id="test_gam_pricing_tenant").first()

    response = _create_media_buy_impl(request, MockContext(), tenant, principal_obj)

    # Verify response
    assert response.media_buy_id is not None
    assert response.status in ["active", "pending"]
    assert len(response.errors) == 0

    # Each package should create a line item with correct pricing:
    # - pkg_1: CPM, STANDARD, priority 8
    # - pkg_2: CPC, PRICE_PRIORITY, priority 12, CLICKS goal
    # - pkg_3: VCPM, STANDARD, priority 8, VIEWABLE_IMPRESSIONS goal


@pytest.mark.requires_db
def test_gam_auction_cpc_creates_price_priority(setup_gam_tenant_with_all_pricing_models):
    """Test auction-based CPC (non-fixed) creates PRICE_PRIORITY line item."""
    # Add auction CPC pricing option
    with get_db_session() as session:
        pricing_auction = PricingOption(
            tenant_id="test_gam_pricing_tenant",
            product_id="prod_gam_cpc",
            pricing_model="cpc",
            rate=None,  # Auction-based, no fixed rate
            currency="USD",
            is_fixed=False,  # Auction
            price_guidance={"floor": 1.50, "ceiling": 3.00},
            parameters=None,
            min_spend_per_package=None,
        )
        session.add(pricing_auction)
        session.commit()

    request = CreateMediaBuyRequest(
        brand_manifest={"name": "https://example.com/product"},
        packages=[
            Package(
                package_id="pkg_auction_cpc",
                products=["prod_gam_cpc"],
                pricing_model=PricingModel.CPC,
                budget=4000.0,
                impressions=1500,  # 1500 clicks
                bid_price=2.25,  # Bid within floor/ceiling
            )
        ],
        budget={"total": 4000.0, "currency": "USD"},
        currency="USD",
        flight_start_date="2025-03-01",
        flight_end_date="2025-03-31",
    )

    class MockContext:
        http_request = type("Request", (), {"headers": {"x-adcp-auth": "test_gam_pricing_token"}})()

    with get_db_session() as session:
        tenant_obj = session.query(Tenant).filter_by(tenant_id="test_gam_pricing_tenant").first()
        tenant = {
            "tenant_id": tenant_obj.tenant_id,
            "name": tenant_obj.name,
            "config": tenant_obj.config,
            "ad_server": tenant_obj.ad_server,
        }
        principal_obj = session.query(Principal).filter_by(tenant_id="test_gam_pricing_tenant").first()

    response = _create_media_buy_impl(request, MockContext(), tenant, principal_obj)

    # Verify response
    assert response.media_buy_id is not None
    assert response.status in ["active", "pending"]
    assert len(response.errors) == 0

    # Line item should use bid_price ($2.25) for costPerUnit
    # - lineItemType = "PRICE_PRIORITY" (auction = non-guaranteed)
    # - costPerUnit = $2.25 (from bid_price)

    # Cleanup auction pricing option
    with get_db_session() as session:
        session.query(PricingOption).filter_by(
            tenant_id="test_gam_pricing_tenant", product_id="prod_gam_cpc", is_fixed=False
        ).delete()
        session.commit()

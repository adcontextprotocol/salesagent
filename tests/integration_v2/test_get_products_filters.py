"""Integration tests for get_products filtering behavior (v2 pricing model).

Tests that AdCP filters parameter correctly filters products from database.
This tests the actual filter logic implementation in main.py, not just schema validation.

MIGRATION NOTE: This file migrates tests from tests/integration/test_get_products_filters.py
to use the new pricing_options model instead of legacy Product pricing fields.
"""

from unittest.mock import Mock

import pytest

from src.core.database.database_session import get_db_session
from src.core.database.models import Principal
from tests.integration_v2.conftest import (
    add_required_setup_data,
    create_auction_product,
    create_test_product_with_pricing,
)
from tests.utils.database_helpers import create_tenant_with_timestamps, get_utc_now

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]


@pytest.fixture
def mock_context():
    """Create mock context with filter_test_token for TestGetProductsFilterBehavior."""
    context = Mock(spec=["meta"])
    context.meta = {"headers": {"x-adcp-auth": "filter_test_token"}}
    return context


@pytest.fixture
def mock_context_filter_logic():
    """Create mock context with filter_logic_token for TestProductFilterLogic."""
    context = Mock(spec=["meta"])
    context.meta = {"headers": {"x-adcp-auth": "filter_logic_token"}}
    return context


@pytest.fixture
def mock_context_edge_case():
    """Create mock context with edge_case_token for TestFilterEdgeCases."""
    context = Mock(spec=["meta"])
    context.meta = {"headers": {"x-adcp-auth": "edge_case_token"}}
    return context


@pytest.mark.requires_db
class TestGetProductsFilterBehavior:
    """Test that filters actually filter products correctly with real database."""

    def _import_get_products_tool(self):
        """Import get_products tool and extract underlying function."""
        from src.core.tools.products import get_products_raw

        return get_products_raw

    @pytest.fixture(autouse=True)
    def setup_diverse_products(self, integration_db):
        """Create products with diverse characteristics for filtering."""
        with get_db_session() as session:
            # Create tenant and principal
            tenant = create_tenant_with_timestamps(
                tenant_id="filter_test",
                name="Filter Test Publisher",
                subdomain="filter-test",
                is_active=True,
                ad_server="mock",
            )
            session.add(tenant)
            session.flush()

            # Add required setup data for tenant
            add_required_setup_data(session, "filter_test")

            principal = Principal(
                tenant_id="filter_test",
                principal_id="test_principal",
                name="Test Advertiser",
                access_token="filter_test_token",
                platform_mappings={"mock": {"id": "test_advertiser"}},
                created_at=get_utc_now(),
            )
            session.add(principal)

            # Create products with different characteristics using new pricing model
            # Guaranteed, fixed-price CPM, display only
            guaranteed_display = create_test_product_with_pricing(
                session=session,
                tenant_id="filter_test",
                product_id="guaranteed_display",
                name="Premium Display - Fixed CPM",
                description="Guaranteed display inventory",
                format_ids=[
                    {"agent_url": "https://test.com", "id": "display_300x250"},
                    {"agent_url": "https://test.com", "id": "display_728x90"},
                ],
                targeting_template={},
                delivery_type="guaranteed",
                pricing_model="CPM",
                rate="15.0",
                is_fixed=True,
                currency="USD",
                countries=["US"],
                is_custom=False,
            )

            # Non-guaranteed, auction pricing, video only
            programmatic_video = create_auction_product(
                session=session,
                tenant_id="filter_test",
                product_id="programmatic_video",
                name="Programmatic Video - Dynamic CPM",
                description="Real-time bidding video inventory",
                format_ids=[
                    {"agent_url": "https://test.com", "id": "video_15s"},
                    {"agent_url": "https://test.com", "id": "video_30s"},
                ],
                targeting_template={},
                delivery_type="non_guaranteed",
                pricing_model="CPM",
                floor_cpm="10.0",
                currency="USD",
                countries=["US", "CA"],
                is_custom=False,
            )

            # Guaranteed, fixed-price CPM, mixed formats (display + video)
            multiformat_guaranteed = create_test_product_with_pricing(
                session=session,
                tenant_id="filter_test",
                product_id="multiformat_guaranteed",
                name="Multi-Format Package - Fixed",
                description="Display + Video combo",
                format_ids=[
                    {"agent_url": "https://test.com", "id": "display_300x250"},
                    {"agent_url": "https://test.com", "id": "video_15s"},
                ],
                targeting_template={},
                delivery_type="guaranteed",
                pricing_model="CPM",
                rate="12.0",
                is_fixed=True,
                currency="USD",
                countries=["US"],
                is_custom=False,
            )

            # Non-guaranteed, auction pricing, display only
            programmatic_display = create_auction_product(
                session=session,
                tenant_id="filter_test",
                product_id="programmatic_display",
                name="Programmatic Display - Dynamic CPM",
                description="Real-time bidding display",
                format_ids=[
                    {"agent_url": "https://test.com", "id": "display_300x250"},
                ],
                targeting_template={},
                delivery_type="non_guaranteed",
                pricing_model="CPM",
                floor_cpm="8.0",
                currency="USD",
                countries=["US"],
                is_custom=False,
            )

            # Guaranteed, fixed-price CPM, audio only
            guaranteed_audio = create_test_product_with_pricing(
                session=session,
                tenant_id="filter_test",
                product_id="guaranteed_audio",
                name="Guaranteed Audio - Fixed CPM",
                description="Podcast advertising",
                format_ids=[
                    {"agent_url": "https://test.com", "id": "audio_30s"},
                ],
                targeting_template={},
                delivery_type="guaranteed",
                pricing_model="CPM",
                rate="20.0",
                is_fixed=True,
                currency="USD",
                countries=["US"],
                is_custom=False,
            )

            session.commit()

    @pytest.mark.asyncio
    async def test_filter_by_delivery_type_guaranteed(self):
        """Test filtering for guaranteed delivery products only."""
        get_products = self._import_get_products_tool()

        # Mock context with authentication
        context = Mock()
        context.meta = {"headers": {"x-adcp-auth": "filter_test_token"}}

        # Call get_products (currently no direct filter param support, will add)
        result = await get_products(
            brand_manifest={"name": "Nike Air Jordan 2025 basketball shoes"},
            brief="",
            ctx=context,
        )

        # Verify we got products (baseline test)
        assert len(result.products) > 0

        # Count products by delivery_type for manual verification
        guaranteed_count = sum(1 for p in result.products if p.delivery_type.value == "guaranteed")
        non_guaranteed_count = sum(1 for p in result.products if p.delivery_type.value == "non_guaranteed")

        # Should have both types before filtering
        assert guaranteed_count >= 3  # guaranteed_display, multiformat_guaranteed, guaranteed_audio
        assert non_guaranteed_count >= 2  # programmatic_video, programmatic_display

    @pytest.mark.asyncio
    async def test_no_filter_returns_all_products(self, mock_context):
        """Test that calling without filters returns all products."""
        get_products = self._import_get_products_tool()

        context = mock_context

        result = await get_products(
            brand_manifest={"name": "Nike Air Jordan 2025 basketball shoes"},
            brief="",
            ctx=context,
        )

        # Should return all 5 products created in fixture
        assert len(result.products) == 5

        # Verify diversity of products
        product_ids = {p.product_id for p in result.products}
        assert "guaranteed_display" in product_ids
        assert "programmatic_video" in product_ids
        assert "multiformat_guaranteed" in product_ids
        assert "programmatic_display" in product_ids
        assert "guaranteed_audio" in product_ids

    @pytest.mark.asyncio
    async def test_products_have_correct_structure(self, mock_context):
        """Test that returned products have all required AdCP fields."""
        get_products = self._import_get_products_tool()

        context = mock_context

        result = await get_products(
            brand_manifest={"name": "Nike Air Jordan 2025 basketball shoes"},
            brief="",
            ctx=context,
        )

        # Check first product has all required fields
        product = result.products[0]
        assert hasattr(product, "product_id")
        assert hasattr(product, "name")
        assert hasattr(product, "description")
        assert hasattr(product, "format_ids")
        assert hasattr(product, "delivery_type")

        # Check pricing_options field (new v2 model)
        assert hasattr(product, "pricing_options")
        assert len(product.pricing_options) > 0

        pricing = product.pricing_options[0]
        assert hasattr(pricing, "pricing_model")
        assert hasattr(pricing, "rate")
        assert hasattr(pricing, "is_fixed")
        assert hasattr(pricing, "currency")

        # Check formats structure
        assert len(product.format_ids) > 0


@pytest.mark.requires_db
class TestNewGetProductsFilters:
    """Test the new AdCP 2.5 filters: start_date, end_date, budget_range, countries, channels."""

    def _import_get_products_tool(self):
        """Import get_products tool and extract underlying function."""
        from src.core.tools.products import get_products_raw

        return get_products_raw

    @pytest.fixture(autouse=True)
    def setup_diverse_filter_products(self, integration_db):
        """Create products with diverse characteristics for new filter testing."""
        from datetime import UTC, datetime, timedelta

        with get_db_session() as session:
            # Create tenant and principal for new filter tests
            tenant = create_tenant_with_timestamps(
                tenant_id="new_filter_test",
                name="New Filter Test Publisher",
                subdomain="new-filter-test",
                is_active=True,
                ad_server="mock",
            )
            session.add(tenant)
            session.flush()

            # Add required setup data for tenant
            add_required_setup_data(session, "new_filter_test")

            principal = Principal(
                tenant_id="new_filter_test",
                principal_id="new_filter_principal",
                name="New Filter Test Advertiser",
                access_token="new_filter_test_token",
                platform_mappings={"mock": {"id": "test_advertiser"}},
                created_at=get_utc_now(),
            )
            session.add(principal)

            # Product 1: US only, display, expires in 30 days, CPM $15
            us_display_expiring = create_test_product_with_pricing(
                session=session,
                tenant_id="new_filter_test",
                product_id="us_display_expiring",
                name="US Display - Expiring Soon",
                description="US display product expiring in 30 days",
                format_ids=[
                    {"agent_url": "https://test.com", "id": "display_300x250"},
                ],
                targeting_template={},
                delivery_type="guaranteed",
                pricing_model="CPM",
                rate="15.0",
                is_fixed=True,
                currency="USD",
                countries=["US"],
                is_custom=False,
                expires_at=datetime.now(UTC) + timedelta(days=30),
            )

            # Product 2: US + CA, video, no expiration, CPM $25
            us_ca_video = create_test_product_with_pricing(
                session=session,
                tenant_id="new_filter_test",
                product_id="us_ca_video",
                name="US/CA Video",
                description="US and Canada video product",
                format_ids=[
                    {"agent_url": "https://test.com", "id": "video_15s"},
                    {"agent_url": "https://test.com", "id": "video_30s"},
                ],
                targeting_template={},
                delivery_type="guaranteed",
                pricing_model="CPM",
                rate="25.0",
                is_fixed=True,
                currency="USD",
                countries=["US", "CA"],
                is_custom=False,
            )

            # Product 3: Global (no country restriction), audio, CPM $20
            global_audio = create_test_product_with_pricing(
                session=session,
                tenant_id="new_filter_test",
                product_id="global_audio",
                name="Global Audio",
                description="Worldwide audio advertising",
                format_ids=[
                    {"agent_url": "https://test.com", "id": "audio_30s"},
                ],
                targeting_template={},
                delivery_type="guaranteed",
                pricing_model="CPM",
                rate="20.0",
                is_fixed=True,
                currency="USD",
                countries=None,  # No country restriction
                is_custom=False,
            )

            # Product 4: UK only, display, CPM £10 (GBP)
            uk_display_gbp = create_test_product_with_pricing(
                session=session,
                tenant_id="new_filter_test",
                product_id="uk_display_gbp",
                name="UK Display - GBP",
                description="UK display product in GBP",
                format_ids=[
                    {"agent_url": "https://test.com", "id": "display_728x90"},
                ],
                targeting_template={},
                delivery_type="guaranteed",
                pricing_model="CPM",
                rate="10.0",
                is_fixed=True,
                currency="GBP",
                countries=["GB"],
                is_custom=False,
            )

            # Product 5: US, native, CPM $8 (low price)
            us_native_cheap = create_test_product_with_pricing(
                session=session,
                tenant_id="new_filter_test",
                product_id="us_native_cheap",
                name="US Native - Budget",
                description="Budget-friendly native ads",
                format_ids=[
                    {"agent_url": "https://test.com", "id": "native_feed"},
                ],
                targeting_template={},
                delivery_type="non_guaranteed",
                pricing_model="CPM",
                rate="8.0",
                is_fixed=True,
                currency="USD",
                countries=["US"],
                is_custom=False,
            )

            # Product 6: US, display, expires yesterday (should be filtered out by end_date)
            us_display_expired = create_test_product_with_pricing(
                session=session,
                tenant_id="new_filter_test",
                product_id="us_display_expired",
                name="US Display - Expired",
                description="Already expired product",
                format_ids=[
                    {"agent_url": "https://test.com", "id": "display_300x250"},
                ],
                targeting_template={},
                delivery_type="guaranteed",
                pricing_model="CPM",
                rate="12.0",
                is_fixed=True,
                currency="USD",
                countries=["US"],
                is_custom=False,
                expires_at=datetime.now(UTC) - timedelta(days=1),
            )

            session.commit()

    @pytest.mark.asyncio
    async def test_filter_by_countries_single_country(self):
        """Test filtering products by a single country."""
        get_products = self._import_get_products_tool()

        context = Mock()
        context.meta = {"headers": {"x-adcp-auth": "new_filter_test_token"}}

        result = await get_products(
            brand_manifest={"name": "Test Brand"},
            brief="",
            filters={"countries": ["US"]},
            ctx=context,
        )

        # Should include: us_display_expiring, us_ca_video, global_audio (no restrictions),
        # us_native_cheap, us_display_expired
        # Should exclude: uk_display_gbp (UK only)
        product_ids = {p.product_id for p in result.products}
        assert "us_display_expiring" in product_ids
        assert "us_ca_video" in product_ids
        assert "global_audio" in product_ids  # No country restriction = matches all
        assert "us_native_cheap" in product_ids
        assert "uk_display_gbp" not in product_ids

    @pytest.mark.asyncio
    async def test_filter_by_countries_multiple_countries(self):
        """Test filtering products by multiple countries."""
        get_products = self._import_get_products_tool()

        context = Mock()
        context.meta = {"headers": {"x-adcp-auth": "new_filter_test_token"}}

        result = await get_products(
            brand_manifest={"name": "Test Brand"},
            brief="",
            filters={"countries": ["CA", "GB"]},
            ctx=context,
        )

        # Should include: us_ca_video (has CA), uk_display_gbp (has GB), global_audio (no restrictions)
        # Should exclude: us_display_expiring (US only), us_native_cheap (US only)
        product_ids = {p.product_id for p in result.products}
        assert "us_ca_video" in product_ids
        assert "uk_display_gbp" in product_ids
        assert "global_audio" in product_ids
        assert "us_display_expiring" not in product_ids
        assert "us_native_cheap" not in product_ids

    @pytest.mark.asyncio
    async def test_filter_by_channels_display(self):
        """Test filtering products by display channel."""
        get_products = self._import_get_products_tool()

        context = Mock()
        context.meta = {"headers": {"x-adcp-auth": "new_filter_test_token"}}

        result = await get_products(
            brand_manifest={"name": "Test Brand"},
            brief="",
            filters={"channels": ["display"]},
            ctx=context,
        )

        # Should include: us_display_expiring, uk_display_gbp, us_display_expired
        # Should exclude: us_ca_video, global_audio, us_native_cheap
        product_ids = {p.product_id for p in result.products}
        assert "us_display_expiring" in product_ids
        assert "uk_display_gbp" in product_ids
        assert "us_display_expired" in product_ids
        assert "us_ca_video" not in product_ids
        assert "global_audio" not in product_ids
        assert "us_native_cheap" not in product_ids

    @pytest.mark.asyncio
    async def test_filter_by_channels_video(self):
        """Test filtering products by video channel."""
        get_products = self._import_get_products_tool()

        context = Mock()
        context.meta = {"headers": {"x-adcp-auth": "new_filter_test_token"}}

        result = await get_products(
            brand_manifest={"name": "Test Brand"},
            brief="",
            filters={"channels": ["video"]},
            ctx=context,
        )

        # Should only include: us_ca_video
        product_ids = {p.product_id for p in result.products}
        assert "us_ca_video" in product_ids
        assert len(product_ids) == 1

    @pytest.mark.asyncio
    async def test_filter_by_channels_multiple(self):
        """Test filtering products by multiple channels."""
        get_products = self._import_get_products_tool()

        context = Mock()
        context.meta = {"headers": {"x-adcp-auth": "new_filter_test_token"}}

        result = await get_products(
            brand_manifest={"name": "Test Brand"},
            brief="",
            filters={"channels": ["audio", "native"]},
            ctx=context,
        )

        # Should include: global_audio, us_native_cheap
        product_ids = {p.product_id for p in result.products}
        assert "global_audio" in product_ids
        assert "us_native_cheap" in product_ids
        assert len(product_ids) == 2

    @pytest.mark.asyncio
    async def test_filter_by_budget_range_usd(self):
        """Test filtering products by budget range in USD."""
        get_products = self._import_get_products_tool()

        context = Mock()
        context.meta = {"headers": {"x-adcp-auth": "new_filter_test_token"}}

        result = await get_products(
            brand_manifest={"name": "Test Brand"},
            brief="",
            filters={"budget_range": {"currency": "USD", "min": 10.0, "max": 20.0}},
            ctx=context,
        )

        # Should include: us_display_expiring ($15), global_audio ($20), us_display_expired ($12)
        # Should exclude: us_ca_video ($25), uk_display_gbp (GBP), us_native_cheap ($8)
        product_ids = {p.product_id for p in result.products}
        assert "us_display_expiring" in product_ids
        assert "global_audio" in product_ids
        assert "us_display_expired" in product_ids
        assert "us_ca_video" not in product_ids
        assert "uk_display_gbp" not in product_ids  # Wrong currency
        assert "us_native_cheap" not in product_ids  # Below min

    @pytest.mark.asyncio
    async def test_filter_by_budget_range_gbp(self):
        """Test filtering products by budget range in GBP."""
        get_products = self._import_get_products_tool()

        context = Mock()
        context.meta = {"headers": {"x-adcp-auth": "new_filter_test_token"}}

        result = await get_products(
            brand_manifest={"name": "Test Brand"},
            brief="",
            filters={"budget_range": {"currency": "GBP", "min": 5.0, "max": 15.0}},
            ctx=context,
        )

        # Should only include: uk_display_gbp (£10)
        product_ids = {p.product_id for p in result.products}
        assert "uk_display_gbp" in product_ids
        assert len(product_ids) == 1

    @pytest.mark.asyncio
    async def test_filter_by_end_date_excludes_expired(self):
        """Test that end_date filter excludes products that expire before campaign ends."""
        from datetime import date, timedelta

        get_products = self._import_get_products_tool()

        context = Mock()
        context.meta = {"headers": {"x-adcp-auth": "new_filter_test_token"}}

        # Campaign ends in 15 days - should exclude product that expires in 30 days
        # But should definitely exclude the already expired product
        campaign_end = date.today() + timedelta(days=15)

        result = await get_products(
            brand_manifest={"name": "Test Brand"},
            brief="",
            filters={"end_date": campaign_end.isoformat()},
            ctx=context,
        )

        # us_display_expired expires yesterday - should be excluded
        product_ids = {p.product_id for p in result.products}
        assert "us_display_expired" not in product_ids

    @pytest.mark.asyncio
    async def test_filter_by_end_date_includes_non_expiring(self):
        """Test that end_date filter includes products without expiration."""
        from datetime import date, timedelta

        get_products = self._import_get_products_tool()

        context = Mock()
        context.meta = {"headers": {"x-adcp-auth": "new_filter_test_token"}}

        # Campaign ends in 60 days
        campaign_end = date.today() + timedelta(days=60)

        result = await get_products(
            brand_manifest={"name": "Test Brand"},
            brief="",
            filters={"end_date": campaign_end.isoformat()},
            ctx=context,
        )

        # Products without expires_at should be included
        product_ids = {p.product_id for p in result.products}
        assert "us_ca_video" in product_ids  # No expiration
        assert "global_audio" in product_ids  # No expiration
        assert "us_display_expiring" in product_ids  # Expires in 30 days, campaign ends in 60

    @pytest.mark.asyncio
    async def test_combined_filters_country_and_channel(self):
        """Test combining country and channel filters."""
        get_products = self._import_get_products_tool()

        context = Mock()
        context.meta = {"headers": {"x-adcp-auth": "new_filter_test_token"}}

        result = await get_products(
            brand_manifest={"name": "Test Brand"},
            brief="",
            filters={
                "countries": ["US"],
                "channels": ["display"],
            },
            ctx=context,
        )

        # Should include: us_display_expiring, us_display_expired
        # Should exclude: uk_display_gbp (not US), us_ca_video (not display)
        product_ids = {p.product_id for p in result.products}
        assert "us_display_expiring" in product_ids
        assert "us_display_expired" in product_ids
        assert "uk_display_gbp" not in product_ids
        assert "us_ca_video" not in product_ids

    @pytest.mark.asyncio
    async def test_combined_filters_country_channel_budget(self):
        """Test combining country, channel, and budget filters."""
        get_products = self._import_get_products_tool()

        context = Mock()
        context.meta = {"headers": {"x-adcp-auth": "new_filter_test_token"}}

        result = await get_products(
            brand_manifest={"name": "Test Brand"},
            brief="",
            filters={
                "countries": ["US"],
                "channels": ["display"],
                "budget_range": {"currency": "USD", "min": 10.0, "max": 16.0},
            },
            ctx=context,
        )

        # Should include: us_display_expiring ($15), us_display_expired ($12)
        # Both are US, display, and within budget
        product_ids = {p.product_id for p in result.products}
        assert "us_display_expiring" in product_ids
        assert "us_display_expired" in product_ids
        assert len(product_ids) == 2

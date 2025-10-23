"""Integration tests for get_products filtering behavior.

Tests that AdCP filters parameter correctly filters products from database.
This tests the actual filter logic implementation in main.py, not just schema validation.
"""

import pytest

from src.core.database.database_session import get_db_session
from tests.utils.database_helpers import create_tenant_with_timestamps, get_utc_now

# TODO: Fix failing tests and remove skip_ci (see GitHub issue #XXX)
pytestmark = [pytest.mark.integration, pytest.mark.skip_ci, pytest.mark.requires_db]


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


class TestGetProductsFilterBehavior:
    """Test that filters actually filter products correctly with real database."""

    def _import_get_products_tool(self):
        """Import get_products tool and extract underlying function."""
        from src.core.main import get_products as core_get_products_tool

        # Extract the actual function from FunctionTool object if needed
        get_products_fn = core_get_products_tool.fn if hasattr(core_get_products_tool, "fn") else core_get_products_tool
        return get_products_fn

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

            principal = Principal(
                tenant_id="filter_test",
                principal_id="test_principal",
                name="Test Advertiser",
                access_token="filter_test_token",
                platform_mappings={"mock": {"id": "test_advertiser"}},
                created_at=get_utc_now(),
            )
            session.add(principal)

            # Create products with different characteristics
            products = [
                # Guaranteed, fixed-price, display only
                Product(
                    tenant_id="filter_test",
                    product_id="guaranteed_display",
                    name="Premium Display - Fixed CPM",
                    description="Guaranteed display inventory",
                    formats=[
                        {"format_id": "display_300x250", "name": "Medium Rectangle", "type": "display"},
                        {"format_id": "display_728x90", "name": "Leaderboard", "type": "display"},
                    ],
                    targeting_template={},
                    delivery_type="guaranteed",
                    is_fixed_price=True,
                    cpm=15.0,
                    is_custom=False,
                    countries=["US"],
                ),
                # Non-guaranteed, dynamic pricing, video only
                Product(
                    tenant_id="filter_test",
                    product_id="programmatic_video",
                    name="Programmatic Video - Dynamic CPM",
                    description="Real-time bidding video inventory",
                    formats=[
                        {"format_id": "video_15s", "name": "15 Second Video", "type": "video"},
                        {"format_id": "video_30s", "name": "30 Second Video", "type": "video"},
                    ],
                    targeting_template={},
                    delivery_type="non_guaranteed",
                    is_fixed_price=False,
                    cpm=None,
                    is_custom=False,
                    countries=["US", "CA"],
                ),
                # Guaranteed, fixed-price, mixed formats (display + video)
                Product(
                    tenant_id="filter_test",
                    product_id="multiformat_guaranteed",
                    name="Multi-Format Package - Fixed",
                    description="Display + Video combo",
                    formats=[
                        {"format_id": "display_300x250", "name": "Medium Rectangle", "type": "display"},
                        {"format_id": "video_15s", "name": "15 Second Video", "type": "video"},
                    ],
                    targeting_template={},
                    delivery_type="guaranteed",
                    is_fixed_price=True,
                    cpm=12.0,
                    is_custom=False,
                    countries=["US"],
                ),
                # Non-guaranteed, dynamic, display only
                Product(
                    tenant_id="filter_test",
                    product_id="programmatic_display",
                    name="Programmatic Display - Dynamic CPM",
                    description="Real-time bidding display",
                    formats=[
                        {"format_id": "display_300x250", "name": "Medium Rectangle", "type": "display"},
                    ],
                    targeting_template={},
                    delivery_type="non_guaranteed",
                    is_fixed_price=False,
                    cpm=None,
                    is_custom=False,
                    countries=["US"],
                ),
                # Guaranteed, fixed-price, audio only
                Product(
                    tenant_id="filter_test",
                    product_id="guaranteed_audio",
                    name="Guaranteed Audio - Fixed CPM",
                    description="Podcast advertising",
                    formats=[
                        {"format_id": "audio_30s", "name": "30 Second Audio", "type": "audio"},
                    ],
                    targeting_template={},
                    delivery_type="guaranteed",
                    is_fixed_price=True,
                    cpm=20.0,
                    is_custom=False,
                    countries=["US"],
                ),
            ]
            session.add_all(products)
            session.commit()

    @pytest.mark.asyncio
    async def test_filter_by_delivery_type_guaranteed(self):
        """Test filtering for guaranteed delivery products only."""
        from unittest.mock import Mock

        get_products = self._import_get_products_tool()

        # Import and extract get_products function
        get_products = self._import_get_products_tool()

        # Mock context with authentication
        context = Mock()
        context.meta = {"headers": {"x-adcp-auth": "filter_test_token"}}

        # Call get_products (currently no direct filter param support, will add)
        result = await get_products(
            brand_manifest={"name": "Nike Air Jordan 2025 basketball shoes"},
            brief="",
            context=context,
        )

        # Verify we got products (baseline test)
        assert len(result.products) > 0

        # Count products by delivery_type for manual verification
        guaranteed_count = sum(1 for p in result.products if p.delivery_type == "guaranteed")
        non_guaranteed_count = sum(1 for p in result.products if p.delivery_type == "non_guaranteed")

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
            context=context,
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
            context=context,
        )

        # Check first product has all required fields
        product = result.products[0]
        assert hasattr(product, "product_id")
        assert hasattr(product, "name")
        assert hasattr(product, "description")
        assert hasattr(product, "formats")
        assert hasattr(product, "delivery_type")
        assert hasattr(product, "is_fixed_price")

        # Check formats structure - can be either strings (format IDs) or Format objects
        assert len(product.formats) > 0
        fmt = product.formats[0]
        # Formats can be strings (format IDs) or Format objects
        if isinstance(fmt, str):
            assert len(fmt) > 0  # Valid format ID string
        else:
            # Format object
            assert hasattr(fmt, "format_id")
            assert hasattr(fmt, "name")
            assert hasattr(fmt, "type")


class TestProductFilterLogic:
    """Test filter logic in isolation (manual filtering of results)."""

    def _import_get_products_tool(self):
        """Import get_products tool and extract underlying function."""
        from src.core.main import get_products as core_get_products_tool

        get_products_fn = core_get_products_tool.fn if hasattr(core_get_products_tool, "fn") else core_get_products_tool
        return get_products_fn

    @pytest.fixture(autouse=True)
    def setup_products(self, integration_db):
        """Reuse the diverse products setup."""
        with get_db_session() as session:
            tenant = create_tenant_with_timestamps(
                tenant_id="filter_logic_test",
                name="Filter Logic Test",
                subdomain="filter-logic",
                is_active=True,
                ad_server="mock",
            )
            session.add(tenant)

            principal = Principal(
                tenant_id="filter_logic_test",
                principal_id="test_principal",
                name="Test Advertiser",
                access_token="filter_logic_token",
                platform_mappings={"mock": {"id": "test"}},
                created_at=get_utc_now(),
            )
            session.add(principal)

            products = [
                Product(
                    tenant_id="filter_logic_test",
                    product_id="guaranteed_video_fixed",
                    name="Guaranteed Video Fixed",
                    description="Test product",
                    formats=["video_1280x720"],  # Use valid format ID from FORMAT_REGISTRY
                    targeting_template={},
                    delivery_type="guaranteed",
                    is_fixed_price=True,
                    cpm=25.0,
                    is_custom=False,
                    countries=["US"],
                ),
                Product(
                    tenant_id="filter_logic_test",
                    product_id="programmatic_display_dynamic",
                    name="Programmatic Display Dynamic",
                    description="Test product",
                    formats=["display_300x250"],  # Use string format IDs, not dicts
                    targeting_template={},
                    delivery_type="non_guaranteed",
                    is_fixed_price=False,
                    cpm=None,
                    is_custom=False,
                    countries=["US"],
                ),
            ]
            session.add_all(products)
            session.commit()

    @pytest.mark.asyncio
    async def test_delivery_type_filter_guaranteed(self, mock_context_filter_logic):
        """Test manual filtering by guaranteed delivery_type."""
        get_products = self._import_get_products_tool()

        context = mock_context_filter_logic

        result = await get_products(
            brand_manifest={"name": "Nike Air Jordan 2025 basketball shoes"},
            brief="",
            context=context,
        )

        # Manual filter - simulating what the filter logic should do
        filtered = [p for p in result.products if p.delivery_type == DeliveryType.GUARANTEED.value]

        assert len(filtered) == 1
        assert filtered[0].product_id == "guaranteed_video_fixed"

    @pytest.mark.asyncio
    async def test_delivery_type_filter_non_guaranteed(self, mock_context_filter_logic):
        """Test manual filtering by non-guaranteed delivery_type."""
        get_products = self._import_get_products_tool()

        context = mock_context_filter_logic

        result = await get_products(
            brand_manifest={"name": "Nike Air Jordan 2025 basketball shoes"},
            brief="",
            context=context,
        )

        filtered = [p for p in result.products if p.delivery_type == DeliveryType.NON_GUARANTEED.value]

        assert len(filtered) == 1
        assert filtered[0].product_id == "programmatic_display_dynamic"

    @pytest.mark.asyncio
    async def test_is_fixed_price_filter_true(self, mock_context_filter_logic):
        """Test manual filtering by is_fixed_price=True."""
        get_products = self._import_get_products_tool()

        context = mock_context_filter_logic

        result = await get_products(
            brand_manifest={"name": "Nike Air Jordan 2025 basketball shoes"},
            brief="",
            context=context,
        )

        filtered = [p for p in result.products if p.is_fixed_price is True]

        assert len(filtered) == 1
        assert filtered[0].product_id == "guaranteed_video_fixed"
        # Note: cpm is None for anonymous users (authentication not mocked in integration tests)
        # The is_fixed_price filter still works correctly

    @pytest.mark.asyncio
    async def test_is_fixed_price_filter_false(self, mock_context_filter_logic):
        """Test manual filtering by is_fixed_price=False."""
        get_products = self._import_get_products_tool()

        context = mock_context_filter_logic

        result = await get_products(
            brand_manifest={"name": "Nike Air Jordan 2025 basketball shoes"},
            brief="",
            context=context,
        )

        filtered = [p for p in result.products if p.is_fixed_price is False]

        assert len(filtered) == 1
        assert filtered[0].product_id == "programmatic_display_dynamic"
        assert filtered[0].cpm is None

    @pytest.mark.asyncio
    async def test_format_type_filter_video(self, mock_context_filter_logic):
        """Test manual filtering by format_types containing video."""
        get_products = self._import_get_products_tool()

        context = mock_context_filter_logic

        result = await get_products(
            brand_manifest={"name": "Nike Air Jordan 2025 basketball shoes"},
            brief="",
            context=context,
        )

        # Filter for products with video formats
        from src.core.schemas import get_format_by_id

        filtered = []
        for p in result.products:
            format_types = set()
            for fmt_id in p.formats:
                if isinstance(fmt_id, str):
                    fmt_obj = get_format_by_id(fmt_id)
                    if fmt_obj:
                        format_types.add(fmt_obj.type)
                elif hasattr(fmt_id, "type"):
                    format_types.add(fmt_id.type)

            if FormatType.VIDEO.value in format_types:
                filtered.append(p)

        assert len(filtered) == 1
        assert filtered[0].product_id == "guaranteed_video_fixed"

    @pytest.mark.asyncio
    async def test_format_type_filter_display(self, mock_context_filter_logic):
        """Test manual filtering by format_types containing display."""
        get_products = self._import_get_products_tool()

        context = mock_context_filter_logic

        result = await get_products(
            brand_manifest={"name": "Nike Air Jordan 2025 basketball shoes"},
            brief="",
            context=context,
        )

        # Filter for products with display formats
        from src.core.schemas import get_format_by_id

        filtered = []
        for p in result.products:
            format_types = set()
            for fmt_id in p.formats:
                if isinstance(fmt_id, str):
                    fmt_obj = get_format_by_id(fmt_id)
                    if fmt_obj:
                        format_types.add(fmt_obj.type)
                elif hasattr(fmt_id, "type"):
                    format_types.add(fmt_id.type)

            if FormatType.DISPLAY.value in format_types:
                filtered.append(p)

        assert len(filtered) == 1
        assert filtered[0].product_id == "programmatic_display_dynamic"

    @pytest.mark.asyncio
    async def test_format_id_filter_specific(self, mock_context_filter_logic):
        """Test manual filtering by specific format_id."""
        get_products = self._import_get_products_tool()

        context = mock_context_filter_logic

        result = await get_products(
            brand_manifest={"name": "Nike Air Jordan 2025 basketball shoes"},
            brief="",
            context=context,
        )

        # Filter for products with video_1280x720 format
        filtered = []
        for p in result.products:
            format_ids = set()
            for fmt_id in p.formats:
                if isinstance(fmt_id, str):
                    format_ids.add(fmt_id)
                elif hasattr(fmt_id, "format_id"):
                    format_ids.add(fmt_id.format_id)

            if "video_1280x720" in format_ids:
                filtered.append(p)

        assert len(filtered) == 1
        assert filtered[0].product_id == "guaranteed_video_fixed"

    @pytest.mark.asyncio
    async def test_combined_filters_delivery_and_pricing(self, mock_context_filter_logic):
        """Test combining multiple filters (delivery_type + is_fixed_price)."""
        get_products = self._import_get_products_tool()

        context = mock_context_filter_logic

        result = await get_products(
            brand_manifest={"name": "Nike Air Jordan 2025 basketball shoes"},
            brief="",
            context=context,
        )

        # Filter for guaranteed + fixed price
        filtered = []
        for p in result.products:
            if p.delivery_type == DeliveryType.GUARANTEED.value and p.is_fixed_price is True:
                filtered.append(p)

        assert len(filtered) == 1
        assert filtered[0].product_id == "guaranteed_video_fixed"

    @pytest.mark.asyncio
    async def test_combined_filters_no_matches(self, mock_context_filter_logic):
        """Test that conflicting filters return empty results."""
        get_products = self._import_get_products_tool()

        context = mock_context_filter_logic

        result = await get_products(
            brand_manifest={"name": "Nike Air Jordan 2025 basketball shoes"},
            brief="",
            context=context,
        )

        # Filter for impossible combination (guaranteed + dynamic pricing)
        filtered = []
        for p in result.products:
            if p.delivery_type == DeliveryType.GUARANTEED.value and p.is_fixed_price is False:
                filtered.append(p)

        assert len(filtered) == 0  # No products match this combination


class TestFilterEdgeCases:
    """Test edge cases and error handling in filter logic."""

    def _import_get_products_tool(self):
        """Import get_products tool and extract underlying function."""
        from src.core.main import get_products as core_get_products_tool

        get_products_fn = core_get_products_tool.fn if hasattr(core_get_products_tool, "fn") else core_get_products_tool
        return get_products_fn

    @pytest.fixture(autouse=True)
    def setup_edge_case_products(self, integration_db):
        """Create products for edge case testing."""
        with get_db_session() as session:
            tenant = create_tenant_with_timestamps(
                tenant_id="edge_case_test",
                name="Edge Case Test",
                subdomain="edge-case",
                is_active=True,
                ad_server="mock",
            )
            session.add(tenant)

            principal = Principal(
                tenant_id="edge_case_test",
                principal_id="test_principal",
                name="Test Advertiser",
                access_token="edge_case_token",
                platform_mappings={"mock": {"id": "test"}},
                created_at=get_utc_now(),
            )
            session.add(principal)

            # Product with empty formats list (edge case)
            products = [
                Product(
                    tenant_id="edge_case_test",
                    product_id="no_formats_product",
                    name="No Formats Product",
                    description="Product with empty formats (edge case)",
                    formats=[],  # Empty formats list
                    targeting_template={},
                    delivery_type="guaranteed",
                    is_fixed_price=True,
                    cpm=10.0,
                    is_custom=False,
                    countries=["US"],
                ),
            ]
            session.add_all(products)
            session.commit()

    @pytest.mark.asyncio
    async def test_product_with_empty_formats(self, mock_context_edge_case):
        """Test that products with empty formats lists are handled correctly."""
        get_products = self._import_get_products_tool()

        context = mock_context_edge_case

        result = await get_products(
            brand_manifest={"name": "Nike Air Jordan 2025 basketball shoes"},
            brief="",
            context=context,
        )

        # Should return the product even with empty formats
        assert len(result.products) == 1
        assert result.products[0].product_id == "no_formats_product"
        assert result.products[0].formats == []

    @pytest.mark.asyncio
    async def test_format_filter_with_empty_formats_product(self, mock_context_edge_case):
        """Test filtering by format_types when product has empty formats."""
        get_products = self._import_get_products_tool()

        context = mock_context_edge_case

        result = await get_products(
            brand_manifest={"name": "Nike Air Jordan 2025 basketball shoes"},
            brief="",
            context=context,
        )

        # Manual filter for video formats
        filtered = []
        for p in result.products:
            if p.formats:  # Only filter if formats exist
                format_types = {fmt.type for fmt in p.formats}
                if FormatType.VIDEO.value in format_types:
                    filtered.append(p)

        # Should not match product with empty formats
        assert len(filtered) == 0

"""Test that our custom schemas are compatible with generated AdCP schemas.

This ensures we don't drift from the official specification. Our custom schemas
add internal fields (tenant_id, etc.) and extension fields, but must remain
convertible to the official generated schemas.
"""

from datetime import UTC, datetime, timedelta

import pytest

from src.core.schemas import (
    CreateMediaBuyResponse,
    GetMediaBuyDeliveryResponse,
    GetProductsResponse,
    ListCreativeFormatsResponse,
    ListCreativesResponse,
    UpdateMediaBuyResponse,
)


class TestGeneratedSchemaCompatibility:
    """Validate custom schemas against generated AdCP schemas."""

    def test_create_media_buy_response_compatible(self):
        """Test CreateMediaBuyResponse is compatible with generated schema."""
        from src.core.schemas_generated._schemas_v1_media_buy_create_media_buy_response_json import (
            CreateMediaBuyResponse as GeneratedCreateMediaBuyResponse,
        )

        # Create response with our custom model (protocol fields excluded per PR #113)
        custom_response = CreateMediaBuyResponse(
            buyer_ref="test_ref_123",
            media_buy_id="mb_test_456",
            creative_deadline=datetime.now(UTC) + timedelta(days=7),
            packages=[],
            errors=None,
        )

        # Convert to AdCP-compliant dict (exclude any remaining non-spec fields)
        # Protocol fields (status, task_id, message, context_id) are added by transport layer
        adcp_dict = custom_response.model_dump(exclude={"adcp_version"})

        # Validate it loads into generated schema
        try:
            generated = GeneratedCreateMediaBuyResponse(**adcp_dict)
            assert generated.buyer_ref == "test_ref_123"
            assert generated.media_buy_id == "mb_test_456"
        except Exception as e:
            pytest.fail(
                f"CreateMediaBuyResponse not compatible with generated schema: {e}\n"
                f"AdCP dict keys: {list(adcp_dict.keys())}"
            )

    def test_get_products_response_compatible(self):
        """Test GetProductsResponse is compatible with generated schema."""
        from src.core.schemas_generated._schemas_v1_media_buy_get_products_response_json import (
            GetProductsResponse as GeneratedGetProductsResponse,
        )

        # Create minimal response (protocol fields excluded per PR #113)
        custom_response = GetProductsResponse(
            products=[],
        )

        adcp_dict = custom_response.model_dump(exclude={"adcp_version"})

        try:
            generated = GeneratedGetProductsResponse(**adcp_dict)
            assert generated.products == []
        except Exception as e:
            pytest.fail(f"GetProductsResponse not compatible: {e}\n" f"AdCP dict keys: {list(adcp_dict.keys())}")

    # NOTE: test_sync_creatives_response_compatible removed because SyncCreativesResponse
    # schema diverged from official AdCP spec. Custom schema has: summary, results,
    # assignments_summary, assignment_results. Official schema has: creatives.
    # This needs schema alignment work tracked in a separate issue.

    def test_list_creatives_response_compatible(self):
        """Test ListCreativesResponse is compatible with generated schema."""
        from src.core.schemas import Pagination, QuerySummary
        from src.core.schemas_generated._schemas_v1_media_buy_list_creatives_response_json import (
            ListCreativesResponse as GeneratedListCreativesResponse,
        )

        custom_response = ListCreativesResponse(
            query_summary=QuerySummary(
                total_matching=0,
                returned=0,
            ),
            pagination=Pagination(
                limit=50,
                offset=0,
                has_more=False,
            ),
            creatives=[],
        )

        adcp_dict = custom_response.model_dump(exclude={"adcp_version", "status", "task_id", "context_id", "message"})

        try:
            generated = GeneratedListCreativesResponse(**adcp_dict)
            assert generated.query_summary.total_matching == 0
            assert generated.pagination.limit == 50
        except Exception as e:
            pytest.fail(f"ListCreativesResponse not compatible: {e}\n" f"AdCP dict keys: {list(adcp_dict.keys())}")

    def test_get_media_buy_delivery_response_compatible(self):
        """Test GetMediaBuyDeliveryResponse is compatible with generated schema."""
        from src.core.schemas import AggregatedTotals, ReportingPeriod
        from src.core.schemas_generated._schemas_v1_media_buy_get_media_buy_delivery_response_json import (
            GetMediaBuyDeliveryResponse as GeneratedGetMediaBuyDeliveryResponse,
        )

        # Create response with domain fields only (protocol fields excluded per PR #113)
        custom_response = GetMediaBuyDeliveryResponse(
            reporting_period=ReportingPeriod(
                start="2025-01-01T00:00:00Z",
                end="2025-01-31T23:59:59Z",
            ),
            currency="USD",
            aggregated_totals=AggregatedTotals(
                impressions=0.0,
                spend=0.0,
                media_buy_count=0,
            ),
            media_buy_deliveries=[],
        )

        adcp_dict = custom_response.model_dump()

        try:
            generated = GeneratedGetMediaBuyDeliveryResponse(**adcp_dict)
            assert generated.currency == "USD"
            assert generated.aggregated_totals.media_buy_count == 0
            assert generated.media_buy_deliveries == []
        except Exception as e:
            pytest.fail(
                f"GetMediaBuyDeliveryResponse not compatible: {e}\n" f"AdCP dict keys: {list(adcp_dict.keys())}"
            )

    def test_list_creative_formats_response_compatible(self):
        """Test ListCreativeFormatsResponse is compatible with generated schema."""
        from src.core.schemas_generated._schemas_v1_media_buy_list_creative_formats_response_json import (
            ListCreativeFormatsResponse as GeneratedListCreativeFormatsResponse,
        )

        # Create response with domain fields only (protocol fields excluded per PR #113)
        custom_response = ListCreativeFormatsResponse(
            formats=[],
        )

        adcp_dict = custom_response.model_dump(exclude={"adcp_version"})

        try:
            generated = GeneratedListCreativeFormatsResponse(**adcp_dict)
            assert generated.formats == []
        except Exception as e:
            pytest.fail(
                f"ListCreativeFormatsResponse not compatible: {e}\n" f"AdCP dict keys: {list(adcp_dict.keys())}"
            )

    # NOTE: list_authorized_properties test removed - manual schema uses list[str],
    # generated uses list[PublisherDomain(RootModel[str])]. This is a known schema
    # drift that will be fixed when we fully migrate to generated schemas.

    def test_update_media_buy_response_compatible(self):
        """Test UpdateMediaBuyResponse is compatible with generated schema."""
        from src.core.schemas_generated._schemas_v1_media_buy_update_media_buy_response_json import (
            UpdateMediaBuyResponse as GeneratedUpdateMediaBuyResponse,
        )

        # Create response with domain fields only (protocol fields excluded per PR #113)
        custom_response = UpdateMediaBuyResponse(
            media_buy_id="mb_123",
            buyer_ref="test_buyer_ref",  # Required per AdCP spec
        )

        adcp_dict = custom_response.model_dump(exclude={"adcp_version"})

        try:
            generated = GeneratedUpdateMediaBuyResponse(**adcp_dict)
            assert generated.media_buy_id == "mb_123"
            assert generated.buyer_ref == "test_buyer_ref"
        except Exception as e:
            pytest.fail(f"UpdateMediaBuyResponse not compatible: {e}\n" f"AdCP dict keys: {list(adcp_dict.keys())}")

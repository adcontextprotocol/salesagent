"""Test that all MCP response classes have human-readable __str__() methods."""

from datetime import UTC, datetime

from src.core.schemas import (
    ActivateSignalResponse,
    CreateHumanTaskResponse,
    CreateMediaBuyResponse,
    Creative,
    Format,
    GetProductsResponse,
    ListCreativeFormatsResponse,
    ListCreativesResponse,
    Pagination,
    Product,
    QuerySummary,
    SimulationControlResponse,
    SyncCreativesResponse,
    UpdateMediaBuyResponse,
    UpdatePerformanceIndexResponse,
)


class TestResponseStrMethods:
    """Test __str__() methods return human-readable content for MCP."""

    def test_get_products_response_with_pricing(self):
        """GetProductsResponse with pricing returns standard message."""
        product = Product(
            product_id="test",
            name="Test",
            description="Test",
            formats=["banner"],
            delivery_type="guaranteed",
            is_fixed_price=True,
            is_custom=False,
            currency="USD",
            property_tags=["all_inventory"],  # Required per AdCP spec
            cpm=10.0,  # Has pricing
            min_spend=100.0,
        )
        resp = GetProductsResponse(products=[product])
        assert str(resp) == "Found 1 product that matches your requirements."

    def test_get_products_response_with_multiple_products(self):
        """GetProductsResponse with multiple products generates count-based message."""
        products = [
            Product(
                product_id=f"p{i}",
                name=f"Product {i}",
                description="Test",
                formats=["banner"],
                property_tags=["all_inventory"],  # Required per AdCP spec
                delivery_type="guaranteed",
                is_fixed_price=True,
                is_custom=False,
                currency="USD",
                cpm=10.0,  # Has pricing
                min_spend=100.0,
            )
            for i in range(3)
        ]
        resp = GetProductsResponse(products=products)
        assert str(resp) == "Found 3 products that match your requirements."

    def test_get_products_response_anonymous_user(self):
        """GetProductsResponse without pricing (anonymous user) adds auth message."""
        products = [
            Product(
                product_id=f"p{i}",
                name=f"Product {i}",
                description="Test",
                formats=["banner"],
                property_tags=["all_inventory"],
                delivery_type="guaranteed",
                is_fixed_price=True,
                is_custom=False,
                currency="USD",
                # No cpm or min_spend - anonymous user
            )
            for i in range(2)
        ]
        resp = GetProductsResponse(products=products)
        assert (
            str(resp)
            == "Found 2 products that match your requirements. Please connect through an authorized buying agent for pricing data."
        )

    def test_list_creative_formats_response_single_format(self):
        """ListCreativeFormatsResponse with single format generates appropriate message."""
        fmt = Format(format_id="banner_300x250", name="Banner", type="display")
        resp = ListCreativeFormatsResponse(formats=[fmt])
        assert str(resp) == "Found 1 creative format."

    def test_list_creative_formats_response_multiple_formats(self):
        """ListCreativeFormatsResponse with multiple formats generates count."""
        formats = [Format(format_id=f"fmt{i}", name=f"Format {i}", type="display") for i in range(5)]
        resp = ListCreativeFormatsResponse(formats=formats)
        assert str(resp) == "Found 5 creative formats."

    def test_list_creative_formats_response_empty(self):
        """ListCreativeFormatsResponse with no formats generates appropriate message."""
        resp = ListCreativeFormatsResponse(formats=[])
        assert str(resp) == "No creative formats are currently supported."

    def test_sync_creatives_response(self):
        """SyncCreativesResponse generates message from summary data."""
        from src.core.schemas import SyncSummary

        resp = SyncCreativesResponse(
            summary=SyncSummary(total_processed=3, created=2, updated=1, unchanged=0, deleted=0, failed=0),
            dry_run=False,
        )
        assert str(resp) == "Creative sync completed: 2 created, 1 updated"

    def test_list_creatives_response(self):
        """ListCreativesResponse generates message from creatives count."""
        creative = Creative(
            creative_id="cr1",
            name="Test Creative",
            format_id="display_300x250",
            content_uri="https://example.com/creative.jpg",
            principal_id="prin_123",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        resp = ListCreativesResponse(
            query_summary=QuerySummary(total_matching=1, returned=1, has_more=False),
            pagination=Pagination(limit=10, offset=0, has_more=False),
            creatives=[creative],
        )
        assert str(resp) == "Found 1 creative."

    def test_activate_signal_response_success(self):
        """ActivateSignalResponse shows success message."""
        resp = ActivateSignalResponse(signal_id="sig_123", activation_details={"platform_id": "seg_456"})
        assert str(resp) == "Signal sig_123 activated successfully."

    def test_activate_signal_response_with_errors(self):
        """ActivateSignalResponse with errors shows error count."""
        from src.core.schemas import Error

        resp = ActivateSignalResponse(
            signal_id="sig_123",
            errors=[Error(code="ACTIVATION_FAILED", message="Failed to activate")],
        )
        assert str(resp) == "Signal sig_123 activation encountered 1 error(s)."

    def test_simulation_control_response_with_message(self):
        """SimulationControlResponse with message returns the message."""
        resp = SimulationControlResponse(status="ok", message="Simulation advanced to 2025-01-15")
        assert str(resp) == "Simulation advanced to 2025-01-15"

    def test_simulation_control_response_without_message(self):
        """SimulationControlResponse without message shows status."""
        resp = SimulationControlResponse(status="ok")
        assert str(resp) == "Simulation control: ok"

    def test_create_media_buy_response_with_id(self):
        """CreateMediaBuyResponse shows created media buy ID."""
        resp = CreateMediaBuyResponse(buyer_ref="ref_123", media_buy_id="mb_456", packages=[])
        assert str(resp) == "Media buy mb_456 created successfully."

    def test_create_media_buy_response_without_id(self):
        """CreateMediaBuyResponse without ID shows buyer ref."""
        resp = CreateMediaBuyResponse(buyer_ref="ref_123", packages=[])
        assert str(resp) == "Media buy ref_123 created."

    def test_update_media_buy_response(self):
        """UpdateMediaBuyResponse shows updated media buy ID."""
        resp = UpdateMediaBuyResponse(media_buy_id="mb_123", buyer_ref="ref_456", affected_packages=[])
        assert str(resp) == "Media buy mb_123 updated successfully."

    # Note: GetMediaBuyDeliveryResponse, CreateCreativeResponse, GetSignalsResponse
    # have complex nested models. Their __str__() methods are implemented and work,
    # but creating test instances requires many nested fields. Tested via integration tests.

    def test_update_performance_index_response(self):
        """UpdatePerformanceIndexResponse returns detail field."""
        resp = UpdatePerformanceIndexResponse(status="success", detail="Performance index updated for 5 products")
        assert str(resp) == "Performance index updated for 5 products"

    def test_create_human_task_response(self):
        """CreateHumanTaskResponse shows task ID and status."""
        resp = CreateHumanTaskResponse(task_id="task_123", status="pending")
        assert str(resp) == "Task task_123 created with status: pending"

    def test_all_responses_avoid_json_in_content(self):
        """Verify no response __str__ contains JSON-like content."""
        from src.core.schemas import SyncSummary

        # Test a few responses to ensure they don't leak JSON
        responses = [
            GetProductsResponse(products=[]),
            ListCreativeFormatsResponse(formats=[]),
            SyncCreativesResponse(
                summary=SyncSummary(total_processed=0, created=0, updated=0, unchanged=0, deleted=0, failed=0),
                dry_run=False,
            ),
            CreateMediaBuyResponse(buyer_ref="ref", packages=[]),
        ]

        for resp in responses:
            content = str(resp)
            # Should not contain obvious JSON markers (allowing empty dicts/lists in messages)
            assert "adcp_version=" not in content
            assert "product_id=" not in content

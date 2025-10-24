"""Integration tests for create_media_buy creative_ids validation.

Tests that create_media_buy rejects non-existent creative IDs, matching the
behavior of update_media_buy.
"""

from datetime import UTC
from unittest.mock import MagicMock, patch

import pytest

from src.core.database.models import Creative as DBCreative
from src.core.main import _create_media_buy_impl
from src.core.schemas import CreateMediaBuyResponse


@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_create_media_buy_rejects_missing_creatives(integration_db):
    """Test that create_media_buy rejects requests with non-existent creative IDs.

    This ensures consistency with update_media_buy which also validates creative IDs.
    """
    from datetime import datetime

    from src.core.database.database_session import get_db_session
    from src.core.database.models import (
        CurrencyLimit,
        Principal,
        Product,
        PropertyTag,
        Tenant,
    )

    with get_db_session() as session:
        # Create tenant
        tenant = Tenant(
            tenant_id="test_tenant",
            name="Test Org",
            subdomain="test",
        )
        session.add(tenant)

        # Create currency limit (required for product)
        currency_limit = CurrencyLimit(
            tenant_id="test_tenant",
            currency_code="USD",
            max_daily_package_spend=10000.0,
        )
        session.add(currency_limit)

        # Create property tag (required for product)
        property_tag = PropertyTag(
            tenant_id="test_tenant",
            tag_id="all_inventory",
            name="All Inventory",
            description="All available inventory",
        )
        session.add(property_tag)

        # Create principal
        principal = Principal(
            principal_id="test_principal",
            tenant_id="test_tenant",
            name="Test Advertiser",
            platform_mappings={"google_ad_manager": {"advertiser_id": "test_adv_123"}},
            access_token="test_token",
        )
        session.add(principal)

        # Create product
        product = Product(
            product_id="test_product",
            tenant_id="test_tenant",
            name="Test Product",
            description="Test Product Description",
            formats=[{"format_id": "display_300x250", "name": "Medium Rectangle", "type": "display"}],
            targeting_template={},
            delivery_type="guaranteed",
            property_tags=["all_inventory"],
        )
        session.add(product)

        # Note: Intentionally NOT creating any creatives
        session.commit()

    # Mock context and tenant resolution
    mock_context = MagicMock()
    mock_context.headers = {"x-adcp-auth": "test_token"}

    with (
        patch("src.core.main._verify_principal"),
        patch("src.core.main._get_principal_id_from_context", return_value="test_principal"),
        patch("src.core.main.get_current_tenant", return_value={"tenant_id": "test_tenant"}),
        patch("src.core.main.get_principal_object", return_value=principal),
        patch("src.core.main.get_adapter") as mock_get_adapter,
        patch("src.core.main.get_context_manager") as mock_ctx_mgr,
    ):
        # Mock adapter
        mock_adapter = MagicMock()
        mock_adapter.manual_approval_required = False
        mock_adapter.create_media_buy.return_value = {
            "order_id": "order_123",
            "line_items": [{"line_item_id": "li_123", "package_id": "pkg_1"}],
        }
        mock_get_adapter.return_value = mock_adapter

        # Mock context manager
        mock_ctx_manager_inst = MagicMock()
        mock_ctx_manager_inst.get_or_create_context.return_value = MagicMock(context_id="ctx_123")
        mock_ctx_manager_inst.create_workflow_step.return_value = MagicMock(step_id="step_123")
        mock_ctx_mgr.return_value = mock_ctx_manager_inst

        # Call create_media_buy with non-existent creative IDs
        response = await _create_media_buy_impl(
            buyer_ref="buyer_ref_123",
            brand_manifest={"website": "https://example.com"},
            packages=[
                {
                    "package_id": "pkg_1",
                    "product_ids": ["test_product"],
                    "impressions": 100000,
                    "creative_ids": ["nonexistent_creative_1", "nonexistent_creative_2"],
                }
            ],
            start_time=datetime(2025, 11, 1, tzinfo=UTC),
            end_time=datetime(2025, 11, 30, tzinfo=UTC),
            budget=1000.0,
            context=mock_context,
        )

    # Verify error response
    assert isinstance(response, CreateMediaBuyResponse)
    assert response.errors is not None
    assert len(response.errors) > 0
    assert response.errors[0]["code"] == "creatives_not_found"
    assert "nonexistent_creative_1" in response.errors[0]["message"]
    assert "nonexistent_creative_2" in response.errors[0]["message"]


@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_create_media_buy_accepts_existing_creatives(integration_db):
    """Test that create_media_buy accepts valid creative IDs."""
    from datetime import datetime

    from src.core.database.database_session import get_db_session
    from src.core.database.models import (
        CurrencyLimit,
        Principal,
        Product,
        PropertyTag,
        Tenant,
    )

    with get_db_session() as session:
        # Create tenant
        tenant = Tenant(
            tenant_id="test_tenant",
            name="Test Org",
            subdomain="test",
        )
        session.add(tenant)

        # Create currency limit (required for product)
        currency_limit = CurrencyLimit(
            tenant_id="test_tenant",
            currency_code="USD",
            max_daily_package_spend=10000.0,
        )
        session.add(currency_limit)

        # Create property tag (required for product)
        property_tag = PropertyTag(
            tenant_id="test_tenant",
            tag_id="all_inventory",
            name="All Inventory",
            description="All available inventory",
        )
        session.add(property_tag)

        # Create principal
        principal = Principal(
            principal_id="test_principal",
            tenant_id="test_tenant",
            name="Test Advertiser",
            platform_mappings={"google_ad_manager": {"advertiser_id": "test_adv_123"}},
            access_token="test_token",
        )
        session.add(principal)

        # Create product
        product = Product(
            product_id="test_product",
            tenant_id="test_tenant",
            name="Test Product",
            description="Test Product Description",
            formats=[{"format_id": "display_300x250", "name": "Medium Rectangle", "type": "display"}],
            targeting_template={},
            delivery_type="guaranteed",
            property_tags=["all_inventory"],
        )
        session.add(product)
        session.commit()  # Commit before adding creatives (foreign key constraint)

        # Create valid creatives
        creative1 = DBCreative(
            creative_id="creative_1",
            tenant_id="test_tenant",
            principal_id="test_principal",
            name="Creative 1",
            format="display_300x250",
            agent_url="https://creative.adcontextprotocol.org/",
            status="approved",
            data={"platform_creative_id": "gam_123"},
        )
        creative2 = DBCreative(
            creative_id="creative_2",
            tenant_id="test_tenant",
            principal_id="test_principal",
            name="Creative 2",
            format="display_300x250",
            agent_url="https://creative.adcontextprotocol.org/",
            status="approved",
            data={"platform_creative_id": "gam_456"},
        )
        session.add_all([creative1, creative2])
        session.commit()

    # Mock context and tenant resolution
    mock_context = MagicMock()
    mock_context.headers = {"x-adcp-auth": "test_token"}

    with (
        patch("src.core.main._verify_principal"),
        patch("src.core.main._get_principal_id_from_context", return_value="test_principal"),
        patch("src.core.main.get_current_tenant", return_value={"tenant_id": "test_tenant"}),
        patch("src.core.main.get_principal_object", return_value=principal),
        patch("src.core.main.get_adapter") as mock_get_adapter,
        patch("src.core.main.get_context_manager") as mock_ctx_mgr,
    ):
        # Mock adapter
        mock_adapter = MagicMock()
        mock_adapter.manual_approval_required = False
        mock_adapter.create_media_buy.return_value = {
            "order_id": "order_123",
            "line_items": [{"line_item_id": "li_123", "package_id": "pkg_1"}],
        }
        mock_adapter.associate_creatives.return_value = [
            {"creative_id": "gam_123", "line_item_id": "li_123", "status": "ACTIVE"}
        ]
        mock_get_adapter.return_value = mock_adapter

        # Mock context manager
        mock_ctx_manager_inst = MagicMock()
        mock_ctx_manager_inst.get_or_create_context.return_value = MagicMock(context_id="ctx_123")
        mock_ctx_manager_inst.create_workflow_step.return_value = MagicMock(step_id="step_123")
        mock_ctx_mgr.return_value = mock_ctx_manager_inst

        # Call create_media_buy with valid creative IDs
        response = await _create_media_buy_impl(
            buyer_ref="buyer_ref_123",
            brand_manifest={"website": "https://example.com"},
            packages=[
                {
                    "package_id": "pkg_1",
                    "product_ids": ["test_product"],
                    "impressions": 100000,
                    "creative_ids": ["creative_1", "creative_2"],
                }
            ],
            start_time=datetime(2025, 11, 1, tzinfo=UTC),
            end_time=datetime(2025, 11, 30, tzinfo=UTC),
            budget=1000.0,
            context=mock_context,
        )

    # Verify success response
    assert isinstance(response, CreateMediaBuyResponse)
    assert response.errors == [] or response.errors is None
    assert response.media_buy_id is not None


@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_create_media_buy_rejects_partial_missing_creatives(integration_db):
    """Test that create_media_buy rejects if ANY creative ID is missing.

    Even if some creative IDs exist, the entire request should be rejected if
    any creative ID is non-existent.
    """
    from datetime import datetime

    from src.core.database.database_session import get_db_session
    from src.core.database.models import (
        CurrencyLimit,
        Principal,
        Product,
        PropertyTag,
        Tenant,
    )

    with get_db_session() as session:
        # Create tenant
        tenant = Tenant(
            tenant_id="test_tenant",
            name="Test Org",
            subdomain="test",
        )
        session.add(tenant)

        # Create currency limit (required for product)
        currency_limit = CurrencyLimit(
            tenant_id="test_tenant",
            currency_code="USD",
            max_daily_package_spend=10000.0,
        )
        session.add(currency_limit)

        # Create property tag (required for product)
        property_tag = PropertyTag(
            tenant_id="test_tenant",
            tag_id="all_inventory",
            name="All Inventory",
            description="All available inventory",
        )
        session.add(property_tag)

        # Create principal
        principal = Principal(
            principal_id="test_principal",
            tenant_id="test_tenant",
            name="Test Advertiser",
            platform_mappings={"google_ad_manager": {"advertiser_id": "test_adv_123"}},
            access_token="test_token",
        )
        session.add(principal)

        # Create product
        product = Product(
            product_id="test_product",
            tenant_id="test_tenant",
            name="Test Product",
            description="Test Product Description",
            formats=[{"format_id": "display_300x250", "name": "Medium Rectangle", "type": "display"}],
            targeting_template={},
            delivery_type="guaranteed",
            property_tags=["all_inventory"],
        )
        session.add(product)
        session.commit()  # Commit before adding creatives (foreign key constraint)

        # Create ONLY ONE creative (creative_1 exists, creative_2 doesn't)
        creative1 = DBCreative(
            creative_id="creative_1",
            tenant_id="test_tenant",
            principal_id="test_principal",
            name="Creative 1",
            format="display_300x250",
            agent_url="https://creative.adcontextprotocol.org/",
            status="approved",
            data={"platform_creative_id": "gam_123"},
        )
        session.add(creative1)
        session.commit()

    # Mock context and tenant resolution
    mock_context = MagicMock()
    mock_context.headers = {"x-adcp-auth": "test_token"}

    with (
        patch("src.core.main._verify_principal"),
        patch("src.core.main._get_principal_id_from_context", return_value="test_principal"),
        patch("src.core.main.get_current_tenant", return_value={"tenant_id": "test_tenant"}),
        patch("src.core.main.get_principal_object", return_value=principal),
        patch("src.core.main.get_adapter") as mock_get_adapter,
        patch("src.core.main.get_context_manager") as mock_ctx_mgr,
    ):
        # Mock adapter
        mock_adapter = MagicMock()
        mock_adapter.manual_approval_required = False
        mock_adapter.create_media_buy.return_value = {
            "order_id": "order_123",
            "line_items": [{"line_item_id": "li_123", "package_id": "pkg_1"}],
        }
        mock_get_adapter.return_value = mock_adapter

        # Mock context manager
        mock_ctx_manager_inst = MagicMock()
        mock_ctx_manager_inst.get_or_create_context.return_value = MagicMock(context_id="ctx_123")
        mock_ctx_manager_inst.create_workflow_step.return_value = MagicMock(step_id="step_123")
        mock_ctx_mgr.return_value = mock_ctx_manager_inst

        # Call create_media_buy with mix of existing and non-existent creative IDs
        response = await _create_media_buy_impl(
            buyer_ref="buyer_ref_123",
            brand_manifest={"website": "https://example.com"},
            packages=[
                {
                    "package_id": "pkg_1",
                    "product_ids": ["test_product"],
                    "impressions": 100000,
                    "creative_ids": ["creative_1", "creative_2"],  # creative_2 doesn't exist
                }
            ],
            start_time=datetime(2025, 11, 1, tzinfo=UTC),
            end_time=datetime(2025, 11, 30, tzinfo=UTC),
            budget=1000.0,
            context=mock_context,
        )

    # Verify error response - should reject because creative_2 doesn't exist
    assert isinstance(response, CreateMediaBuyResponse)
    assert response.errors is not None
    assert len(response.errors) > 0
    assert response.errors[0]["code"] == "creatives_not_found"
    assert "creative_2" in response.errors[0]["message"]

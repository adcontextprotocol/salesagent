"""Integration tests for update_media_buy creative assignment functionality."""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

from src.core.database.models import Creative as DBCreative
from src.core.database.models import CreativeAssignment as DBAssignment
from src.core.schemas import UpdateMediaBuyResponse
from src.core.tools.media_buy_update import _update_media_buy_impl


@pytest.mark.requires_db
def test_update_media_buy_assigns_creatives_to_package(integration_db):
    """Test that update_media_buy can assign creatives to a package."""
    from src.core.database.database_session import get_db_session
    from src.core.database.models import MediaBuy, Principal, Product, PropertyTag, Tenant

    with get_db_session() as session:
        # Create tenant
        tenant = Tenant(
            tenant_id="test_tenant",
            name="Test Org",
            subdomain="test",
        )
        session.add(tenant)

        # Create property tag (required for products)
        property_tag = PropertyTag(
            tenant_id="test_tenant",
            tag_id="all_inventory",
            name="All Inventory",
            description="All available inventory",
        )
        session.add(property_tag)

        # Create principal (MUST be flushed before creatives due to FK constraint)
        principal = Principal(
            principal_id="test_principal",
            tenant_id="test_tenant",
            name="Test Advertiser",
            access_token="test_token",
            platform_mappings={"mock": {"id": "test_advertiser"}},
        )
        session.add(principal)
        session.flush()  # Ensure principal exists before creating creatives

        # Create product
        product = Product(
            product_id="test_product",
            tenant_id="test_tenant",
            name="Test Product",
            description="Test product for creative assignment",
            format_ids=["display_300x250"],
            targeting_template={},
            delivery_type="guaranteed",
            property_tags=["all_inventory"],
        )
        session.add(product)

        # Create media buy
        media_buy = MediaBuy(
            media_buy_id="test_buy_123",
            tenant_id="test_tenant",
            principal_id="test_principal",
            buyer_ref="buyer_ref_123",
            order_name="Test Order",
            advertiser_name="Test Advertiser",
            start_date="2025-11-01",
            end_date="2025-11-30",
            start_time="2025-11-01T00:00:00Z",
            end_time="2025-11-30T23:59:59Z",
            raw_request={
                "packages": [{"package_id": "pkg_default", "impressions": 100000, "products": ["test_product"]}]
            },
        )
        session.add(media_buy)

        # Create creatives (FK to principal now satisfied)
        creative1 = DBCreative(
            creative_id="creative_1",
            tenant_id="test_tenant",
            principal_id="test_principal",
            name="Creative 1",
            agent_url="https://creative.adcontextprotocol.org",
            format="display",
            status="ready",
            data={"platform_creative_id": "gam_123"},
        )
        creative2 = DBCreative(
            creative_id="creative_2",
            tenant_id="test_tenant",
            principal_id="test_principal",
            name="Creative 2",
            agent_url="https://creative.adcontextprotocol.org",
            format="display",
            status="ready",
            data={"platform_creative_id": "gam_456"},
        )
        session.add_all([creative1, creative2])
        session.commit()

    # Mock context and tenant resolution
    mock_context = MagicMock()
    mock_context.headers = {"x-adcp-auth": "test_token"}

    with (
        patch("src.core.helpers.get_principal_id_from_context", return_value="test_principal"),
        patch("src.core.config_loader.get_current_tenant", return_value={"tenant_id": "test_tenant"}),
        patch("src.core.auth.get_principal_object", return_value=principal),
        patch("src.core.helpers.adapter_helpers.get_adapter") as mock_get_adapter,
        patch("src.core.context_manager.get_context_manager") as mock_ctx_mgr,
    ):
        # Mock adapter
        mock_adapter = MagicMock()
        mock_adapter.manual_approval_required = False
        mock_get_adapter.return_value = mock_adapter

        # Mock context manager
        mock_ctx_manager_inst = MagicMock()
        mock_ctx_manager_inst.get_or_create_context.return_value = MagicMock(context_id="ctx_123")
        mock_ctx_manager_inst.create_workflow_step.return_value = MagicMock(step_id="step_123")
        mock_ctx_mgr.return_value = mock_ctx_manager_inst

        # Call update_media_buy with creative assignment
        response = _update_media_buy_impl(
            media_buy_id="test_buy_123",
            buyer_ref="buyer_ref_123",
            packages=[
                {
                    "package_id": "pkg_default",
                    "creative_ids": ["creative_1", "creative_2"],
                }
            ],
            ctx=mock_context,
        )

    # Verify response
    assert isinstance(response, UpdateMediaBuyResponse)
    assert response.media_buy_id == "test_buy_123"
    assert response.buyer_ref == "buyer_ref_123"
    assert response.affected_packages is not None
    assert len(response.affected_packages) == 1

    # Check affected_packages structure
    affected = response.affected_packages[0]
    assert affected.buyer_package_ref == "pkg_default"  # Internal field
    assert affected.changes_applied is not None  # Internal field
    assert "creative_ids" in affected.changes_applied

    creative_changes = affected.changes_applied["creative_ids"]
    assert set(creative_changes["added"]) == {"creative_1", "creative_2"}
    assert creative_changes["removed"] == []
    assert set(creative_changes["current"]) == {"creative_1", "creative_2"}

    # Verify assignments were created in database
    with get_db_session() as session:
        assignment_stmt = select(DBAssignment).where(
            DBAssignment.tenant_id == "test_tenant",
            DBAssignment.media_buy_id == "test_buy_123",
            DBAssignment.package_id == "pkg_default",
        )
        assignments = session.scalars(assignment_stmt).all()
        assert len(assignments) == 2
        assigned_creative_ids = {a.creative_id for a in assignments}
        assert assigned_creative_ids == {"creative_1", "creative_2"}


@pytest.mark.requires_db
def test_update_media_buy_replaces_creatives(integration_db):
    """Test that update_media_buy can replace existing creative assignments."""
    from src.core.database.database_session import get_db_session
    from src.core.database.models import MediaBuy, Principal, Product, PropertyTag, Tenant

    with get_db_session() as session:
        # Create tenant
        tenant = Tenant(
            tenant_id="test_tenant",
            name="Test Org",
            subdomain="test",
        )
        session.add(tenant)

        # Create property tag (required for products)
        property_tag = PropertyTag(
            tenant_id="test_tenant",
            tag_id="all_inventory",
            name="All Inventory",
            description="All available inventory",
        )
        session.add(property_tag)

        # Create principal (MUST be flushed before creatives due to FK constraint)
        principal = Principal(
            principal_id="test_principal",
            tenant_id="test_tenant",
            name="Test Advertiser",
            access_token="test_token",
            platform_mappings={"mock": {"id": "test_advertiser"}},
        )
        session.add(principal)
        session.flush()  # Ensure principal exists before creating creatives

        # Create product
        product = Product(
            product_id="test_product",
            tenant_id="test_tenant",
            name="Test Product",
            description="Test product for creative assignment",
            format_ids=["display_300x250"],
            targeting_template={},
            delivery_type="guaranteed",
            property_tags=["all_inventory"],
        )
        session.add(product)

        # Create media buy
        media_buy = MediaBuy(
            media_buy_id="test_buy_456",
            tenant_id="test_tenant",
            principal_id="test_principal",
            buyer_ref="buyer_ref_456",
            order_name="Test Order",
            advertiser_name="Test Advertiser",
            start_date="2025-11-01",
            end_date="2025-11-30",
            start_time="2025-11-01T00:00:00Z",
            end_time="2025-11-30T23:59:59Z",
            raw_request={
                "packages": [{"package_id": "pkg_default", "impressions": 100000, "products": ["test_product"]}]
            },
        )
        session.add(media_buy)
        session.flush()  # Ensure media_buy exists before creating assignments

        # Create creatives (FK to principal now satisfied)
        creative1 = DBCreative(
            creative_id="creative_1",
            tenant_id="test_tenant",
            principal_id="test_principal",
            name="Creative 1",
            agent_url="https://creative.adcontextprotocol.org",
            format="display",
            status="ready",
            data={},
        )
        creative2 = DBCreative(
            creative_id="creative_2",
            tenant_id="test_tenant",
            principal_id="test_principal",
            name="Creative 2",
            agent_url="https://creative.adcontextprotocol.org",
            format="display",
            status="ready",
            data={},
        )
        creative3 = DBCreative(
            creative_id="creative_3",
            tenant_id="test_tenant",
            principal_id="test_principal",
            name="Creative 3",
            agent_url="https://creative.adcontextprotocol.org",
            format="display",
            status="ready",
            data={},
        )
        session.add_all([creative1, creative2, creative3])

        # Create existing assignments (creative_1 already assigned)
        assignment1 = DBAssignment(
            assignment_id="assign_existing",
            tenant_id="test_tenant",
            media_buy_id="test_buy_456",
            package_id="pkg_default",
            creative_id="creative_1",
        )
        session.add(assignment1)
        session.commit()

    # Mock context and tenant resolution
    mock_context = MagicMock()
    mock_context.headers = {"x-adcp-auth": "test_token"}

    with (
        patch("src.core.helpers.get_principal_id_from_context", return_value="test_principal"),
        patch("src.core.config_loader.get_current_tenant", return_value={"tenant_id": "test_tenant"}),
        patch("src.core.auth.get_principal_object", return_value=principal),
        patch("src.core.helpers.adapter_helpers.get_adapter") as mock_get_adapter,
        patch("src.core.context_manager.get_context_manager") as mock_ctx_mgr,
    ):
        # Mock adapter
        mock_adapter = MagicMock()
        mock_adapter.manual_approval_required = False
        mock_get_adapter.return_value = mock_adapter

        # Mock context manager
        mock_ctx_manager_inst = MagicMock()
        mock_ctx_manager_inst.get_or_create_context.return_value = MagicMock(context_id="ctx_456")
        mock_ctx_manager_inst.create_workflow_step.return_value = MagicMock(step_id="step_456")
        mock_ctx_mgr.return_value = mock_ctx_manager_inst

        # Call update_media_buy to replace creative_1 with creative_2 and creative_3
        response = _update_media_buy_impl(
            media_buy_id="test_buy_456",
            buyer_ref="buyer_ref_456",
            packages=[
                {
                    "package_id": "pkg_default",
                    "creative_ids": ["creative_2", "creative_3"],
                }
            ],
            ctx=mock_context,
        )

    # Verify response
    assert isinstance(response, UpdateMediaBuyResponse)
    assert response.affected_packages is not None
    assert len(response.affected_packages) == 1

    # Check changes
    affected = response.affected_packages[0]
    creative_changes = affected.changes_applied["creative_ids"]  # Access internal field via attribute
    assert set(creative_changes["added"]) == {"creative_2", "creative_3"}
    assert set(creative_changes["removed"]) == {"creative_1"}
    assert set(creative_changes["current"]) == {"creative_2", "creative_3"}

    # Verify database state
    with get_db_session() as session:
        assignment_stmt = select(DBAssignment).where(
            DBAssignment.tenant_id == "test_tenant",
            DBAssignment.media_buy_id == "test_buy_456",
            DBAssignment.package_id == "pkg_default",
        )
        assignments = session.scalars(assignment_stmt).all()
        assert len(assignments) == 2
        assigned_creative_ids = {a.creative_id for a in assignments}
        assert assigned_creative_ids == {"creative_2", "creative_3"}


@pytest.mark.requires_db
def test_update_media_buy_rejects_missing_creatives(integration_db):
    """Test that update_media_buy rejects requests with non-existent creative IDs."""
    from src.core.database.database_session import get_db_session
    from src.core.database.models import MediaBuy, Principal, Product, PropertyTag, Tenant

    with get_db_session() as session:
        # Create tenant
        tenant = Tenant(
            tenant_id="test_tenant",
            name="Test Org",
            subdomain="test",
        )
        session.add(tenant)

        # Create property tag (required for products)
        property_tag = PropertyTag(
            tenant_id="test_tenant",
            tag_id="all_inventory",
            name="All Inventory",
            description="All available inventory",
        )
        session.add(property_tag)

        # Create principal (MUST be flushed before creatives due to FK constraint)
        principal = Principal(
            principal_id="test_principal",
            tenant_id="test_tenant",
            name="Test Advertiser",
            access_token="test_token",
            platform_mappings={"mock": {"id": "test_advertiser"}},
        )
        session.add(principal)
        session.flush()  # Ensure principal exists before creating creatives

        # Create product
        product = Product(
            product_id="test_product",
            tenant_id="test_tenant",
            name="Test Product",
            description="Test product for creative assignment",
            format_ids=["display_300x250"],
            targeting_template={},
            delivery_type="guaranteed",
            property_tags=["all_inventory"],
        )
        session.add(product)

        # Create media buy
        media_buy = MediaBuy(
            media_buy_id="test_buy_789",
            tenant_id="test_tenant",
            principal_id="test_principal",
            buyer_ref="buyer_ref_789",
            order_name="Test Order",
            advertiser_name="Test Advertiser",
            start_date="2025-11-01",
            end_date="2025-11-30",
            start_time="2025-11-01T00:00:00Z",
            end_time="2025-11-30T23:59:59Z",
            raw_request={
                "packages": [{"package_id": "pkg_default", "impressions": 100000, "products": ["test_product"]}]
            },
        )
        session.add(media_buy)
        session.commit()

    # Mock context and tenant resolution
    mock_context = MagicMock()
    mock_context.headers = {"x-adcp-auth": "test_token"}

    with (
        patch("src.core.helpers.get_principal_id_from_context", return_value="test_principal"),
        patch("src.core.config_loader.get_current_tenant", return_value={"tenant_id": "test_tenant"}),
        patch("src.core.auth.get_principal_object", return_value=principal),
        patch("src.core.helpers.adapter_helpers.get_adapter") as mock_get_adapter,
        patch("src.core.context_manager.get_context_manager") as mock_ctx_mgr,
    ):
        # Mock adapter
        mock_adapter = MagicMock()
        mock_adapter.manual_approval_required = False
        mock_get_adapter.return_value = mock_adapter

        # Mock context manager
        mock_ctx_manager_inst = MagicMock()
        mock_ctx_manager_inst.get_or_create_context.return_value = MagicMock(context_id="ctx_789")
        mock_ctx_manager_inst.create_workflow_step.return_value = MagicMock(step_id="step_789")
        mock_ctx_mgr.return_value = mock_ctx_manager_inst

        # Call update_media_buy with non-existent creative IDs
        response = _update_media_buy_impl(
            media_buy_id="test_buy_789",
            buyer_ref="buyer_ref_789",
            packages=[
                {
                    "package_id": "pkg_default",
                    "creative_ids": ["nonexistent_creative"],
                }
            ],
            ctx=mock_context,
        )

    # Verify error response
    assert isinstance(response, UpdateMediaBuyResponse)
    assert response.errors is not None
    assert len(response.errors) > 0
    assert response.errors[0].code == "creatives_not_found"
    assert "nonexistent_creative" in response.errors[0].message


@pytest.mark.requires_db
def test_update_media_buy_serializes_changes_applied(integration_db):
    """Test that update_media_buy properly serializes changes_applied in response.

    This is a critical test that verifies clients receive the changes_applied field
    in the serialized JSON response, not just as a Python object attribute.
    """
    from src.core.database.database_session import get_db_session
    from src.core.database.models import MediaBuy, Principal, Product, PropertyTag, Tenant

    with get_db_session() as session:
        # Create tenant
        tenant = Tenant(
            tenant_id="test_tenant",
            name="Test Org",
            subdomain="test",
        )
        session.add(tenant)

        # Create property tag (required for products)
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
            access_token="test_token",
            platform_mappings={"mock": {"id": "test_advertiser"}},
        )
        session.add(principal)
        session.flush()

        # Create product
        product = Product(
            product_id="test_product",
            tenant_id="test_tenant",
            name="Test Product",
            description="Test product",
            format_ids=["display_300x250"],
            targeting_template={},
            delivery_type="guaranteed",
            property_tags=["all_inventory"],
        )
        session.add(product)

        # Create media buy
        media_buy = MediaBuy(
            media_buy_id="test_buy_serialize",
            tenant_id="test_tenant",
            principal_id="test_principal",
            buyer_ref="buyer_ref_serialize",
            order_name="Test Order",
            advertiser_name="Test Advertiser",
            start_date="2025-11-01",
            end_date="2025-11-30",
            start_time="2025-11-01T00:00:00Z",
            end_time="2025-11-30T23:59:59Z",
            raw_request={
                "packages": [{"package_id": "pkg_default", "impressions": 100000, "products": ["test_product"]}]
            },
        )
        session.add(media_buy)

        # Create creatives
        creative1 = DBCreative(
            creative_id="creative_serialize_1",
            tenant_id="test_tenant",
            principal_id="test_principal",
            name="Test Creative 1",
            format_id="display_300x250",
            status="approved",
            asset_url="https://example.com/creative1.jpg",
            width=300,
            height=250,
        )
        session.add(creative1)
        session.commit()

    # Mock context and tenant resolution
    mock_context = MagicMock()
    mock_context.tenant = {"tenant_id": "test_tenant", "adapter_type": "mock"}

    with patch("src.core.tools.media_buy_update.get_tenant_from_request", return_value=mock_context.tenant):
        # Call update_media_buy to assign creative
        response = _update_media_buy_impl(
            media_buy_id="test_buy_serialize",
            buyer_ref="buyer_ref_serialize",
            packages=[
                {
                    "package_id": "pkg_default",
                    "creative_ids": ["creative_serialize_1"],
                }
            ],
            ctx=mock_context,
        )

    # Verify response object has changes_applied
    assert isinstance(response, UpdateMediaBuyResponse)
    assert response.affected_packages is not None
    assert len(response.affected_packages) == 1
    assert response.affected_packages[0].changes_applied is not None

    # ✅ CRITICAL: Verify serialized response includes changes_applied
    # This is what clients actually receive!
    serialized = response.model_dump()

    assert "affected_packages" in serialized, "Serialized response must have affected_packages"
    assert len(serialized["affected_packages"]) == 1, "Should have 1 affected package"

    pkg_dict = serialized["affected_packages"][0]
    assert "buyer_ref" in pkg_dict, "Must have buyer_ref in serialized package"
    assert "package_id" in pkg_dict, "Must have package_id in serialized package"
    assert "changes_applied" in pkg_dict, "Must have changes_applied in serialized package (this was the bug!)"

    # Verify changes_applied structure
    changes = pkg_dict["changes_applied"]
    assert "creative_ids" in changes, "changes_applied must have creative_ids"
    assert "added" in changes["creative_ids"], "creative_ids must have added array"
    assert "removed" in changes["creative_ids"], "creative_ids must have removed array"
    assert "current" in changes["creative_ids"], "creative_ids must have current array"

    # Verify content
    assert changes["creative_ids"]["added"] == ["creative_serialize_1"]
    assert changes["creative_ids"]["removed"] == []
    assert changes["creative_ids"]["current"] == ["creative_serialize_1"]

    # Verify internal fields are NOT serialized
    assert "buyer_package_ref" not in pkg_dict, "Internal field should not be in serialized response"

"""Integration tests for individual creative approval and upload flow.

Tests that individual creative approval properly uploads creatives to existing media buys
in the ad server (GAM), separate from the full media buy creation flow.
"""

import logging
import pytest
from datetime import UTC, datetime, timedelta
from sqlalchemy import select

from src.admin.blueprints.creatives import execute_approved_creative_upload
from src.core.database.models import Creative, CreativeAssignment, MediaBuy, Principal, Product, Tenant
from src.core.database.database_session import get_db_session
from src.core.config_loader import set_current_tenant

logger = logging.getLogger(__name__)


@pytest.mark.requires_db
def test_execute_approved_creative_upload_with_existing_media_buy(integration_db):
    """Test creative upload when media buy already exists in adapter."""

    tenant_id = "test_tenant_creative_upload"
    principal_id = "test_principal"
    product_id = "test_product"
    media_buy_id = "test_media_buy"
    creative_id = "test_creative_001"
    package_id = "test_package_001"

    with get_db_session() as session:
        # Create tenant
        tenant = Tenant(
            tenant_id=tenant_id,
            name="Test Tenant",
            subdomain="testcreative",
            ad_server="mock",
            is_active=True,
        )
        session.add(tenant)

        # Create principal
        principal = Principal(
            tenant_id=tenant_id,
            principal_id=principal_id,
            name="Test Advertiser",
            platform_ids={"gam_advertiser_id": "12345"},
        )
        session.add(principal)

        # Create product
        product = Product(
            tenant_id=tenant_id,
            product_id=product_id,
            name="Test Product",
            delivery_type="guaranteed",
            formats=["display_300x250_image"],
        )
        session.add(product)

        # Create media buy that already exists in adapter (has order_id)
        media_buy = MediaBuy(
            media_buy_id=media_buy_id,
            tenant_id=tenant_id,
            principal_id=principal_id,
            status="pending_creatives",  # Already created in adapter, waiting for creatives
            start_time=datetime.now(UTC),
            end_time=datetime.now(UTC) + timedelta(days=7),
            raw_request={"promoted_offering": "Test Campaign"},
            adapter_ids={"order_id": "9876543210"},  # Order exists in GAM
        )
        session.add(media_buy)

        # Create creative (approved status)
        creative = Creative(
            creative_id=creative_id,
            tenant_id=tenant_id,
            principal_id=principal_id,
            name="Test Creative",
            agent_url="https://test.com",
            format="display_300x250_image",
            status="approved",
            data={
                "url": "https://example.com/creative.jpg",
                "width": 300,
                "height": 250,
                "asset_type": "image",
            },
        )
        session.add(creative)

        # Create creative assignment
        assignment = CreativeAssignment(
            assignment_id="test_assignment_001",
            tenant_id=tenant_id,
            creative_id=creative_id,
            media_buy_id=media_buy_id,
            package_id=package_id,
            weight=100,
        )
        session.add(assignment)

        session.commit()

        # Set tenant context
        tenant_dict = {
            "tenant_id": tenant.tenant_id,
            "name": tenant.name,
            "subdomain": tenant.subdomain,
            "ad_server": tenant.ad_server,
            "virtual_host": tenant.virtual_host,
        }
        set_current_tenant(tenant_dict)

    # Execute creative upload
    success, error_msg = execute_approved_creative_upload(creative_id, tenant_id)

    # Verify results
    assert success, f"Creative upload should succeed, got error: {error_msg}"
    assert error_msg is None

    # Check creative status updated
    with get_db_session() as session:
        stmt = select(Creative).filter_by(creative_id=creative_id)
        creative = session.scalars(stmt).first()

        # For mock adapter, creative should be marked as active
        assert creative.status in ["active", "approved"], f"Creative status should be active/approved, got: {creative.status}"

        # Check upload metadata added
        if creative.status == "active":
            assert "uploaded_at" in creative.data, "Creative data should have uploaded_at timestamp"
            assert "uploaded_to_media_buy" in creative.data, "Creative data should have uploaded_to_media_buy"


@pytest.mark.requires_db
def test_execute_approved_creative_upload_without_media_buy_in_adapter(integration_db):
    """Test creative upload when media buy does NOT exist in adapter yet (pending approval)."""

    tenant_id = "test_tenant_pending"
    principal_id = "test_principal_pending"
    media_buy_id = "test_media_buy_pending"
    creative_id = "test_creative_pending"
    package_id = "test_package_pending"

    with get_db_session() as session:
        # Create tenant
        tenant = Tenant(
            tenant_id=tenant_id,
            name="Test Tenant Pending",
            subdomain="testpending",
            ad_server="mock",
            is_active=True,
        )
        session.add(tenant)

        # Create principal
        principal = Principal(
            tenant_id=tenant_id,
            principal_id=principal_id,
            name="Test Advertiser Pending",
            platform_ids={"gam_advertiser_id": "12345"},
        )
        session.add(principal)

        # Create media buy that does NOT exist in adapter yet
        media_buy = MediaBuy(
            media_buy_id=media_buy_id,
            tenant_id=tenant_id,
            principal_id=principal_id,
            status="pending_approval",  # Not yet created in adapter
            start_time=datetime.now(UTC),
            end_time=datetime.now(UTC) + timedelta(days=7),
            raw_request={"promoted_offering": "Test Campaign"},
            adapter_ids={},  # No order_id yet
        )
        session.add(media_buy)

        # Create creative (approved status)
        creative = Creative(
            creative_id=creative_id,
            tenant_id=tenant_id,
            principal_id=principal_id,
            name="Test Creative Pending",
            agent_url="https://test.com",
            format="display_728x90_image",
            status="approved",
            data={
                "url": "https://example.com/creative.jpg",
                "width": 728,
                "height": 90,
                "asset_type": "image",
            },
        )
        session.add(creative)

        # Create creative assignment
        assignment = CreativeAssignment(
            assignment_id="test_assignment_pending",
            tenant_id=tenant_id,
            creative_id=creative_id,
            media_buy_id=media_buy_id,
            package_id=package_id,
            weight=100,
        )
        session.add(assignment)

        session.commit()

        # Set tenant context
        tenant_dict = {
            "tenant_id": tenant.tenant_id,
            "name": tenant.name,
            "subdomain": tenant.subdomain,
            "ad_server": tenant.ad_server,
            "virtual_host": tenant.virtual_host,
        }
        set_current_tenant(tenant_dict)

    # Execute creative upload
    success, error_msg = execute_approved_creative_upload(creative_id, tenant_id)

    # Should succeed but skip upload (media buy not in adapter yet)
    assert success, f"Creative upload should succeed (skip), got error: {error_msg}"

    # Check creative status remains approved (not uploaded yet)
    with get_db_session() as session:
        stmt = select(Creative).filter_by(creative_id=creative_id)
        creative = session.scalars(stmt).first()

        # Creative should remain approved (not active) since media buy not in adapter
        assert creative.status == "approved", f"Creative status should remain approved, got: {creative.status}"


@pytest.mark.requires_db
def test_execute_approved_creative_upload_missing_dimensions(integration_db):
    """Test creative upload fails gracefully when creative missing dimensions."""

    tenant_id = "test_tenant_missing_dims"
    principal_id = "test_principal_missing"
    media_buy_id = "test_media_buy_missing"
    creative_id = "test_creative_missing_dims"
    package_id = "test_package_missing"

    with get_db_session() as session:
        # Create tenant
        tenant = Tenant(
            tenant_id=tenant_id,
            name="Test Tenant Missing Dims",
            subdomain="testmissing",
            ad_server="mock",
            is_active=True,
        )
        session.add(tenant)

        # Create principal
        principal = Principal(
            tenant_id=tenant_id,
            principal_id=principal_id,
            name="Test Advertiser Missing",
            platform_ids={"gam_advertiser_id": "12345"},
        )
        session.add(principal)

        # Create media buy
        media_buy = MediaBuy(
            media_buy_id=media_buy_id,
            tenant_id=tenant_id,
            principal_id=principal_id,
            status="pending_creatives",
            start_time=datetime.now(UTC),
            end_time=datetime.now(UTC) + timedelta(days=7),
            raw_request={"promoted_offering": "Test Campaign"},
            adapter_ids={"order_id": "9999999999"},
        )
        session.add(media_buy)

        # Create creative with MISSING dimensions
        creative = Creative(
            creative_id=creative_id,
            tenant_id=tenant_id,
            principal_id=principal_id,
            name="Test Creative Missing Dims",
            agent_url="https://test.com",
            format="display_invalid",  # Format without dimensions
            status="approved",
            data={
                "url": "https://example.com/creative.jpg",
                # Missing width and height
                "asset_type": "image",
            },
        )
        session.add(creative)

        # Create creative assignment
        assignment = CreativeAssignment(
            assignment_id="test_assignment_missing",
            tenant_id=tenant_id,
            creative_id=creative_id,
            media_buy_id=media_buy_id,
            package_id=package_id,
            weight=100,
        )
        session.add(assignment)

        session.commit()

        # Set tenant context
        tenant_dict = {
            "tenant_id": tenant.tenant_id,
            "name": tenant.name,
            "subdomain": tenant.subdomain,
            "ad_server": tenant.ad_server,
            "virtual_host": tenant.virtual_host,
        }
        set_current_tenant(tenant_dict)

    # Execute creative upload
    success, error_msg = execute_approved_creative_upload(creative_id, tenant_id)

    # Should fail with helpful error message
    assert not success, "Creative upload should fail when dimensions missing"
    assert error_msg is not None
    assert "missing dimensions" in error_msg.lower()

    # Check creative status updated to failed
    with get_db_session() as session:
        stmt = select(Creative).filter_by(creative_id=creative_id)
        creative = session.scalars(stmt).first()

        assert creative.status == "failed", f"Creative status should be failed, got: {creative.status}"
        assert "upload_error" in creative.data, "Creative data should have upload_error"
        assert "upload_failed_at" in creative.data, "Creative data should have upload_failed_at timestamp"

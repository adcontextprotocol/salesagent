"""Integration test for auto-approve creative syncing with adapter upload.

Tests that when approval_mode is "auto-approve", creatives are:
1. Automatically marked as "approved"
2. Uploaded to the ad server adapter via add_creative_assets()
3. Properly handle errors from adapter upload
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from src.core.schemas import AssetStatus
from src.core.tools.creatives import _sync_creatives_impl


@pytest.mark.requires_db
class TestAutoApproveCreativeUpload:
    """Test auto-approve creative sync with adapter upload."""

    def test_auto_approve_uploads_to_adapter(self, integration_db):
        """Test that auto-approved creatives are uploaded to adapter."""
        from src.core.database.database_session import get_db_session
        from src.core.database.models import (
            AdapterConfig,
            Creative,
            CreativeAssignment,
            MediaBuy,
            MediaPackage,
            Principal,
            Product,
            Tenant,
        )

        tenant_id = f"test_tenant_{uuid.uuid4().hex[:8]}"
        principal_id = "test_principal"
        media_buy_id = f"mb_{uuid.uuid4().hex[:8]}"
        creative_id = f"cr_{uuid.uuid4().hex[:8]}"
        package_id = f"pkg_{uuid.uuid4().hex[:8]}"

        # Setup database
        with get_db_session() as session:
            # Create tenant with auto-approve mode
            tenant = Tenant(
                tenant_id=tenant_id,
                name="Test Tenant",
                subdomain="test",
                approval_mode="auto-approve",  # KEY: Enable auto-approve
                created_at=datetime.now(UTC),
            )
            session.add(tenant)

            # Create principal
            principal = Principal(
                tenant_id=tenant_id,
                principal_id=principal_id,
                name="Test Principal",
                auth_token="test_token",
                created_at=datetime.now(UTC),
            )
            session.add(principal)

            # Create adapter config (mock adapter)
            adapter_config = AdapterConfig(
                tenant_id=tenant_id,
                adapter_type="mock",
                created_at=datetime.now(UTC),
            )
            session.add(adapter_config)

            # Create product
            product = Product(
                tenant_id=tenant_id,
                product_id="test_product",
                name="Test Product",
                created_at=datetime.now(UTC),
                pricing={
                    "model": "CPM",
                    "amount": 10.0,
                    "currency": "USD",
                },
            )
            session.add(product)

            # Create media buy
            media_buy = MediaBuy(
                tenant_id=tenant_id,
                media_buy_id=media_buy_id,
                principal_id=principal_id,
                buyer_ref="test_buyer",
                order_name="Test Order",
                advertiser_name="Test Advertiser",
                status="active",
                start_date=datetime.now(UTC).date(),
                end_date=datetime.now(UTC).date(),
                created_at=datetime.now(UTC),
            )
            session.add(media_buy)

            # Create package
            package = MediaPackage(
                tenant_id=tenant_id,
                media_buy_id=media_buy_id,
                package_id=package_id,
                product_id="test_product",
                created_at=datetime.now(UTC),
            )
            session.add(package)

            session.commit()

        # Mock context
        mock_context = MagicMock()
        mock_context.request_context = MagicMock()
        mock_context.request_context.meta = {"principal_id": principal_id}

        # Mock adapter to track add_creative_assets calls
        mock_adapter = MagicMock()
        mock_adapter.add_creative_assets = MagicMock(
            return_value=[
                AssetStatus(
                    creative_id=creative_id,
                    status="active",
                    message="Successfully uploaded",
                )
            ]
        )

        # Prepare creative data
        creatives = [
            {
                "creative_id": creative_id,
                "name": "Test Creative",
                "format_id": "banner",
                "url": "https://example.com/creative.jpg",
                "width": 300,
                "height": 250,
            }
        ]

        # Prepare assignments
        assignments = {
            creative_id: [package_id],
        }

        with patch("src.core.tools.creatives.get_current_tenant") as mock_get_tenant:
            mock_get_tenant.return_value = {
                "tenant_id": tenant_id,
                "approval_mode": "auto-approve",
            }

            with patch("src.core.helpers.context_helpers.get_principal_from_context") as mock_get_principal:
                mock_get_principal.return_value = (principal_id, {"tenant_id": tenant_id})

                with patch("src.core.tools.creatives.get_adapter") as mock_get_adapter:
                    mock_get_adapter.return_value = mock_adapter

                    # Mock creative agent registry (no validation needed for this test)
                    with patch("src.core.tools.creatives.run_async_in_sync_context") as mock_async:
                        mock_async.return_value = []  # No formats needed

                        # Call sync_creatives
                        response = _sync_creatives_impl(
                            creatives=creatives,
                            assignments=assignments,
                            context=mock_context,
                        )

        # Verify creative was approved
        with get_db_session() as session:
            from sqlalchemy import select

            stmt = select(Creative).filter_by(tenant_id=tenant_id, creative_id=creative_id)
            creative = session.scalars(stmt).first()

            assert creative is not None, "Creative should be created"
            assert creative.status == "approved", "Creative should be auto-approved"

        # Verify assignment was created
        with get_db_session() as session:
            from sqlalchemy import select

            stmt = select(CreativeAssignment).filter_by(
                tenant_id=tenant_id,
                creative_id=creative_id,
                media_buy_id=media_buy_id,
            )
            assignment = session.scalars(stmt).first()

            assert assignment is not None, "Assignment should be created"

        # KEY ASSERTION: Verify adapter.add_creative_assets was called
        mock_adapter.add_creative_assets.assert_called_once()

        # Verify the call arguments
        call_args = mock_adapter.add_creative_assets.call_args
        assert call_args[1]["media_buy_id"] == media_buy_id
        assert len(call_args[1]["assets"]) == 1
        assert call_args[1]["assets"][0]["creative_id"] == creative_id

        # Verify response
        assert len(response.creatives) == 1
        assert response.creatives[0].creative_id == creative_id
        assert response.creatives[0].status == "approved"

    def test_auto_approve_handles_adapter_errors(self, integration_db):
        """Test that adapter upload errors are properly handled."""
        from src.core.database.database_session import get_db_session
        from src.core.database.models import (
            AdapterConfig,
            Creative,
            CreativeAssignment,
            MediaBuy,
            MediaPackage,
            Principal,
            Product,
            Tenant,
        )

        tenant_id = f"test_tenant_{uuid.uuid4().hex[:8]}"
        principal_id = "test_principal"
        media_buy_id = f"mb_{uuid.uuid4().hex[:8]}"
        creative_id = f"cr_{uuid.uuid4().hex[:8]}"
        package_id = f"pkg_{uuid.uuid4().hex[:8]}"

        # Setup database (same as above)
        with get_db_session() as session:
            tenant = Tenant(
                tenant_id=tenant_id,
                name="Test Tenant",
                subdomain="test",
                approval_mode="auto-approve",
                created_at=datetime.now(UTC),
            )
            session.add(tenant)

            principal = Principal(
                tenant_id=tenant_id,
                principal_id=principal_id,
                name="Test Principal",
                auth_token="test_token",
                created_at=datetime.now(UTC),
            )
            session.add(principal)

            adapter_config = AdapterConfig(
                tenant_id=tenant_id,
                adapter_type="mock",
                created_at=datetime.now(UTC),
            )
            session.add(adapter_config)

            product = Product(
                tenant_id=tenant_id,
                product_id="test_product",
                name="Test Product",
                created_at=datetime.now(UTC),
                pricing={
                    "model": "CPM",
                    "amount": 10.0,
                    "currency": "USD",
                },
            )
            session.add(product)

            media_buy = MediaBuy(
                tenant_id=tenant_id,
                media_buy_id=media_buy_id,
                principal_id=principal_id,
                buyer_ref="test_buyer",
                order_name="Test Order",
                advertiser_name="Test Advertiser",
                status="active",
                start_date=datetime.now(UTC).date(),
                end_date=datetime.now(UTC).date(),
                created_at=datetime.now(UTC),
            )
            session.add(media_buy)

            package = MediaPackage(
                tenant_id=tenant_id,
                media_buy_id=media_buy_id,
                package_id=package_id,
                product_id="test_product",
                created_at=datetime.now(UTC),
            )
            session.add(package)

            session.commit()

        # Mock context
        mock_context = MagicMock()
        mock_context.request_context = MagicMock()
        mock_context.request_context.meta = {"principal_id": principal_id}

        # Mock adapter to return failure
        mock_adapter = MagicMock()
        mock_adapter.add_creative_assets = MagicMock(
            return_value=[
                AssetStatus(
                    creative_id=creative_id,
                    status="failed",
                    message="Invalid creative size",
                )
            ]
        )

        creatives = [
            {
                "creative_id": creative_id,
                "name": "Test Creative",
                "format_id": "banner",
                "url": "https://example.com/creative.jpg",
                "width": 300,
                "height": 250,
            }
        ]

        assignments = {
            creative_id: [package_id],
        }

        with patch("src.core.tools.creatives.get_current_tenant") as mock_get_tenant:
            mock_get_tenant.return_value = {
                "tenant_id": tenant_id,
                "approval_mode": "auto-approve",
            }

            with patch("src.core.helpers.context_helpers.get_principal_from_context") as mock_get_principal:
                mock_get_principal.return_value = (principal_id, {"tenant_id": tenant_id})

                with patch("src.core.tools.creatives.get_adapter") as mock_get_adapter:
                    mock_get_adapter.return_value = mock_adapter

                    with patch("src.core.tools.creatives.run_async_in_sync_context") as mock_async:
                        mock_async.return_value = []

                        # Call sync_creatives
                        response = _sync_creatives_impl(
                            creatives=creatives,
                            assignments=assignments,
                            context=mock_context,
                        )

        # Verify creative status was changed to failed
        with get_db_session() as session:
            from sqlalchemy import select

            stmt = select(Creative).filter_by(tenant_id=tenant_id, creative_id=creative_id)
            creative = session.scalars(stmt).first()

            assert creative is not None, "Creative should exist"
            assert creative.status == "failed", "Creative should be marked as failed after upload error"
            assert creative.data.get("upload_error") == "Invalid creative size"

        # Verify error is in response
        assert len(response.creatives) == 1
        assert response.creatives[0].creative_id == creative_id
        assert response.creatives[0].errors is not None
        assert "Invalid creative size" in response.creatives[0].errors[0]

    def test_no_upload_when_no_assignments(self, integration_db):
        """Test that creatives without assignments are not uploaded."""
        from src.core.database.database_session import get_db_session
        from src.core.database.models import AdapterConfig, Creative, Principal, Tenant

        tenant_id = f"test_tenant_{uuid.uuid4().hex[:8]}"
        principal_id = "test_principal"
        creative_id = f"cr_{uuid.uuid4().hex[:8]}"

        # Setup database
        with get_db_session() as session:
            tenant = Tenant(
                tenant_id=tenant_id,
                name="Test Tenant",
                subdomain="test",
                approval_mode="auto-approve",
                created_at=datetime.now(UTC),
            )
            session.add(tenant)

            principal = Principal(
                tenant_id=tenant_id,
                principal_id=principal_id,
                name="Test Principal",
                auth_token="test_token",
                created_at=datetime.now(UTC),
            )
            session.add(principal)

            adapter_config = AdapterConfig(
                tenant_id=tenant_id,
                adapter_type="mock",
                created_at=datetime.now(UTC),
            )
            session.add(adapter_config)

            session.commit()

        # Mock context
        mock_context = MagicMock()
        mock_context.request_context = MagicMock()
        mock_context.request_context.meta = {"principal_id": principal_id}

        # Mock adapter
        mock_adapter = MagicMock()

        creatives = [
            {
                "creative_id": creative_id,
                "name": "Test Creative",
                "format_id": "banner",
                "url": "https://example.com/creative.jpg",
                "width": 300,
                "height": 250,
            }
        ]

        # NO assignments provided
        assignments = None

        with patch("src.core.tools.creatives.get_current_tenant") as mock_get_tenant:
            mock_get_tenant.return_value = {
                "tenant_id": tenant_id,
                "approval_mode": "auto-approve",
            }

            with patch("src.core.helpers.context_helpers.get_principal_from_context") as mock_get_principal:
                mock_get_principal.return_value = (principal_id, {"tenant_id": tenant_id})

                with patch("src.core.tools.creatives.get_adapter") as mock_get_adapter:
                    mock_get_adapter.return_value = mock_adapter

                    with patch("src.core.tools.creatives.run_async_in_sync_context") as mock_async:
                        mock_async.return_value = []

                        # Call sync_creatives
                        response = _sync_creatives_impl(
                            creatives=creatives,
                            assignments=assignments,
                            context=mock_context,
                        )

        # Verify creative is approved but NOT uploaded
        with get_db_session() as session:
            from sqlalchemy import select

            stmt = select(Creative).filter_by(tenant_id=tenant_id, creative_id=creative_id)
            creative = session.scalars(stmt).first()

            assert creative is not None, "Creative should be created"
            assert creative.status == "approved", "Creative should be auto-approved"

        # KEY: Adapter should NOT be called (no assignments)
        mock_adapter.add_creative_assets.assert_not_called()

    def test_dry_run_skips_adapter_upload(self, integration_db):
        """Test that dry_run mode skips adapter upload."""
        from src.core.database.database_session import get_db_session
        from src.core.database.models import (
            AdapterConfig,
            MediaBuy,
            MediaPackage,
            Principal,
            Product,
            Tenant,
        )

        tenant_id = f"test_tenant_{uuid.uuid4().hex[:8]}"
        principal_id = "test_principal"
        media_buy_id = f"mb_{uuid.uuid4().hex[:8]}"
        creative_id = f"cr_{uuid.uuid4().hex[:8]}"
        package_id = f"pkg_{uuid.uuid4().hex[:8]}"

        # Setup database
        with get_db_session() as session:
            tenant = Tenant(
                tenant_id=tenant_id,
                name="Test Tenant",
                subdomain="test",
                approval_mode="auto-approve",
                created_at=datetime.now(UTC),
            )
            session.add(tenant)

            principal = Principal(
                tenant_id=tenant_id,
                principal_id=principal_id,
                name="Test Principal",
                auth_token="test_token",
                created_at=datetime.now(UTC),
            )
            session.add(principal)

            adapter_config = AdapterConfig(
                tenant_id=tenant_id,
                adapter_type="mock",
                created_at=datetime.now(UTC),
            )
            session.add(adapter_config)

            product = Product(
                tenant_id=tenant_id,
                product_id="test_product",
                name="Test Product",
                created_at=datetime.now(UTC),
                pricing={
                    "model": "CPM",
                    "amount": 10.0,
                    "currency": "USD",
                },
            )
            session.add(product)

            media_buy = MediaBuy(
                tenant_id=tenant_id,
                media_buy_id=media_buy_id,
                principal_id=principal_id,
                buyer_ref="test_buyer",
                order_name="Test Order",
                advertiser_name="Test Advertiser",
                status="active",
                start_date=datetime.now(UTC).date(),
                end_date=datetime.now(UTC).date(),
                created_at=datetime.now(UTC),
            )
            session.add(media_buy)

            package = MediaPackage(
                tenant_id=tenant_id,
                media_buy_id=media_buy_id,
                package_id=package_id,
                product_id="test_product",
                created_at=datetime.now(UTC),
            )
            session.add(package)

            session.commit()

        # Mock context
        mock_context = MagicMock()
        mock_context.request_context = MagicMock()
        mock_context.request_context.meta = {"principal_id": principal_id}

        # Mock adapter
        mock_adapter = MagicMock()

        creatives = [
            {
                "creative_id": creative_id,
                "name": "Test Creative",
                "format_id": "banner",
                "url": "https://example.com/creative.jpg",
                "width": 300,
                "height": 250,
            }
        ]

        assignments = {
            creative_id: [package_id],
        }

        with patch("src.core.tools.creatives.get_current_tenant") as mock_get_tenant:
            mock_get_tenant.return_value = {
                "tenant_id": tenant_id,
                "approval_mode": "auto-approve",
            }

            with patch("src.core.helpers.context_helpers.get_principal_from_context") as mock_get_principal:
                mock_get_principal.return_value = (principal_id, {"tenant_id": tenant_id})

                with patch("src.core.tools.creatives.get_adapter") as mock_get_adapter:
                    mock_get_adapter.return_value = mock_adapter

                    with patch("src.core.tools.creatives.run_async_in_sync_context") as mock_async:
                        mock_async.return_value = []

                        # Call sync_creatives with dry_run=True
                        response = _sync_creatives_impl(
                            creatives=creatives,
                            assignments=assignments,
                            dry_run=True,  # KEY: dry_run mode
                            context=mock_context,
                        )

        # Adapter should NOT be called in dry_run mode
        mock_adapter.add_creative_assets.assert_not_called()

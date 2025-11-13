#!/usr/bin/env python3
"""
Test error handling in media buy approval when adapter returns CreateMediaBuyError.

This tests the fix for the bug where trying to approve a media buy would crash with:
"'CreateMediaBuyError' object has no attribute 'media_buy_id'"
"""

from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from src.core.schemas import CreateMediaBuyError, Error
from src.core.tools.media_buy_create import execute_approved_media_buy

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]


class TestApprovalErrorHandling:
    """Test error handling when adapter creation fails during approval."""

    def test_execute_approved_media_buy_handles_adapter_error_response(
        self, integration_db, sample_tenant, sample_principal, sample_product
    ):
        """Test that execute_approved_media_buy handles CreateMediaBuyError response correctly."""
        tenant_id = sample_tenant["tenant_id"]
        principal_id = sample_principal["principal_id"]

        # Create a mock media buy in the database with all required data
        from src.core.database.database_session import get_db_session
        from src.core.database.models import MediaBuy, MediaPackage

        media_buy_id = "mb_test_error_handling"

        with get_db_session() as session:
            # Create media buy record
            media_buy = MediaBuy(
                media_buy_id=media_buy_id,
                tenant_id=tenant_id,
                principal_id=principal_id,
                buyer_ref="test_ref_123",
                status="pending_approval",
                start_time=datetime.now(UTC),
                end_time=datetime.now(UTC).replace(month=12),
                raw_request={
                    "buyer_ref": "test_ref_123",
                    "promoted_offering": "test_product",
                    "packages": [],
                },
            )
            session.add(media_buy)

            # Create media package record
            media_package = MediaPackage(
                package_id="pkg_test_123",
                media_buy_id=media_buy_id,
                tenant_id=tenant_id,
                package_config={
                    "package_id": "pkg_test_123",
                    "product_id": sample_product["product_id"],
                    "budget": 1000.0,
                    "pricing_model": "cpm",
                },
            )
            session.add(media_package)
            session.commit()

        # Mock the adapter to return CreateMediaBuyError instead of CreateMediaBuySuccess
        mock_adapter_error = CreateMediaBuyError(
            errors=[
                Error(code="VALIDATION_ERROR", message="Budget exceeds daily limit"),
                Error(code="INVENTORY_ERROR", message="Requested inventory not available"),
            ]
        )

        with patch("src.core.tools.media_buy_create._execute_adapter_media_buy_creation") as mock_execute:
            mock_execute.return_value = mock_adapter_error

            # Execute approval - should return False and error message (not crash)
            success, error_msg = execute_approved_media_buy(media_buy_id, tenant_id)

            # Verify it handled the error correctly
            assert success is False, "Should return False when adapter returns error"
            assert error_msg is not None, "Should return error message"
            assert "Budget exceeds daily limit" in error_msg, "Should include first error message"
            assert "Requested inventory not available" in error_msg, "Should include second error message"

    def test_execute_approved_media_buy_handles_empty_errors(
        self, integration_db, sample_tenant, sample_principal, sample_product
    ):
        """Test that execute_approved_media_buy handles CreateMediaBuyError with no errors list."""
        tenant_id = sample_tenant["tenant_id"]
        principal_id = sample_principal["principal_id"]

        # Create a mock media buy in the database with all required data
        from src.core.database.database_session import get_db_session
        from src.core.database.models import MediaBuy, MediaPackage

        media_buy_id = "mb_test_empty_errors"

        with get_db_session() as session:
            # Create media buy record
            media_buy = MediaBuy(
                media_buy_id=media_buy_id,
                tenant_id=tenant_id,
                principal_id=principal_id,
                buyer_ref="test_ref_456",
                status="pending_approval",
                start_time=datetime.now(UTC),
                end_time=datetime.now(UTC).replace(month=12),
                raw_request={
                    "buyer_ref": "test_ref_456",
                    "promoted_offering": "test_product",
                    "packages": [],
                },
            )
            session.add(media_buy)

            # Create media package record
            media_package = MediaPackage(
                package_id="pkg_test_456",
                media_buy_id=media_buy_id,
                tenant_id=tenant_id,
                package_config={
                    "package_id": "pkg_test_456",
                    "product_id": sample_product["product_id"],
                    "budget": 1000.0,
                    "pricing_model": "cpm",
                },
            )
            session.add(media_package)
            session.commit()

        # Mock the adapter to return CreateMediaBuyError with empty errors
        mock_adapter_error = CreateMediaBuyError(errors=[])

        with patch("src.core.tools.media_buy_create._execute_adapter_media_buy_creation") as mock_execute:
            mock_execute.return_value = mock_adapter_error

            # Execute approval - should return False and error message (not crash)
            success, error_msg = execute_approved_media_buy(media_buy_id, tenant_id)

            # Verify it handled the error correctly
            assert success is False, "Should return False when adapter returns error"
            assert error_msg is not None, "Should return error message"
            assert "Unknown error" in error_msg, "Should return 'Unknown error' when errors list is empty"

"""
Integration tests for GAM order lifecycle management (Issue #117).

Tests the full lifecycle actions: activate_order, submit_for_approval,
approve_order, and archive_order with proper validation.
"""

from datetime import datetime
from unittest.mock import patch

import pytest

from src.adapters.constants import UPDATE_ACTIONS
from src.adapters.google_ad_manager import GoogleAdManager
from src.core.schemas import Principal


class TestGAMOrderLifecycle:
    """Test GAM order lifecycle management actions."""

    @pytest.fixture
    def mock_principal(self):
        """Create a mock principal for testing."""
        return Principal(
            tenant_id="test_tenant",
            principal_id="test_advertiser",
            name="Test Advertiser",
            access_token="test_token",
            platform_mappings={"gam_advertiser_id": "123456"},
        )

    @pytest.fixture
    def admin_principal(self):
        """Create a mock admin principal for testing."""
        return Principal(
            tenant_id="test_tenant",
            principal_id="admin_user",
            name="Admin User",
            access_token="admin_token",
            platform_mappings={"gam_advertiser_id": "123456", "gam_admin": True},
        )

    @pytest.fixture
    def gam_config(self):
        """Standard GAM adapter configuration."""
        return {"network_code": "12345678", "refresh_token": "test_refresh_token", "trafficker_id": "987654"}

    def test_new_lifecycle_actions_in_constants(self):
        """Test that new lifecycle actions are properly defined in constants."""
        required_actions = ["activate_order", "submit_for_approval", "approve_order", "archive_order"]

        for action in required_actions:
            assert action in UPDATE_ACTIONS, f"Action '{action}' missing from UPDATE_ACTIONS"
            assert isinstance(UPDATE_ACTIONS[action], str), f"Action '{action}' description should be string"

    def test_lifecycle_actions_dry_run_basic(self, mock_principal, gam_config):
        """Test basic lifecycle actions in dry-run mode with minimal mocking."""
        with patch("src.adapters.google_ad_manager.GoogleAdManager._init_client"):
            gam_adapter = GoogleAdManager(gam_config, mock_principal, dry_run=True, tenant_id="test_tenant")

            test_cases = [
                ("submit_for_approval", "submit_for_approval"),
                ("archive_order", "archive_order"),
            ]

            for action, expected_detail in test_cases:
                response = gam_adapter.update_media_buy(
                    media_buy_id="12345", action=action, package_id=None, budget=None, today=datetime.now()
                )
                assert response.status == "accepted"
                assert expected_detail in response.detail
                assert response.implementation_date is not None

    def test_activation_validation_logic(self, mock_principal, gam_config):
        """Test activation validation with guaranteed vs non-guaranteed items."""
        with patch("src.adapters.google_ad_manager.GoogleAdManager._init_client"):
            gam_adapter = GoogleAdManager(gam_config, mock_principal, dry_run=True, tenant_id="test_tenant")

            # Test with non-guaranteed items - should succeed
            with patch.object(gam_adapter, "_check_order_has_guaranteed_items", return_value=(False, [])):
                response = gam_adapter.update_media_buy(
                    media_buy_id="12345", action="activate_order", package_id=None, budget=None, today=datetime.now()
                )
                assert response.status == "accepted"

            # Test with guaranteed items - should be blocked
            with patch.object(gam_adapter, "_check_order_has_guaranteed_items", return_value=(True, ["STANDARD"])):
                response = gam_adapter.update_media_buy(
                    media_buy_id="12345", action="activate_order", package_id=None, budget=None, today=datetime.now()
                )
                assert response.status == "failed"
                assert "Cannot auto-activate order with guaranteed line items" in response.reason

    def test_admin_permission_validation(self, mock_principal, admin_principal, gam_config):
        """Test admin permission validation for approve_order action."""
        with patch("src.adapters.google_ad_manager.GoogleAdManager._init_client"):
            # Test non-admin user
            gam_adapter = GoogleAdManager(gam_config, mock_principal, dry_run=True, tenant_id="test_tenant")
            with patch.object(gam_adapter, "_is_admin_principal", return_value=False):
                response = gam_adapter.update_media_buy(
                    media_buy_id="12345", action="approve_order", package_id=None, budget=None, today=datetime.now()
                )
                assert response.status == "failed"
                assert "Only admin users can approve orders" in response.reason

            # Test admin user
            gam_adapter = GoogleAdManager(gam_config, admin_principal, dry_run=True, tenant_id="test_tenant")
            with patch.object(gam_adapter, "_is_admin_principal", return_value=True):
                response = gam_adapter.update_media_buy(
                    media_buy_id="12345", action="approve_order", package_id=None, budget=None, today=datetime.now()
                )
                assert response.status == "accepted"

    def test_admin_principal_detection_patterns(self, gam_config):
        """Test admin principal detection with different configuration patterns."""
        test_principals = [
            # Test with gam_admin flag
            Principal(
                tenant_id="test_tenant",
                principal_id="admin1",
                name="Admin 1",
                access_token="token1",
                platform_mappings={"gam_advertiser_id": "123", "gam_admin": True},
            ),
            # Test with is_admin flag
            Principal(
                tenant_id="test_tenant",
                principal_id="admin2",
                name="Admin 2",
                access_token="token2",
                platform_mappings={"gam_advertiser_id": "123", "is_admin": True},
            ),
        ]

        with patch("src.adapters.google_ad_manager.GoogleAdManager._init_client"):
            for principal in test_principals:
                gam_adapter = GoogleAdManager(gam_config, principal, dry_run=True, tenant_id="test_tenant")
                assert gam_adapter._is_admin_principal() is True

    def test_line_item_type_validation_patterns(self, mock_principal, gam_config):
        """Test line item type validation with different item types."""
        with patch("src.adapters.google_ad_manager.GoogleAdManager._init_client"):
            gam_adapter = GoogleAdManager(gam_config, mock_principal, dry_run=True, tenant_id="test_tenant")

            # Test with guaranteed types
            guaranteed_items = [
                {"id": "1", "lineItemType": "STANDARD", "name": "Standard Item"},
                {"id": "2", "lineItemType": "SPONSORSHIP", "name": "Sponsorship Item"},
            ]

            with patch.object(gam_adapter, "_get_order_line_items", return_value=guaranteed_items):
                has_guaranteed, types = gam_adapter._check_order_has_guaranteed_items("12345")
                assert has_guaranteed is True
                assert "STANDARD" in types and "SPONSORSHIP" in types

            # Test with non-guaranteed types
            non_guaranteed_items = [
                {"id": "3", "lineItemType": "NETWORK", "name": "Network Item"},
                {"id": "4", "lineItemType": "BULK", "name": "Bulk Item"},
            ]

            with patch.object(gam_adapter, "_get_order_line_items", return_value=non_guaranteed_items):
                has_guaranteed, types = gam_adapter._check_order_has_guaranteed_items("12345")
                assert has_guaranteed is False
                assert len(types) == 0

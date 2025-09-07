"""
Integration tests for GAM automatic order activation feature.

Tests the implementation of Issue #116: automatic activation for non-guaranteed GAM orders.
"""

import json
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest

from src.adapters.google_ad_manager import GUARANTEED_LINE_ITEM_TYPES, NON_GUARANTEED_LINE_ITEM_TYPES, GoogleAdManager
from src.core.database.database_session import get_db_session
from src.core.database.models import ObjectWorkflowMapping, Product, WorkflowStep
from src.core.schemas import CreateMediaBuyRequest, MediaPackage, Principal, Targeting


class TestGAMAutomaticActivation:
    """Test GAM automatic activation feature for non-guaranteed orders."""

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
    def gam_config(self):
        """Standard GAM adapter configuration."""
        return {"network_code": "12345678", "refresh_token": "test_refresh_token", "trafficker_id": "987654"}

    @pytest.fixture
    def mock_packages(self):
        """Create mock media packages for testing."""
        return [
            MediaPackage(
                package_id="test_product_network",
                name="Network Test Package",
                delivery_type="non_guaranteed",
                impressions=10000,
                cpm=2.50,
                format_ids=["display_300x250"],
            ),
            MediaPackage(
                package_id="test_product_house",
                name="House Test Package",
                delivery_type="non_guaranteed",
                impressions=5000,
                cpm=1.00,
                format_ids=["display_300x250"],
            ),
        ]

    @pytest.fixture
    def create_test_products(self, mock_packages):
        """Create test products in database with different automation configurations."""
        with get_db_session() as db_session:
            # Non-guaranteed product with automatic activation
            product_network = Product(
                tenant_id="test_tenant",
                product_id="test_product_network",
                name="Network Product",
                formats=[{"format_id": "display_300x250", "name": "Display 300x250", "type": "display"}],
                targeting_template={},
                delivery_type="non_guaranteed",
                is_fixed_price=True,
                cpm=2.50,
                implementation_config=json.dumps(
                    {
                        "line_item_type": "NETWORK",
                        "non_guaranteed_automation": "automatic",
                        "creative_placeholders": [{"width": 300, "height": 250, "expected_creative_count": 1}],
                    }
                ),
            )

            # Non-guaranteed product with confirmation required
            product_house = Product(
                tenant_id="test_tenant",
                product_id="test_product_house",
                name="House Product",
                formats=[{"format_id": "display_728x90", "name": "Leaderboard 728x90", "type": "display"}],
                targeting_template={},
                delivery_type="non_guaranteed",
                is_fixed_price=True,
                cpm=1.00,
                implementation_config=json.dumps(
                    {
                        "line_item_type": "HOUSE",
                        "non_guaranteed_automation": "confirmation_required",
                        "creative_placeholders": [{"width": 728, "height": 90, "expected_creative_count": 1}],
                    }
                ),
            )

            # Guaranteed product (should ignore automation setting)
            product_standard = Product(
                tenant_id="test_tenant",
                product_id="test_product_standard",
                name="Standard Product",
                formats=[{"format_id": "display_300x250", "name": "Display 300x250", "type": "display"}],
                targeting_template={},
                delivery_type="guaranteed",
                is_fixed_price=True,
                cpm=5.00,
                implementation_config=json.dumps(
                    {
                        "line_item_type": "STANDARD",
                        "non_guaranteed_automation": "automatic",  # Should be ignored
                        "creative_placeholders": [{"width": 300, "height": 250, "expected_creative_count": 1}],
                    }
                ),
            )

            db_session.add_all([product_network, product_house, product_standard])
            db_session.commit()

        yield

        # Cleanup
        with get_db_session() as db_session:
            db_session.query(Product).filter_by(tenant_id="test_tenant").delete()
            db_session.commit()

    def test_line_item_type_constants(self):
        """Test that line item type constants are correctly defined."""
        # Test guaranteed types
        assert "STANDARD" in GUARANTEED_LINE_ITEM_TYPES
        assert "SPONSORSHIP" in GUARANTEED_LINE_ITEM_TYPES

        # Test non-guaranteed types
        assert "NETWORK" in NON_GUARANTEED_LINE_ITEM_TYPES
        assert "HOUSE" in NON_GUARANTEED_LINE_ITEM_TYPES
        assert "PRICE_PRIORITY" in NON_GUARANTEED_LINE_ITEM_TYPES
        assert "BULK" in NON_GUARANTEED_LINE_ITEM_TYPES

        # Ensure no overlap
        assert not (GUARANTEED_LINE_ITEM_TYPES & NON_GUARANTEED_LINE_ITEM_TYPES)

    @patch("src.adapters.google_ad_manager.GoogleAdManager._init_client")
    def test_automatic_activation_dry_run(
        self, mock_init_client, mock_principal, gam_config, mock_packages, create_test_products
    ):
        """Test automatic activation in dry-run mode."""
        # Create GAM adapter in dry-run mode
        adapter = GoogleAdManager(config=gam_config, principal=mock_principal, dry_run=True, tenant_id="test_tenant")

        # Create request with targeting overlay
        request = CreateMediaBuyRequest(po_number="TEST-AUTO-001", total_budget=1000.0, targeting_overlay=Targeting())

        # Test create_media_buy with automatic activation
        start_time = datetime.now()
        end_time = start_time + timedelta(days=7)

        response = adapter.create_media_buy(request, [mock_packages[0]], start_time, end_time)

        # Should return active status due to automatic activation
        assert response.status == "active"
        assert "automatically activated" in response.detail
        assert response.media_buy_id is not None

    @patch("src.adapters.google_ad_manager.GoogleAdManager._init_client")
    def test_confirmation_required_workflow_creation(
        self, mock_init_client, mock_principal, gam_config, mock_packages, create_test_products
    ):
        """Test that confirmation_required mode creates workflow step."""
        with patch("src.core.context_manager.ContextManager.get_current_context_id", return_value="test_context"):
            adapter = GoogleAdManager(
                config=gam_config, principal=mock_principal, dry_run=True, tenant_id="test_tenant"
            )

            request = CreateMediaBuyRequest(
                po_number="TEST-CONF-001", total_budget=500.0, targeting_overlay=Targeting()
            )

            start_time = datetime.now()
            end_time = start_time + timedelta(days=7)

            response = adapter.create_media_buy(request, [mock_packages[1]], start_time, end_time)

            # Should return pending_confirmation status
            assert response.status == "pending_confirmation"
            assert "awaiting approval" in response.detail

            # Check that workflow step was created
            with get_db_session() as db_session:
                workflow_step = (
                    db_session.query(WorkflowStep)
                    .filter_by(context_id="test_context", status="requires_approval")
                    .first()
                )

                assert workflow_step is not None
                assert workflow_step.step_type == "approval"
                assert workflow_step.tool_name == "activate_gam_order"
                assert "activate_gam_order" in workflow_step.request_data["action_type"]

                # Check object mapping exists
                object_mapping = (
                    db_session.query(ObjectWorkflowMapping)
                    .filter_by(step_id=workflow_step.step_id, object_type="media_buy", action="activate")
                    .first()
                )

                assert object_mapping is not None

    @patch("src.adapters.google_ad_manager.GoogleAdManager._init_client")
    def test_guaranteed_orders_ignore_automation(
        self, mock_init_client, mock_principal, gam_config, create_test_products
    ):
        """Test that guaranteed order types ignore automation settings."""
        adapter = GoogleAdManager(config=gam_config, principal=mock_principal, dry_run=True, tenant_id="test_tenant")

        # Create guaranteed package (STANDARD type with automatic setting - should be ignored)
        guaranteed_package = MediaPackage(
            package_id="test_product_standard",
            name="Standard Package",
            delivery_type="guaranteed",
            impressions=50000,
            cpm=5.00,
            format_ids=["display_300x250"],
        )

        request = CreateMediaBuyRequest(
            po_number="TEST-GUARANTEED-001", total_budget=2500.0, targeting_overlay=Targeting()
        )

        start_time = datetime.now()
        end_time = start_time + timedelta(days=14)

        response = adapter.create_media_buy(request, [guaranteed_package], start_time, end_time)

        # Should remain pending_activation regardless of automation setting
        assert response.status == "pending_activation"
        assert "Google Ad Manager" in response.detail
        assert response.media_buy_id is not None

    @patch("src.adapters.google_ad_manager.GoogleAdManager._init_client")
    def test_manual_mode_behavior(self, mock_init_client, mock_principal, gam_config, create_test_products):
        """Test that manual mode keeps default behavior."""
        # Create product with manual mode
        with get_db_session() as db_session:
            product_manual = Product(
                tenant_id="test_tenant",
                product_id="test_product_manual",
                name="Manual Product",
                formats=[{"format_id": "display_300x250", "name": "Display 300x250", "type": "display"}],
                targeting_template={},
                delivery_type="non_guaranteed",
                is_fixed_price=True,
                cpm=3.00,
                implementation_config=json.dumps(
                    {
                        "line_item_type": "NETWORK",
                        "non_guaranteed_automation": "manual",
                        "creative_placeholders": [{"width": 300, "height": 250, "expected_creative_count": 1}],
                    }
                ),
            )
            db_session.add(product_manual)
            db_session.commit()

        adapter = GoogleAdManager(config=gam_config, principal=mock_principal, dry_run=True, tenant_id="test_tenant")

        manual_package = MediaPackage(
            package_id="test_product_manual",
            name="Manual Package",
            delivery_type="non_guaranteed",
            impressions=15000,
            cpm=3.00,
            format_ids=["display_300x250"],
        )

        request = CreateMediaBuyRequest(po_number="TEST-MANUAL-001", total_budget=450.0, targeting_overlay=Targeting())

        start_time = datetime.now()
        end_time = start_time + timedelta(days=5)

        response = adapter.create_media_buy(request, [manual_package], start_time, end_time)

        # Should remain pending_activation like original behavior
        assert response.status == "pending_activation"
        assert "Google Ad Manager" in response.detail

    @patch("src.adapters.google_ad_manager.GoogleAdManager._init_client")
    def test_mixed_order_types_behavior(self, mock_init_client, mock_principal, gam_config, create_test_products):
        """Test behavior when order contains both guaranteed and non-guaranteed line items."""
        adapter = GoogleAdManager(config=gam_config, principal=mock_principal, dry_run=True, tenant_id="test_tenant")

        # Mix of guaranteed and non-guaranteed packages
        mixed_packages = [
            MediaPackage(
                package_id="test_product_network",
                name="Network Package",
                delivery_type="non_guaranteed",
                impressions=10000,
                cpm=2.50,
                format_ids=["display_300x250"],
            ),
            MediaPackage(
                package_id="test_product_standard",
                name="Standard Package",
                delivery_type="guaranteed",
                impressions=20000,
                cpm=4.00,
                format_ids=["display_300x250"],
            ),
        ]

        request = CreateMediaBuyRequest(po_number="TEST-MIXED-001", total_budget=1050.0, targeting_overlay=Targeting())

        start_time = datetime.now()
        end_time = start_time + timedelta(days=10)

        response = adapter.create_media_buy(request, mixed_packages, start_time, end_time)

        # Should use automation for non-guaranteed (first non-guaranteed package found)
        assert response.status == "active"  # Network package has automatic activation
        assert "automatically activated" in response.detail

    def test_activation_method_dry_run(self, mock_principal, gam_config):
        """Test the _activate_order_automatically method in dry-run mode."""
        with patch("src.adapters.google_ad_manager.GoogleAdManager._init_client"):
            adapter = GoogleAdManager(
                config=gam_config, principal=mock_principal, dry_run=True, tenant_id="test_tenant"
            )

            # Test activation method
            result = adapter._activate_order_automatically("test_order_123")

            # Should return True in dry-run mode
            assert result is True

    @patch("src.adapters.google_ad_manager.GoogleAdManager._init_client")
    def test_activation_method_real_gam_success(self, mock_init_client, mock_principal, gam_config):
        """Test activation method with mocked GAM client success."""
        # Mock GAM client and services
        mock_client = Mock()
        mock_order_service = Mock()
        mock_line_item_service = Mock()

        # Mock successful responses
        mock_order_service.performOrderAction.return_value = {"numChanges": 1}
        mock_line_item_service.performLineItemAction.return_value = {"numChanges": 2}

        mock_client.GetService.side_effect = lambda service_name: {
            "OrderService": mock_order_service,
            "LineItemService": mock_line_item_service,
        }[service_name]

        # Mock statement builder
        mock_statement_builder = Mock()
        mock_statement = Mock()
        mock_statement_builder.where.return_value = mock_statement_builder
        mock_statement_builder.with_bind_variable.return_value = mock_statement_builder
        mock_statement_builder.to_statement.return_value = mock_statement
        mock_client.new_statement_builder.return_value = mock_statement_builder

        adapter = GoogleAdManager(config=gam_config, principal=mock_principal, dry_run=False, tenant_id="test_tenant")
        adapter.client = mock_client

        # Test activation
        result = adapter._activate_order_automatically("123456")

        # Should succeed
        assert result is True

        # Verify GAM API calls were made
        assert mock_order_service.performOrderAction.called
        assert mock_line_item_service.performLineItemAction.called

        # Check order action parameters
        order_call_args = mock_order_service.performOrderAction.call_args
        order_action = order_call_args[0][0]
        assert order_action["xsi_type"] == "ResumeOrders"

        # Check line item action parameters
        line_item_call_args = mock_line_item_service.performLineItemAction.call_args
        line_item_action = line_item_call_args[0][0]
        assert line_item_action["xsi_type"] == "ActivateLineItems"

    @patch("src.adapters.google_ad_manager.GoogleAdManager._init_client")
    def test_activation_method_gam_error(self, mock_init_client, mock_principal, gam_config):
        """Test activation method handling GAM API errors."""
        # Mock GAM client that raises exception
        mock_client = Mock()
        mock_order_service = Mock()
        mock_order_service.performOrderAction.side_effect = Exception("GAM API Error")

        mock_client.GetService.return_value = mock_order_service
        mock_statement_builder = Mock()
        mock_statement_builder.where.return_value = mock_statement_builder
        mock_statement_builder.with_bind_variable.return_value = mock_statement_builder
        mock_statement_builder.to_statement.return_value = Mock()
        mock_client.new_statement_builder.return_value = mock_statement_builder

        adapter = GoogleAdManager(config=gam_config, principal=mock_principal, dry_run=False, tenant_id="test_tenant")
        adapter.client = mock_client

        # Test activation with error
        result = adapter._activate_order_automatically("123456")

        # Should return False on error
        assert result is False


class TestGAMAutomationIntegration:
    """Integration tests requiring real database and workflow system."""

    @pytest.mark.integration
    def test_end_to_end_automatic_activation(self):
        """End-to-end test of automatic activation workflow."""
        # This would test with real database and workflow system
        # Implementation depends on test environment setup
        pass

    @pytest.mark.integration
    def test_end_to_end_confirmation_workflow(self):
        """End-to-end test of confirmation workflow."""
        # This would test workflow step creation, approval, and subsequent activation
        pass


# Cleanup function for workflow steps created during testing
def cleanup_test_workflow_steps():
    """Clean up any workflow steps created during testing."""
    with get_db_session() as db_session:
        # Clean up test workflow steps
        db_session.query(WorkflowStep).filter(WorkflowStep.context_id == "test_context").delete()

        # Clean up test object mappings
        db_session.query(ObjectWorkflowMapping).filter(ObjectWorkflowMapping.object_id.like("test_%")).delete()

        db_session.commit()


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--tb=short"])

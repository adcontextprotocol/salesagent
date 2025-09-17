"""
Unit tests for GAMOrdersManager class.

Tests order creation, management, status checking, archival operations,
and advertiser management functionality.
"""

from datetime import datetime
from unittest.mock import Mock, patch

import pytest

from src.adapters.gam.managers.orders import GAMOrdersManager


class TestGAMOrdersManager:
    """Test suite for GAMOrdersManager order lifecycle management."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_client_manager = Mock()
        self.advertiser_id = "123456789"
        self.trafficker_id = "987654321"

        # Common date fixtures
        self.start_time = datetime(2025, 3, 1, 0, 0, 0)
        self.end_time = datetime(2025, 3, 31, 23, 59, 59)

    def test_init_with_valid_parameters(self):
        """Test initialization with valid parameters."""
        orders_manager = GAMOrdersManager(
            self.mock_client_manager, self.advertiser_id, self.trafficker_id, dry_run=False
        )

        assert orders_manager.client_manager == self.mock_client_manager
        assert orders_manager.advertiser_id == self.advertiser_id
        assert orders_manager.trafficker_id == self.trafficker_id
        assert orders_manager.dry_run is False

    def test_init_with_dry_run_enabled(self):
        """Test initialization with dry_run enabled."""
        orders_manager = GAMOrdersManager(
            self.mock_client_manager, self.advertiser_id, self.trafficker_id, dry_run=True
        )

        assert orders_manager.dry_run is True

    def test_create_order_success(self):
        """Test successful order creation."""
        mock_order_service = Mock()
        created_order = {"id": 54321, "name": "Test Order"}
        mock_order_service.createOrders.return_value = [created_order]
        self.mock_client_manager.get_service.return_value = mock_order_service

        orders_manager = GAMOrdersManager(self.mock_client_manager, self.advertiser_id, self.trafficker_id)

        order_id = orders_manager.create_order(
            order_name="Test Order", total_budget=5000.0, start_time=self.start_time, end_time=self.end_time
        )

        assert order_id == "54321"

        # Verify service call
        self.mock_client_manager.get_service.assert_called_once_with("OrderService")
        mock_order_service.createOrders.assert_called_once()

        # Verify order structure
        call_args = mock_order_service.createOrders.call_args[0][0]
        order_data = call_args[0]

        assert order_data["name"] == "Test Order"
        assert order_data["advertiserId"] == self.advertiser_id
        assert order_data["traffickerId"] == self.trafficker_id
        assert order_data["totalBudget"]["currencyCode"] == "USD"
        assert order_data["totalBudget"]["microAmount"] == 5000000000  # 5000 * 1M

    def test_create_order_with_optional_parameters(self):
        """Test order creation with optional PO number and team IDs."""
        mock_order_service = Mock()
        created_order = {"id": 54321, "name": "Test Order with PO"}
        mock_order_service.createOrders.return_value = [created_order]
        self.mock_client_manager.get_service.return_value = mock_order_service

        orders_manager = GAMOrdersManager(self.mock_client_manager, self.advertiser_id, self.trafficker_id)

        order_id = orders_manager.create_order(
            order_name="Test Order with PO",
            total_budget=10000.0,
            start_time=self.start_time,
            end_time=self.end_time,
            po_number="PO-2025-001",
            applied_team_ids=["team_1", "team_2"],
        )

        assert order_id == "54321"

        # Verify order structure includes optional fields
        call_args = mock_order_service.createOrders.call_args[0][0]
        order_data = call_args[0]

        assert order_data["poNumber"] == "PO-2025-001"
        assert order_data["appliedTeamIds"] == ["team_1", "team_2"]

    def test_create_order_dry_run_mode(self):
        """Test order creation in dry-run mode."""
        orders_manager = GAMOrdersManager(
            self.mock_client_manager, self.advertiser_id, self.trafficker_id, dry_run=True
        )

        order_id = orders_manager.create_order(
            order_name="Dry Run Order", total_budget=2500.0, start_time=self.start_time, end_time=self.end_time
        )

        # Should return mock order ID
        assert order_id.startswith("dry_run_order_")

        # Should not call GAM service
        self.mock_client_manager.get_service.assert_not_called()

    def test_create_order_no_orders_returned_raises_error(self):
        """Test that no orders returned from GAM raises exception."""
        mock_order_service = Mock()
        mock_order_service.createOrders.return_value = []  # Empty list
        self.mock_client_manager.get_service.return_value = mock_order_service

        orders_manager = GAMOrdersManager(self.mock_client_manager, self.advertiser_id, self.trafficker_id)

        with pytest.raises(Exception, match="Failed to create order - no orders returned"):
            orders_manager.create_order(
                order_name="Failed Order", total_budget=1000.0, start_time=self.start_time, end_time=self.end_time
            )

    def test_create_order_datetime_conversion(self):
        """Test that datetime objects are properly converted to GAM format."""
        mock_order_service = Mock()
        created_order = {"id": 54321, "name": "DateTime Test Order"}
        mock_order_service.createOrders.return_value = [created_order]
        self.mock_client_manager.get_service.return_value = mock_order_service

        orders_manager = GAMOrdersManager(self.mock_client_manager, self.advertiser_id, self.trafficker_id)

        # Test with specific datetime
        test_start = datetime(2025, 6, 15, 9, 30, 45)
        test_end = datetime(2025, 12, 31, 23, 59, 59)

        orders_manager.create_order(
            order_name="DateTime Test Order", total_budget=1000.0, start_time=test_start, end_time=test_end
        )

        # Verify datetime conversion
        call_args = mock_order_service.createOrders.call_args[0][0]
        order_data = call_args[0]

        start_dt = order_data["startDateTime"]
        end_dt = order_data["endDateTime"]

        assert start_dt["date"]["year"] == 2025
        assert start_dt["date"]["month"] == 6
        assert start_dt["date"]["day"] == 15
        assert start_dt["hour"] == 9
        assert start_dt["minute"] == 30
        assert start_dt["second"] == 45

        assert end_dt["date"]["year"] == 2025
        assert end_dt["date"]["month"] == 12
        assert end_dt["date"]["day"] == 31
        assert end_dt["hour"] == 23
        assert end_dt["minute"] == 59
        assert end_dt["second"] == 59

    def test_get_order_status_success(self):
        """Test successful order status retrieval."""
        mock_order_service = Mock()
        mock_statement_builder = Mock()
        mock_statement = Mock()

        # Setup statement builder chain
        mock_statement_builder.Where.return_value = mock_statement_builder
        mock_statement_builder.WithBindVariable.return_value = mock_statement_builder
        mock_statement_builder.ToStatement.return_value = mock_statement

        # Mock GAM response
        mock_order_service.getOrdersByStatement.return_value = {"results": [{"status": "APPROVED", "id": 12345}]}

        self.mock_client_manager.get_service.return_value = mock_order_service

        # Mock statement builder creation
        with patch("src.adapters.gam.managers.orders.ad_manager.StatementBuilder") as mock_sb_class:
            mock_sb_class.return_value = mock_statement_builder

            orders_manager = GAMOrdersManager(self.mock_client_manager, self.advertiser_id, self.trafficker_id)

            status = orders_manager.get_order_status("12345")

            assert status == "APPROVED"

            # Verify statement builder usage
            mock_statement_builder.Where.assert_called_once_with("id = :orderId")
            mock_statement_builder.WithBindVariable.assert_called_once_with("orderId", 12345)
            mock_order_service.getOrdersByStatement.assert_called_once_with(mock_statement)

    def test_get_order_status_not_found(self):
        """Test order status when order is not found."""
        mock_order_service = Mock()
        mock_statement_builder = Mock()
        mock_statement = Mock()

        mock_statement_builder.Where.return_value = mock_statement_builder
        mock_statement_builder.WithBindVariable.return_value = mock_statement_builder
        mock_statement_builder.ToStatement.return_value = mock_statement

        # Mock empty response
        mock_order_service.getOrdersByStatement.return_value = {"results": []}

        self.mock_client_manager.get_service.return_value = mock_order_service

        with patch("src.adapters.gam.managers.orders.ad_manager.StatementBuilder") as mock_sb_class:
            mock_sb_class.return_value = mock_statement_builder

            orders_manager = GAMOrdersManager(self.mock_client_manager, self.advertiser_id, self.trafficker_id)

            status = orders_manager.get_order_status("99999")

            assert status == "NOT_FOUND"

    def test_get_order_status_dry_run_mode(self):
        """Test order status retrieval in dry-run mode."""
        orders_manager = GAMOrdersManager(
            self.mock_client_manager, self.advertiser_id, self.trafficker_id, dry_run=True
        )

        status = orders_manager.get_order_status("12345")

        assert status == "DRAFT"
        self.mock_client_manager.get_service.assert_not_called()

    def test_get_order_status_api_error(self):
        """Test order status retrieval when API call fails."""
        mock_order_service = Mock()
        mock_order_service.getOrdersByStatement.side_effect = Exception("API Error")
        self.mock_client_manager.get_service.return_value = mock_order_service

        with patch("src.adapters.gam.managers.orders.ad_manager.StatementBuilder"):
            orders_manager = GAMOrdersManager(self.mock_client_manager, self.advertiser_id, self.trafficker_id)

            status = orders_manager.get_order_status("12345")

            assert status == "ERROR"

    def test_archive_order_success(self):
        """Test successful order archival."""
        mock_order_service = Mock()
        mock_statement_builder = Mock()
        mock_statement = Mock()

        mock_statement_builder.Where.return_value = mock_statement_builder
        mock_statement_builder.WithBindVariable.return_value = mock_statement_builder
        mock_statement_builder.ToStatement.return_value = mock_statement

        # Mock successful archive response
        mock_order_service.performOrderAction.return_value = {"numChanges": 1}

        self.mock_client_manager.get_service.return_value = mock_order_service

        with patch("src.adapters.gam.managers.orders.ad_manager.StatementBuilder") as mock_sb_class:
            mock_sb_class.return_value = mock_statement_builder

            orders_manager = GAMOrdersManager(self.mock_client_manager, self.advertiser_id, self.trafficker_id)

            result = orders_manager.archive_order("12345")

            assert result is True

            # Verify archive action
            mock_order_service.performOrderAction.assert_called_once()
            call_args = mock_order_service.performOrderAction.call_args[0]
            archive_action = call_args[0]
            statement = call_args[1]

            assert archive_action["xsi_type"] == "ArchiveOrders"
            assert statement == mock_statement

    def test_archive_order_dry_run_mode(self):
        """Test order archival in dry-run mode."""
        orders_manager = GAMOrdersManager(
            self.mock_client_manager, self.advertiser_id, self.trafficker_id, dry_run=True
        )

        result = orders_manager.archive_order("12345")

        assert result is True
        self.mock_client_manager.get_service.assert_not_called()

    def test_archive_order_no_changes(self):
        """Test order archival when no changes are made (already archived)."""
        mock_order_service = Mock()
        mock_order_service.performOrderAction.return_value = {"numChanges": 0}
        self.mock_client_manager.get_service.return_value = mock_order_service

        with patch("src.adapters.gam.managers.orders.ad_manager.StatementBuilder"):
            orders_manager = GAMOrdersManager(self.mock_client_manager, self.advertiser_id, self.trafficker_id)

            result = orders_manager.archive_order("12345")

            assert result is True  # Still considered successful

    def test_archive_order_api_error(self):
        """Test order archival when API call fails."""
        mock_order_service = Mock()
        mock_order_service.performOrderAction.side_effect = Exception("Archive failed")
        self.mock_client_manager.get_service.return_value = mock_order_service

        with patch("src.adapters.gam.managers.orders.ad_manager.StatementBuilder"):
            orders_manager = GAMOrdersManager(self.mock_client_manager, self.advertiser_id, self.trafficker_id)

            result = orders_manager.archive_order("12345")

            assert result is False

    def test_get_order_line_items_success(self):
        """Test successful retrieval of order line items."""
        mock_lineitem_service = Mock()
        mock_statement_builder = Mock()
        mock_statement = Mock()

        mock_statement_builder.Where.return_value = mock_statement_builder
        mock_statement_builder.WithBindVariable.return_value = mock_statement_builder
        mock_statement_builder.ToStatement.return_value = mock_statement

        # Mock line items response
        line_items = [
            {"id": 111, "name": "Line Item 1", "lineItemType": "STANDARD"},
            {"id": 222, "name": "Line Item 2", "lineItemType": "NETWORK"},
        ]
        mock_lineitem_service.getLineItemsByStatement.return_value = {"results": line_items}

        self.mock_client_manager.get_service.return_value = mock_lineitem_service

        with patch("src.adapters.gam.managers.orders.ad_manager.StatementBuilder") as mock_sb_class:
            mock_sb_class.return_value = mock_statement_builder

            orders_manager = GAMOrdersManager(self.mock_client_manager, self.advertiser_id, self.trafficker_id)

            result = orders_manager.get_order_line_items("12345")

            assert result == line_items
            self.mock_client_manager.get_service.assert_called_once_with("LineItemService")

    def test_get_order_line_items_dry_run_mode(self):
        """Test line items retrieval in dry-run mode."""
        orders_manager = GAMOrdersManager(
            self.mock_client_manager, self.advertiser_id, self.trafficker_id, dry_run=True
        )

        result = orders_manager.get_order_line_items("12345")

        assert result == []
        self.mock_client_manager.get_service.assert_not_called()

    def test_get_order_line_items_api_error(self):
        """Test line items retrieval when API call fails."""
        mock_lineitem_service = Mock()
        mock_lineitem_service.getLineItemsByStatement.side_effect = Exception("API Error")
        self.mock_client_manager.get_service.return_value = mock_lineitem_service

        with patch("src.adapters.gam.managers.orders.ad_manager.StatementBuilder"):
            orders_manager = GAMOrdersManager(self.mock_client_manager, self.advertiser_id, self.trafficker_id)

            result = orders_manager.get_order_line_items("12345")

            assert result == []

    def test_check_order_has_guaranteed_items_with_guaranteed(self):
        """Test checking for guaranteed line items when they exist."""
        orders_manager = GAMOrdersManager(self.mock_client_manager, self.advertiser_id, self.trafficker_id)

        # Mock line items with guaranteed types
        line_items = [{"lineItemType": "STANDARD"}, {"lineItemType": "NETWORK"}, {"lineItemType": "SPONSORSHIP"}]

        with patch.object(orders_manager, "get_order_line_items") as mock_get_line_items:
            mock_get_line_items.return_value = line_items

            has_guaranteed, guaranteed_types = orders_manager.check_order_has_guaranteed_items("12345")

            assert has_guaranteed is True
            assert "STANDARD" in guaranteed_types
            assert "SPONSORSHIP" in guaranteed_types
            assert "NETWORK" not in guaranteed_types  # Not a guaranteed type

    def test_check_order_has_guaranteed_items_without_guaranteed(self):
        """Test checking for guaranteed line items when none exist."""
        orders_manager = GAMOrdersManager(self.mock_client_manager, self.advertiser_id, self.trafficker_id)

        # Mock line items without guaranteed types
        line_items = [{"lineItemType": "NETWORK"}, {"lineItemType": "HOUSE"}, {"lineItemType": "PRICE_PRIORITY"}]

        with patch.object(orders_manager, "get_order_line_items") as mock_get_line_items:
            mock_get_line_items.return_value = line_items

            has_guaranteed, guaranteed_types = orders_manager.check_order_has_guaranteed_items("12345")

            assert has_guaranteed is False
            assert guaranteed_types == []

    def test_create_order_statement_helper(self):
        """Test the helper method for creating order statements."""
        mock_statement_builder = Mock()
        mock_statement = Mock()

        mock_statement_builder.Where.return_value = mock_statement_builder
        mock_statement_builder.WithBindVariable.return_value = mock_statement_builder
        mock_statement_builder.ToStatement.return_value = mock_statement

        with patch("src.adapters.gam.managers.orders.ad_manager.StatementBuilder") as mock_sb_class:
            mock_sb_class.return_value = mock_statement_builder

            orders_manager = GAMOrdersManager(self.mock_client_manager, self.advertiser_id, self.trafficker_id)

            statement = orders_manager.create_order_statement(12345)

            assert statement == mock_statement
            mock_statement_builder.Where.assert_called_once_with("orderId = :orderId")
            mock_statement_builder.WithBindVariable.assert_called_once_with("orderId", 12345)

    def test_get_advertisers_success(self):
        """Test successful advertiser retrieval."""
        mock_company_service = Mock()
        mock_statement_builder = Mock()
        mock_statement = Mock()

        mock_statement_builder.Where.return_value = mock_statement_builder
        mock_statement_builder.WithBindVariable.return_value = mock_statement_builder
        mock_statement_builder.ToStatement.return_value = mock_statement

        # Mock advertisers response
        companies = [
            {"id": 123, "name": "Advertiser B", "type": "ADVERTISER"},
            {"id": 456, "name": "Advertiser A", "type": "ADVERTISER"},
            {"id": 789, "name": "Advertiser C", "type": "ADVERTISER"},
        ]
        mock_company_service.getCompaniesByStatement.return_value = {"results": companies}

        self.mock_client_manager.get_service.return_value = mock_company_service

        with patch("src.adapters.gam.managers.orders.ad_manager.StatementBuilder") as mock_sb_class:
            mock_sb_class.return_value = mock_statement_builder

            orders_manager = GAMOrdersManager(self.mock_client_manager, self.advertiser_id, self.trafficker_id)

            advertisers = orders_manager.get_advertisers()

            # Should be sorted by name
            assert len(advertisers) == 3
            assert advertisers[0]["name"] == "Advertiser A"
            assert advertisers[1]["name"] == "Advertiser B"
            assert advertisers[2]["name"] == "Advertiser C"

            # Should convert IDs to strings
            assert all(isinstance(adv["id"], str) for adv in advertisers)

            self.mock_client_manager.get_service.assert_called_once_with("CompanyService")

    def test_get_advertisers_dry_run_mode(self):
        """Test advertiser retrieval in dry-run mode."""
        orders_manager = GAMOrdersManager(
            self.mock_client_manager, self.advertiser_id, self.trafficker_id, dry_run=True
        )

        advertisers = orders_manager.get_advertisers()

        assert len(advertisers) == 2
        assert advertisers[0]["name"] == "Test Advertiser 1"
        assert advertisers[1]["name"] == "Test Advertiser 2"
        self.mock_client_manager.get_service.assert_not_called()

    def test_get_advertisers_api_error(self):
        """Test advertiser retrieval when API call fails."""
        mock_company_service = Mock()
        mock_company_service.getCompaniesByStatement.side_effect = Exception("API Error")
        self.mock_client_manager.get_service.return_value = mock_company_service

        with patch("src.adapters.gam.managers.orders.ad_manager.StatementBuilder"):
            orders_manager = GAMOrdersManager(self.mock_client_manager, self.advertiser_id, self.trafficker_id)

            advertisers = orders_manager.get_advertisers()

            assert advertisers == []


class TestGAMOrdersManagerEdgeCases:
    """Test edge cases and boundary conditions."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_client_manager = Mock()
        self.advertiser_id = "123456789"
        self.trafficker_id = "987654321"

    def test_create_order_zero_budget(self):
        """Test order creation with zero budget."""
        mock_order_service = Mock()
        created_order = {"id": 54321, "name": "Zero Budget Order"}
        mock_order_service.createOrders.return_value = [created_order]
        self.mock_client_manager.get_service.return_value = mock_order_service

        orders_manager = GAMOrdersManager(self.mock_client_manager, self.advertiser_id, self.trafficker_id)

        order_id = orders_manager.create_order(
            order_name="Zero Budget Order",
            total_budget=0.0,
            start_time=datetime(2025, 1, 1),
            end_time=datetime(2025, 1, 31),
        )

        assert order_id == "54321"

        # Verify zero budget is handled correctly
        call_args = mock_order_service.createOrders.call_args[0][0]
        order_data = call_args[0]
        assert order_data["totalBudget"]["microAmount"] == 0

    def test_create_order_fractional_budget(self):
        """Test order creation with fractional budget."""
        mock_order_service = Mock()
        created_order = {"id": 54321, "name": "Fractional Budget Order"}
        mock_order_service.createOrders.return_value = [created_order]
        self.mock_client_manager.get_service.return_value = mock_order_service

        orders_manager = GAMOrdersManager(self.mock_client_manager, self.advertiser_id, self.trafficker_id)

        order_id = orders_manager.create_order(
            order_name="Fractional Budget Order",
            total_budget=1234.56,
            start_time=datetime(2025, 1, 1),
            end_time=datetime(2025, 1, 31),
        )

        assert order_id == "54321"

        # Verify fractional budget conversion
        call_args = mock_order_service.createOrders.call_args[0][0]
        order_data = call_args[0]
        assert order_data["totalBudget"]["microAmount"] == 1234560000  # 1234.56 * 1M

    def test_create_order_same_start_end_date(self):
        """Test order creation with same start and end date."""
        mock_order_service = Mock()
        created_order = {"id": 54321, "name": "Same Day Order"}
        mock_order_service.createOrders.return_value = [created_order]
        self.mock_client_manager.get_service.return_value = mock_order_service

        orders_manager = GAMOrdersManager(self.mock_client_manager, self.advertiser_id, self.trafficker_id)

        same_date = datetime(2025, 3, 15, 12, 0, 0)

        order_id = orders_manager.create_order(
            order_name="Same Day Order", total_budget=1000.0, start_time=same_date, end_time=same_date
        )

        assert order_id == "54321"

    def test_get_order_status_malformed_response(self):
        """Test order status handling with malformed GAM response."""
        mock_order_service = Mock()
        mock_order_service.getOrdersByStatement.return_value = {"results": [{"id": 12345}]}  # Missing status field
        self.mock_client_manager.get_service.return_value = mock_order_service

        with patch("src.adapters.gam.managers.orders.ad_manager.StatementBuilder"):
            orders_manager = GAMOrdersManager(self.mock_client_manager, self.advertiser_id, self.trafficker_id)

            status = orders_manager.get_order_status("12345")

            assert status == "UNKNOWN"

    def test_get_order_status_none_response(self):
        """Test order status handling with None response."""
        mock_order_service = Mock()
        mock_order_service.getOrdersByStatement.return_value = None
        self.mock_client_manager.get_service.return_value = mock_order_service

        with patch("src.adapters.gam.managers.orders.ad_manager.StatementBuilder"):
            orders_manager = GAMOrdersManager(self.mock_client_manager, self.advertiser_id, self.trafficker_id)

            status = orders_manager.get_order_status("12345")

            assert status == "NOT_FOUND"

    def test_archive_order_missing_response_field(self):
        """Test order archival with missing numChanges field in response."""
        mock_order_service = Mock()
        mock_order_service.performOrderAction.return_value = {}  # Missing numChanges
        self.mock_client_manager.get_service.return_value = mock_order_service

        with patch("src.adapters.gam.managers.orders.ad_manager.StatementBuilder"):
            orders_manager = GAMOrdersManager(self.mock_client_manager, self.advertiser_id, self.trafficker_id)

            result = orders_manager.archive_order("12345")

            assert result is True  # Should still be considered successful

    def test_get_order_line_items_missing_results(self):
        """Test line items retrieval with missing results field."""
        mock_lineitem_service = Mock()
        mock_lineitem_service.getLineItemsByStatement.return_value = {}  # Missing results
        self.mock_client_manager.get_service.return_value = mock_lineitem_service

        with patch("src.adapters.gam.managers.orders.ad_manager.StatementBuilder"):
            orders_manager = GAMOrdersManager(self.mock_client_manager, self.advertiser_id, self.trafficker_id)

            result = orders_manager.get_order_line_items("12345")

            assert result == []

    def test_check_order_has_guaranteed_items_missing_line_item_type(self):
        """Test guaranteed items check with line items missing lineItemType field."""
        orders_manager = GAMOrdersManager(self.mock_client_manager, self.advertiser_id, self.trafficker_id)

        # Mock line items with missing lineItemType
        line_items = [
            {"id": 111, "name": "Line Item 1"},  # Missing lineItemType
            {"id": 222, "lineItemType": "STANDARD"},
        ]

        with patch.object(orders_manager, "get_order_line_items") as mock_get_line_items:
            mock_get_line_items.return_value = line_items

            has_guaranteed, guaranteed_types = orders_manager.check_order_has_guaranteed_items("12345")

            assert has_guaranteed is True
            assert guaranteed_types == ["STANDARD"]

    def test_get_advertisers_empty_response(self):
        """Test advertiser retrieval with empty response."""
        mock_company_service = Mock()
        mock_company_service.getCompaniesByStatement.return_value = {"results": []}
        self.mock_client_manager.get_service.return_value = mock_company_service

        with patch("src.adapters.gam.managers.orders.ad_manager.StatementBuilder"):
            orders_manager = GAMOrdersManager(self.mock_client_manager, self.advertiser_id, self.trafficker_id)

            advertisers = orders_manager.get_advertisers()

            assert advertisers == []

    def test_create_order_with_unicode_characters(self):
        """Test order creation with Unicode characters in order name."""
        mock_order_service = Mock()
        created_order = {"id": 54321, "name": "测试订单 🚀"}
        mock_order_service.createOrders.return_value = [created_order]
        self.mock_client_manager.get_service.return_value = mock_order_service

        orders_manager = GAMOrdersManager(self.mock_client_manager, self.advertiser_id, self.trafficker_id)

        order_id = orders_manager.create_order(
            order_name="测试订单 🚀",
            total_budget=1000.0,
            start_time=datetime(2025, 1, 1),
            end_time=datetime(2025, 1, 31),
        )

        assert order_id == "54321"

        # Verify Unicode name is preserved
        call_args = mock_order_service.createOrders.call_args[0][0]
        order_data = call_args[0]
        assert order_data["name"] == "测试订单 🚀"

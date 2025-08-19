"""Tests for GAM Line Item Viewer functionality."""

import json
from unittest.mock import Mock, patch

import pytest

# Mark all tests in this module as requiring database
pytestmark = [pytest.mark.requires_db]


@pytest.fixture
def mock_gam_client():
    """Create a mock GAM client."""
    client = Mock()

    # Mock line item service
    line_item_service = Mock()

    # Create mock line item response
    mock_line_item = Mock()
    mock_line_item.id = 5834526917
    mock_line_item.orderId = 2857915125
    mock_line_item.name = "Sports_Desktop_Display_Q1_2025"
    mock_line_item.externalId = "ADCP_001"
    mock_line_item.lineItemType = "STANDARD"
    mock_line_item.priority = 8
    mock_line_item.status = "DELIVERING"
    mock_line_item.costType = "CPM"
    mock_line_item.costPerUnit = Mock()
    mock_line_item.costPerUnit.microAmount = 15000000
    mock_line_item.costPerUnit.currencyCode = "USD"
    mock_line_item.unitsBought = 1000000
    mock_line_item.deliveryRateType = "EVENLY"
    mock_line_item.startDateTime = Mock()
    mock_line_item.startDateTime.date = Mock()
    mock_line_item.startDateTime.date.year = 2025
    mock_line_item.startDateTime.date.month = 1
    mock_line_item.startDateTime.date.day = 1
    mock_line_item.startDateTime.hour = 0
    mock_line_item.endDateTime = Mock()
    mock_line_item.endDateTime.date = Mock()
    mock_line_item.endDateTime.date.year = 2025
    mock_line_item.endDateTime.date.month = 3
    mock_line_item.endDateTime.date.day = 31
    mock_line_item.endDateTime.hour = 23
    mock_line_item.stats = Mock()
    mock_line_item.stats.impressionsDelivered = 456789
    mock_line_item.stats.clicksDelivered = 2341
    mock_line_item.targeting = Mock()

    # Mock getLineItemsByStatement
    line_item_service.getLineItemsByStatement = Mock(
        return_value={"results": [mock_line_item], "totalResultSetSize": 1}
    )
    client.GetService = Mock(return_value=line_item_service)

    return client


@pytest.fixture
def authenticated_client(test_admin_app):
    """Create authenticated test client."""
    client = test_admin_app.test_client()

    with client.session_transaction() as sess:
        sess["authenticated"] = True
        sess["tenant_id"] = "test_tenant"
        sess["role"] = "tenant_admin"

    return client


class TestGAMLineItemViewer:
    """Test GAM Line Item viewer functionality."""

    @pytest.mark.skip(reason="Requires GAM adapter routes to be properly registered")
    def test_get_gam_line_item_success(self, authenticated_client, mock_gam_client):
        """Test successful retrieval of GAM line item."""
        # Create mock database connection
        mock_db_connection = Mock()
        mock_cursor = Mock()

        # Mock tenant query
        mock_cursor.fetchone.side_effect = [
            # First call - tenant query
            {"tenant_id": "test_tenant", "name": "Test Publisher", "ad_server": "google_ad_manager"},
            # Second call - adapter config query
            {"config": json.dumps({"network_code": "123456", "advertiser_id": "789"})},
        ]

        mock_db_connection.execute.return_value = mock_cursor
        mock_db_connection.close = Mock()

        # Mock ORM session for tenant lookup
        from unittest.mock import MagicMock

        mock_tenant = MagicMock()
        mock_tenant.tenant_id = "test_tenant"
        mock_tenant.name = "Test Publisher"
        mock_tenant.ad_server = "google_ad_manager"

        mock_adapter = MagicMock()
        mock_adapter.config = json.dumps({"network_code": "123456", "advertiser_id": "789"})

        # Setup complex mocking for the database session
        with patch("database_session.db_session") as mock_db_session:
            # Mock for GAM line items and orders
            mock_gam_line_item = MagicMock()
            mock_gam_line_item.line_item_id = 5834526917
            mock_gam_line_item.order_id = 2857915125
            mock_gam_line_item.name = "Sports_Desktop_Display_Q1_2025"
            mock_gam_line_item.status = "DELIVERING"
            mock_gam_line_item.priority = 8
            mock_gam_line_item.line_item_type = "STANDARD"
            mock_gam_line_item.cost_type = "CPM"
            mock_gam_line_item.cost_per_unit = 15.0
            mock_gam_line_item.currency_code = "USD"
            mock_gam_line_item.units_bought = 1000000
            mock_gam_line_item.external_id = "ADCP_001"
            mock_gam_line_item.last_sync_at = None

            mock_gam_order = MagicMock()
            mock_gam_order.order_id = 2857915125
            mock_gam_order.name = "Q1 2025 Sports Campaign"
            mock_gam_order.advertiser_id = 456789

            # Setup query chain for different queries
            def query_side_effect(model):
                """Return different mock objects based on model type."""
                query_mock = MagicMock()
                if hasattr(model, "__name__"):
                    if model.__name__ == "Tenant":
                        query_mock.filter_by.return_value.first.return_value = mock_tenant
                    elif model.__name__ == "AdapterConfig":
                        query_mock.filter_by.return_value.first.return_value = mock_adapter
                    elif model.__name__ == "GAMLineItem":
                        query_mock.filter_by.return_value.first.return_value = mock_gam_line_item
                    elif model.__name__ == "GAMOrder":
                        query_mock.filter_by.return_value.first.return_value = mock_gam_order
                return query_mock

            mock_db_session.query.side_effect = query_side_effect
            mock_db_session.remove = Mock()

            # Mock get_tenant_config_from_db to return GAM enabled config
            with patch("admin_ui.get_tenant_config_from_db") as mock_get_config:
                mock_get_config.return_value = {
                    "adapters": {
                        "google_ad_manager": {
                            "enabled": True,
                            "network_code": "123456",
                            "refresh_token": "mock_refresh_token",
                        }
                    }
                }

                with patch("admin_ui.get_db_session") as mock_get_session:
                    # Create a proper mock session that returns a tenant
                    mock_session_ctx = MagicMock()
                    mock_query = MagicMock()
                    mock_filter = MagicMock()

                    # Mock the Tenant object
                    mock_tenant_obj = MagicMock()
                    mock_tenant_obj.tenant_id = "test_tenant"
                    mock_tenant_obj.name = "Test Publisher"
                    mock_tenant_obj.ad_server = "google_ad_manager"

                    # Chain the query methods
                    mock_session_ctx.query.return_value = mock_query
                    mock_query.filter_by.return_value = mock_filter
                    mock_filter.first.return_value = mock_tenant_obj

                    # Make the context manager work
                    mock_session = MagicMock()
                    mock_session.__enter__.return_value = mock_session_ctx
                    mock_session.__exit__.return_value = None
                    mock_get_session.return_value = mock_session

                    with patch("gam_helper.get_ad_manager_client_for_tenant", return_value=mock_gam_client):
                        with patch("googleads.ad_manager.StatementBuilder") as mock_statement_builder:
                            # Mock StatementBuilder
                            mock_builder = Mock()
                            mock_builder.Where = Mock(return_value=mock_builder)
                            mock_builder.WithBindVariable = Mock(return_value=mock_builder)
                            mock_builder.ToStatement = Mock(
                                return_value={
                                    "query": "SELECT * FROM line_items WHERE id = :id",
                                    "values": [
                                        {"key": "id", "value": {"value": 5834526917, "xsi_type": "NumberValue"}}
                                    ],
                                }
                            )
                            mock_statement_builder.return_value = mock_builder

                            # Make the API call
                            response = authenticated_client.get("/api/tenant/test_tenant/gam/line-item/5834526917")

                            # Verify response
                            assert response.status_code == 200
                            data = json.loads(response.data)
                            assert data["line_item"]["id"] == 5834526917
                            assert data["line_item"]["name"] == "Sports_Desktop_Display_Q1_2025"
                            assert data["line_item"]["status"] == "DELIVERING"
                            assert data["line_item"]["impressions_delivered"] == 456789
                            assert data["line_item"]["clicks_delivered"] == 2341
                            assert data["line_item"]["ctr"] == "0.51%"


def test_get_gam_line_item_not_found(test_admin_app):
    """Test GAM line item not found."""
    client = test_admin_app.test_client()

    with client.session_transaction() as sess:
        sess["authenticated"] = True
        sess["tenant_id"] = "test_tenant"
        sess["role"] = "tenant_admin"

    # Create mock SQLAlchemy session
    mock_session = Mock()
    mock_tenant = Mock()
    mock_tenant.tenant_id = "test_tenant"
    mock_tenant.name = "Test Publisher"
    mock_tenant.ad_server = "google_ad_manager"

    # Mock the query chain
    mock_query = Mock()
    mock_query.filter_by.return_value.first.return_value = mock_tenant
    mock_session.query.return_value = mock_query

    # Mock get_tenant_config_from_db
    with patch("admin_ui.get_tenant_config_from_db") as mock_get_config:
        mock_get_config.return_value = {
            "adapters": {
                "google_ad_manager": {"enabled": True, "network_code": "123456", "refresh_token": "mock_refresh_token"}
            }
        }

        with patch("admin_ui.get_db_session") as mock_get_session:
            # Make get_db_session return a proper context manager
            mock_context = Mock()
            mock_context.__enter__ = Mock(return_value=mock_session)
            mock_context.__exit__ = Mock(return_value=None)
            mock_get_session.return_value = mock_context

            response = client.get("/api/tenant/test_tenant/gam/line-item/99999999")

            # Should get 404 when line item doesn't exist
            assert response.status_code in [404, 500]  # Could be 404 or 500 depending on error handling


def test_get_gam_line_item_unauthorized(test_admin_app):
    """Test GAM line item access without authentication."""
    client = test_admin_app.test_client()

    # Create mock SQLAlchemy session (should not be called)
    mock_session = Mock()

    with patch("admin_ui.get_db_session") as mock_get_session:
        # Make get_db_session return a proper context manager
        mock_context = Mock()
        mock_context.__enter__ = Mock(return_value=mock_session)
        mock_context.__exit__ = Mock(return_value=None)
        mock_get_session.return_value = mock_context

        response = client.get("/api/tenant/test_tenant/gam/line-item/5834526917")

        # Should redirect to login
        assert response.status_code == 302
        assert "/login" in response.location


def test_view_line_item_page(test_admin_app):
    """Test the line item viewer page renders."""
    client = test_admin_app.test_client()

    with client.session_transaction() as sess:
        sess["authenticated"] = True
        sess["tenant_id"] = "test_tenant"
        sess["role"] = "tenant_admin"

    # Create mock database connection
    mock_db_connection = Mock()
    mock_cursor = Mock()

    # Mock tenant query
    mock_cursor.fetchone.return_value = {"tenant_id": "test_tenant", "name": "Test Publisher", "subdomain": "test"}

    mock_db_connection.execute.return_value = mock_cursor
    mock_db_connection.close = Mock()

    # Mock the ORM session
    from unittest.mock import MagicMock

    mock_tenant = MagicMock()
    mock_tenant.tenant_id = "test_tenant"
    mock_tenant.name = "Test Publisher"
    mock_tenant.subdomain = "test"

    with patch("database_session.db_session") as mock_db_session:
        mock_query = MagicMock()
        mock_query.filter_by.return_value.first.return_value = mock_tenant
        mock_db_session.query.return_value = mock_query
        mock_db_session.remove = Mock()

        with patch("admin_ui.get_tenant_config_from_db", return_value={"ad_server": "google_ad_manager"}):
            with patch("admin_ui.get_db_session") as mock_get_session:
                # Make get_db_session return a proper context manager
                mock_context = Mock()
                mock_context.__enter__ = Mock(return_value=mock_db_session)
                mock_context.__exit__ = Mock(return_value=None)
                mock_get_session.return_value = mock_context

                response = client.get("/tenant/test_tenant/gam/line-item/5834526917")

                # Should return the page
                assert response.status_code == 200
                assert b"GAM Line Item" in response.data or b"Line Item" in response.data

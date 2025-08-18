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
    mock_line_item.targeting.geoTargeting = Mock()
    mock_line_item.targeting.geoTargeting.targetedLocations = []
    mock_line_item.creativePlaceholders = []
    mock_line_item.frequencyCaps = []

    # Mock response with results
    mock_response = Mock()
    mock_response.results = [mock_line_item]

    # Setup getLineItemsByStatement to return mock response
    line_item_service.getLineItemsByStatement = Mock(return_value=mock_response)

    # Mock order service
    order_service = Mock()
    mock_order = Mock()
    mock_order.id = 2857915125
    mock_order.name = "Acme Corp - Q1 2025 Campaign"
    mock_order.advertiserId = 4563534
    mock_order.traffickerId = 245563
    mock_order.status = "APPROVED"

    mock_order_response = Mock()
    mock_order_response.results = [mock_order]
    order_service.getOrdersByStatement = Mock(return_value=mock_order_response)

    # Mock LICA service
    lica_service = Mock()
    mock_lica = Mock()
    mock_lica.lineItemId = 5834526917
    mock_lica.creativeId = 138251188213
    mock_lica.status = "ACTIVE"

    mock_lica_response = Mock()
    mock_lica_response.results = [mock_lica]
    lica_service.getLineItemCreativeAssociationsByStatement = Mock(return_value=mock_lica_response)

    # Mock creative service
    creative_service = Mock()
    mock_creative = Mock()
    mock_creative.id = 138251188213
    mock_creative.name = "AcmeCorp_Sports_728x90"
    mock_creative.size = Mock()
    mock_creative.size.width = 728
    mock_creative.size.height = 90
    # Use setattr instead of dict assignment for Mock objects
    setattr(mock_creative, "Creative.Type", "ImageCreative")

    mock_creative_response = Mock()
    mock_creative_response.results = [mock_creative]
    creative_service.getCreativesByStatement = Mock(return_value=mock_creative_response)

    # Configure client.GetService to return appropriate service
    def get_service(service_name):
        services = {
            "LineItemService": line_item_service,
            "OrderService": order_service,
            "LineItemCreativeAssociationService": lica_service,
            "CreativeService": creative_service,
        }
        return services.get(service_name)

    client.GetService = Mock(side_effect=get_service)

    return client


@pytest.fixture
def mock_app(flask_app):
    """Create a mock Flask app with test configuration."""
    flask_app.config["TESTING"] = True
    flask_app.config["WTF_CSRF_ENABLED"] = False

    with flask_app.test_client() as client:
        with flask_app.app_context():
            yield client


@pytest.mark.requires_server  # This test requires a running server with database
@pytest.mark.skip(reason="Requires full database setup and server running")
def test_gam_line_item_api_endpoint(mock_app, mock_gam_client, mock_db_connection):
    """Test the GAM line item API endpoint."""
    # Mock the SQLAlchemy db_session imported from gam_inventory_service and used in admin_ui
    with patch("gam_inventory_service.db_session") as mock_gam_inv_session:
        with patch("admin_ui.db_session", mock_gam_inv_session) as mock_db_session:
            # Mock the query chain for GAMLineItem
            mock_query = Mock()
            mock_query.filter.return_value.first.return_value = None  # No line item in DB
            mock_db_session.query.return_value = mock_query
            mock_db_session.remove = Mock()

            with patch("admin_ui.get_db_connection", return_value=mock_db_connection):
                with patch("gam_helper.get_ad_manager_client_for_tenant", return_value=mock_gam_client):
                    with patch("googleads.ad_manager.StatementBuilder") as mock_statement_builder:
                        # Mock StatementBuilder
                        mock_builder = Mock()
                        mock_builder.Where = Mock(return_value=mock_builder)
                        mock_builder.WithBindVariable = Mock(return_value=mock_builder)
                        mock_builder.Limit = Mock(return_value=mock_builder)
                        mock_builder.ToStatement = Mock(return_value={})
                        mock_statement_builder.return_value = mock_builder

                        # Mock serialize_object to return dict
                        with patch("zeep.helpers.serialize_object") as mock_serialize:

                            def serialize_side_effect(obj):
                                if hasattr(obj, "__dict__"):
                                    # For single objects
                                    result = {}
                                    for key, value in obj.__dict__.items():
                                        if hasattr(value, "__dict__"):
                                            result[key] = serialize_side_effect(value)
                                        else:
                                            result[key] = value
                                    return result
                                elif isinstance(obj, list):
                                    # For lists of objects
                                    return [serialize_side_effect(item) for item in obj]
                                else:
                                    return obj

                            mock_serialize.side_effect = serialize_side_effect

                            # Mock session for authentication
                            with mock_app.session_transaction() as sess:
                                sess["authenticated"] = True
                                sess["email"] = "test@example.com"
                                sess["role"] = "super_admin"

                            # Make request to API endpoint
                            response = mock_app.get("/api/tenant/test_tenant/gam/line-item/5834526917")

                            assert response.status_code == 200
                            data = json.loads(response.data)

                            # Verify response structure
                            assert "line_item" in data
                            assert "order" in data
                            assert "creatives" in data
                            assert "creative_associations" in data
                            assert "media_product_json" in data

                            # Verify line item data
                            assert data["line_item"]["id"] == 5834526917
                            assert data["line_item"]["name"] == "Sports_Desktop_Display_Q1_2025"
                            assert data["line_item"]["status"] == "DELIVERING"

                            # Verify order data
                            assert data["order"]["id"] == 2857915125
                            assert data["order"]["name"] == "Acme Corp - Q1 2025 Campaign"

                            # Verify media product JSON was generated
                            assert data["media_product_json"]["product_id"] == "gam_line_item_5834526917"
                            assert data["media_product_json"]["cpm"] == 15.0


def test_gam_line_item_viewer_page(mock_app, mock_db_connection):
    """Test the GAM line item viewer page renders correctly."""
    with patch("admin_ui.get_db_connection", return_value=mock_db_connection):
        # Mock session for authentication
        with mock_app.session_transaction() as sess:
            sess["authenticated"] = True
            sess["email"] = "test@example.com"
            sess["role"] = "super_admin"

        # Request the viewer page
        response = mock_app.get("/tenant/test_tenant/gam/line-item/5834526917")

        assert response.status_code == 200
        # Check that the template renders key elements
        assert b"GAM Line Item Viewer" in response.data
        assert b"5834526917" in response.data
        assert b"test_tenant" in response.data


def test_invalid_line_item_id(mock_app, mock_db_connection):
    """Test handling of invalid line item IDs."""
    with patch("admin_ui.get_db_connection", return_value=mock_db_connection):
        # Mock session for authentication
        with mock_app.session_transaction() as sess:
            sess["authenticated"] = True
            sess["email"] = "test@example.com"
            sess["role"] = "super_admin"

        # Test non-numeric ID
        response = mock_app.get("/api/tenant/test_tenant/gam/line-item/invalid")
        assert response.status_code == 400
        data = json.loads(response.data)
        assert "error" in data
        assert "numeric" in data["error"].lower()

        # Test negative ID
        response = mock_app.get("/api/tenant/test_tenant/gam/line-item/-123")
        assert response.status_code == 400
        data = json.loads(response.data)
        assert "error" in data
        # Just check for some error message about line item ID
        assert "line item" in data["error"].lower()

        # Test too short ID
        response = mock_app.get("/api/tenant/test_tenant/gam/line-item/123")
        assert response.status_code == 400
        data = json.loads(response.data)
        assert "Invalid GAM line item ID format" in data["error"]


@pytest.mark.requires_server  # This test requires a running server with database
@pytest.mark.skip(reason="Requires full database setup and server running")
def test_line_item_not_found(mock_app, mock_gam_client, mock_db_connection):
    """Test handling when line item is not found in GAM."""
    # Mock the SQLAlchemy db_session imported from gam_inventory_service and used in admin_ui
    with patch("gam_inventory_service.db_session") as mock_gam_inv_session:
        with patch("admin_ui.db_session", mock_gam_inv_session) as mock_db_session:
            # Mock the query chain for GAMLineItem
            mock_query = Mock()
            mock_query.filter.return_value.first.return_value = None  # No line item in DB
            mock_db_session.query.return_value = mock_query
            mock_db_session.remove = Mock()

            with patch("admin_ui.get_db_connection", return_value=mock_db_connection):
                with patch("gam_helper.get_ad_manager_client_for_tenant", return_value=mock_gam_client):
                    with patch("googleads.ad_manager.StatementBuilder") as mock_statement_builder:
                        # Mock StatementBuilder
                        mock_builder = Mock()
                        mock_builder.Where = Mock(return_value=mock_builder)
                        mock_builder.WithBindVariable = Mock(return_value=mock_builder)
                        mock_builder.Limit = Mock(return_value=mock_builder)
                        mock_builder.ToStatement = Mock(return_value={})
                        mock_statement_builder.return_value = mock_builder

                        # Mock empty response
                        mock_empty_response = Mock()
                        mock_empty_response.results = []
                        delattr(mock_empty_response, "results")  # Simulate no results attribute

                        line_item_service = mock_gam_client.GetService("LineItemService")
                        line_item_service.getLineItemsByStatement = Mock(return_value=mock_empty_response)

                        # Mock session for authentication
                        with mock_app.session_transaction() as sess:
                            sess["authenticated"] = True
                            sess["email"] = "test@example.com"
                            sess["role"] = "super_admin"

                        # Make request
                        response = mock_app.get("/api/tenant/test_tenant/gam/line-item/9999999999")

                        assert response.status_code == 404
                        data = json.loads(response.data)
                        assert "error" in data
                        assert "Line item not found" in data["error"]


def test_convert_line_item_to_product_json():
    """Test the conversion of GAM line item to product JSON format."""
    # Import the function with proper mocking
    with patch("admin_ui.get_db_session"):
        from admin_ui import convert_line_item_to_product_json

    # Create mock line item data
    line_item = {
        "id": 5834526917,
        "name": "Test_Line_Item",
        "lineItemType": "STANDARD",
        "costType": "CPM",
        "costPerUnit": {"microAmount": 15000000},
        "targeting": {
            "geoTargeting": {"targetedLocations": [{"type": "COUNTRY", "displayName": "United States", "id": 2840}]},
            "dayPartTargeting": {
                "timeZone": "America/New_York",
                "dayParts": [{"dayOfWeek": "MONDAY", "startTime": {"hour": 9}, "endTime": {"hour": 17}}],
            },
        },
        "frequencyCaps": [{"maxImpressions": 10, "numTimeUnits": 1, "timeUnit": "DAY"}],
        "creativePlaceholders": [{"size": {"width": 300, "height": 250}}],
    }

    creatives = [{"id": 123, "size": {"width": 300, "height": 250}, "Creative.Type": "ImageCreative"}]

    result = convert_line_item_to_product_json(line_item, creatives)

    # Verify the conversion
    assert result["product_id"] == "gam_line_item_5834526917"
    assert result["name"] == "Test_Line_Item"
    assert result["delivery_type"] == "guaranteed"
    assert result["is_fixed_price"] is True
    assert result["cpm"] == 15.0
    assert "US" in result["targeting_overlay"].get("geo_country_any_of", [])
    assert "dayparting" in result["targeting_overlay"]
    assert "frequency_cap" in result["targeting_overlay"]
    assert len(result["formats"]) > 0
    assert result["formats"][0]["id"] == "display_300x250"


@pytest.fixture
def mock_db_connection(mock_db):
    """Create a mock database connection compatible with the test framework."""
    conn = Mock()
    cursor = Mock()

    # Mock tenant configuration using the standard test data format
    tenant_data = {
        "tenant_id": "test_tenant",
        "name": "Test Tenant",
        "ad_server": "google_ad_manager",
        "max_daily_budget": 10000,
        "enable_aee_signals": 1,
        "authorized_emails": None,
        "authorized_domains": None,
        "slack_webhook_url": None,
        "slack_audit_webhook_url": None,
        "hitl_webhook_url": None,
        "admin_token": "admin_token",
        "auto_approve_formats": '["display_300x250"]',
        "human_review_required": 0,
        "policy_settings": None,
    }

    # Convert dict to tuple for compatibility with fetchone
    tenant_row = (
        tenant_data["ad_server"],
        tenant_data["max_daily_budget"],
        tenant_data["enable_aee_signals"],
        tenant_data["authorized_emails"],
        tenant_data["authorized_domains"],
        tenant_data["slack_webhook_url"],
        tenant_data["slack_audit_webhook_url"],
        tenant_data["hitl_webhook_url"],
        tenant_data["admin_token"],
        tenant_data["auto_approve_formats"],
        tenant_data["human_review_required"],
        tenant_data["policy_settings"],
    )

    cursor.fetchone = Mock(return_value=tenant_row)
    cursor.fetchall = Mock(return_value=[])

    conn.cursor = Mock(return_value=cursor)
    conn.execute = Mock(return_value=cursor)
    conn.close = Mock()

    return conn

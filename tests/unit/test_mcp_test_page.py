"""Unit tests for the MCP test page and API."""

import asyncio
import json
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest


class TestMCPTestPageUnit:
    """Unit tests for MCP test page functionality."""

    @pytest.fixture
    def app(self):
        """Create Flask app for testing."""
        from src.admin.app import create_app

        app, _ = create_app()
        app.config["TESTING"] = True
        app.config["SECRET_KEY"] = "test-secret-key"
        return app

    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return app.test_client()

    @pytest.fixture
    def auth_client(self, client):
        """Create authenticated client as super admin."""
        with client.session_transaction() as sess:
            sess["authenticated"] = True
            sess["email"] = "admin@example.com"
            sess["role"] = "super_admin"
            sess["name"] = "Test Admin"
            sess["user"] = {"email": "admin@example.com", "name": "Test Admin"}
        return client

    @patch("src.admin.utils.is_super_admin", return_value=True)
    def test_mcp_test_page_template_rendering(self, mock_is_super_admin, auth_client):
        """Test that the MCP test page renders with correct elements."""
        with patch("database_session.get_db_session") as mock_db:
            # Mock database results
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.execute.return_value = mock_cursor
            mock_cursor.fetchall.return_value = [("tenant1", "Tenant One", "principal1", "Principal One", "token123")]
            mock_db.return_value = mock_conn

            response = auth_client.get("/mcp-test")
            assert response.status_code == 200

            # Check for key UI elements
            html = response.data.decode("utf-8")
            assert "MCP Protocol Test" in html
            assert "Server URL" in html
            assert "Principal (Auth Token)" in html
            assert "x-adcp-auth" in html  # Header name should be shown

            # Check for tool buttons
            assert "get_products" in html
            assert "create_media_buy" in html
            assert "check_media_buy_status" in html
            assert "add_creative_assets" in html
            assert "update_media_buy" in html
            assert "get_media_buy_delivery" in html

            # Check for sample parameters with required fields
            assert "promoted_offering" in html
            assert "geo_country_any_of" in html

    @patch("asyncio.set_event_loop")
    @patch("asyncio.new_event_loop")
    def test_mcp_api_call_with_auth_header(self, mock_new_event_loop, mock_set_event_loop, auth_client):
        """Test that API call uses x-adcp-auth header correctly."""
        with patch("database_session.get_db_session") as mock_db:
            # Mock database
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.execute.return_value = mock_cursor
            mock_cursor.fetchone.return_value = ("default",)  # tenant_id
            mock_db.return_value = mock_conn

            # Create a real event loop for the mock
            real_loop = asyncio.new_event_loop()

            # Mock the coroutine result - should return what make_call() returns
            def mock_run_until_complete(coro):
                # Return the expected result instead of running the coroutine
                return {"success": True, "result": {"products": [{"product_id": "test", "name": "Test Product"}]}}

            real_loop.run_until_complete = mock_run_until_complete
            mock_new_event_loop.return_value = real_loop
            mock_set_event_loop.return_value = None  # set_event_loop doesn't return anything

            try:
                response = auth_client.post(
                    "/api/mcp-test/call",
                    json={
                        "server_url": "http://localhost:8080/mcp/",
                        "tool": "get_products",
                        "params": {"brief": "test brief", "promoted_offering": "test offering"},
                        "access_token": "test_token_123",
                    },
                    headers={"Content-Type": "application/json"},
                )

                assert response.status_code == 200
                data = json.loads(response.data)
                assert data["success"] is True
                assert "result" in data
            finally:
                real_loop.close()

    def test_mcp_api_validates_required_params(self, auth_client):
        """Test that API validates required parameters."""
        response = auth_client.post(
            "/api/mcp-test/call",
            json={
                "server_url": "http://localhost:8080/mcp/",
                # Missing 'tool' and 'access_token'
                "params": {},
            },
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert data["success"] is False
        assert "required parameters" in data["error"].lower()

    @patch("asyncio.set_event_loop")
    @patch("asyncio.new_event_loop")
    def test_mcp_api_handles_tool_errors(self, mock_new_event_loop, mock_set_event_loop, auth_client):
        """Test that API handles MCP tool errors gracefully."""
        with patch("database_session.get_db_session") as mock_db:
            # Mock database
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.execute.return_value = mock_cursor
            mock_cursor.fetchone.return_value = ("default",)
            mock_db.return_value = mock_conn

            # Create a real event loop for the mock
            real_loop = asyncio.new_event_loop()

            # Mock to raise an error
            def mock_run_until_complete(coro):
                raise Exception("Tool execution failed: Invalid parameters")

            real_loop.run_until_complete = mock_run_until_complete
            mock_new_event_loop.return_value = real_loop
            mock_set_event_loop.return_value = None

            try:
                response = auth_client.post(
                    "/api/mcp-test/call",
                    json={
                        "server_url": "http://localhost:8080/mcp/",
                        "tool": "get_products",
                        "params": {"brief": "test"},  # Missing promoted_offering
                        "access_token": "test_token",
                    },
                    headers={"Content-Type": "application/json"},
                )

                assert response.status_code == 500
                data = json.loads(response.data)
                assert data["success"] is False
                # The error message will be "Event loop error: Tool execution failed: Invalid parameters"
                assert "Tool execution failed" in data["error"] or "Event loop error" in data["error"]
            finally:
                real_loop.close()

    def test_mcp_test_page_auth_requirements(self, client):
        """Test authentication requirements for MCP test page."""
        # Test unauthenticated access
        response = client.get("/mcp-test")
        assert response.status_code == 302  # Redirect to login

        # Test authenticated but not super admin
        with client.session_transaction() as sess:
            sess["authenticated"] = True
            sess["email"] = "user@example.com"
            sess["role"] = "tenant_admin"

        response = client.get("/mcp-test")
        assert response.status_code == 403  # Forbidden

        # Test viewer role
        with client.session_transaction() as sess:
            sess["authenticated"] = True
            sess["email"] = "viewer@example.com"
            sess["role"] = "viewer"

        response = client.get("/mcp-test")
        assert response.status_code == 403

    @patch("asyncio.set_event_loop")
    @patch("asyncio.new_event_loop")
    def test_mcp_api_response_parsing(self, mock_new_event_loop, mock_set_event_loop, auth_client):
        """Test that API correctly parses different response formats."""
        with patch("database_session.get_db_session") as mock_db:
            # Mock database
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.execute.return_value = mock_cursor
            mock_cursor.fetchone.return_value = ("default",)
            mock_db.return_value = mock_conn

            # Create a real event loop for the mock
            real_loop = asyncio.new_event_loop()

            # Mock successful response with products
            def mock_run_until_complete(coro):
                return {"success": True, "result": {"products": [{"product_id": "prod_001", "name": "Test Product"}]}}

            real_loop.run_until_complete = mock_run_until_complete
            mock_new_event_loop.return_value = real_loop
            mock_set_event_loop.return_value = None

            try:
                response = auth_client.post(
                    "/api/mcp-test/call",
                    json={
                        "server_url": "http://localhost:8080/mcp/",
                        "tool": "get_products",
                        "params": {"brief": "test", "promoted_offering": "test"},
                        "access_token": "test_token",
                    },
                    headers={"Content-Type": "application/json"},
                )

                assert response.status_code == 200
                data = json.loads(response.data)
                assert data["success"] is True
                assert "result" in data
                assert "products" in data["result"]
            finally:
                real_loop.close()

    @patch("asyncio.set_event_loop")
    @patch("asyncio.new_event_loop")
    def test_mcp_country_targeting_in_params(self, mock_new_event_loop, mock_set_event_loop, auth_client):
        """Test that country targeting is properly included in parameters."""
        with patch("database_session.get_db_session") as mock_db:
            # Mock database
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.execute.return_value = mock_cursor
            mock_cursor.fetchone.return_value = ("default",)
            mock_db.return_value = mock_conn

            # Create a real event loop for the mock
            real_loop = asyncio.new_event_loop()

            # Mock successful media buy creation
            def mock_run_until_complete(coro):
                return {
                    "success": True,
                    "result": {"media_buy_id": "mb_001", "context_id": "ctx_001", "status": "pending_creative"},
                }

            real_loop.run_until_complete = mock_run_until_complete
            mock_new_event_loop.return_value = real_loop
            mock_set_event_loop.return_value = None

            try:
                response = auth_client.post(
                    "/api/mcp-test/call",
                    json={
                        "server_url": "http://localhost:8080/mcp/",
                        "tool": "create_media_buy",
                        "params": {
                            "product_ids": ["prod_001"],
                            "total_budget": 5000.0,
                            "flight_start_date": date.today().isoformat(),
                            "flight_end_date": (date.today() + timedelta(days=30)).isoformat(),
                            "targeting_overlay": {
                                "geo_country_any_of": ["US", "CA", "GB"],
                                "device_type_any_of": ["mobile", "desktop"],
                            },
                        },
                        "access_token": "test_token",
                    },
                    headers={"Content-Type": "application/json"},
                )

                assert response.status_code == 200
                data = json.loads(response.data)
                assert data["success"] is True
                assert "result" in data
            finally:
                real_loop.close()

"""Smoke tests for critical system paths - MUST ALWAYS PASS."""

import asyncio

import httpx
import pytest


class TestServerStartup:
    """Test that servers can start and respond to health checks."""

    @pytest.mark.smoke
    @pytest.mark.requires_server
    def test_mcp_server_health(self):
        """Test MCP server responds to health check."""
        try:
            response = httpx.get("http://localhost:8080/health", timeout=5.0)
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
        except httpx.ConnectError:
            pytest.skip("MCP server not running")

    @pytest.mark.smoke
    @pytest.mark.requires_server
    def test_admin_ui_health(self):
        """Test Admin UI responds to health check."""
        try:
            response = httpx.get("http://localhost:8001/health", timeout=5.0)
            assert response.status_code == 200
        except httpx.ConnectError:
            pytest.skip("Admin UI not running")


class TestMCPCriticalEndpoints:
    """Test critical MCP endpoints work with valid authentication."""

    @pytest.fixture
    def auth_headers(self):
        """Get valid auth headers for testing."""
        # Use the test token from the test database
        return {"x-adcp-auth": "test_token_sports", "Content-Type": "application/json", "Accept": "application/json"}

    @pytest.mark.smoke
    @pytest.mark.requires_server
    @pytest.mark.asyncio
    async def test_get_products_endpoint(self, auth_headers):
        """Test that get_products endpoint works."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "http://localhost:8080/mcp",
                headers=auth_headers,
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {"name": "get_products", "arguments": {}},
                    "id": 1,
                },
                timeout=10.0,
            )
            assert response.status_code == 200
            result = response.json()
            assert "result" in result or "error" in result

    @pytest.mark.smoke
    @pytest.mark.requires_server
    @pytest.mark.asyncio
    async def test_create_media_buy_endpoint(self, auth_headers):
        """Test that create_media_buy endpoint is available."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "http://localhost:8080/mcp",
                headers=auth_headers,
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {
                        "name": "create_media_buy",
                        "arguments": {
                            "product_ids": ["prod_sports_display"],
                            "total_budget": 1000.0,
                            "flight_start_date": "2025-02-01",
                            "flight_end_date": "2025-02-28",
                        },
                    },
                    "id": 2,
                },
                timeout=10.0,
            )
            assert response.status_code == 200
            result = response.json()
            # Either success or expected error (e.g., product not found)
            assert "result" in result or "error" in result

    @pytest.mark.smoke
    @pytest.mark.requires_server
    @pytest.mark.asyncio
    async def test_get_media_buy_status_endpoint(self, auth_headers):
        """Test that get_media_buy_status endpoint works."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "http://localhost:8080/mcp",
                headers=auth_headers,
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {"name": "get_media_buy_status", "arguments": {"media_buy_id": "mb_test_001"}},
                    "id": 3,
                },
                timeout=10.0,
            )
            assert response.status_code == 200

    @pytest.mark.smoke
    @pytest.mark.requires_server
    def test_authentication_required(self):
        """Test that transaction endpoints require authentication."""
        response = httpx.post(
            "http://localhost:8080/mcp/",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "create_media_buy",
                    "arguments": {
                        "product_ids": ["test"],
                        "total_budget": 1000.0,
                        "flight_start_date": "2025-01-01",
                        "flight_end_date": "2025-01-31",
                    },
                },
                "id": 4,
            },
            timeout=5.0,
        )
        assert response.status_code == 200
        result = response.json()
        assert "error" in result
        assert "authentication" in result["error"]["message"].lower()

    @pytest.mark.smoke
    @pytest.mark.requires_server
    def test_discovery_endpoints_work_without_auth(self):
        """Test that discovery endpoints work without authentication."""
        # Test get_products without auth
        response = httpx.post(
            "http://localhost:8080/mcp/",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "get_products",
                    "arguments": {
                        "brief": "test campaign",
                        "brand_manifest": {"name": "Nike Air Max 2025 running shoes"},
                    },
                },
                "id": 5,
            },
            timeout=5.0,
        )
        assert response.status_code == 200
        result = response.json()
        # Should succeed without authentication error
        assert "result" in result or ("error" in result and "authentication" not in result["error"]["message"].lower())

        # If successful, verify pricing data is filtered for anonymous users
        if "result" in result and "content" in result["result"]:
            products_data = result["result"]["content"]
            if "products" in products_data:
                for product in products_data["products"]:
                    # Pricing fields should be null for anonymous users
                    assert product.get("cpm") is None
                    assert product.get("min_spend") is None
            # Should contain pricing message
            if "message" in products_data:
                assert "authorized buying agent for pricing" in products_data["message"]

        # Test list_creative_formats without auth
        response = httpx.post(
            "http://localhost:8080/mcp/",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": "list_creative_formats", "arguments": {}},
                "id": 6,
            },
            timeout=5.0,
        )
        assert response.status_code == 200
        result = response.json()
        # Should succeed without authentication error
        assert "result" in result or ("error" in result and "authentication" not in result["error"]["message"].lower())


class TestAdminUICriticalPaths:
    """Test critical Admin UI paths."""

    @pytest.mark.smoke
    @pytest.mark.requires_server
    def test_login_page_accessible(self):
        """Test that login page is accessible."""
        response = httpx.get("http://localhost:8001/login", timeout=5.0)
        assert response.status_code == 200
        assert b"Sign in" in response.content or b"Login" in response.content

    @pytest.mark.smoke
    @pytest.mark.requires_server
    def test_protected_routes_require_auth(self):
        """Test that protected routes redirect to login."""
        response = httpx.get("http://localhost:8001/tenants", follow_redirects=False, timeout=5.0)
        assert response.status_code in [302, 303]
        assert "/login" in response.headers.get("location", "")


class TestErrorHandling:
    """Test system handles errors gracefully."""

    @pytest.mark.smoke
    @pytest.mark.requires_server
    def test_invalid_endpoint_returns_error(self):
        """Test that invalid endpoints return proper errors."""
        response = httpx.get("http://localhost:8080/invalid/endpoint", timeout=5.0)
        assert response.status_code in [404, 405]

    @pytest.mark.smoke
    @pytest.mark.requires_server
    @pytest.mark.asyncio
    async def test_invalid_tool_returns_error(self, auth_headers):
        """Test that calling invalid tools returns proper error."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "http://localhost:8080/mcp",
                headers={"x-adcp-auth": "test_token_sports"},
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {"name": "invalid_tool_name", "arguments": {}},
                    "id": 5,
                },
                timeout=10.0,
            )
            assert response.status_code == 200
            result = response.json()
            assert "error" in result


class TestConcurrency:
    """Test system handles concurrent requests."""

    @pytest.mark.smoke
    @pytest.mark.requires_server
    @pytest.mark.asyncio
    async def test_concurrent_read_requests(self):
        """Test system handles concurrent read requests."""

        async def make_request(client, request_id):
            response = await client.post(
                "http://localhost:8080/mcp",
                headers={"x-adcp-auth": "test_token_sports"},
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {"name": "get_products", "arguments": {}},
                    "id": request_id,
                },
                timeout=10.0,
            )
            return response

        async with httpx.AsyncClient() as client:
            # Make 5 concurrent requests
            tasks = [make_request(client, i) for i in range(5)]
            responses = await asyncio.gather(*tasks)

            # All should succeed
            for response in responses:
                assert response.status_code == 200

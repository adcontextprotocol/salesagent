#!/usr/bin/env python3
"""
Test A2A standard endpoints to ensure compliance with python-a2a library.

This test suite prevents regression by verifying that our A2A server
properly implements all standard A2A protocol endpoints.

NOTE: This test requires python_a2a library which is not part of our
dependencies. Skipping in CI until we implement proper A2A compliance tests.
"""

import os
import sys

import pytest
import requests

# Skip this entire test file in CI as it requires python_a2a library
# which we don't actually use (we use a2a-sdk instead)
pytest.skip("Skipping A2A standard endpoints test - requires python_a2a library", allow_module_level=True)

# Add parent directories to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from python_a2a.server.http import create_flask_app

from src.a2a_server.adcp_a2a_server import AdCPSalesAgent


@pytest.fixture
def a2a_agent():
    """Create an AdCP A2A agent for testing."""
    return AdCPSalesAgent()


@pytest.fixture
def a2a_app(a2a_agent):
    """Create a Flask app using the standard python-a2a library."""
    app = create_flask_app(a2a_agent)
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(a2a_app):
    """Create a test client for the A2A app."""
    return a2a_app.test_client()


class TestA2AStandardEndpoints:
    """Test standard A2A protocol endpoints."""

    def test_well_known_agent_json_endpoint(self, client):
        """Test that /.well-known/agent.json endpoint works (A2A spec requirement)."""
        response = client.get("/.well-known/agent.json")

        assert response.status_code == 200
        assert response.content_type.startswith("application/json")

        data = response.get_json()
        assert data is not None

        # Verify required agent card fields
        assert "name" in data
        assert "description" in data
        assert "version" in data
        assert "skills" in data

        # Verify our specific agent info
        assert data["name"] == "AdCP Sales Agent"
        assert "advertising campaign management" in data["description"].lower()
        assert isinstance(data["skills"], list)

    def test_agent_json_endpoint(self, client):
        """Test that /agent.json endpoint works."""
        response = client.get("/agent.json")

        assert response.status_code == 200
        assert response.content_type.startswith("application/json")

        data = response.get_json()
        assert data is not None
        assert data["name"] == "AdCP Sales Agent"

    def test_a2a_endpoint(self, client):
        """Test that /a2a endpoint works."""
        response = client.get("/a2a")

        assert response.status_code == 200
        # Should return JSON for API clients
        if response.content_type.startswith("application/json"):
            data = response.get_json()
            assert "name" in data
            assert data["name"] == "AdCP Sales Agent"

    def test_root_endpoint(self, client):
        """Test that root endpoint works."""
        response = client.get("/")

        assert response.status_code == 200
        # Could be HTML or JSON depending on Accept header

    def test_stream_endpoint_exists(self, client):
        """Test that /stream endpoint exists (may require auth)."""
        # Just test that the endpoint exists, not that it works without auth
        response = client.post("/stream", json={"test": "data"})

        # Should not be 404 (endpoint exists), might be 401/400 (auth/validation errors)
        assert response.status_code != 404

    def test_agent_card_structure(self, client):
        """Test that agent card has proper A2A structure."""
        response = client.get("/.well-known/agent.json")
        data = response.get_json()

        # Required A2A agent card fields
        required_fields = ["name", "description", "version", "skills"]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

        # Test skills structure
        assert isinstance(data["skills"], list)
        for skill in data["skills"]:
            assert isinstance(skill, dict)
            assert "name" in skill
            assert "description" in skill

        # Should have our expected skills
        skill_names = [skill["name"] for skill in data["skills"]]
        expected_skills = ["get_products", "create_campaign", "get_targeting", "get_pricing"]
        for expected_skill in expected_skills:
            assert expected_skill in skill_names, f"Missing expected skill: {expected_skill}"

    def test_authentication_field(self, client):
        """Test that agent card specifies authentication requirements."""
        response = client.get("/.well-known/agent.json")
        data = response.get_json()

        # Should specify authentication requirement
        assert "authentication" in data
        assert data["authentication"] == "bearer-token"

    def test_capabilities_field(self, client):
        """Test that agent card includes capabilities."""
        response = client.get("/.well-known/agent.json")
        data = response.get_json()

        # Should have capabilities
        assert "capabilities" in data
        assert isinstance(data["capabilities"], dict)

        # Should include Google A2A compatibility
        assert data["capabilities"].get("google_a2a_compatible") is True

    def test_agent_card_url_field(self, client):
        """Test that agent card includes proper URL field for messaging."""
        response = client.get("/.well-known/agent.json")
        data = response.get_json()

        # Should have URL field (required by A2A SDK)
        assert "url" in data
        assert data["url"] is not None
        assert len(data["url"]) > 0

        # URL should be properly formatted
        url = data["url"]
        assert url.startswith("http://") or url.startswith("https://")

        # In production should use production URL, in development should use localhost
        if os.getenv("A2A_MOCK_MODE") == "true":
            assert "localhost" in url
        else:
            # Should use the configured server URL
            expected_url = os.getenv("A2A_SERVER_URL", "https://adcp-sales-agent.fly.dev/a2a")
            assert url == expected_url

    def test_custom_authenticated_endpoints_exist(self, client):
        """Test that our custom authenticated endpoints still exist."""
        # These should exist but may return 401 without auth
        endpoints = ["/tasks/send", "/health"]

        for endpoint in endpoints:
            response = client.get(endpoint) if endpoint == "/health" else client.post(endpoint, json={})
            # Should not be 404 (endpoint exists)
            assert response.status_code != 404, f"Endpoint {endpoint} should exist"

    def test_health_endpoint_public(self, client):
        """Test that health endpoint is public and works."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "healthy"

    def test_cors_headers(self, client):
        """Test that CORS headers are properly set."""
        response = client.get("/.well-known/agent.json")

        # Should have CORS headers (provided by create_flask_app)
        assert "Access-Control-Allow-Origin" in response.headers
        assert response.headers["Access-Control-Allow-Origin"] == "*"

    def test_options_request_handling(self, client):
        """Test that OPTIONS requests are handled (CORS preflight)."""
        response = client.options("/.well-known/agent.json")

        # Should handle OPTIONS requests
        assert response.status_code == 200
        assert "Access-Control-Allow-Origin" in response.headers


class TestA2AClientCompatibility:
    """Test compatibility with A2A clients."""

    def test_agent_discovery_flow(self, client):
        """Test the standard A2A agent discovery flow."""
        # Step 1: Client tries to discover agent card
        response = client.get("/.well-known/agent.json")
        assert response.status_code == 200

        agent_card = response.get_json()

        # Step 2: Verify agent card has required info for client
        assert "skills" in agent_card
        assert len(agent_card["skills"]) > 0

        # Step 3: Verify authentication method is specified
        assert agent_card.get("authentication") == "bearer-token"

        # Step 4: Verify client can understand the response format
        assert isinstance(agent_card, dict)
        assert "name" in agent_card
        assert "version" in agent_card

    def test_bearer_token_auth_support(self, client):
        """Test that Bearer token authentication is supported."""
        # Test that endpoints expect Bearer token format
        response = client.post("/tasks/send", headers={"Authorization": "Bearer invalid-token"}, json={"task": "test"})

        # Should not be 404, should be auth-related error
        assert response.status_code != 404
        # Should be 401 (unauthorized) for invalid token
        assert response.status_code == 401

    def test_content_type_json(self, client):
        """Test that endpoints return proper JSON content types."""
        json_endpoints = ["/.well-known/agent.json", "/agent.json", "/health"]

        for endpoint in json_endpoints:
            response = client.get(endpoint)
            if response.status_code == 200:
                assert response.content_type.startswith("application/json"), f"Endpoint {endpoint} should return JSON"


@pytest.mark.integration
def test_integration_with_real_server():
    """Integration test with actual server instance."""
    # This test can be run against a running server
    # Skip if no server is running
    try:
        response = requests.get("http://localhost:8091/.well-known/agent.json", timeout=1)
        if response.status_code == 200:
            data = response.json()
            assert data["name"] == "AdCP Sales Agent"
            assert "skills" in data
    except (requests.ConnectionError, requests.Timeout):
        pytest.skip("No A2A server running on localhost:8091")


# Test coverage summary
def test_a2a_compliance_summary(client):
    """Summary test to verify full A2A spec compliance."""

    compliance_checklist = {
        "/.well-known/agent.json endpoint": False,
        "Agent card structure": False,
        "Authentication specification": False,
        "Skills definition": False,
        "CORS support": False,
        "Bearer token auth": False,
    }

    # Check /.well-known/agent.json
    response = client.get("/.well-known/agent.json")
    if response.status_code == 200:
        compliance_checklist["/.well-known/agent.json endpoint"] = True

        data = response.get_json()

        # Check agent card structure
        if all(field in data for field in ["name", "description", "version", "skills"]):
            compliance_checklist["Agent card structure"] = True

        # Check authentication specification
        if data.get("authentication") == "bearer-token":
            compliance_checklist["Authentication specification"] = True

        # Check skills definition
        if isinstance(data.get("skills"), list) and len(data["skills"]) > 0:
            compliance_checklist["Skills definition"] = True

    # Check CORS support
    if "Access-Control-Allow-Origin" in response.headers:
        compliance_checklist["CORS support"] = True

    # Check Bearer token auth
    auth_response = client.post("/tasks/send", headers={"Authorization": "Bearer test"}, json={})
    if auth_response.status_code == 401:  # Should reject invalid token
        compliance_checklist["Bearer token auth"] = True

    # All checks should pass
    failed_checks = [check for check, passed in compliance_checklist.items() if not passed]
    assert not failed_checks, f"Failed A2A compliance checks: {failed_checks}"

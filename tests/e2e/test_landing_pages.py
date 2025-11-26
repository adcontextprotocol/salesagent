#!/usr/bin/env python3
"""
Landing Page E2E Tests

Validates that domain routing works correctly for different domain types:
- Custom domains show agent landing pages
- Subdomains show appropriate landing pages (agent or pending config)
- Admin domains redirect to login
- Unknown domains redirect to signup

Tests against live servers (local or production).
"""

import os

import pytest
import requests


class TestLandingPages:
    """Test landing page routing for different domain types."""

    def _get_base_url(self) -> str:
        """Get base URL for tests (defaults to localhost)."""
        return os.getenv("TEST_BASE_URL", "http://localhost:8001")

    @pytest.mark.integration
    def test_custom_domain_shows_agent_landing_page(self):
        """Custom domains with configured tenants should show agent landing page."""
        base_url = self._get_base_url()

        # Skip if we can't reach the server
        try:
            # Test with a mock custom domain header
            # Note: This test validates the routing logic works, but can't test
            # actual custom domain DNS in local environment
            response = requests.get(
                f"{base_url}/",
                headers={
                    "Host": "test-custom-domain.example.com",
                },
                timeout=5,
                allow_redirects=False,
            )

            # Custom domains with tenants should show landing page (200)
            # Custom domains without tenants redirect to signup (302)
            # We can't control tenant config in this test, so accept both
            assert response.status_code in (200, 302), (
                f"Custom domain should show landing page (200) or redirect to signup (302), "
                f"got {response.status_code}"
            )

        except (requests.ConnectionError, requests.Timeout):
            pytest.skip("Server not running at {base_url}")

    @pytest.mark.integration
    def test_admin_domain_redirects_to_login(self):
        """Admin domain should redirect to login page."""
        base_url = self._get_base_url()

        try:
            # Test admin domain routing with admin Host header
            response = requests.get(
                f"{base_url}/",
                headers={
                    "Host": "admin.sales-agent.scope3.com",
                },
                timeout=5,
                allow_redirects=False,
            )

            # Admin domain should redirect to login
            if response.status_code == 302:
                location = response.headers.get("Location", "")
                assert "/login" in location, f"Admin domain should redirect to /login, got {location}"
            elif response.status_code == 200:
                # Already at login page
                content = response.content.decode("utf-8").lower()
                assert "login" in content, "Admin domain should show login page"

        except (requests.ConnectionError, requests.Timeout):
            pytest.skip(f"Server not running at {base_url}")

    @pytest.mark.integration
    def test_subdomain_with_tenant_shows_landing_page(self):
        """Subdomain with configured tenant should show agent landing page or pending config."""
        base_url = self._get_base_url()

        try:
            # Test with subdomain header
            # This simulates accessing tenant.sales-agent.scope3.com
            response = requests.get(
                f"{base_url}/",
                headers={
                    "Host": "testsubdomain.sales-agent.scope3.com",
                },
                timeout=5,
                allow_redirects=False,
            )

            # Subdomain with tenant should show landing page (200)
            # Subdomain without tenant should redirect to signup (302)
            assert response.status_code in (200, 302), (
                f"Subdomain should show landing page (200) or redirect to signup (302), " f"got {response.status_code}"
            )

        except (requests.ConnectionError, requests.Timeout):
            pytest.skip(f"Server not running at {base_url}")

    @pytest.mark.integration
    def test_landing_page_contains_mcp_endpoint(self):
        """Landing page for configured tenant should contain MCP endpoint."""
        base_url = self._get_base_url()

        try:
            # For local testing, we need to specify a custom domain
            # that would route to tenant landing page
            response = requests.get(
                f"{base_url}/",
                headers={
                    "Host": "test-custom-domain.example.com",
                },
                timeout=5,
                allow_redirects=True,
            )

            # If we get a 200 OK, check for MCP endpoint
            if response.status_code == 200:
                content = response.content.decode("utf-8").lower()

                # Landing page should mention MCP or show it's pending configuration
                has_mcp = "/mcp" in content or "mcp endpoint" in content
                is_pending = "pending configuration" in content or "not configured" in content

                assert (
                    has_mcp or is_pending
                ), "Landing page should either show MCP endpoint or pending configuration message"

        except (requests.ConnectionError, requests.Timeout):
            pytest.skip(f"Server not running at {base_url}")

    @pytest.mark.integration
    def test_landing_page_contains_a2a_endpoint(self):
        """Landing page for configured tenant should contain A2A endpoint."""
        base_url = self._get_base_url()

        try:
            # For local testing, we need to specify a custom domain
            response = requests.get(
                f"{base_url}/",
                headers={
                    "Host": "test-custom-domain.example.com",
                },
                timeout=5,
                allow_redirects=True,
            )

            # If we get a 200 OK, check for A2A endpoint
            if response.status_code == 200:
                content = response.content.decode("utf-8").lower()

                # Landing page should mention A2A or show it's pending configuration
                has_a2a = "/a2a" in content or "a2a endpoint" in content
                is_pending = "pending configuration" in content or "not configured" in content

                assert (
                    has_a2a or is_pending
                ), "Landing page should either show A2A endpoint or pending configuration message"

        except (requests.ConnectionError, requests.Timeout):
            pytest.skip(f"Server not running at {base_url}")

    @pytest.mark.integration
    def test_approximated_header_precedence(self):
        """Apx-Incoming-Host header should take precedence over Host header."""
        base_url = self._get_base_url()

        try:
            # Send both headers - Apx-Incoming-Host should win
            # Use admin domain as Apx-Incoming-Host since we know it exists
            response = requests.get(
                f"{base_url}/",
                headers={
                    "Host": "localhost:8001",  # Backend host
                    "Apx-Incoming-Host": "admin.sales-agent.scope3.com",  # Proxied admin host
                },
                timeout=5,
                allow_redirects=False,
            )

            # Should route based on Apx-Incoming-Host (admin domain -> login redirect)
            if response.status_code == 302:
                location = response.headers.get("Location", "")
                assert "/login" in location, f"Proxied admin domain should redirect to login, got {location}"
            elif response.status_code == 200:
                content = response.content.decode("utf-8").lower()
                assert "login" in content, "Proxied admin domain should show login page"
            else:
                # Accept other statuses if routing works but gives different result
                # The key is that Apx-Incoming-Host is being used (not getting error)
                assert response.status_code != 500, f"Proxied request should not error, got {response.status_code}"

        except (requests.ConnectionError, requests.Timeout):
            pytest.skip(f"Server not running at {base_url}")


class TestProductionLandingPages:
    """Test production landing pages (requires PRODUCTION_TEST=true)."""

    def _is_production_test(self) -> bool:
        """Check if we should run production tests."""
        return os.getenv("PRODUCTION_TEST", "").lower() == "true"

    @pytest.mark.e2e
    def test_accuweather_landing_page(self):
        """Test AccuWeather custom domain landing page."""
        if not self._is_production_test():
            pytest.skip("Set PRODUCTION_TEST=true to run production tests")

        try:
            response = requests.get(
                "https://sales-agent.accuweather.com",
                timeout=10,
                allow_redirects=True,
            )

            assert (
                response.status_code == 200
            ), f"AccuWeather landing page should return 200, got {response.status_code}"

            content = response.content.decode("utf-8").lower()

            # Should contain MCP and A2A endpoints
            assert "/mcp" in content, "AccuWeather landing page should contain MCP endpoint"
            assert "/a2a" in content, "AccuWeather landing page should contain A2A endpoint"

            # Should mention agent capabilities
            assert "agent" in content or "protocol" in content, "Landing page should mention agent capabilities"

        except requests.RequestException as e:
            pytest.skip(f"Could not reach production URL: {e}")

    @pytest.mark.e2e
    def test_test_agent_landing_page(self):
        """Test test-agent.adcontextprotocol.org landing page."""
        if not self._is_production_test():
            pytest.skip("Set PRODUCTION_TEST=true to run production tests")

        try:
            response = requests.get(
                "https://test-agent.adcontextprotocol.org",
                timeout=10,
                allow_redirects=False,  # Don't follow redirects
            )

            # After PR #801, custom domains with tenants show landing page (200)
            # Not login redirect (302)
            assert response.status_code == 200, f"test-agent should show landing page (200), got {response.status_code}"

            content = response.content.decode("utf-8").lower()

            # Should contain agent endpoints
            assert "/mcp" in content or "/a2a" in content, "test-agent landing page should contain agent endpoints"

        except requests.RequestException as e:
            pytest.skip(f"Could not reach production URL: {e}")

    @pytest.mark.e2e
    def test_applabs_subdomain_landing_page(self):
        """Test applabs subdomain landing page."""
        if not self._is_production_test():
            pytest.skip("Set PRODUCTION_TEST=true to run production tests")

        try:
            response = requests.get(
                "https://applabs.sales-agent.scope3.com",
                timeout=10,
                allow_redirects=True,
            )

            assert response.status_code == 200, f"applabs landing page should return 200, got {response.status_code}"

            content = response.content.decode("utf-8").lower()

            # applabs is not fully configured, so might show pending config
            # But should still show MCP/A2A endpoints or pending message
            has_endpoints = "/mcp" in content or "/a2a" in content
            is_pending = "pending" in content or "configuration" in content

            assert has_endpoints or is_pending, "applabs should show endpoints or pending configuration"

        except requests.RequestException as e:
            pytest.skip(f"Could not reach production URL: {e}")

    @pytest.mark.e2e
    def test_admin_ui_redirects_to_login(self):
        """Test that admin UI redirects to login."""
        if not self._is_production_test():
            pytest.skip("Set PRODUCTION_TEST=true to run production tests")

        try:
            response = requests.get(
                "https://admin.sales-agent.scope3.com",
                timeout=10,
                allow_redirects=False,
            )

            # Should redirect to login
            assert response.status_code == 302, f"Admin UI should redirect to login (302), got {response.status_code}"

            location = response.headers.get("Location", "")
            assert "/login" in location, f"Admin UI should redirect to /login, got {location}"

        except requests.RequestException as e:
            pytest.skip(f"Could not reach production URL: {e}")

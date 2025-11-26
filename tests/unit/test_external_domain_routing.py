"""Test external domain routing via Approximated."""

from unittest.mock import Mock, patch

from src.admin.blueprints.core import get_tenant_from_hostname


class TestExternalDomainRouting:
    """Test that external domains (via Approximated) route to tenant home page instead of signup."""

    def test_get_tenant_from_hostname_with_approximated_header(self):
        """Test tenant lookup via Apx-Incoming-Host header."""
        from src.admin.app import create_app

        app, _ = create_app()

        with app.test_request_context(
            "/",
            headers={
                "Host": "backend.example.com",
                "Apx-Incoming-Host": "sales-agent.accuweather.com",
            },
        ):
            with patch("src.admin.blueprints.core.get_db_session") as mock_db:
                # Mock the database session
                mock_session = Mock()
                mock_db.return_value.__enter__.return_value = mock_session

                # Mock tenant object
                mock_tenant = Mock()
                mock_tenant.tenant_id = "accuweather"
                mock_tenant.name = "AccuWeather"
                mock_tenant.subdomain = "accuweather"
                mock_tenant.virtual_host = "sales-agent.accuweather.com"

                # Mock the database query
                mock_scalars = Mock()
                mock_scalars.first.return_value = mock_tenant
                mock_session.scalars.return_value = mock_scalars

                # Call the function
                result = get_tenant_from_hostname()

                # Verify tenant was returned
                assert result is not None
                assert result.tenant_id == "accuweather"
                assert result.virtual_host == "sales-agent.accuweather.com"

    def test_get_tenant_from_hostname_no_tenant_configured(self):
        """Test that None is returned when no tenant is configured for external domain."""
        from src.admin.app import create_app

        app, _ = create_app()

        with app.test_request_context(
            "/",
            headers={
                "Host": "backend.example.com",
                "Apx-Incoming-Host": "unknown-domain.com",
            },
        ):
            with patch("src.admin.blueprints.core.get_db_session") as mock_db:
                # Mock the database session
                mock_session = Mock()
                mock_db.return_value.__enter__.return_value = mock_session

                # Mock the database query - no tenant found
                mock_scalars = Mock()
                mock_scalars.first.return_value = None
                mock_session.scalars.return_value = mock_scalars

                # Call the function
                result = get_tenant_from_hostname()

                # Verify None is returned
                assert result is None

    def test_index_route_external_domain_with_tenant(self):
        """Test that external domain with configured tenant shows agent landing page."""
        from src.admin.app import create_app

        app, _ = create_app()

        with app.test_client() as client:
            with patch("src.admin.blueprints.core.get_tenant_from_hostname") as mock_get_tenant:
                # Mock tenant exists for this external domain
                mock_tenant = Mock()
                mock_tenant.tenant_id = "accuweather"
                mock_tenant.name = "AccuWeather"
                mock_tenant.subdomain = "accuweather"
                mock_tenant.virtual_host = "sales-agent.accuweather.com"
                mock_get_tenant.return_value = mock_tenant

                # Make request with Approximated headers
                response = client.get(
                    "/",
                    headers={
                        "Host": "backend.example.com",
                        "Apx-Incoming-Host": "sales-agent.accuweather.com",
                    },
                )

                # Should show agent landing page (200) with MCP/A2A links
                assert response.status_code == 200
                assert b"AccuWeather" in response.data  # Tenant name should be in landing page
                # Landing page should contain agent protocol information
                assert b"MCP" in response.data or b"mcp" in response.data.lower()

    def test_index_route_external_domain_no_tenant(self):
        """Test that external domain without configured tenant shows signup landing page."""
        from src.admin.app import create_app

        app, _ = create_app()

        with app.test_client() as client:
            with patch("src.admin.blueprints.core.get_tenant_from_hostname") as mock_get_tenant:
                # Mock no tenant exists for this external domain
                mock_get_tenant.return_value = None

                # Make request with Approximated headers
                response = client.get(
                    "/",
                    headers={
                        "Host": "backend.example.com",
                        "Apx-Incoming-Host": "unknown-domain.com",
                    },
                )

                # Should show landing page (200) since no tenant configured
                assert response.status_code == 200
                assert b"landing" in response.data.lower() or b"signup" in response.data.lower()

    def test_index_route_subdomain_with_tenant(self):
        """Test that subdomain (*.sales-agent.scope3.com) with tenant redirects to login."""
        from src.admin.app import create_app

        app, _ = create_app()

        with app.test_client() as client:
            with patch("src.admin.blueprints.core.get_tenant_from_hostname") as mock_get_tenant:
                # Mock tenant exists for this subdomain
                mock_tenant = Mock()
                mock_tenant.tenant_id = "accuweather"
                mock_tenant.name = "AccuWeather"
                mock_tenant.subdomain = "accuweather"
                mock_get_tenant.return_value = mock_tenant

                # Make request with subdomain
                response = client.get(
                    "/",
                    headers={
                        "Host": "accuweather.sales-agent.scope3.com",
                    },
                )

                # Should redirect to login (302) since tenant exists
                assert response.status_code == 302
                assert "/login" in response.location

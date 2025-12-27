"""Test centralized domain routing logic."""

from unittest.mock import patch

from src.core.domain_routing import RoutingResult, route_landing_page


class TestRouteLandingPage:
    """Test the centralized route_landing_page function."""

    def test_admin_domain_routing(self):
        """Admin domains should route to type=admin."""
        # Mock is_admin_domain to return True for our test domain
        with patch("src.core.domain_routing.is_admin_domain") as mock_is_admin:
            mock_is_admin.return_value = True
            headers = {"Host": "admin.sales-agent.example.com"}
            result = route_landing_page(headers)

            assert result.type == "admin"
            assert result.tenant is None
            assert result.effective_host == "admin.sales-agent.example.com"
            mock_is_admin.assert_called_once_with("admin.sales-agent.example.com")

    def test_admin_domain_with_approximated_header(self):
        """Admin domains via Approximated should route to type=admin."""
        from unittest.mock import patch

        with patch("src.core.domain_routing.is_admin_domain") as mock_is_admin:
            mock_is_admin.return_value = True
            headers = {"Host": "backend.internal.com", "Apx-Incoming-Host": "admin.sales-agent.example.com"}
            result = route_landing_page(headers)

            assert result.type == "admin"
            assert result.tenant is None
            assert result.effective_host == "admin.sales-agent.example.com"

    def test_admin_domain_spoofing_prevented(self):
        """Malicious domains starting with 'admin.' should NOT route to admin."""
        from unittest.mock import patch

        # is_admin_domain will return False for non-matching domains
        with patch("src.core.domain_routing.is_admin_domain") as mock_is_admin:
            with patch("src.core.domain_routing.get_tenant_by_virtual_host") as mock_get_tenant:
                mock_is_admin.return_value = False  # Not a valid admin domain
                mock_get_tenant.return_value = None

                # Try to spoof with admin.malicious.com
                headers = {"Host": "admin.malicious.com"}
                result = route_landing_page(headers)

                # Should be treated as custom domain, NOT admin
                assert result.type == "custom_domain"
                assert result.tenant is None
                assert result.effective_host == "admin.malicious.com"
                mock_is_admin.assert_called_once_with("admin.malicious.com")

    @patch("src.core.domain_routing.get_tenant_by_virtual_host")
    @patch("src.core.domain_routing.is_admin_domain", return_value=False)
    @patch("src.core.domain_routing.is_sales_agent_domain", return_value=False)
    def test_custom_domain_with_tenant(self, mock_is_sales, mock_is_admin, mock_get_tenant):
        """Custom domains with tenant should route to type=custom_domain."""
        mock_get_tenant.return_value = {
            "tenant_id": "publisher",
            "name": "Publisher Inc",
            "subdomain": "publisher",
            "virtual_host": "sales-agent.publisher.com",
        }

        headers = {"Host": "sales-agent.publisher.com"}
        result = route_landing_page(headers)

        assert result.type == "custom_domain"
        assert result.tenant is not None
        assert result.tenant["tenant_id"] == "publisher"
        assert result.effective_host == "sales-agent.publisher.com"
        mock_get_tenant.assert_called_once_with("sales-agent.publisher.com")

    @patch("src.core.domain_routing.get_tenant_by_virtual_host")
    @patch("src.core.domain_routing.is_admin_domain", return_value=False)
    @patch("src.core.domain_routing.is_sales_agent_domain", return_value=False)
    def test_custom_domain_without_tenant(self, mock_is_sales, mock_is_admin, mock_get_tenant):
        """Custom domains without tenant should route to type=custom_domain with None tenant."""
        mock_get_tenant.return_value = None

        headers = {"Host": "unknown-domain.com"}
        result = route_landing_page(headers)

        assert result.type == "custom_domain"
        assert result.tenant is None
        assert result.effective_host == "unknown-domain.com"

    @patch("src.core.domain_routing.get_tenant_by_subdomain")
    @patch("src.core.domain_routing.extract_subdomain_from_host", return_value="mytenant")
    @patch("src.core.domain_routing.is_admin_domain", return_value=False)
    @patch("src.core.domain_routing.is_sales_agent_domain", return_value=True)
    def test_subdomain_with_tenant(self, mock_is_sales, mock_is_admin, mock_extract, mock_get_tenant):
        """Sales-agent subdomains with tenant should route to type=subdomain."""
        mock_get_tenant.return_value = {
            "tenant_id": "mytenant",
            "name": "My Tenant",
            "subdomain": "mytenant",
            "virtual_host": None,
        }

        headers = {"Host": "mytenant.sales-agent.example.com"}
        result = route_landing_page(headers)

        assert result.type == "subdomain"
        assert result.tenant is not None
        assert result.tenant["tenant_id"] == "mytenant"
        assert result.effective_host == "mytenant.sales-agent.example.com"

    @patch("src.core.domain_routing.get_tenant_by_subdomain")
    @patch("src.core.domain_routing.extract_subdomain_from_host", return_value="nonexistent")
    @patch("src.core.domain_routing.is_admin_domain", return_value=False)
    @patch("src.core.domain_routing.is_sales_agent_domain", return_value=True)
    def test_subdomain_without_tenant(self, mock_is_sales, mock_is_admin, mock_extract, mock_get_tenant):
        """Sales-agent subdomains without tenant should route to type=subdomain with None tenant."""
        mock_get_tenant.return_value = None

        headers = {"Host": "nonexistent.sales-agent.example.com"}
        result = route_landing_page(headers)

        assert result.type == "subdomain"
        assert result.tenant is None
        assert result.effective_host == "nonexistent.sales-agent.example.com"

    def test_no_host_header(self):
        """Missing host header should route to type=unknown."""
        headers = {}
        result = route_landing_page(headers)

        assert result.type == "unknown"
        assert result.tenant is None
        assert result.effective_host == ""

    @patch("src.core.domain_routing.get_tenant_by_virtual_host")
    @patch("src.core.domain_routing.is_admin_domain", return_value=False)
    @patch("src.core.domain_routing.is_sales_agent_domain", return_value=False)
    def test_approximated_header_takes_precedence(self, mock_is_sales, mock_is_admin, mock_get_tenant):
        """Apx-Incoming-Host should take precedence over Host header."""
        mock_get_tenant.return_value = {"tenant_id": "publisher", "name": "Publisher Inc"}

        headers = {"Host": "backend.internal.com", "Apx-Incoming-Host": "sales-agent.publisher.com"}
        result = route_landing_page(headers)

        assert result.effective_host == "sales-agent.publisher.com"
        mock_get_tenant.assert_called_once_with("sales-agent.publisher.com")

    @patch("src.core.domain_routing.is_admin_domain", return_value=True)
    def test_case_insensitive_headers(self, mock_is_admin):
        """Headers should work with different cases."""
        # Test lowercase apx-incoming-host
        headers = {"host": "backend.internal.com", "apx-incoming-host": "admin.sales-agent.example.com"}
        result = route_landing_page(headers)
        assert result.type == "admin"

        # Test uppercase Apx-Incoming-Host
        headers = {"Host": "backend.internal.com", "Apx-Incoming-Host": "admin.sales-agent.example.com"}
        result = route_landing_page(headers)
        assert result.type == "admin"


class TestRoutingResultDataclass:
    """Test the RoutingResult dataclass."""

    def test_routing_result_creation(self):
        """RoutingResult should be created with correct fields."""
        tenant = {"tenant_id": "test", "name": "Test"}
        result = RoutingResult("custom_domain", tenant, "test.example.com")

        assert result.type == "custom_domain"
        assert result.tenant == tenant
        assert result.effective_host == "test.example.com"

    def test_routing_result_none_tenant(self):
        """RoutingResult should allow None tenant."""
        result = RoutingResult("unknown", None, "")

        assert result.type == "unknown"
        assert result.tenant is None
        assert result.effective_host == ""


# Tenant lookup functions (get_tenant_by_virtual_host, get_tenant_by_subdomain)
# are imported from config_loader and tested there, so we don't duplicate those tests here.

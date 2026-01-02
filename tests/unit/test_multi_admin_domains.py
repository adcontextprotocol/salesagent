"""Test multi-admin domain configuration support."""

from unittest.mock import patch

from src.core.domain_config import get_admin_domains, is_admin_domain


class TestGetAdminDomains:
    """Test the get_admin_domains function."""

    def test_returns_empty_when_no_config(self):
        """Returns empty list when no admin domain is configured."""
        with patch.dict("os.environ", {}, clear=True):
            # Also need to clear SALES_AGENT_DOMAIN to prevent fallback
            result = get_admin_domains()
            assert result == []

    def test_returns_single_admin_domain(self):
        """Returns single admin domain from ADMIN_DOMAIN env var."""
        with patch.dict(
            "os.environ",
            {"ADMIN_DOMAIN": "admin.example.com"},
            clear=True,
        ):
            result = get_admin_domains()
            assert result == ["admin.example.com"]

    def test_returns_admin_domains_from_list(self):
        """Returns multiple admin domains from ADMIN_DOMAINS env var."""
        with patch.dict(
            "os.environ",
            {"ADMIN_DOMAINS": "admin1.example.com, admin2.example.com"},
            clear=True,
        ):
            result = get_admin_domains()
            assert "admin1.example.com" in result
            assert "admin2.example.com" in result

    def test_combines_admin_domains_and_admin_domain(self):
        """Combines ADMIN_DOMAINS and ADMIN_DOMAIN without duplicates."""
        with patch.dict(
            "os.environ",
            {
                "ADMIN_DOMAINS": "admin1.example.com, admin2.example.com",
                "ADMIN_DOMAIN": "admin3.example.com",
            },
            clear=True,
        ):
            result = get_admin_domains()
            assert "admin1.example.com" in result
            assert "admin2.example.com" in result
            assert "admin3.example.com" in result
            assert len(result) == 3

    def test_deduplicates_when_primary_in_list(self):
        """Deduplicates when ADMIN_DOMAIN is also in ADMIN_DOMAINS."""
        with patch.dict(
            "os.environ",
            {
                "ADMIN_DOMAINS": "admin1.example.com, admin.example.com",
                "ADMIN_DOMAIN": "admin.example.com",
            },
            clear=True,
        ):
            result = get_admin_domains()
            assert result.count("admin.example.com") == 1
            assert len(result) == 2

    def test_falls_back_to_sales_agent_domain(self):
        """Falls back to admin.{SALES_AGENT_DOMAIN} if no explicit config."""
        with patch.dict(
            "os.environ",
            {"SALES_AGENT_DOMAIN": "sales-agent.example.com"},
            clear=True,
        ):
            result = get_admin_domains()
            assert "admin.sales-agent.example.com" in result


class TestIsAdminDomain:
    """Test the is_admin_domain function with multiple admin domains."""

    def test_matches_primary_admin_domain(self):
        """Matches the primary admin domain."""
        with patch.dict(
            "os.environ",
            {"ADMIN_DOMAIN": "admin.example.com"},
            clear=True,
        ):
            assert is_admin_domain("admin.example.com") is True
            assert is_admin_domain("other.example.com") is False

    def test_matches_secondary_admin_domain(self):
        """Matches secondary admin domains from ADMIN_DOMAINS list."""
        with patch.dict(
            "os.environ",
            {
                "ADMIN_DOMAINS": "admin1.example.com, admin2.example.com",
                "ADMIN_DOMAIN": "admin.example.com",
            },
            clear=True,
        ):
            assert is_admin_domain("admin.example.com") is True
            assert is_admin_domain("admin1.example.com") is True
            assert is_admin_domain("admin2.example.com") is True
            assert is_admin_domain("other.example.com") is False

    def test_matches_admin_domain_with_port(self):
        """Matches admin domain when port is included."""
        with patch.dict(
            "os.environ",
            {"ADMIN_DOMAIN": "admin.example.com"},
            clear=True,
        ):
            assert is_admin_domain("admin.example.com:8080") is True
            assert is_admin_domain("other.example.com:8080") is False

    def test_returns_false_when_no_admin_domains_configured(self):
        """Returns False when no admin domains are configured."""
        with patch.dict("os.environ", {}, clear=True):
            assert is_admin_domain("anything.example.com") is False

    def test_exact_match_required(self):
        """Requires exact match, not substring match."""
        with patch.dict(
            "os.environ",
            {"ADMIN_DOMAIN": "admin.example.com"},
            clear=True,
        ):
            # Should not match subdomains or domains containing the admin domain
            assert is_admin_domain("sub.admin.example.com") is False
            assert is_admin_domain("admin.example.com.evil.com") is False


class TestMultiAdminDomainIntegration:
    """Integration tests for multi-admin domain support."""

    def test_scope3_admin_domain_scenario(self):
        """Test the specific Scope3 use case: sales-agent.scope3.com as secondary admin."""
        with patch.dict(
            "os.environ",
            {
                "SALES_AGENT_DOMAIN": "sales-agent.adcontextprotocol.org",
                "ADMIN_DOMAINS": "sales-agent.scope3.com",
            },
            clear=True,
        ):
            # Primary admin domain (derived from SALES_AGENT_DOMAIN)
            assert is_admin_domain("admin.sales-agent.adcontextprotocol.org") is True

            # Secondary admin domain (explicitly configured)
            assert is_admin_domain("sales-agent.scope3.com") is True

            # Tenant subdomains should not be admin domains
            assert is_admin_domain("tenant.sales-agent.adcontextprotocol.org") is False

            # Random domains should not be admin domains
            assert is_admin_domain("random.example.com") is False

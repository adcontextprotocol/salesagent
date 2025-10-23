"""Integration tests for SignalsDiscoveryProvider with reduced mocking.

Reduces excessive mocking while still providing comprehensive test coverage
for the signals discovery functionality by focusing on configuration,
initialization, and fallback behavior.
"""

import pytest

from product_catalog_providers.signals import SignalsDiscoveryProvider


class TestSignalsDiscoveryProviderIntegration:
    """Integration tests for SignalsDiscoveryProvider with minimal mocking."""

    def test_provider_configuration_patterns(self):
        """Test various configuration patterns without mocking internals."""
        # Test 1: Default configuration
        provider_default = SignalsDiscoveryProvider({})
        assert provider_default.tenant_id is None
        assert provider_default.fallback_to_database is True
        assert provider_default.max_signal_products == 10
        assert provider_default.registry is not None

        # Test 2: Complete configuration
        config_complete = {
            "tenant_id": "test_tenant",
            "fallback_to_database": False,
            "max_signal_products": 5,
        }

        provider_complete = SignalsDiscoveryProvider(config_complete)
        assert provider_complete.tenant_id == "test_tenant"
        assert provider_complete.fallback_to_database is False
        assert provider_complete.max_signal_products == 5
        assert provider_complete.registry is not None

        # Test 3: Partial configuration (real-world scenario)
        config_partial = {
            "tenant_id": "prod_tenant",
        }

        provider_partial = SignalsDiscoveryProvider(config_partial)
        assert provider_partial.tenant_id == "prod_tenant"
        # Should use defaults for unspecified values
        assert provider_partial.fallback_to_database is True
        assert provider_partial.max_signal_products == 10

    @pytest.mark.asyncio
    async def test_initialization_behavior_without_mocking(self):
        """Test initialization behavior is a no-op (registry handles connections)."""
        # Test 1: Default provider
        provider_default = SignalsDiscoveryProvider({})
        await provider_default.initialize()
        # Should complete without error - registry handles all connections

        # Test 2: Configured provider
        provider_configured = SignalsDiscoveryProvider({"tenant_id": "test_tenant"})
        await provider_configured.initialize()
        # Should complete without error - registry handles all connections

    def test_tenant_id_configuration(self):
        """Test tenant ID configuration patterns."""
        test_cases = [
            ("tenant_123", "tenant_123"),
            ("", ""),
            (None, None),
        ]

        for tenant_id_input, expected_tenant_id in test_cases:
            config = {"tenant_id": tenant_id_input} if tenant_id_input is not None else {}
            provider = SignalsDiscoveryProvider(config)
            assert provider.tenant_id == expected_tenant_id

    def test_max_signal_products_configuration(self):
        """Test max_signal_products configurations work correctly."""
        # Test boundary values
        test_configs = [
            {"max_signal_products": 1},
            {"max_signal_products": 100},
            {"max_signal_products": 0},  # Edge case
        ]

        for config in test_configs:
            provider = SignalsDiscoveryProvider(config)
            assert provider.max_signal_products == config["max_signal_products"]

    def test_fallback_behavior_configuration(self):
        """Test fallback behavior configuration."""
        # Test fallback_to_database configuration
        test_values = [True, False]

        for fallback_to_db in test_values:
            config = {"fallback_to_database": fallback_to_db}
            provider = SignalsDiscoveryProvider(config)
            assert provider.fallback_to_database == fallback_to_db

    @pytest.mark.asyncio
    async def test_client_lifecycle_management(self):
        """Test client lifecycle - no-op for registry-based architecture."""
        provider = SignalsDiscoveryProvider({"tenant_id": "test_tenant"})

        # Initialization is a no-op (registry handles connections)
        await provider.initialize()

        # Shutdown is also a no-op
        await provider.shutdown()

        # Registry should still be available
        assert provider.registry is not None

    def test_signals_provider_integration_readiness(self):
        """Test that provider is ready for integration with actual signals systems."""
        # Test realistic production-like configuration
        production_config = {
            "tenant_id": "production_tenant",
            "fallback_to_database": True,
            "max_signal_products": 20,
        }

        provider = SignalsDiscoveryProvider(production_config)

        # Verify all configuration is correctly applied
        assert provider.tenant_id == "production_tenant"
        assert provider.fallback_to_database is True
        assert provider.max_signal_products == 20
        assert provider.registry is not None

        # Verify the provider is in a valid state for initialization
        assert hasattr(provider, "initialize")
        assert hasattr(provider, "shutdown")
        assert hasattr(provider, "get_products")

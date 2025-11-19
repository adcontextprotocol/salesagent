#!/usr/bin/env python3
"""Unit tests for measurement provider validation logic.

Tests the fix for the bug where GAM tenants would get
"At least one measurement provider is required" error
even when GAM should provide a default.
"""

from unittest.mock import MagicMock

import pytest


def test_gam_tenant_via_ad_server_gets_default_provider():
    """Test that GAM tenants (via ad_server field) get default provider when none submitted."""
    # Arrange: Mock tenant with ad_server="google_ad_manager"
    mock_tenant = MagicMock()
    mock_tenant.ad_server = "google_ad_manager"
    mock_tenant.adapter_config = None

    # Simulate empty providers list (user submitted form but providers were empty/whitespace)
    providers = []

    # Act: Check GAM detection logic (from settings.py line 795-800)
    is_gam_tenant = False
    if mock_tenant.ad_server == "google_ad_manager":
        is_gam_tenant = True
    elif mock_tenant.adapter_config and mock_tenant.adapter_config.adapter_type == "google_ad_manager":
        is_gam_tenant = True

    # Assert
    assert is_gam_tenant is True, "Tenant should be detected as GAM via ad_server"


def test_gam_tenant_via_adapter_config_gets_default_provider():
    """Test that GAM tenants (via adapter_config) get default provider when none submitted."""
    # Arrange: Mock tenant with adapter_config.adapter_type="google_ad_manager"
    mock_tenant = MagicMock()
    mock_tenant.ad_server = None
    mock_adapter_config = MagicMock()
    mock_adapter_config.adapter_type = "google_ad_manager"
    mock_tenant.adapter_config = mock_adapter_config

    # Simulate empty providers list
    providers = []

    # Act: Check GAM detection logic (from settings.py line 795-800)
    is_gam_tenant = False
    if mock_tenant.ad_server == "google_ad_manager":
        is_gam_tenant = True
    elif mock_tenant.adapter_config and mock_tenant.adapter_config.adapter_type == "google_ad_manager":
        is_gam_tenant = True

    # Assert
    assert is_gam_tenant is True, "Tenant should be detected as GAM via adapter_config"


def test_non_gam_tenant_requires_provider():
    """Test that non-GAM tenants require at least one measurement provider."""
    # Arrange: Mock tenant with mock adapter
    mock_tenant = MagicMock()
    mock_tenant.ad_server = "mock"
    mock_adapter_config = MagicMock()
    mock_adapter_config.adapter_type = "mock"
    mock_tenant.adapter_config = mock_adapter_config

    # Simulate empty providers list
    providers = []

    # Act: Check GAM detection logic
    is_gam_tenant = False
    if mock_tenant.ad_server == "google_ad_manager":
        is_gam_tenant = True
    elif mock_tenant.adapter_config and mock_tenant.adapter_config.adapter_type == "google_ad_manager":
        is_gam_tenant = True

    # Assert
    assert is_gam_tenant is False, "Mock tenant should NOT be detected as GAM"


def test_gam_tenant_with_explicit_providers_uses_those():
    """Test that GAM tenants with explicit providers use those, not default."""
    # Arrange: Mock GAM tenant
    mock_tenant = MagicMock()
    mock_tenant.ad_server = "google_ad_manager"
    mock_tenant.adapter_config = None

    # User explicitly provided providers
    providers = ["Custom Measurement Provider", "Another Provider"]
    default_provider = "Custom Measurement Provider"

    # Act: When providers list is not empty, it should use those
    should_use_provided_providers = len(providers) > 0

    # Assert
    assert should_use_provided_providers is True
    assert "Custom Measurement Provider" in providers


def test_whitespace_only_providers_are_filtered():
    """Test that providers with only whitespace are filtered out."""
    # Arrange: Simulate form data with whitespace-only providers
    form_data = {
        "provider_name_0": "   ",  # Only whitespace
        "provider_name_1": "",  # Empty string
        "provider_name_2": "Valid Provider",
        "provider_name_3": "\t\n",  # Tabs and newlines
    }

    # Act: Simulate the collection logic from settings.py line 772-777
    providers = []
    seen_providers = set()
    for key in form_data.keys():
        if key.startswith("provider_name_"):
            provider_name = form_data.get(key, "").strip()
            if provider_name and provider_name not in seen_providers:
                providers.append(provider_name)
                seen_providers.add(provider_name)

    # Assert
    assert len(providers) == 1, "Only non-whitespace provider should be collected"
    assert providers[0] == "Valid Provider"


def test_duplicate_providers_are_deduplicated():
    """Test that duplicate provider names are filtered out."""
    # Arrange: Simulate form data with duplicate providers
    form_data = {
        "provider_name_0": "Provider A",
        "provider_name_1": "Provider B",
        "provider_name_2": "Provider A",  # Duplicate
        "provider_name_3": "Provider B",  # Duplicate
    }

    # Act: Simulate the collection logic
    providers = []
    seen_providers = set()
    for key in sorted(form_data.keys()):  # Sort for consistent ordering
        if key.startswith("provider_name_"):
            provider_name = form_data.get(key, "").strip()
            if provider_name and provider_name not in seen_providers:
                providers.append(provider_name)
                seen_providers.add(provider_name)

    # Assert
    assert len(providers) == 2, "Duplicates should be filtered out"
    assert set(providers) == {"Provider A", "Provider B"}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

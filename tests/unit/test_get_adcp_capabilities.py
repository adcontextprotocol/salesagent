"""Unit tests for get_adcp_capabilities tool.

Tests the capabilities endpoint that returns what this sales agent supports
per the AdCP spec.
"""

import pytest
from adcp.types import GetAdcpCapabilitiesResponse
from adcp.types.generated_poc.protocol.get_adcp_capabilities_response import (
    SupportedProtocol,
)


class TestGetAdcpCapabilitiesSchema:
    """Test GetAdcpCapabilitiesResponse schema validation."""

    def test_response_requires_adcp_field(self):
        """Test that response requires adcp field."""
        # Must have adcp and supported_protocols per spec
        with pytest.raises(ValueError):
            GetAdcpCapabilitiesResponse(supported_protocols=[SupportedProtocol.media_buy])

    def test_response_requires_supported_protocols(self):
        """Test that response requires supported_protocols field."""
        from adcp.types.generated_poc.protocol.get_adcp_capabilities_response import (
            Adcp,
            MajorVersion,
        )

        # Must have supported_protocols (non-empty list)
        with pytest.raises(ValueError):
            GetAdcpCapabilitiesResponse(
                adcp=Adcp(major_versions=[MajorVersion(root=3)]),
                supported_protocols=[],  # Empty not allowed
            )

    def test_valid_minimal_response(self):
        """Test creating a valid minimal response."""
        from adcp.types.generated_poc.protocol.get_adcp_capabilities_response import (
            Adcp,
            MajorVersion,
        )

        response = GetAdcpCapabilitiesResponse(
            adcp=Adcp(major_versions=[MajorVersion(root=3)]),
            supported_protocols=[SupportedProtocol.media_buy],
        )

        assert response.adcp is not None
        assert len(response.adcp.major_versions) == 1
        assert response.adcp.major_versions[0].root == 3
        assert SupportedProtocol.media_buy in response.supported_protocols

    def test_response_with_media_buy_capabilities(self):
        """Test creating response with media_buy capabilities."""
        from adcp.types.generated_poc.core.media_buy_features import MediaBuyFeatures
        from adcp.types.generated_poc.protocol.get_adcp_capabilities_response import (
            Adcp,
            Execution,
            MajorVersion,
            MediaBuy,
            Portfolio,
            PublisherDomain,
            Targeting,
        )

        response = GetAdcpCapabilitiesResponse(
            adcp=Adcp(major_versions=[MajorVersion(root=3)]),
            supported_protocols=[SupportedProtocol.media_buy],
            media_buy=MediaBuy(
                portfolio=Portfolio(
                    description="Test portfolio",
                    publisher_domains=[PublisherDomain(root="example.com")],
                ),
                features=MediaBuyFeatures(
                    content_standards=True,
                    inline_creative_management=True,
                    property_list_filtering=True,
                ),
                execution=Execution(
                    targeting=Targeting(
                        geo_countries=True,
                        geo_regions=True,
                    ),
                ),
            ),
        )

        assert response.media_buy is not None
        assert response.media_buy.portfolio is not None
        assert len(response.media_buy.portfolio.publisher_domains) == 1
        assert response.media_buy.features is not None
        assert response.media_buy.features.content_standards is True


class TestGetAdcpCapabilitiesImports:
    """Test that get_adcp_capabilities can be imported correctly."""

    def test_capabilities_module_imports(self):
        """Test that the capabilities module can be imported."""
        from src.core.tools import capabilities

        assert capabilities is not None

    def test_impl_function_exists(self):
        """Test that the impl function exists."""
        from src.core.tools.capabilities import _get_adcp_capabilities_impl

        assert callable(_get_adcp_capabilities_impl)

    def test_mcp_wrapper_exists(self):
        """Test that the MCP wrapper function exists."""
        from src.core.tools.capabilities import get_adcp_capabilities

        assert callable(get_adcp_capabilities)

    def test_raw_function_exists(self):
        """Test that the raw function exists."""
        from src.core.tools.capabilities import get_adcp_capabilities_raw

        assert callable(get_adcp_capabilities_raw)

    def test_raw_function_exported_from_tools(self):
        """Test that the raw function is exported from tools module."""
        from src.core.tools import get_adcp_capabilities_raw

        assert callable(get_adcp_capabilities_raw)


class TestGetAdcpCapabilitiesImpl:
    """Test the _get_adcp_capabilities_impl function."""

    def test_impl_returns_response_without_context(self):
        """Test that impl returns minimal response when no context is available."""
        from src.core.config_loader import current_tenant
        from src.core.tools.capabilities import _get_adcp_capabilities_impl

        # Reset tenant context to ensure clean state (tests may have set it)
        current_tenant.set(None)

        # Call without context - should return minimal response
        response = _get_adcp_capabilities_impl(None, None)

        assert isinstance(response, GetAdcpCapabilitiesResponse)
        assert response.adcp is not None
        assert response.adcp.major_versions[0].root == 3
        assert SupportedProtocol.media_buy in response.supported_protocols

    def test_impl_returns_valid_adcp_response(self):
        """Test that impl response can be serialized to valid JSON."""
        from src.core.config_loader import current_tenant
        from src.core.tools.capabilities import _get_adcp_capabilities_impl

        # Reset tenant context to ensure clean state
        current_tenant.set(None)

        response = _get_adcp_capabilities_impl(None, None)

        # Should be able to serialize - use mode="json" for JSON-compatible output
        data = response.model_dump(mode="json")

        assert "adcp" in data
        assert "supported_protocols" in data
        assert data["supported_protocols"] == ["media_buy"]

#!/usr/bin/env python3
"""
Test A2A get_products brand_manifest parameter extraction.

Unit tests to verify that the A2A server properly extracts brand_manifest
from skill invocation parameters.
"""

import logging
from unittest.mock import MagicMock, patch

import pytest

from src.a2a_server.adcp_a2a_server import AdCPRequestHandler

logger = logging.getLogger(__name__)


@pytest.mark.asyncio
async def test_handle_get_products_skill_extracts_brand_manifest():
    """Test that _handle_get_products_skill extracts brand_manifest parameter."""
    handler = AdCPRequestHandler()

    # Mock dependencies
    with (
        patch.object(handler, "_create_tool_context_from_a2a") as mock_create_context,
        patch("src.a2a_server.adcp_a2a_server.core_get_products_tool") as mock_core_tool,
        patch.object(handler, "_tool_context_to_mcp_context") as mock_to_mcp,
    ):
        # Setup mocks
        mock_create_context.return_value = MagicMock(tenant_id="test_tenant", principal_id="test_principal")
        mock_to_mcp.return_value = MagicMock()

        # Mock successful response
        mock_response = MagicMock()
        mock_response.model_dump.return_value = {"products": [], "message": "Test products"}
        mock_core_tool.return_value = mock_response

        # Test parameters with brand_manifest
        parameters = {
            "brand_manifest": {"name": "Nike", "url": "https://nike.com"},
            "brief": "Athletic footwear",
        }

        # Call handler
        result = await handler._handle_get_products_skill(parameters, "test_token")

        # Verify core tool was called with brand_manifest
        mock_core_tool.assert_called_once()
        call_kwargs = mock_core_tool.call_args.kwargs

        assert "brand_manifest" in call_kwargs, "brand_manifest should be passed to core tool"
        assert call_kwargs["brand_manifest"] == {
            "name": "Nike",
            "url": "https://nike.com",
        }, "brand_manifest value should match input"
        assert call_kwargs["brief"] == "Athletic footwear", "brief should be passed"


@pytest.mark.asyncio
async def test_handle_get_products_skill_extracts_all_parameters():
    """Test that _handle_get_products_skill extracts all optional parameters."""
    handler = AdCPRequestHandler()

    # Mock dependencies
    with (
        patch.object(handler, "_create_tool_context_from_a2a") as mock_create_context,
        patch("src.a2a_server.adcp_a2a_server.core_get_products_tool") as mock_core_tool,
        patch.object(handler, "_tool_context_to_mcp_context") as mock_to_mcp,
    ):
        # Setup mocks
        mock_create_context.return_value = MagicMock(tenant_id="test_tenant", principal_id="test_principal")
        mock_to_mcp.return_value = MagicMock()

        # Mock successful response
        mock_response = MagicMock()
        mock_response.model_dump.return_value = {"products": [], "message": "Test products"}
        mock_core_tool.return_value = mock_response

        # Test parameters with all optional fields
        parameters = {
            "brand_manifest": {"name": "Nike"},
            "brief": "Athletic footwear",
            "filters": {"delivery_type": "guaranteed"},
            "min_exposures": 10000,
            "adcp_version": "2.2.0",
            "strategy_id": "test_strategy_123",
        }

        # Call handler
        result = await handler._handle_get_products_skill(parameters, "test_token")

        # Verify core tool was called with all parameters
        mock_core_tool.assert_called_once()
        call_kwargs = mock_core_tool.call_args.kwargs

        assert call_kwargs["brand_manifest"] == {"name": "Nike"}
        assert call_kwargs["brief"] == "Athletic footwear"
        assert call_kwargs["filters"] == {"delivery_type": "guaranteed"}
        assert call_kwargs["min_exposures"] == 10000
        assert call_kwargs["adcp_version"] == "2.2.0"
        assert call_kwargs["strategy_id"] == "test_strategy_123"


@pytest.mark.asyncio
async def test_handle_get_products_skill_backward_compat_promoted_offering():
    """Test backward compatibility with promoted_offering parameter."""
    handler = AdCPRequestHandler()

    # Mock dependencies
    with (
        patch.object(handler, "_create_tool_context_from_a2a") as mock_create_context,
        patch("src.a2a_server.adcp_a2a_server.core_get_products_tool") as mock_core_tool,
        patch.object(handler, "_tool_context_to_mcp_context") as mock_to_mcp,
    ):
        # Setup mocks
        mock_create_context.return_value = MagicMock(tenant_id="test_tenant", principal_id="test_principal")
        mock_to_mcp.return_value = MagicMock()

        # Mock successful response
        mock_response = MagicMock()
        mock_response.model_dump.return_value = {"products": [], "message": "Test products"}
        mock_core_tool.return_value = mock_response

        # Test with promoted_offering (deprecated) instead of brand_manifest
        parameters = {
            "promoted_offering": "Nike Athletic Footwear",
            "brief": "Display ads",
        }

        # Call handler
        result = await handler._handle_get_products_skill(parameters, "test_token")

        # Verify promoted_offering is still passed
        mock_core_tool.assert_called_once()
        call_kwargs = mock_core_tool.call_args.kwargs

        assert call_kwargs["promoted_offering"] == "Nike Athletic Footwear"
        assert call_kwargs["brand_manifest"] is None  # Not provided


@pytest.mark.asyncio
async def test_handle_get_products_skill_brand_manifest_url_string():
    """Test brand_manifest as URL string."""
    handler = AdCPRequestHandler()

    # Mock dependencies
    with (
        patch.object(handler, "_create_tool_context_from_a2a") as mock_create_context,
        patch("src.a2a_server.adcp_a2a_server.core_get_products_tool") as mock_core_tool,
        patch.object(handler, "_tool_context_to_mcp_context") as mock_to_mcp,
    ):
        # Setup mocks
        mock_create_context.return_value = MagicMock(tenant_id="test_tenant", principal_id="test_principal")
        mock_to_mcp.return_value = MagicMock()

        # Mock successful response
        mock_response = MagicMock()
        mock_response.model_dump.return_value = {"products": [], "message": "Test products"}
        mock_core_tool.return_value = mock_response

        # Test with brand_manifest as URL string
        parameters = {
            "brand_manifest": "https://nike.com",
            "brief": "Athletic footwear",
        }

        # Call handler
        result = await handler._handle_get_products_skill(parameters, "test_token")

        # Verify brand_manifest URL is passed
        mock_core_tool.assert_called_once()
        call_kwargs = mock_core_tool.call_args.kwargs

        assert call_kwargs["brand_manifest"] == "https://nike.com"

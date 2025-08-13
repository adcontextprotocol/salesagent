#!/usr/bin/env python3
"""Integration tests for AdCP spec compliance verification."""

import pytest
import asyncio
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
@pytest.mark.requires_server
async def test_spec_compliance_tools_exposed(sample_principal):
    """Test that only AdCP-compliant tools are exposed."""
    
    # Create client with test token from fixture
    headers = {"x-adcp-auth": sample_principal["access_token"]}
    transport = StreamableHttpTransport(url="http://localhost:8080/mcp/", headers=headers)
    client = Client(transport=transport)
    
    async with client:
        # Get server capabilities (this will show available tools)
        capabilities = await client.initialize()
        
        assert capabilities is not None, "Could not get server capabilities"
        assert hasattr(capabilities, 'tools'), "Server capabilities missing tools"
        
        tool_names = [tool.name for tool in capabilities.tools]
        
        # Check for non-spec tool removal
        assert "get_principal_summary" not in tool_names, \
            "get_principal_summary still exposed (not part of AdCP spec)"
        
        # Check for correct creative tool
        assert "add_creative_assets" in tool_names, \
            "add_creative_assets not found"
        
        # Ensure old tool name is not present
        assert "submit_creatives" not in tool_names, \
            "submit_creatives found (should be add_creative_assets)"
        
        # Verify core AdCP tools are present
        expected_tools = [
            "get_products",
            "create_media_buy", 
            "get_media_buy_delivery",
            "add_creative_assets"
        ]
        
        for tool in expected_tools:
            assert tool in tool_names, f"Required AdCP tool '{tool}' not found"


@pytest.mark.asyncio
@pytest.mark.requires_server
async def test_adcp_tool_count(sample_principal):
    """Test that we have the expected number of core AdCP tools."""
    
    headers = {"x-adcp-auth": sample_principal["access_token"]}
    transport = StreamableHttpTransport(url="http://localhost:8080/mcp/", headers=headers)
    client = Client(transport=transport)
    
    async with client:
        capabilities = await client.initialize()
        tool_names = [tool.name for tool in capabilities.tools]
        
        # Should have core AdCP tools plus some utility tools
        assert len(tool_names) >= 4, f"Expected at least 4 tools, found {len(tool_names)}"
        assert len(tool_names) <= 20, f"Too many tools exposed: {len(tool_names)}"

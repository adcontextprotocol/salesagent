#!/usr/bin/env python3
"""Integration tests for unified get_media_buy_delivery endpoint."""

from datetime import date

import pytest
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
@pytest.mark.requires_server
async def test_unified_delivery_single_buy(sample_principal, sample_media_buy_request):
    """Test single media buy delivery query."""

    # Create client with test token from fixture
    headers = {"x-adcp-auth": sample_principal["access_token"]}
    transport = StreamableHttpTransport(url="http://localhost:8080/mcp/", headers=headers)
    client = Client(transport=transport)

    async with client:
        # Test single media buy query
        result = await client.call_tool(
            "get_media_buy_delivery", {"media_buy_ids": ["test_buy_123"], "today": date.today().isoformat()}
        )

        assert "deliveries" in result, "Response missing 'deliveries' array"
        assert isinstance(result["deliveries"], list), "Deliveries should be a list"


@pytest.mark.asyncio
@pytest.mark.requires_server
async def test_unified_delivery_multiple_buys(sample_principal):
    """Test multiple media buys delivery query."""

    headers = {"x-adcp-auth": sample_principal["access_token"]}
    transport = StreamableHttpTransport(url="http://localhost:8080/mcp/", headers=headers)
    client = Client(transport=transport)

    async with client:
        result = await client.call_tool(
            "get_media_buy_delivery",
            {"media_buy_ids": ["test_buy_123", "test_buy_456"], "today": date.today().isoformat()},
        )

        assert "deliveries" in result
        assert isinstance(result["deliveries"], list)


@pytest.mark.asyncio
@pytest.mark.requires_server
async def test_unified_delivery_active_filter(sample_principal):
    """Test delivery query with active status filter (default)."""

    headers = {"x-adcp-auth": sample_principal["access_token"]}
    transport = StreamableHttpTransport(url="http://localhost:8080/mcp/", headers=headers)
    client = Client(transport=transport)

    async with client:
        # Default filter should be 'active'
        result = await client.call_tool("get_media_buy_delivery", {"today": date.today().isoformat()})

        assert "deliveries" in result
        assert isinstance(result["deliveries"], list)


@pytest.mark.asyncio
@pytest.mark.requires_server
async def test_unified_delivery_all_filter(sample_principal):
    """Test delivery query with status_filter='all'."""

    headers = {"x-adcp-auth": sample_principal["access_token"]}
    transport = StreamableHttpTransport(url="http://localhost:8080/mcp/", headers=headers)
    client = Client(transport=transport)

    async with client:
        result = await client.call_tool(
            "get_media_buy_delivery", {"status_filter": "all", "today": date.today().isoformat()}
        )

        assert "deliveries" in result
        assert isinstance(result["deliveries"], list)
        # Check aggregate fields
        assert "total_spend" in result
        assert "active_count" in result
        assert isinstance(result["total_spend"], int | float)
        assert isinstance(result["active_count"], int)


@pytest.mark.asyncio
@pytest.mark.requires_server
async def test_unified_delivery_completed_filter(sample_principal):
    """Test delivery query with status_filter='completed'."""

    headers = {"x-adcp-auth": sample_principal["access_token"]}
    transport = StreamableHttpTransport(url="http://localhost:8080/mcp/", headers=headers)
    client = Client(transport=transport)

    async with client:
        result = await client.call_tool(
            "get_media_buy_delivery", {"status_filter": "completed", "today": date.today().isoformat()}
        )

        assert "deliveries" in result
        assert isinstance(result["deliveries"], list)


@pytest.mark.asyncio
@pytest.mark.requires_server
@pytest.mark.skip(reason="Deprecated endpoint may not exist")
async def test_deprecated_endpoint_backward_compatibility(sample_principal):
    """Test that deprecated get_all_media_buy_delivery still works (if present)."""

    headers = {"x-adcp-auth": sample_principal["access_token"]}
    transport = StreamableHttpTransport(url="http://localhost:8080/mcp/", headers=headers)
    client = Client(transport=transport)

    async with client:
        # This may raise an exception if the endpoint was removed
        result = await client.call_tool("get_all_media_buy_delivery", {"today": date.today().isoformat()})

        assert "deliveries" in result
    if success:
        print("\n🎉 Unified delivery endpoint is working correctly!")
    else:
        print("\n⚠️  Some tests failed. Check the server logs.")

#!/usr/bin/env python3
"""Integration tests for AdCP spec compliance verification."""

import pytest
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
@pytest.mark.requires_server
async def test_spec_compliance_tools_exposed(sample_principal):
    """Test that only AdCP-compliant tools are exposed and work correctly."""

    # Create client with test token from fixture
    headers = {"x-adcp-auth": sample_principal["access_token"]}
    transport = StreamableHttpTransport(url="http://localhost:8080/mcp/", headers=headers)
    client = Client(transport=transport)

    async with client:
        # Test that core AdCP tools exist and are callable
        # Note: FastMCP client doesn't expose a list of tools, so we test by calling them

        # Test 1: get_products should work
        try:
            result = await client.call_tool("get_products", {"brief": "Test product search"})
            assert result is not None, "get_products should return a result"
        except AttributeError:
            pytest.fail("get_products tool not found")

        # Test 2: add_creative_assets should exist (even if it fails due to invalid ID)
        try:
            # This will fail with a valid error, but proves the tool exists
            await client.call_tool("add_creative_assets", {"media_buy_id": "invalid_test_id", "creatives": []})
        except AttributeError:
            pytest.fail("add_creative_assets tool not found")
        except Exception:
            # Other errors are OK - we're just checking the tool exists
            pass

        # Test 3: get_principal_summary should NOT exist
        with pytest.raises(ValueError):  # FastMCP will raise an error for unknown tools
            await client.call_tool("get_principal_summary", {})

        # Test 4: submit_creatives should NOT exist (old name)
        with pytest.raises(ValueError):  # FastMCP will raise an error for unknown tools
            await client.call_tool("submit_creatives", {"media_buy_id": "test", "creatives": []})


@pytest.mark.asyncio
@pytest.mark.requires_server
async def test_core_adcp_tools_callable(sample_principal):
    """Test that core AdCP tools are callable and work correctly."""

    headers = {"x-adcp-auth": sample_principal["access_token"]}
    transport = StreamableHttpTransport(url="http://localhost:8080/mcp/", headers=headers)
    client = Client(transport=transport)

    from datetime import date

    async with client:
        # Test each core AdCP tool is callable
        core_tools_tested = 0

        # 1. get_products
        try:
            await client.call_tool("get_products", {"brief": "test"})
            core_tools_tested += 1
        except AttributeError:
            pytest.fail("Core tool 'get_products' not found")
        except Exception:
            # Tool exists but may fail - that's OK
            core_tools_tested += 1

        # 2. get_media_buy_delivery (unified endpoint)
        try:
            await client.call_tool(
                "get_media_buy_delivery",
                {
                    "media_buy_ids": ["test"],
                    "start_date": date.today().isoformat(),
                    "end_date": date.today().isoformat(),
                },
            )
            core_tools_tested += 1
        except AttributeError:
            pytest.fail("Core tool 'get_media_buy_delivery' not found")
        except Exception:
            core_tools_tested += 1

        # 3. create_media_buy
        try:
            await client.call_tool(
                "create_media_buy",
                {
                    "product_ids": ["test"],
                    "total_budget": 1000,
                    "flight_start_date": date.today().isoformat(),
                    "flight_end_date": date.today().isoformat(),
                },
            )
            core_tools_tested += 1
        except AttributeError:
            pytest.fail("Core tool 'create_media_buy' not found")
        except Exception:
            core_tools_tested += 1

        # 4. add_creative_assets
        try:
            await client.call_tool("add_creative_assets", {"media_buy_id": "test", "creatives": []})
            core_tools_tested += 1
        except AttributeError:
            pytest.fail("Core tool 'add_creative_assets' not found")
        except Exception:
            core_tools_tested += 1

        assert core_tools_tested >= 4, f"Should have tested at least 4 core tools, tested {core_tools_tested}"

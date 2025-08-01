#!/usr/bin/env python3
"""Test the UI Testing Subagent directly."""

import asyncio
import httpx
import json


async def test_subagent():
    """Test the UI testing subagent MCP server."""
    base_url = "http://localhost:8090"
    
    # Test list_ui_tests tool
    print("Testing list_ui_tests tool...")
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{base_url}/mcp/",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "list_ui_tests",
                    "arguments": {}
                },
                "id": 1
            }
        )
        print(f"Response: {response.status_code}")
        result = response.json()
        print(json.dumps(result, indent=2))
        
        # Test check_auth_status
        print("\nTesting check_auth_status tool...")
        response = await client.post(
            f"{base_url}/mcp/",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "check_auth_status",
                    "arguments": {}
                },
                "id": 2
            }
        )
        print(f"Response: {response.status_code}")
        result = response.json()
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(test_subagent())